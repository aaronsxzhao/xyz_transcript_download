"""Video note generation endpoints with background processing."""
import asyncio
import json
import os
import shutil
import threading
import time
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Optional, Set

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, UploadFile, File, Form, Query, Request

from api.media import sign_media_urls
from api.auth import get_current_user, User
from api.local_media import LOCAL_VIDEO_CHANNEL, LOCAL_VIDEO_EXTENSIONS
from api.upload_chunks import save_upload_chunk, validated_upload_parts
from api.routers.processing import (
    manager, get_main_loop, ConnectionManager,
)
from config import (
    DATA_DIR,
    USE_SUPABASE,
    VIDEO_UPLOAD_ASSEMBLY_COPY_BYTES,
    VIDEO_UPLOAD_CHUNK_SIZE,
    VIDEO_UPLOAD_CLIENT_CONCURRENCY,
)
from logger import get_logger
from summary_errors import ProcessingCancelledError

logger = get_logger("video_notes")

router = APIRouter()

from resource_scheduler import TASK_EXECUTOR, start_task, task_started_at
VIDEO_EXECUTOR = TASK_EXECUTOR

_list_cache: dict = {}
_LIST_TTL = 5.0
_channel_checks: set[str] = set()


def _invalidate_list_cache(user_id: str = None):
    prefix = user_id or "__local__"
    # Remove all cache entries for this user (tasks, channels, by-channel)
    to_delete = [k for k in _list_cache if k == prefix or k.startswith(f"{prefix}:")]
    for k in to_delete:
        _list_cache.pop(k, None)

_cancel_lock = threading.Lock()
_cancelled_tasks: Set[str] = set()
_video_attempts: dict[str, int] = {}
_video_worker = threading.local()
_video_locks: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
_video_workers: set[asyncio.Task] = set()
_upload_meta_lock = threading.Lock()
_last_upload_cleanup = 0.0


class VideoCancelledException(ProcessingCancelledError):
    pass


def _local_video_title(path_value: str) -> str:
    """Best-effort title for uploaded local files before metadata is fetched."""
    if not path_value:
        return ""
    name = os.path.basename(path_value)
    stem, _ = os.path.splitext(name)
    return stem or name


def _upload_session_dir(upload_id: str) -> Path:
    import re
    if not re.fullmatch(r"[a-f0-9-]{12,36}", upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload session")
    return CHUNK_UPLOAD_DIR / upload_id


def _session_meta_path(upload_id: str) -> Path:
    return _upload_session_dir(upload_id) / "meta.json"


def _session_chunk_path(upload_id: str, index: int) -> Path:
    return _upload_session_dir(upload_id) / f"{index:06d}.part"


def _cleanup_upload_session(upload_id: str):
    try:
        shutil.rmtree(_upload_session_dir(upload_id), ignore_errors=True)
    except Exception:
        pass


def _cleanup_upload_parts(upload_id: str):
    session_dir = _upload_session_dir(upload_id)
    if not session_dir.exists():
        return
    for part_path in session_dir.glob("*.part"):
        part_path.unlink(missing_ok=True)


def _read_upload_meta_unlocked(upload_id: str) -> dict:
    meta_path = _session_meta_path(upload_id)
    if not meta_path.exists():
        raise FileNotFoundError(upload_id)
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _write_upload_meta_unlocked(upload_id: str, meta: dict) -> dict:
    meta["last_updated"] = time.time()
    _session_meta_path(upload_id).write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _get_upload_meta(upload_id: str) -> dict:
    with _upload_meta_lock:
        return _read_upload_meta_unlocked(upload_id)


def _update_upload_meta(upload_id: str, updater) -> dict:
    with _upload_meta_lock:
        meta = _read_upload_meta_unlocked(upload_id)
        meta = updater(meta) or meta
        return _write_upload_meta_unlocked(upload_id, meta)


def _mark_upload_failed(upload_id: str, error: str):
    try:
        _update_upload_meta(upload_id, lambda meta: {
            **meta,
            "phase": "failed",
            "error": error,
        })
    except Exception:
        pass


def _maybe_cleanup_stale_uploads(force: bool = False):
    global _last_upload_cleanup
    now = time.time()
    if not force and now - _last_upload_cleanup < 1800:
        return

    stale_before = now - (24 * 3600)
    cleaned = 0
    for session_dir in CHUNK_UPLOAD_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "meta.json"
        try:
            last_updated = meta_path.stat().st_mtime if meta_path.exists() else session_dir.stat().st_mtime
        except Exception:
            continue
        if last_updated < stale_before:
            shutil.rmtree(session_dir, ignore_errors=True)
            cleaned += 1
    _last_upload_cleanup = now
    if cleaned:
        logger.info(f"Cleaned up {cleaned} stale upload session(s)")


def _upload_status_payload(upload_id: str, meta: dict) -> dict:
    size = int(meta.get("size") or 0)
    received_bytes = int(meta.get("received_bytes") or 0)
    assembled_bytes = int(meta.get("assembled_bytes") or 0)
    total_chunks = int(meta.get("total_chunks") or 0)
    received_chunks = sorted(int(i) for i in meta.get("received_chunks", []))
    phase = meta.get("phase") or "initializing"

    upload_percent = 100.0 if size <= 0 else min(100.0, (received_bytes / size) * 100)
    assemble_percent = 0.0 if size <= 0 else min(100.0, (assembled_bytes / size) * 100)

    if phase == "assembling":
        display_percent = max(upload_percent, assemble_percent)
        status_text = "Upload complete. Finalizing file on server..."
    elif phase == "complete":
        display_percent = 100.0
        status_text = "Upload complete. File is saved on the server."
    elif phase == "failed":
        display_percent = upload_percent
        status_text = meta.get("error") or "Upload failed"
    elif received_bytes > 0:
        display_percent = upload_percent
        status_text = f"Uploading to server... {len(received_chunks)}/{max(total_chunks, 1)} chunks received"
    else:
        display_percent = 0.0
        status_text = "Waiting for upload to start..."

    return {
        "upload_id": upload_id,
        "filename": meta.get("filename", ""),
        "size": size,
        "received_bytes": received_bytes,
        "assembled_bytes": assembled_bytes,
        "received_chunks": received_chunks,
        "received_chunks_count": len(received_chunks),
        "total_chunks": total_chunks,
        "phase": phase,
        "error": meta.get("error", ""),
        "path": meta.get("path", ""),
        "file_id": meta.get("file_id", ""),
        "last_updated": meta.get("last_updated", meta.get("created_at")),
        "upload_percent": upload_percent,
        "assemble_percent": assemble_percent,
        "percent": display_percent,
        "status_text": status_text,
        "location_label": "Server upload storage" if phase == "complete" else "Temporary server upload area",
    }


def _has_active_video_tasks(tasks: list[dict]) -> bool:
    for task in tasks:
        if task.get("status") not in ("success", "failed", "cancelled", "discovered"):
            return True
    return False


def is_video_task_cancelled(task_id: str) -> bool:
    from processing_execution import CURRENT
    execution = CURRENT.get()
    if execution and execution.cancelled: return True
    with _cancel_lock:
        return task_id in _cancelled_tasks or _attempt_superseded(task_id)


def _attempt_superseded(task_id: str) -> bool:
    attempt = getattr(_video_worker, "attempt_id", None)
    return (getattr(_video_worker, "task_id", None) == task_id and attempt is not None
            and attempt != _video_attempts.get(task_id))


def _new_video_attempt(task_id: str) -> int:
    with _cancel_lock:
        attempt = _video_attempts.get(task_id, 0) + 1
        _video_attempts[task_id] = attempt
        _cancelled_tasks.discard(task_id)
        return attempt


def _clear_cancelled(task_id: str):
    with _cancel_lock:
        if not _attempt_superseded(task_id):
            _cancelled_tasks.discard(task_id)

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHUNK_UPLOAD_DIR = UPLOAD_DIR / "_chunks"
CHUNK_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def broadcast_video_job(task_id: str, task_data: dict, user_id: Optional[str] = None):
    """Broadcast video task update to WebSocket clients."""
    from api.media import sign_media_urls
    from api.progress_payload import video_progress_payload
    await manager.broadcast_to_user({
        "type": "video_job_update",
        "task": sign_media_urls({**video_progress_payload(task_data),"started_at":task_started_at("video",task_id)}, task_id),
    }, user_id)


def _broadcast_from_thread(task_id: str, task_data: dict, user_id: Optional[str] = None):
    """Thread-safe broadcast wrapper."""
    try:
        loop = get_main_loop()
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast_video_job(task_id, task_data, user_id), loop
            )
    except Exception as e:
        logger.debug(f"Broadcast error: {e}")


def _update_task_status(db, task_id: str, status: str, progress: float = 0,
                        message: str = "", user_id: Optional[str] = None, **kwargs):
    """Update task in DB and broadcast.

    Uses the in-memory cache (get_task reads from cache first in Supabase
    mode) so the WebSocket broadcast never blocks on an extra HTTP call.
    """
    if _attempt_superseded(task_id) or (status not in ("cancelled", "failed") and is_video_task_cancelled(task_id)):
        return
    current_task = db.get_task(task_id, user_id)
    current_progress = 0.0
    if current_task:
        try:
            current_progress = float(current_task.get("progress") or 0)
        except Exception:
            current_progress = 0.0

    # Keep in-flight progress monotonic so optional branches (screenshots,
    # saved transcripts, video understanding) never make the bar jump backward.
    if status not in ("pending", "failed", "cancelled", "success"):
        progress = max(progress, current_progress)
    updates = {"status": status, "progress": progress, "message": message}
    updates.update(kwargs)
    db.update_task(task_id, updates)
    if status in ("success", "failed", "cancelled"):
        _invalidate_list_cache(user_id)
    # get_task now returns from in-memory cache on Supabase backend,
    # so this is essentially free (no extra HTTP round-trip).
    task = db.get_task(task_id, user_id)
    if task:
        _broadcast_from_thread(task_id, task, user_id)


CHANNEL_FETCH_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="channel_fetch")


def _discover_channel_videos(
    channel_url: str,
    channel: str,
    channel_avatar: str,
    platform: str,
    user_id: Optional[str],
    current_url: str,
):
    """Fetch latest videos from a new channel and create 'discovered' tasks."""
    try:
        from video_downloader import list_channel_videos, normalize_video_url
        from video_task_db import get_video_task_db

        db = get_video_task_db()

        if platform not in ("youtube", "bilibili"):
            logger.info(
                f"Skipping automatic channel discovery for platform '{platform}' "
                f"({channel_url}) - not supported yet"
            )
            return

        existing_count = db.count_channel_tasks(channel, user_id)
        if existing_count > 1:
            logger.info(f"Channel '{channel}' already has {existing_count} tasks, skipping discovery")
            return

        logger.info(f"New channel detected: '{channel}' — fetching latest videos from {channel_url}")
        from cookie_manager import get_cookie_manager
        videos = list_channel_videos(channel_url, platform, cookies=get_cookie_manager(user_id).get_cookie(platform), limit=15)
        if not videos:
            logger.info(f"No videos found for channel '{channel}'")
            return

        current_url = normalize_video_url(current_url, platform)
        for v in videos:
            v["url"] = normalize_video_url(v["url"], platform)

        urls = [v["url"] for v in videos]
        existing_urls = db.get_existing_urls(urls, user_id)
        existing_urls.add(current_url)

        created = 0
        for v in videos:
            if v["url"] in existing_urls:
                continue
            try:
                db.create_task({
                    "url": v["url"],
                    "platform": platform,
                    "title": v.get("title", ""),
                    "thumbnail": v.get("thumbnail", ""),
                    "duration": v.get("duration", 0),
                    "published_at": v.get("published_at", ""),
                    "channel": channel,
                    "channel_url": channel_url,
                    "channel_avatar": channel_avatar,
                    "status": "discovered",
                    "user_id": user_id,
                })
                created += 1
            except Exception as e:
                logger.warning(f"Failed to create discovered task for {v['url']}: {e}")

        if created:
            _invalidate_list_cache(user_id)
            logger.info(f"Created {created} discovered tasks from channel '{channel}'")
    except Exception as e:
        logger.error(f"Channel discovery failed for '{channel}': {e}")


def process_video_note_sync(
    task_id: str,
    url: str,
    platform: str,
    style: str,
    formats: list,
    quality: str,
    llm_model: str,
    extras: str,
    video_understanding: bool,
    video_interval: int,
    grid_cols: int,
    grid_rows: int,
    user_id: Optional[str],
    video_quality: str = "720",
    attempt_id: Optional[int] = None,
):
    """Synchronous video note processing pipeline."""
    start_task("video", task_id)
    _video_worker.task_id = task_id
    _video_worker.attempt_id = attempt_id
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    downloader = None
    video_download_future = None
    download_stop = threading.Event()
    try:
        from social_content import social_platform, resolve_social_content, SocialSourceError
        from content_sources import resolve_content, saved_web_media
        social_source = None
        if not platform and url.startswith(('http://','https://')):
            from video_downloader import detect_platform
            platform = detect_platform(url)
        if platform == 'web' or social_platform(url):
            if is_video_task_cancelled(task_id):
                raise VideoCancelledException('Cancelled')
            saved_task = db.get_task(task_id, user_id)
            if not saved_task:
                return
            _update_task_status(db, task_id, 'parsing', 5, 'Reading original article or media…', user_id)
            from urllib.parse import urlsplit
            host = urlsplit(url).hostname or ''
            generic = platform == 'web' or (platform == 'substack' and host != 'substack.com' and not host.endswith('.substack.com'))
            social_source = saved_web_media(saved_task)
            if social_source is None:
                social_source = resolve_content(url) if generic else resolve_social_content(url)
            platform = social_source.platform
            db.update_task(task_id, {'platform':platform,'title':social_source.title,'thumbnail':social_source.thumbnail,
                'channel':social_source.author or platform,'channel_url':social_source.author_url or social_source.url,'published_at':social_source.published})
            if platform == 'web':
                db.update_task(task_id, {'source_metadata':social_source.metadata()})
            if not social_source.media:
                if is_video_task_cancelled(task_id):
                    raise VideoCancelledException('Cancelled')
                db.update_task(task_id, {'style':'original','formats':['original'],'model':'','duration':0,'transcript_json':''})
                _update_task_status(db,task_id,'saving',95,'Saving original text — no AI summarization…',user_id)
                db.complete_task(task_id,social_source.markdown(),'original','',user_id)
                _invalidate_list_cache(user_id)
                _broadcast_from_thread(task_id,db.get_task(task_id,user_id),user_id)
                return
            if all(item['kind']=='audio' for item in social_source.media):
                formats=[value for value in formats if value!='screenshot']
                video_understanding=False
            # Timestamps refer to the combined attachments; generic source links
            # must not pretend that every service supports timestamp deep links.
            formats=[value for value in formats if value!='link']
            if style=='original': style='detailed'
            db.update_task(task_id, {'formats':formats,'video_understanding':video_understanding,'style':style})
        from api.user_settings import get_user_settings
        preferences = get_user_settings(user_id)
        llm_model = llm_model or preferences.get("llm_model", "")
        from api.llm_settings import resolve_llm_settings
        llm_settings = resolve_llm_settings(preferences, llm_model)
        llm_model = llm_settings["model"]
        if video_understanding and llm_settings["base_url"].rstrip('/') == "https://api.groq.com/openai/v1":
            raise ValueError("Groq summaries use the transcript. Turn off Video Understanding, or choose a vision-capable provider in Settings.")
        from video_downloader import get_downloader, detect_platform, normalize_video_url, VideoDownloadError
        from cookie_manager import get_cookie_manager
        from note_summarizer import get_note_summarizer, NOTE_CHUNK_CHARS
        from screenshot_extractor import (
            extract_timestamps_from_markdown,
            extract_screenshots_batch,
            replace_screenshot_markers,
            replace_content_markers,
            extract_first_frame_thumbnail,
        )

        cookie_mgr = get_cookie_manager(user_id)
        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # Check if we already have a transcript from a previous run (for retry)
        existing_task = db.get_task(task_id, user_id)
        if not existing_task:
            return
        # Keep a readable previous result stable until complete_task atomically
        # saves its replacement. First attempts may still expose partial output.
        preserve_existing_note = bool((existing_task.get("markdown") or "").strip())
        existing_transcript = existing_task.get("transcript") if existing_task else None
        has_saved_transcript = (
            existing_transcript
            and existing_transcript.get("text")
            and len(existing_transcript["text"]) > 50
        )

        if social_source:
            from social_downloader import SocialDownloader
            downloader = SocialDownloader(social_source)
        else:
            downloader = None
        title = (existing_task or {}).get("title", "")
        thumbnail = (existing_task or {}).get("thumbnail", "")
        duration = (existing_task or {}).get("duration", 0)
        channel = (existing_task or {}).get("channel", "")
        channel_url = (existing_task or {}).get("channel_url", "")
        channel_avatar = (existing_task or {}).get("channel_avatar", "")
        tags = []
        transcript_text = ""
        transcript_segments = []
        audio_path = None
        video_path = None
        media_warning = ''

        if has_saved_transcript:
            logger.info(f"Reusing saved transcript for {task_id} ({len(existing_transcript['text'])} chars), skipping download+transcribe")
            _update_task_status(db, task_id, "transcribing", 60, "Reusing saved transcript — skipping download and transcription", user_id)
            transcript_text = existing_transcript["text"]
            transcript_segments = existing_transcript.get("segments", [])
        else:
            # Full pipeline: metadata → download → transcribe

            # Phase 1: Parse / metadata (0-10%)
            _update_task_status(db, task_id, "parsing", 5, "Fetching video info...", user_id)

            if not platform:
                platform = detect_platform(url)
            if not platform:
                _update_task_status(db, task_id, "failed", 0, "Could not detect platform", user_id,
                                    error="Unsupported URL")
                return
            url = normalize_video_url(url, platform)
            is_local = platform == "local"

            cookies = cookie_mgr.get_cookie(platform)
            logger.info(f"[{task_id}] Platform={platform}, has_cookies={bool(cookies)}, cookie_len={len(cookies) if cookies else 0}")

            if platform == "bilibili" and not cookies:
                _update_task_status(
                    db, task_id, "failed", 0,
                    "BiliBili requires login. Go to Settings → Platform Accounts → BiliBili to scan QR code.",
                    user_id,
                    error="BILIBILI_LOGIN_REQUIRED",
                )
                return

            if platform == "youtube" and not cookies and USE_SUPABASE:
                logger.warning(
                    f"[{task_id}] YouTube without cookies on cloud server — "
                    "may fail due to bot detection. Recommend uploading cookies."
                )

            downloader = downloader or get_downloader(platform, cookies)

            metadata = None
            try:
                from resource_scheduler import NETWORK_EXECUTOR
                metadata_future = NETWORK_EXECUTOR.submit(downloader.get_metadata, url)
                metadata = metadata_future.result(timeout=45)
            except FutureTimeout:
                metadata_future.cancel()
                logger.warning(f"[{task_id}] Metadata fetch timed out for {url}; continuing without metadata")
            published_at = ""
            if metadata:
                if is_local:
                    title = title or metadata.title
                else:
                    title = metadata.title or title
                thumbnail = metadata.thumbnail or thumbnail
                duration = metadata.duration or duration
                tags = metadata.tags or []
                channel = metadata.channel or channel
                channel_url = metadata.channel_url or channel_url
                channel_avatar = metadata.channel_avatar or channel_avatar
                published_at = metadata.published_at or ""

            task_updates: dict = {
                "url": url,
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
                "channel": channel,
                "channel_url": channel_url,
                "channel_avatar": channel_avatar,
            }
            if published_at:
                task_updates["published_at"] = published_at
            db.update_task(task_id, task_updates)
            _update_task_status(db, task_id, "parsing", 10, f"Found: {title}", user_id)

            if channel and channel_url:
                CHANNEL_FETCH_EXECUTOR.submit(
                    _discover_channel_videos,
                    channel_url, channel, channel_avatar,
                    platform, user_id, url,
                )

            if is_video_task_cancelled(task_id):
                _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
                _clear_cancelled(task_id)
                return

            # Phase 2: Check for subtitles first (avoids downloading audio entirely)
            _update_task_status(db, task_id, "downloading", 12, "Checking for existing subtitles on platform...", user_id)
            subtitles = downloader.get_subtitles(url, task_id)

            if subtitles:
                _update_task_status(db, task_id, "transcribing", 24, "Found platform subtitles — skipping audio download", user_id)
                transcript_segments = subtitles
                transcript_text = " ".join(s["text"] for s in subtitles)
                logger.info(f"Using platform subtitles for {task_id}, skipping audio download")
            else:
                _update_task_status(db, task_id, "downloading", 14, "No subtitles found — downloading audio for transcription...", user_id)

                last_audio_update = [0.0]
                def audio_progress(pct: float, msg: str):
                    if is_video_task_cancelled(task_id):
                        raise VideoCancelledException("Cancelled during download")
                    now = time.monotonic()
                    if pct < 1 and now - last_audio_update[0] < 1:
                        return
                    last_audio_update[0] = now
                    job_pct = 14 + pct * 10
                    _update_task_status(db, task_id, "downloading", job_pct, msg, user_id)

                try:
                    audio_path = downloader.download_audio(url, task_id, quality, progress_callback=audio_progress)
                except VideoDownloadError as e:
                    _update_task_status(db, task_id, "failed", 0, str(e), user_id,
                                        error=e.error_code)
                    return
                if not audio_path:
                    _update_task_status(db, task_id, "failed", 0, "Audio download failed", user_id,
                                        error="Download failed")
                    return

                dl_info = getattr(downloader, 'get_last_download_info', lambda: None)()
                if dl_info:
                    if not title or title == "Untitled":
                        title = dl_info.title or title
                    if not thumbnail:
                        thumbnail = dl_info.thumbnail
                    if not duration and dl_info.duration:
                        duration = dl_info.duration
                    if not tags and dl_info.tags:
                        tags = dl_info.tags
                    if not channel and dl_info.channel:
                        channel = dl_info.channel
                    if not channel_url and dl_info.channel_url:
                        channel_url = dl_info.channel_url
                    if not channel_avatar and dl_info.channel_avatar:
                        channel_avatar = dl_info.channel_avatar
                    downloaded_updates = {
                        "title": title,
                        "thumbnail": thumbnail,
                        "duration": duration,
                        "channel": channel,
                        "channel_url": channel_url,
                        "channel_avatar": channel_avatar,
                    }
                    if dl_info.published_at and not published_at:
                        published_at = dl_info.published_at
                        downloaded_updates["published_at"] = published_at
                    db.update_task(task_id, downloaded_updates)

            if not subtitles:
                _update_task_status(db, task_id, "downloading", 24, "Audio download complete", user_id)

            if is_video_task_cancelled(task_id):
                _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
                _clear_cancelled(task_id)
                return

            # Phase 3: Transcribe (42-60%) — only if subtitles weren't found
            if not transcript_text:
                _update_task_status(db, task_id, "transcribing", 42, "Transcribing audio with Whisper...", user_id)

                from transcriber import get_transcriber
                transcriber = get_transcriber(model=preferences.get("whisper_model") or None, **({"preferences": preferences} if preferences.get("transcription_provider") == "custom" else {}))

                last_progress = [42]

                def transcribe_progress(progress: float):
                    if is_video_task_cancelled(task_id):
                        raise VideoCancelledException("Cancelled during transcription")
                    job_progress = 42 + (progress * 18)
                    if job_progress - last_progress[0] >= 1:
                        last_progress[0] = job_progress
                        pct = int(progress * 100)
                        _update_task_status(
                            db, task_id, "transcribing", job_progress,
                            f"Transcribing... {pct}%", user_id,
                        )

                transcript = transcriber.transcribe(
                    audio_path, task_id,
                    progress_callback=transcribe_progress,
                )
                if not transcript:
                    if is_video_task_cancelled(task_id):
                        _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
                        _clear_cancelled(task_id)
                        return
                    transcribe_error = getattr(transcriber, "last_error", "") or "Transcription failed"
                    _update_task_status(db, task_id, "failed", 0, transcribe_error, user_id,
                                        error=transcribe_error)
                    return
                transcript_text = transcript.text
                transcript_segments = [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in transcript.segments
                ]

            # Save transcript
            if social_source and not duration:
                duration=max((float(segment.get('end') or 0) for segment in transcript_segments),default=0)
                db.update_task(task_id,{'duration':duration})
            db.update_task(task_id, {
                "transcript_json": json.dumps({
                    "text": transcript_text,
                    "segments": transcript_segments,
                    "duration": duration,
                }, ensure_ascii=False),
            })
            _update_task_status(db, task_id, "transcribing", 60, "Transcription complete — preparing to generate notes...", user_id)

        # Download video whenever screenshots or video understanding are requested.
        # This must also run for retry/re-process paths that reuse an existing transcript.
        needs_video = "screenshot" in formats or video_understanding
        if needs_video and not video_path:
            _update_task_status(db, task_id, "downloading", 26, "Downloading video for screenshots...", user_id)

            last_video_update = [0.0]
            def video_progress(pct: float, msg: str):
                if download_stop.is_set() or is_video_task_cancelled(task_id):
                    raise VideoCancelledException("Cancelled during video download")
                if video_download_future is not None:
                    return
                # Accept either normalized 0..1 progress or legacy 0..100 values.
                pct = pct / 100.0 if pct > 1 else pct
                pct = max(0.0, min(pct, 1.0))
                now = time.monotonic()
                if pct < 1 and now - last_video_update[0] < 1:
                    return
                last_video_update[0] = now
                job_pct = 26 + pct * 14
                _update_task_status(db, task_id, "downloading", job_pct, msg, user_id)

            try:
                if not platform:
                    platform = detect_platform(url)
                if platform and downloader is None:
                    cookies = cookie_mgr.get_cookie(platform)
                    downloader = get_downloader(platform, cookies)
                if downloader:
                    from processing_execution import CURRENT
                    if CURRENT.get() is not None and not video_understanding:
                        import contextvars
                        from resource_scheduler import NETWORK_EXECUTOR
                        context = contextvars.copy_context()
                        video_download_future = NETWORK_EXECUTOR.submit(context.run,downloader.download_video,
                            url,task_id,video_quality=video_quality,progress_callback=video_progress)
                    else:
                        video_path = downloader.download_video(url,task_id,video_quality=video_quality,progress_callback=video_progress)
            except (VideoDownloadError, SocialSourceError) as e:
                logger.warning(f"Optional video download failed, continuing with transcript: {e}")
                media_warning = 'Screenshots could not be downloaded. Check the original media link or platform connection and retry screenshots.'
                video_path = None

        # Thumbnail fallback: extract first frame if no thumbnail was fetched
        if not thumbnail:
            source = video_path or audio_path
            if source:
                thumb_url = extract_first_frame_thumbnail(str(source), task_id)
                if thumb_url:
                    thumbnail = thumb_url
                    db.update_task(task_id, {"thumbnail": thumbnail})
                    logger.info(f"[{task_id}] Thumbnail fallback from local file succeeded")
        # Phase 3b: Video understanding (60-70%)
        visual_context = ""
        if video_understanding and video_path:
            _update_task_status(db, task_id, "transcribing", 62, "Analyzing video frames...", user_id)
            try:
                from video_understanding import extract_frame_grids, analyze_grids
                grids = extract_frame_grids(
                    str(video_path), task_id,
                    interval=video_interval,
                    grid_cols=grid_cols,
                    grid_rows=grid_rows,
                )
                if grids:
                    _update_task_status(db, task_id, "transcribing", 68, "Running vision analysis...", user_id)
                    visual_context = analyze_grids(
                        grids, title=title, **llm_settings,
                    )
            except Exception as e:
                logger.warning(f"Video understanding failed: {e}")

        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # Incomplete segment metadata must not replace a complete raw source.
        if ("screenshot" in formats or "link" in formats) and transcript_segments:
            from source_coverage import video_source_text
            transcript_text = video_source_text(transcript_text, transcript_segments)

        transcript_chars = len(transcript_text)
        num_expected_chunks = max(1, transcript_chars // NOTE_CHUNK_CHARS + (1 if transcript_chars % NOTE_CHUNK_CHARS else 0))
        if num_expected_chunks > 1:
            _update_task_status(db, task_id, "summarizing", 72,
                                f"Starting AI note generation — splitting into ~{num_expected_chunks} sections...", user_id)
        else:
            _update_task_status(db, task_id, "summarizing", 72, "Starting AI note generation...", user_id)

        # Phase 4: Generate notes (72-92%)
        note_summarizer = get_note_summarizer(
            **llm_settings,
        )

        last_summarize_progress = [72]
        import time as _time
        _last_stream_broadcast = [0.0]
        _stream_interval = 2.0 if USE_SUPABASE else 0.6

        def summarize_progress(chars, partial_text="", chunk_num=0, total_chunks=0):
            if is_video_task_cancelled(task_id):
                raise VideoCancelledException("Cancelled during summarization")
            progress_ratio = min(chars / 8000, 1.0)
            job_progress = 72 + (progress_ratio * 20)

            if total_chunks > 1 and chunk_num > 0:
                chunk_progress_base = (chunk_num - 1) / total_chunks
                chunk_progress_current = 1 / total_chunks * min(chars / 3000, 1.0) if chars > 0 else 0
                job_progress = 72 + (chunk_progress_base + chunk_progress_current) * 20

            now = _time.monotonic()
            should_broadcast = (
                job_progress - last_summarize_progress[0] >= 1
                or (partial_text and now - _last_stream_broadcast[0] >= _stream_interval)
            )
            if should_broadcast:
                if is_video_task_cancelled(task_id):
                    raise VideoCancelledException("Cancelled during summarization")
                last_summarize_progress[0] = job_progress
                _last_stream_broadcast[0] = now
                if total_chunks > 1 and chunk_num > 0:
                    msg = f"Writing notes — section {chunk_num}/{total_chunks} ({chars:,} chars)"
                else:
                    msg = f"Writing notes ({chars:,} chars)..."
                partial_update = {"markdown": partial_text} if partial_text and not preserve_existing_note else {}
                _update_task_status(db, task_id, "summarizing", job_progress, msg, user_id,
                                    **partial_update)

        markdown = note_summarizer.generate_note(
            title=title,
            transcript_text=transcript_text,
            style=style,
            formats=formats,
            visual_context=visual_context,
            tags=tags,
            extras=extras,
            progress_callback=summarize_progress,
            duration=duration,
        )
        if is_video_task_cancelled(task_id):
            raise VideoCancelledException("Cancelled during summarization")

        if not markdown:
            _update_task_status(db, task_id, "failed", 0, "Note generation failed", user_id,
                                error="LLM failed")
            return

        if video_download_future is not None:
            _update_task_status(db, task_id, "saving", 94, "Notes generated — waiting for screenshot media...", user_id)
            try:
                video_path = video_download_future.result(timeout=300)
                if video_path and not thumbnail:
                    thumbnail = extract_first_frame_thumbnail(str(video_path),task_id)
                    if thumbnail: db.update_task(task_id,{'thumbnail':thumbnail})
            except (VideoDownloadError,SocialSourceError,FutureTimeout):
                video_path = None
                media_warning = 'Notes are ready. Screenshot media is unavailable; use Repair screenshots to retry it.'

        # Phase 5: Post-processing (94-100%)
        _update_task_status(db, task_id, "saving", 94, "Notes generated — adding links and screenshots...", user_id)

        # Replace *Content-[mm:ss] markers with clickable links to original video
        if "link" in formats:
            markdown = replace_content_markers(markdown, url, platform)

        # Extract and capture screenshots if needed
        if "screenshot" in formats:
            if video_path:
                timestamps = extract_timestamps_from_markdown(markdown)
                if timestamps:
                    _update_task_status(db, task_id, "saving", 96,
                                        f"Extracting {len(timestamps)} screenshots...", user_id)
                    captured = extract_screenshots_batch(str(video_path), timestamps, task_id)
                    if sum(bool(filename) for _, filename in captured) < len(set(timestamps)):
                        media_warning = 'Some screenshots could not be extracted or uploaded. Retry screenshots to complete this note.'
                    markdown = replace_screenshot_markers(markdown, task_id, keep_missing=True)
            else:
                media_warning = media_warning or 'Screenshots are unavailable. Check the original media link or platform connection, then use Repair screenshots.'
                # Preserve deterministic image references so a screenshot-only
                # retry can fill them later without changing the saved note.
                markdown = replace_screenshot_markers(markdown, task_id, keep_missing=True)

        if social_source:
            # Quoting keeps generated-note cleanup and marker replacement from
            # interpreting the original author's headings or media markers.
            original='\n'.join('> '+line for line in social_source.markdown().splitlines())
            markdown += '\n\n---\n\n## Original post / article\n\n' + original

        if _attempt_superseded(task_id) or is_video_task_cancelled(task_id):
            raise VideoCancelledException('Processing superseded or cancelled')
        from processing_execution import assert_lease
        assert_lease()
        try:
            db.complete_task(task_id, markdown, style, llm_model, user_id, media_warning)
        except Exception as save_error:
            raise RuntimeError('The final save could not be confirmed. A recovery copy was retained. Use Recover pending save before regenerating.') from save_error
        _invalidate_list_cache(user_id)
        _broadcast_from_thread(task_id, db.get_task(task_id, user_id), user_id)
        logger.info(f"Video note completed: {task_id} ({title})")

    except VideoCancelledException:
        _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
        _clear_cancelled(task_id)
        db.flush_task(task_id)
        logger.info(f"Video task cancelled: {task_id}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            if is_video_task_cancelled(task_id):
                _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
                _clear_cancelled(task_id)
            else:
                _update_task_status(db, task_id, "failed", 0, f"Error: {str(e)}", user_id,
                                    error=str(e))
            db.flush_task(task_id)
        except Exception:
            logger.error(f"[Video {task_id}] Failed during error handling: {e}")
    finally:
        download_stop.set()
        if video_download_future is not None and not video_download_future.done():
            video_download_future.cancel()
        if platform == 'web' and downloader is not None:
            cleanup = getattr(downloader, 'cleanup', None)
            if cleanup:
                def clean_media(_=None):
                    try: cleanup()
                    except OSError: logger.warning('Temporary public media cleanup will be retried later')
                if video_download_future is not None and not video_download_future.done():
                    video_download_future.add_done_callback(clean_media)
                else:
                    clean_media()


async def process_video_note_async(task_id: str, **kwargs):
    loop = asyncio.get_event_loop()
    lock = _video_locks.setdefault(task_id, asyncio.Lock())
    try:
        async with lock:
            attempt = kwargs.get("attempt_id")
            if attempt is not None and attempt != _video_attempts.get(task_id):
                return
            await loop.run_in_executor(
                VIDEO_EXECUTOR,
                lambda: process_video_note_sync(task_id, **kwargs),
            )
    except Exception as e:
        logger.error(f"[Video {task_id}] Unhandled error: {e}")


async def enqueue_video_note(task_id: str, **kwargs):
    """End the submission request after admission, not after media processing.

    Keep strong references until completion. The existing bounded executor,
    per-task lock and attempt checks still control actual processing.
    """
    from execution_store import enabled, get_store
    if enabled():
        store = get_store()
        owner = kwargs.get('user_id')
        previous = await asyncio.to_thread(store.latest, owner, 'video', task_id)
        source = previous['source_id'] if previous and previous['state'] != 'completed' else 'video:' + task_id + ':' + str(uuid.uuid4())
        await asyncio.to_thread(store.enqueue, owner, 'video', task_id, source, kwargs)
        return
    worker = asyncio.create_task(process_video_note_async(task_id, **kwargs))
    _video_workers.add(worker)
    worker.add_done_callback(_video_workers.discard)


@router.post("/generate")
def generate_note(
    background_tasks: BackgroundTasks,
    url: str = Form(""),
    title: str = Form(""),
    platform: str = Form(""),
    style: str = Form("detailed"),
    formats: str = Form("[]"),
    quality: str = Form("medium"),
    video_quality: str = Form("720"),
    llm_model: str = Form(""),
    extras: str = Form(""),
    video_understanding: bool = Form(False),
    video_interval: int = Form(4),
    grid_cols: int = Form(3),
    grid_rows: int = Form(3),
    user: Optional[User] = Depends(get_current_user),
):
    """Start video note generation."""
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    user_id = user.id if user else None

    if not user_id and USE_SUPABASE:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in and try again.")

    try:
        fmt_list = json.loads(formats) if isinstance(formats, str) else formats
    except (json.JSONDecodeError, TypeError):
        fmt_list = []

    from video_task_db import get_video_task_db
    from video_downloader import normalize_video_url, detect_platform
    db = get_video_task_db()
    platform = detect_platform(url) or platform
    try:
        url = normalize_video_url(url, platform)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    platform = detect_platform(url) or platform
    is_local = platform == "local"

    _invalidate_list_cache(user_id)

    existing = db.get_task_by_url(url, user_id)
    if is_local and USE_SUPABASE:
        from api.local_media import get_local_video_dir
        candidate = Path(url).resolve()
        owned_root = get_local_video_dir(user_id).resolve()
        legacy_owned = existing and candidate.is_relative_to(UPLOAD_DIR.resolve())
        if not candidate.is_file() or not (candidate.is_relative_to(owned_root) or legacy_owned):
            raise HTTPException(status_code=403, detail="Upload this video from your own account before processing it")
    if existing:
        task_id = existing["id"]
        db.update_task(task_id, {
            "title": title or (_local_video_title(url) if is_local and not existing.get("title") else existing.get("title", "")),
            "platform": platform or existing.get('platform',''),
            "style": style,
            "formats": fmt_list,
            "quality": quality,
            "video_quality": video_quality,
            "model": llm_model,
            "extras": extras,
            "status": "pending",
            "progress": 0,
            "message": "Queued for processing...",
            "error": "",
        })
    else:
        try:
            task_id = db.create_task({
                "url": url,
                "platform": platform,
                "title": title or (_local_video_title(url) if is_local else ""),
                "style": style,
                "formats": fmt_list,
                "quality": quality,
                "video_quality": video_quality,
                "model": llm_model,
                "extras": extras,
                "video_understanding": video_understanding,
                "video_interval": video_interval,
                "grid_cols": grid_cols,
                "grid_rows": grid_rows,
                "user_id": user_id,
                "channel": LOCAL_VIDEO_CHANNEL if is_local else "",
            })
            db.update_task(task_id, {
                "status": "pending",
                "progress": 0,
                "message": "Queued for processing...",
                "error": "",
            })
        except Exception as e:
            logger.error(f"[generate] create_task failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create task: {type(e).__name__}: {e}")

    background_tasks.add_task(
        enqueue_video_note,
        task_id,
        attempt_id=_new_video_attempt(task_id),
        url=url,
        platform=platform,
        style=style,
        formats=fmt_list,
        quality=quality,
        llm_model=llm_model,
        extras=extras,
        video_understanding=video_understanding,
        video_interval=video_interval,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        user_id=user_id,
        video_quality=video_quality,
    )

    return {"task_id": task_id, "message": "Processing started"}


@router.get("/submission")
def video_submission(url: str = Query(..., max_length=2048), platform: str = Query('', max_length=32),
                     user: Optional[User] = Depends(get_current_user)):
    """Reconcile a lost acknowledgement without re-submitting processing work."""
    from video_task_db import get_video_task_db
    from video_downloader import normalize_video_url, detect_platform
    if USE_SUPABASE and not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    task = get_video_task_db().get_task_by_url(normalize_video_url(url, platform), user.id if user else None)
    if not task or task.get('status') == 'discovered':
        return {"task_id": None}
    return {"task_id": task['id'], "status": task.get('status')}


@router.post("/generate-json")
def generate_note_json(
    data: dict,
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user),
):
    """Start video note generation (JSON body)."""
    url = data.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    user_id = user.id if user else None

    if not user_id and USE_SUPABASE:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in and try again."
        )

    from video_task_db import get_video_task_db
    from video_downloader import normalize_video_url, detect_platform
    db = get_video_task_db()
    platform = data.get("platform", "")
    platform = detect_platform(url) or platform
    try:
        url = normalize_video_url(url, platform)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    platform = detect_platform(url) or platform
    is_local = platform == "local"

    _invalidate_list_cache(user_id)

    existing = db.get_task_by_url(url, user_id)
    if existing and data.get("skip_existing") and existing.get("status") != "discovered":
        return {"task_id":existing["id"], "skipped":True}
    if is_local and USE_SUPABASE:
        from api.local_media import get_local_video_dir
        candidate = Path(url).resolve()
        owned_root = get_local_video_dir(user_id).resolve()
        legacy_owned = existing and candidate.is_relative_to(UPLOAD_DIR.resolve())
        if not candidate.is_file() or not (candidate.is_relative_to(owned_root) or legacy_owned):
            raise HTTPException(status_code=403, detail="Upload this video from your own account before processing it")
    if existing:
        task_id = existing["id"]
        db.update_task(task_id, {
            "title": data.get("title", "") or (_local_video_title(url) if is_local and not existing.get("title") else existing.get("title", "")),
            "platform": platform or existing.get('platform',''),
            "style": data.get("style", "detailed"),
            "formats": data.get("formats", []),
            "quality": data.get("quality", "medium"),
            "video_quality": data.get("video_quality", "720"),
            "model": data.get("llm_model", ""),
            "extras": data.get("extras", ""),
            "status": "pending",
            "progress": 0,
            "message": "Queued for processing...",
            "error": "",
        })
    else:
        task_payload = {
            "url": url,
            "platform": platform,
            "title": data.get("title", "") or (_local_video_title(url) if is_local else ""),
            "style": data.get("style", "detailed"),
            "formats": data.get("formats", []),
            "quality": data.get("quality", "medium"),
            "video_quality": data.get("video_quality", "720"),
            "model": data.get("llm_model", ""),
            "extras": data.get("extras", ""),
            "video_understanding": data.get("video_understanding", False),
            "video_interval": data.get("video_interval", 4),
            "grid_cols": data.get("grid_cols", 3),
            "grid_rows": data.get("grid_rows", 3),
            "user_id": user_id,
            "channel": LOCAL_VIDEO_CHANNEL if is_local else "",
        }
        try:
            task_id = db.create_task(task_payload)
            db.update_task(task_id, {
                "status": "pending",
                "progress": 0,
                "message": "Queued for processing...",
                "error": "",
            })
        except Exception as e:
            logger.error(f"[generate-json] create_task failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create task: {type(e).__name__}: {e}")

    background_tasks.add_task(
        enqueue_video_note,
        task_id,
        attempt_id=_new_video_attempt(task_id),
        url=url,
        platform=platform,
        style=data.get("style", "detailed"),
        formats=data.get("formats", []),
        quality=data.get("quality", "medium"),
        llm_model=data.get("llm_model", ""),
        extras=data.get("extras", ""),
        video_understanding=data.get("video_understanding", False),
        video_interval=data.get("video_interval", 4),
        grid_cols=data.get("grid_cols", 3),
        grid_rows=data.get("grid_rows", 3),
        user_id=user_id,
        video_quality=data.get("video_quality", "720"),
    )

    return {"task_id": task_id, "message": "Processing started"}


@router.get('/progress')
def video_progress(known: str = Query('', max_length=5000), user: Optional[User] = Depends(get_current_user)):
    from video_task_db import get_video_task_db
    import re
    ids = [value for value in known.split(',') if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value)][:100]
    tasks = get_video_task_db().list_progress_tasks(user.id if user else None, ids)
    return {'tasks': sign_media_urls([{**task,'started_at':task_started_at('video',task['id'])} for task in tasks])}


@router.get("/tasks")
def list_tasks(user: Optional[User] = Depends(get_current_user)):
    """List all video note tasks (cached for 5s to avoid excessive Supabase calls)."""
    from video_task_db import get_video_task_db
    user_id = user.id if user else None
    cache_key = user_id or "__local__"
    now = time.monotonic()
    entry = _list_cache.get(cache_key)
    if entry and now - entry["t"] < _LIST_TTL and not _has_active_video_tasks(entry["data"].get("tasks", [])):
        return entry["data"]
    db = get_video_task_db()
    tasks = db.list_tasks(user_id)
    result = {"tasks": sign_media_urls(tasks)}
    if not _has_active_video_tasks(tasks):
        _list_cache[cache_key] = {"t": now, "data": result}
    else:
        _list_cache.pop(cache_key, None)
    return result


@router.get("/channels")
def list_channels(user: Optional[User] = Depends(get_current_user)):
    """List all channels with aggregated stats (count, done, thumbnail). No task payload."""
    from video_task_db import get_video_task_db
    user_id = user.id if user else None
    cache_key = f"{user_id or '__local__'}:channels"
    now = time.monotonic()
    entry = _list_cache.get(cache_key)
    if entry and now - entry["t"] < _LIST_TTL:
        return entry["data"]
    db = get_video_task_db()
    try:
        channels = db.list_channels_with_stats(user_id)
    except Exception:
        logger.warning('Video channel read failed', exc_info=True)
        raise HTTPException(status_code=503, detail="Video channels are temporarily unavailable. Your saved videos are unchanged. Please retry.")
    result = {"channels": [sign_media_urls(ch, Path(ch.get("thumbnail") or "").stem.split("_")[0]) for ch in channels]}
    _list_cache[cache_key] = {"t": now, "data": result}
    return result


@router.get("/tasks/by-channel")
def list_tasks_by_channel(
    channel: str = Query(..., max_length=300), platform: str = Query(..., max_length=32),
    limit: int = Query(40, ge=1, le=60), cursor: str = Query('', max_length=512),
    q: str = Query('', max_length=200), status: str = Query('', max_length=32),
    sort: str = Query('newest', pattern='^(newest|oldest)$'),
    user: Optional[User] = Depends(get_current_user),
):
    from video_task_db import get_video_task_db
    from api.channel_paging import page
    try:
        result = page(get_video_task_db()._backend, channel, platform, user.id if user else None, limit, cursor, q, status, sort)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    result['tasks'] = sign_media_urls(result['tasks'])
    return result


@router.get("/recent")
def list_recent_tasks(
    limit: int = Query(6, ge=1, le=20),
    user: Optional[User] = Depends(get_current_user),
):
    """List recent successful video notes for the dashboard."""
    from video_task_db import get_video_task_db
    user_id = user.id if user else None
    cache_key = f"{user_id or '__local__'}:recent:{limit}"
    now = time.monotonic()
    entry = _list_cache.get(cache_key)
    if entry and now - entry["t"] < _LIST_TTL:
        return entry["data"]

    db = get_video_task_db()
    tasks = db.list_recent_success_tasks(user_id, limit)
    result = {"tasks": sign_media_urls(tasks)}
    _list_cache[cache_key] = {"t": now, "data": result}
    return result


@router.get("/tasks/{task_id}")
def get_task(task_id: str, view: str = Query("full", pattern="^(full|note)$"), user: Optional[User] = Depends(get_current_user)):
    """Get a video note task with versions."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    task = db.get_task(task_id, user_id, include_transcript=view == "full")
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["versions"] = db.get_versions(task_id, include_content=view == "full")
    if task.get('style') == 'original' and task.get('platform') in ('twitter', 'substack', 'web'):
        from article_markdown import repair_article_markdown
        task['versions'] = [{**v, 'content': repair_article_markdown(v['content'])} if v.get('content') and v.get('style') == 'original' else v for v in task['versions']]
    from api.media import sign_media_urls
    return sign_media_urls(task, task_id)


@router.get("/tasks/{task_id}/transcript")
def get_task_transcript(task_id: str, user: User = Depends(get_current_user)):
    from video_task_db import get_video_task_db
    task = get_video_task_db().get_task(task_id, user.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"transcript": task.get("transcript")}


@router.get("/tasks/{task_id}/versions/{version_id}")
def get_task_version(task_id: str, version_id: str, user: User = Depends(get_current_user)):
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    task = db.get_task(task_id, user.id, include_transcript=False)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    version = db.get_version(task_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    if task.get('platform') in ('twitter', 'substack', 'web') and version.get('style') == 'original':
        from article_markdown import repair_article_markdown
        version = {**version, 'content': repair_article_markdown(version.get('content') or '')}
        if task.get('platform') == 'web':
            from article_markdown import repair_web_attribution
            from api.article_images import sign_article_markdown
            version['content'] = sign_article_markdown(repair_web_attribution(version['content'], task.get('url') or ''))
    return sign_media_urls(version, task_id)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, user: Optional[User] = Depends(get_current_user)):
    """Delete a video note task and cancel any in-progress processing."""
    from screenshot_extractor import delete_task_assets
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    if not db.get_task(task_id, user_id):
        raise HTTPException(status_code=404, detail="Task not found")
    from execution_store import enabled, get_store
    if enabled(): get_store().cancel(user_id, 'video', task_id, deleted=True)
    with _cancel_lock:
        _cancelled_tasks.add(task_id)

    deleted = db.delete_task(task_id, user_id)
    if not deleted:
        _clear_cancelled(task_id)
        raise HTTPException(status_code=404, detail="Task not found")
    delete_task_assets(task_id)
    _invalidate_list_cache(user_id)
    return {"message": "Task deleted"}


@router.delete("/channels/{channel_name}")
def delete_channel(channel_name: str, user: Optional[User] = Depends(get_current_user)):
    """Delete all video tasks for a channel."""
    from screenshot_extractor import delete_task_assets
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    if channel_name == "__unknown__":
        tasks = [task for task in db.list_tasks(user_id, limit=10000) if not task.get("channel")]
    else:
        tasks = [task for task in db.list_tasks(user_id, limit=10000) if task.get("channel") == channel_name]
    from execution_store import enabled, get_store
    if enabled():
        for task in tasks: get_store().cancel(user_id,'video',task['id'],deleted=True)
    count = db.delete_channel(channel_name, user_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="Channel not found or no tasks to delete")
    with _cancel_lock:
        _cancelled_tasks.update(task["id"] for task in tasks if task.get("id"))
    for task in tasks:
        task_id = task.get("id")
        if task_id:
            delete_task_assets(task_id)
    _invalidate_list_cache(user_id)
    return {"message": f"Deleted {count} video(s) from channel '{channel_name}'", "deleted": count}


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    """Retry a video note task.

    If the client sends processing defaults in the JSON body, prefer those
    values so retry/re-process uses the user's current Settings selections.
    """
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    task = await asyncio.to_thread(db.get_task, task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    retryable = ("failed", "cancelled", "cancelling", "success", "downloading", "parsing", "transcribing", "summarizing", "saving", "pending", "discovered")
    if task["status"] not in retryable:
        raise HTTPException(status_code=400, detail=f"Cannot retry task in '{task['status']}' status")

    from execution_store import enabled
    if enabled() and task['status'] in ('downloading','parsing','transcribing','summarizing','saving','pending','cancelling'):
        raise HTTPException(status_code=409, detail='This task is still running or stopping. Wait for it to finish before retrying.')
    overrides: dict = {}
    try:
        body = await request.json()
        if isinstance(body, dict):
            overrides = body
    except Exception:
        pass

    style = overrides.get("style", task.get("style") or "detailed")
    formats = overrides.get("formats", task.get("formats") or ["toc", "summary", "screenshot"])
    quality = overrides.get("quality", task.get("quality") or "medium")
    video_quality = overrides.get("video_quality", task.get("video_quality") or "720")
    llm_model = overrides.get("llm_model", task.get("model") or "")

    if isinstance(formats, str):
        try:
            formats = json.loads(formats)
        except (json.JSONDecodeError, TypeError):
            formats = ["toc", "summary", "screenshot"]
    if not formats:
        formats = overrides.get("formats", ["toc", "summary", "screenshot"])

    await asyncio.to_thread(db.update_task, task_id, {
        "status": "pending", "progress": 0,
        "message": "Starting..." if task["status"] == "discovered" else "Retrying...",
        "error": "",
        "style": style,
        "formats": formats,
        "quality": quality,
        "video_quality": video_quality,
        "model": llm_model,
    })

    background_tasks.add_task(
        enqueue_video_note,
        task_id,
        attempt_id=_new_video_attempt(task_id),
        url=task["url"],
        platform=task["platform"],
        style=style,
        formats=formats,
        quality=quality,
        llm_model=llm_model,
        extras=task.get("extras", ""),
        video_understanding=task.get("video_understanding", False),
        video_interval=task.get("video_interval", 4),
        grid_cols=task.get("grid_cols", 3),
        grid_rows=task.get("grid_rows", 3),
        user_id=user_id,
        video_quality=video_quality,
    )

    _invalidate_list_cache(user_id)
    return {"message": "Retry started", "task_id": task_id}


@router.post("/tasks/{task_id}/cancel")
def cancel_task(
    task_id: str,
    user: Optional[User] = Depends(get_current_user),
):
    """Cancel an in-progress video note task."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    task = db.get_task(task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    terminal = ("success", "failed", "cancelled")
    if task["status"] in terminal:
        return {"message": f"Task already {task['status']}", "status": task["status"]}

    from execution_store import enabled, get_store
    if enabled(): get_store().cancel(user_id, 'video', task_id)
    with _cancel_lock:
        _cancelled_tasks.add(task_id)

    next_status = "cancelled" if task["status"] == "pending" else "cancelling"
    db.update_task(task_id, {"status": next_status, "message": "Cancelled" if next_status == "cancelled" else "Stopping safely…"})
    _invalidate_list_cache(user_id)
    logger.info(f"Cancel requested for video task: {task_id}")
    return {"message": "Cancel requested", "task_id": task_id, "status": next_status}


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user),
):
    """Upload a local video file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in LOCAL_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    file_id = str(uuid.uuid4())[:12]
    from api.local_media import get_local_video_dir
    save_path = get_local_video_dir(user.id if user else None) / f"{file_id}{ext}"
    total_size = 0

    try:
        with open(save_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                total_size += len(chunk)
    finally:
        await file.close()

    if total_size <= 0:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    return {
        "file_id": file_id,
        "filename": file.filename,
        "path": str(save_path),
        "size": total_size,
    }


@router.post("/upload/init")
def init_chunked_upload(
    filename: str = Form(...),
    size: int = Form(...),
    content_type: str = Form(""),
    user: Optional[User] = Depends(get_current_user),
):
    """Initialize a chunked local video upload session."""
    _maybe_cleanup_stale_uploads()

    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    ext = Path(filename).suffix.lower()
    if ext not in LOCAL_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    upload_id = str(uuid.uuid4())[:16]
    session_dir = _upload_session_dir(upload_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    chunk_size = VIDEO_UPLOAD_CHUNK_SIZE
    total_size = max(0, int(size or 0))
    total_chunks = max(1, (total_size + chunk_size - 1) // chunk_size)
    meta = {
        "filename": Path(filename).name,
        "size": total_size,
        "content_type": content_type or "",
        "ext": ext,
        "user_id": user.id if user else None,
        "created_at": time.time(),
        "received_bytes": 0,
        "assembled_bytes": 0,
        "received_chunks": [],
        "total_chunks": total_chunks,
        "phase": "initializing",
        "error": "",
    }
    with _upload_meta_lock:
        _write_upload_meta_unlocked(upload_id, meta)
    return {
        "upload_id": upload_id,
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
        "recommended_concurrency": VIDEO_UPLOAD_CLIENT_CONCURRENCY,
    }


@router.post("/upload/chunk")
async def upload_video_chunk(
    upload_id: str = Form(...),
    index: int = Form(...),
    chunk: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user),
):
    """Upload one chunk of a local video file."""
    try:
        meta = _get_upload_meta(upload_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload session not found")
    except Exception:
        _cleanup_upload_session(upload_id)
        raise HTTPException(status_code=500, detail="Upload session is corrupted")

    if meta.get("user_id") != (user.id if user else None):
        raise HTTPException(status_code=403, detail="Upload session does not belong to this user")

    if index < 0:
        raise HTTPException(status_code=400, detail="Chunk index must be >= 0")
    total_chunks = int(meta.get("total_chunks") or 0)
    if total_chunks and index >= total_chunks:
        raise HTTPException(status_code=400, detail=f"Chunk index {index} is out of range")

    part_path = _session_chunk_path(upload_id, index)
    total_size, previous_size = await save_upload_chunk(chunk, part_path)

    try:
        status = _update_upload_meta(upload_id, lambda current: {
            **current,
            "received_bytes": max(0, int(current.get("received_bytes") or 0) - previous_size + total_size),
            "received_chunks": sorted({
                *[int(i) for i in current.get("received_chunks", [])],
                index,
            }),
            "phase": "uploaded" if len({
                *[int(i) for i in current.get("received_chunks", [])],
                index,
            }) >= int(current.get("total_chunks") or 0) else "uploading",
            "error": "",
        })
    except Exception:
        _mark_upload_failed(upload_id, "Failed to record uploaded chunk")
        raise HTTPException(status_code=500, detail="Failed to record uploaded chunk")

    return {
        "upload_id": upload_id,
        "index": index,
        "size": total_size,
        "status": _upload_status_payload(upload_id, status),
    }


@router.post("/upload/complete")
def complete_chunked_upload(
    upload_id: str = Form(...),
    user: Optional[User] = Depends(get_current_user),
):
    """Finalize a chunked upload and assemble the saved local file."""
    try:
        meta = _get_upload_meta(upload_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload session not found")
    except Exception:
        _cleanup_upload_session(upload_id)
        raise HTTPException(status_code=500, detail="Upload session is corrupted")

    if meta.get("user_id") != (user.id if user else None):
        raise HTTPException(status_code=403, detail="Upload session does not belong to this user")

    session_dir = _upload_session_dir(upload_id)
    part_paths = validated_upload_parts(
        session_dir, int(meta.get("total_chunks") or 0), int(meta.get("size") or 0),
    )

    try:
        meta = _update_upload_meta(upload_id, lambda current: {
            **current,
            "phase": "assembling",
            "assembled_bytes": 0,
            "error": "",
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to start upload finalization")

    file_id = str(uuid.uuid4())[:12]
    ext = meta.get("ext") or Path(meta.get("filename", "")).suffix.lower()
    from api.local_media import get_local_video_dir
    save_path = get_local_video_dir(user.id if user else None) / f"{file_id}{ext}"
    bytes_written = 0

    try:
        with open(save_path, "wb") as out:
            for part_path in part_paths:
                with open(part_path, "rb") as src:
                    shutil.copyfileobj(src, out, length=VIDEO_UPLOAD_ASSEMBLY_COPY_BYTES)
                bytes_written += part_path.stat().st_size
                part_path.unlink(missing_ok=True)
                _snapshot = bytes_written
                _update_upload_meta(upload_id, lambda current, _bw=_snapshot: {
                    **current,
                    "phase": "assembling",
                    "assembled_bytes": _bw,
                })
    except Exception:
        save_path.unlink(missing_ok=True)
        # Best-effort cleanup of any chunks not yet unlinked by the loop above
        # so a failed assembly doesn't leak ~hundreds of MB on the persistent
        # disk until the 24h stale sweep runs.
        _cleanup_upload_parts(upload_id)
        _mark_upload_failed(upload_id, "Failed to assemble uploaded file")
        raise HTTPException(status_code=500, detail="Failed to assemble uploaded file")

    expected_size = int(meta.get("size") or 0)
    if expected_size > 0 and bytes_written != expected_size:
        save_path.unlink(missing_ok=True)
        _mark_upload_failed(
            upload_id,
            f"Upload incomplete: expected {expected_size} bytes, received {bytes_written} bytes",
        )
        raise HTTPException(
            status_code=400,
            detail=f"Upload incomplete: expected {expected_size} bytes, received {bytes_written} bytes",
        )

    final_meta = _update_upload_meta(upload_id, lambda current: {
        **current,
        "phase": "complete",
        "file_id": file_id,
        "path": str(save_path),
        "assembled_bytes": bytes_written,
        "received_bytes": max(bytes_written, int(current.get("received_bytes") or 0)),
        "error": "",
    })
    _cleanup_upload_parts(upload_id)

    return {
        "file_id": file_id,
        "filename": meta.get("filename", ""),
        "path": str(save_path),
        "size": bytes_written,
        "status": _upload_status_payload(upload_id, final_meta),
    }


@router.get("/upload/status")
def get_chunked_upload_status(
    upload_id: str = Query(...),
    user: Optional[User] = Depends(get_current_user),
):
    """Get current status for a chunked upload session."""
    try:
        meta = _get_upload_meta(upload_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload session not found")
    except Exception:
        _cleanup_upload_session(upload_id)
        raise HTTPException(status_code=500, detail="Upload session is corrupted")

    if meta.get("user_id") != (user.id if user else None):
        raise HTTPException(status_code=403, detail="Upload session does not belong to this user")

    return _upload_status_payload(upload_id, meta)


@router.post("/check-channels")
async def check_channels_for_updates(
    channel: Optional[str] = Query(None, description="Filter to a specific channel name"),
    platform: Optional[str] = Query(None, description="Filter to a specific platform"),
    paged: bool = Query(False, description="Check one source per request"),
    cursor: Optional[str] = Query(None, max_length=100),
    request: Request = None,
    user: Optional[User] = Depends(get_current_user),
):
    """Scan video channels for new videos and create discovered tasks.

    Without filters: checks all channels.
    With platform: checks only channels on that platform.
    With channel: checks only that specific channel.
    """
    from video_task_db import get_video_task_db
    from video_downloader import list_channel_videos
    from cookie_manager import get_cookie_manager

    db = get_video_task_db()
    user_id = user.id if user else None
    defaults: dict = {}
    if request is not None:
        try:
            body = await request.json()
            if isinstance(body, dict):
                defaults = body
        except Exception:
            pass

    paged = paged is True  # Direct callers may receive FastAPI Query defaults.
    cursor = cursor if isinstance(cursor, str) else None
    try:
        all_channels = await asyncio.wait_for(asyncio.to_thread(db.get_distinct_channels, user_id), timeout=10)
    except TimeoutError:
        raise HTTPException(status_code=504, detail='Loading saved sources timed out. No source check was started; retry.') from None

    if platform:
        all_channels = [c for c in all_channels if c.get("platform") == platform]
    if channel:
        all_channels = [c for c in all_channels if c.get("channel") == channel]
    supported = {'youtube','bilibili','douyin','twitter','substack'}
    skipped = sum(c.get('platform') not in supported for c in all_channels)
    # Legacy social imports saved a post URL on every item. Scan each displayed
    # source once, preferring an already saved author/publication URL.
    grouped = {}
    for item in all_channels:
        if item.get('platform') not in supported: continue
        key = (item.get('platform'), item.get('channel'))
        if item.get('platform') == 'substack' and item.get('channel_url'):
            from source_updates import author_url
            from social_content import SocialSourceError
            try: key += (author_url('substack',item['channel_url']),)
            except (SocialSourceError, ValueError): key += ('unavailable',)
        if key not in grouped or (item.get('channel_url') and not any(part in item['channel_url'] for part in ('/status/','/article/','/p/','/note/'))):
            grouped[key] = item
    keys = sorted(grouped, key=lambda key: tuple(str(value or '') for value in key))
    all_channels = [grouped[key] for key in keys]
    total = len(all_channels)
    offset = 0
    next_cursor = None
    if paged:
        import hashlib
        fingerprint = hashlib.sha256(json.dumps([user_id, keys], ensure_ascii=False).encode()).hexdigest()[:24]
        if cursor:
            try:
                token, position = cursor.split(':')
                offset = int(position)
                if token != fingerprint or not 0 < offset < total:
                    raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(status_code=409, detail='The source list changed. Previously found items were saved; check updates again.')
        all_channels = all_channels[offset:offset+1]
        if offset + 1 < total:
            next_cursor = f'{fingerprint}:{offset+1}'
        if offset:
            skipped = 0

    if not all_channels:
        return {"message": "No sources with automatic updates found", "new_videos": 0, "channels_checked": 0,'channels_failed':0,'channels_skipped':skipped,'failures':[], 'next_cursor':None, 'channels_total':0, 'channels_processed':0}

    loop = asyncio.get_event_loop()
    total_created = 0
    checked = 0
    failures = []
    saving = []
    semaphore = asyncio.Semaphore(3)
    deadline = time.monotonic()+40
    owner_key = user_id or '__local__'
    if owner_key in _channel_checks:
        raise HTTPException(status_code=409,detail='An update check is already running. Wait for its result before checking again.')
    _channel_checks.add(owner_key)

    async def scan(ch):
        nonlocal total_created, checked
        ch_name = ch.get("channel", "")
        channel_url = ch.get("channel_url", "")
        channel_avatar = ch.get("channel_avatar", "")
        ch_platform = ch.get("platform", "")
        if not channel_url:
            failures.append({'channel':ch_name,'platform':ch_platform,'message':'No original source URL is saved. Import an original link again.'})
            return
        try:
            if ch_platform in ('twitter','substack'):
                from source_updates import list_author_updates
                fetch = lambda: list_author_updates(channel_url,ch_platform,limit=15)
            else:
                fetch = lambda: list_channel_videos(channel_url,ch_platform,cookies=get_cookie_manager(user_id).get_cookie(ch_platform),limit=15,strict=True)
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise TimeoutError()
            videos = await asyncio.wait_for(loop.run_in_executor(None,fetch),timeout=min(20,remaining))
            if not videos:
                checked += 1
                return
            if paged:
                rows = [{
                    'url': v['url'], 'platform': ch_platform,
                    'title': v.get('title', ''), 'thumbnail': v.get('thumbnail', ''),
                    'duration': v.get('duration', 0), 'channel': ch_name,
                    'channel_url': v.get('channel_url') or channel_url,
                    'channel_avatar': channel_avatar,
                    'style': defaults.get('style', 'detailed'),
                    'formats': defaults.get('formats', ['toc', 'summary', 'screenshot']),
                    'quality': defaults.get('quality', 'medium'),
                    'video_quality': defaults.get('video_quality', '720'),
                    'model': defaults.get('llm_model', ''), 'status': 'discovered',
                    'published_at': v.get('published_at') or '',
                } for v in videos[:15]]
                save = asyncio.create_task(asyncio.to_thread(db.save_discoveries, rows, user_id))
                saving.append(save)
                # A timeout stops waiting, not an already submitted DB write.
                # Keep the owner lock until acknowledgement actually arrives.
                total_created += await asyncio.wait_for(asyncio.shield(save), timeout=25)
                checked += 1
                return
            urls = [v["url"] for v in videos]
            existing_urls = await asyncio.to_thread(db.get_existing_urls, urls, user_id)
            # Backfill published_at on existing tasks that are missing it
            for v in videos:
                if v["url"] in existing_urls and v.get("published_at"):
                    existing = await asyncio.to_thread(db.get_task_by_url, v["url"], user_id)
                    if existing and not existing.get("published_at"):
                        await asyncio.to_thread(db.update_task, existing["id"], {"published_at": v["published_at"]})
            for v in videos:
                if v["url"] in existing_urls:
                    continue
                try:
                    await asyncio.to_thread(db.create_task, {
                        "url": v["url"],
                        "platform": ch_platform,
                        "title": v.get("title", ""),
                        "thumbnail": v.get("thumbnail", ""),
                        "duration": v.get("duration", 0),
                        "channel": ch_name,
                        "channel_url": v.get('channel_url') or channel_url,
                        "channel_avatar": channel_avatar,
                        "style": defaults.get("style", "detailed"),
                        "formats": defaults.get("formats", ["toc", "summary", "screenshot"]),
                        "quality": defaults.get("quality", "medium"),
                        "video_quality": defaults.get("video_quality", "720"),
                        "model": defaults.get("llm_model", ""),
                        "status": "discovered",
                        "user_id": user_id,
                        "published_at": v.get("published_at", ""),
                    })
                    total_created += 1
                    existing_urls.add(v['url'])
                except Exception as e:
                    raise RuntimeError('Could not save a discovered item') from e
            checked += 1
        except Exception as e:
            from social_content import SocialSourceError
            message = str(e) if isinstance(e,SocialSourceError) else 'This source could not be checked or saved. Previously discovered items were kept; retry this source.'
            failures.append({'channel':ch_name,'platform':ch_platform,'message':message})
            logger.warning('Source update check failed: platform=%s error=%s',ch_platform,type(e).__name__)

    async def bounded(ch):
        async with semaphore:
            await scan(ch)
    try:
        await asyncio.gather(*(bounded(ch) for ch in all_channels))
    finally:
        if any(not save.done() for save in saving):
            def saved(_):
                _invalidate_list_cache(user_id)
                _channel_checks.discard(owner_key)
            asyncio.gather(*saving, return_exceptions=True).add_done_callback(saved)
        else:
            _channel_checks.discard(owner_key)

    if total_created:
        _invalidate_list_cache(user_id)

    return {
        "message": f"Found {total_created} new item(s); {len(failures)} source(s) could not be checked" if failures else f"Found {total_created} new item(s)" if total_created else "No new items found",
        "new_videos": total_created,
        "channels_checked": checked,
        'channels_failed':len(failures),'channels_skipped':skipped,'failures':failures,
        'next_cursor':next_cursor, 'channels_total':total,
        'channels_processed':offset+len(all_channels),
    }


@router.get("/sys-health")
def sys_health():
    """Check system dependencies (FFmpeg, yt-dlp)."""
    from video_downloader import check_ffmpeg, check_ytdlp
    result = {
        "ffmpeg": check_ffmpeg(),
        "ytdlp": check_ytdlp(),
    }
    return result


@router.get("/styles")
def get_styles():
    """Get available note styles."""
    from note_summarizer import get_available_styles
    return {"styles": get_available_styles()}
