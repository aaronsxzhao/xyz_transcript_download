"""Video note generation endpoints with background processing."""
import asyncio
import json
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Optional, Set

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, UploadFile, File, Form, Query, Request

from api.auth import get_current_user, User
from api.local_media import LOCAL_VIDEO_CHANNEL, LOCAL_VIDEO_EXTENSIONS
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

logger = get_logger("video_notes")

router = APIRouter()

VIDEO_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video_processor")

_list_cache: dict = {}
_LIST_TTL = 5.0


def _invalidate_list_cache(user_id: str = None):
    key = user_id or "__local__"
    _list_cache.pop(key, None)

_cancel_lock = threading.Lock()
_cancelled_tasks: Set[str] = set()
_upload_meta_lock = threading.Lock()
_last_upload_cleanup = 0.0


class VideoCancelledException(Exception):
    pass


def _local_video_title(path_value: str) -> str:
    """Best-effort title for uploaded local files before metadata is fetched."""
    if not path_value:
        return ""
    name = os.path.basename(path_value)
    stem, _ = os.path.splitext(name)
    return stem or name


def _upload_session_dir(upload_id: str) -> Path:
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
    with _cancel_lock:
        return task_id in _cancelled_tasks


def _clear_cancelled(task_id: str):
    with _cancel_lock:
        _cancelled_tasks.discard(task_id)

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHUNK_UPLOAD_DIR = UPLOAD_DIR / "_chunks"
CHUNK_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def broadcast_video_job(task_id: str, task_data: dict, user_id: Optional[str] = None):
    """Broadcast video task update to WebSocket clients."""
    await manager.broadcast_to_user({
        "type": "video_job_update",
        "task": task_data,
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
    if status not in ("cancelled", "failed") and is_video_task_cancelled(task_id):
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
        videos = list_channel_videos(channel_url, platform, limit=15)
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
):
    """Synchronous video note processing pipeline."""
    try:
        from video_task_db import get_video_task_db
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

        db = get_video_task_db()
        cookie_mgr = get_cookie_manager()
        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # Check if we already have a transcript from a previous run (for retry)
        existing_task = db.get_task(task_id, user_id)
        existing_transcript = existing_task.get("transcript") if existing_task else None
        has_saved_transcript = (
            existing_transcript
            and existing_transcript.get("text")
            and len(existing_transcript["text"]) > 50
        )

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

            downloader = get_downloader(platform, cookies)

            metadata = None
            try:
                with ThreadPoolExecutor(max_workers=1) as metadata_executor:
                    metadata = metadata_executor.submit(downloader.get_metadata, url).result(timeout=45)
            except FutureTimeout:
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

                def audio_progress(pct: float, msg: str):
                    if is_video_task_cancelled(task_id):
                        raise VideoCancelledException("Cancelled during download")
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
                    db.update_task(task_id, {
                        "title": title,
                        "thumbnail": thumbnail,
                        "duration": duration,
                        "channel": channel,
                        "channel_url": channel_url,
                        "channel_avatar": channel_avatar,
                    })

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
                transcriber = get_transcriber()

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

            def video_progress(pct: float, msg: str):
                if is_video_task_cancelled(task_id):
                    raise VideoCancelledException("Cancelled during video download")
                # Accept either normalized 0..1 progress or legacy 0..100 values.
                pct = pct / 100.0 if pct > 1 else pct
                pct = max(0.0, min(pct, 1.0))
                job_pct = 26 + pct * 14
                _update_task_status(db, task_id, "downloading", job_pct, msg, user_id)

            try:
                if not platform:
                    platform = detect_platform(url)
                if platform and downloader is None:
                    cookies = cookie_mgr.get_cookie(platform)
                    downloader = get_downloader(platform, cookies)
                if downloader:
                    video_path = downloader.download_video(
                        url,
                        task_id,
                        video_quality=video_quality,
                        progress_callback=video_progress,
                    )
            except VideoDownloadError as e:
                logger.warning(f"Video download failed ({e.error_code}), continuing without video: {e}")
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
            # If still no thumbnail and we have a URL, try a quick video download just for thumbnail
            if not thumbnail and url:
                if not platform:
                    platform = detect_platform(url)
                if platform:
                    logger.info(f"[{task_id}] Attempting lightweight video download for thumbnail...")
                    try:
                        cookies = cookie_mgr.get_cookie(platform)
                        thumb_downloader = get_downloader(platform, cookies)
                        thumb_video = thumb_downloader.download_video(url, task_id, video_quality="360")
                        if thumb_video:
                            thumb_url = extract_first_frame_thumbnail(str(thumb_video), task_id)
                            if thumb_url:
                                thumbnail = thumb_url
                                db.update_task(task_id, {"thumbnail": thumbnail})
                                logger.info(f"[{task_id}] Thumbnail fallback from downloaded video succeeded")
                    except Exception as e:
                        logger.warning(f"[{task_id}] Thumbnail video download fallback failed: {e}")

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
                        grids, title=title, model=llm_model,
                    )
            except Exception as e:
                logger.warning(f"Video understanding failed: {e}")

        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # When screenshots are requested, embed segment timestamps in transcript
        # so the LLM can place Screenshot markers at real video timestamps.
        if "screenshot" in formats and transcript_segments:
            timestamped_parts = []
            for seg in transcript_segments:
                m = int(seg["start"] // 60)
                s = int(seg["start"] % 60)
                timestamped_parts.append(f"[{m:02d}:{s:02d}] {seg['text']}")
            transcript_text = "\n".join(timestamped_parts)

        transcript_chars = len(transcript_text)
        num_expected_chunks = max(1, transcript_chars // NOTE_CHUNK_CHARS + (1 if transcript_chars % NOTE_CHUNK_CHARS else 0))
        if num_expected_chunks > 1:
            _update_task_status(db, task_id, "summarizing", 72,
                                f"Starting AI note generation — splitting into ~{num_expected_chunks} sections...", user_id)
        else:
            _update_task_status(db, task_id, "summarizing", 72, "Starting AI note generation...", user_id)

        # Phase 4: Generate notes (72-92%)
        note_summarizer = get_note_summarizer(
            model=llm_model if llm_model else "",
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
                updates = {
                    "status": "summarizing",
                    "progress": job_progress,
                    "message": msg,
                }
                if partial_text:
                    updates["markdown"] = partial_text
                _update_task_status(db, task_id, "summarizing", job_progress, msg, user_id,
                                    **({"markdown": partial_text} if partial_text else {}))

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

        if not markdown:
            _update_task_status(db, task_id, "failed", 0, "Note generation failed", user_id,
                                error="LLM failed")
            return

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
                    extract_screenshots_batch(str(video_path), timestamps, task_id)
                    markdown = replace_screenshot_markers(markdown, task_id)
            else:
                logger.warning(f"No video file for screenshots in task {task_id}, removing markers")
                import re
                markdown = re.sub(
                    r'\*?Screenshot-\[\d+(?::\d+){1,2}\]\*?\n?', '', markdown
                )

        # Save result
        db.update_task(task_id, {"markdown": markdown, "status": "success", "progress": 100, "message": "Done"})

        # Save version
        db.add_version(task_id, markdown, style, llm_model)

        # Ensure all pending writes are flushed to Supabase
        db.flush_task(task_id)

        _update_task_status(db, task_id, "success", 100, "Notes generated!", user_id)
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


async def process_video_note_async(task_id: str, **kwargs):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            VIDEO_EXECUTOR,
            lambda: process_video_note_sync(task_id, **kwargs),
        )
    except Exception as e:
        logger.error(f"[Video {task_id}] Unhandled error: {e}")


@router.post("/generate")
async def generate_note(
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
    from video_downloader import normalize_video_url
    db = get_video_task_db()
    url = normalize_video_url(url, platform)
    is_local = platform == "local"

    _invalidate_list_cache(user_id)

    existing = db.get_task_by_url(url, user_id)
    if existing:
        task_id = existing["id"]
        db.update_task(task_id, {
            "title": title or (_local_video_title(url) if is_local and not existing.get("title") else existing.get("title", "")),
            "style": style,
            "formats": fmt_list,
            "quality": quality,
            "video_quality": video_quality,
            "model": llm_model,
            "extras": extras,
            "status": "pending",
            "progress": 0,
            "message": "",
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
        except Exception as e:
            logger.error(f"[generate] create_task failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create task: {type(e).__name__}: {e}")

    background_tasks.add_task(
        process_video_note_async,
        task_id,
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


@router.post("/generate-json")
async def generate_note_json(
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
    from video_downloader import normalize_video_url
    db = get_video_task_db()
    platform = data.get("platform", "")
    url = normalize_video_url(url, platform)
    is_local = platform == "local"

    _invalidate_list_cache(user_id)

    existing = db.get_task_by_url(url, user_id)
    if existing:
        task_id = existing["id"]
        db.update_task(task_id, {
            "title": data.get("title", "") or (_local_video_title(url) if is_local and not existing.get("title") else existing.get("title", "")),
            "style": data.get("style", "detailed"),
            "formats": data.get("formats", []),
            "quality": data.get("quality", "medium"),
            "video_quality": data.get("video_quality", "720"),
            "model": data.get("llm_model", ""),
            "extras": data.get("extras", ""),
            "status": "pending",
            "progress": 0,
            "message": "",
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
        except Exception as e:
            logger.error(f"[generate-json] create_task failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create task: {type(e).__name__}: {e}")

    background_tasks.add_task(
        process_video_note_async,
        task_id,
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


@router.get("/tasks")
async def list_tasks(user: Optional[User] = Depends(get_current_user)):
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
    result = {"tasks": tasks}
    if not _has_active_video_tasks(tasks):
        _list_cache[cache_key] = {"t": now, "data": result}
    else:
        _list_cache.pop(cache_key, None)
    return result


@router.get("/recent")
async def list_recent_tasks(
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
    result = {"tasks": tasks}
    _list_cache[cache_key] = {"t": now, "data": result}
    return result


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user: Optional[User] = Depends(get_current_user)):
    """Get a video note task with versions."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    task = db.get_task(task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["versions"] = db.get_versions(task_id)
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: Optional[User] = Depends(get_current_user)):
    """Delete a video note task and cancel any in-progress processing."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None

    with _cancel_lock:
        _cancelled_tasks.add(task_id)

    deleted = db.delete_task(task_id, user_id)
    if not deleted:
        _clear_cancelled(task_id)
        raise HTTPException(status_code=404, detail="Task not found")
    _invalidate_list_cache(user_id)
    return {"message": "Task deleted"}


@router.delete("/channels/{channel_name}")
async def delete_channel(channel_name: str, user: Optional[User] = Depends(get_current_user)):
    """Delete all video tasks for a channel."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    count = db.delete_channel(channel_name, user_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="Channel not found or no tasks to delete")
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
    task = db.get_task(task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    retryable = ("failed", "cancelled", "success", "downloading", "parsing", "transcribing", "summarizing", "saving", "pending", "discovered")
    if task["status"] not in retryable:
        raise HTTPException(status_code=400, detail=f"Cannot retry task in '{task['status']}' status")

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

    db.update_task(task_id, {
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
        process_video_note_async,
        task_id,
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

    return {"message": "Retry started", "task_id": task_id}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
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

    with _cancel_lock:
        _cancelled_tasks.add(task_id)

    db.update_task(task_id, {"status": "cancelled", "message": "Cancelling..."})
    logger.info(f"Cancel requested for video task: {task_id}")
    return {"message": "Cancel requested", "task_id": task_id}


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
    save_path = UPLOAD_DIR / f"{file_id}{ext}"
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
async def init_chunked_upload(
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
    previous_size = part_path.stat().st_size if part_path.exists() else 0
    total_size = 0
    try:
        with open(part_path, "wb") as f:
            while True:
                data = await chunk.read(1024 * 1024)
                if not data:
                    break
                f.write(data)
                total_size += len(data)
    finally:
        await chunk.close()

    if total_size <= 0:
        part_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded chunk is empty")

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
async def complete_chunked_upload(
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
    part_paths = sorted(session_dir.glob("*.part"))
    if not part_paths:
        raise HTTPException(status_code=400, detail="No uploaded chunks found")

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
    save_path = UPLOAD_DIR / f"{file_id}{ext}"
    bytes_written = 0

    try:
        with open(save_path, "wb") as out:
            for part_path in part_paths:
                with open(part_path, "rb") as src:
                    shutil.copyfileobj(src, out, length=VIDEO_UPLOAD_ASSEMBLY_COPY_BYTES)
                bytes_written += part_path.stat().st_size
                _snapshot = bytes_written
                _update_upload_meta(upload_id, lambda current, _bw=_snapshot: {
                    **current,
                    "phase": "assembling",
                    "assembled_bytes": _bw,
                })
    except Exception:
        save_path.unlink(missing_ok=True)
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
async def get_chunked_upload_status(
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

    all_channels = db.get_distinct_channels(user_id)

    if channel:
        all_channels = [c for c in all_channels if c.get("channel") == channel]
    elif platform:
        all_channels = [c for c in all_channels if c.get("platform") == platform]

    if not all_channels:
        return {"message": "No video channels found", "new_videos": 0, "channels_checked": 0}

    loop = asyncio.get_event_loop()
    total_created = 0

    for ch in all_channels:
        ch_name = ch.get("channel", "")
        channel_url = ch.get("channel_url", "")
        channel_avatar = ch.get("channel_avatar", "")
        ch_platform = ch.get("platform", "")
        if not channel_url:
            continue
        try:
            videos = await loop.run_in_executor(
                None, lambda cu=channel_url, p=ch_platform: list_channel_videos(cu, p, limit=15)
            )
            if not videos:
                continue
            urls = [v["url"] for v in videos]
            existing_urls = db.get_existing_urls(urls, user_id)
            for v in videos:
                if v["url"] in existing_urls:
                    continue
                try:
                    db.create_task({
                        "url": v["url"],
                        "platform": ch_platform,
                        "title": v.get("title", ""),
                        "thumbnail": v.get("thumbnail", ""),
                        "duration": v.get("duration", 0),
                        "channel": ch_name,
                        "channel_url": channel_url,
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
                except Exception as e:
                    logger.warning(f"Failed to create discovered task for {v['url']}: {e}")
        except Exception as e:
            logger.warning(f"Failed to check channel '{ch_name}': {e}")

    if total_created:
        _invalidate_list_cache(user_id)

    return {
        "message": f"Found {total_created} new video(s)" if total_created else "No new videos found",
        "new_videos": total_created,
        "channels_checked": len(all_channels),
    }


@router.get("/sys-health")
async def sys_health():
    """Check system dependencies (FFmpeg, yt-dlp)."""
    from video_downloader import check_ffmpeg, check_ytdlp
    result = {
        "ffmpeg": check_ffmpeg(),
        "ytdlp": check_ytdlp(),
    }
    return result


@router.get("/styles")
async def get_styles():
    """Get available note styles."""
    from note_summarizer import get_available_styles
    return {"styles": get_available_styles()}
