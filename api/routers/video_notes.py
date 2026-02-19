"""Video note generation endpoints with background processing."""
import asyncio
import json
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Set

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, UploadFile, File, Form

from api.auth import get_current_user, User
from api.routers.processing import (
    manager, get_main_loop, ConnectionManager,
)
from config import DATA_DIR
from logger import get_logger

logger = get_logger("video_notes")

router = APIRouter()

VIDEO_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video_processor")

_cancel_lock = threading.Lock()
_cancelled_tasks: Set[str] = set()


class VideoCancelledException(Exception):
    pass


def is_video_task_cancelled(task_id: str) -> bool:
    with _cancel_lock:
        return task_id in _cancelled_tasks


def _clear_cancelled(task_id: str):
    with _cancel_lock:
        _cancelled_tasks.discard(task_id)

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
    """Update task in DB and broadcast."""
    updates = {"status": status, "progress": progress, "message": message}
    updates.update(kwargs)
    db.update_task(task_id, updates)
    task = db.get_task(task_id, user_id)
    if task:
        _broadcast_from_thread(task_id, task, user_id)


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
    max_output_tokens: int = 0,
):
    """Synchronous video note processing pipeline."""
    from video_task_db import get_video_task_db
    from video_downloader import get_downloader, detect_platform, VideoDownloadError
    from cookie_manager import get_cookie_manager
    from note_summarizer import get_note_summarizer
    from screenshot_extractor import (
        extract_timestamps_from_markdown,
        extract_screenshots_batch,
        replace_screenshot_markers,
    )

    db = get_video_task_db()
    cookie_mgr = get_cookie_manager()

    try:
        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # Phase 1: Parse / metadata (0-10%)
        _update_task_status(db, task_id, "parsing", 5, "Fetching video info...", user_id)

        if not platform:
            platform = detect_platform(url)
        if not platform:
            _update_task_status(db, task_id, "failed", 0, "Could not detect platform", user_id,
                                error="Unsupported URL")
            return

        cookies = cookie_mgr.get_cookie(platform)

        if platform == "bilibili" and not cookies:
            _update_task_status(
                db, task_id, "failed", 0,
                "BiliBili requires login. Go to Settings → BiliBili Login to scan the QR code first.",
                user_id,
                error="BILIBILI_LOGIN_REQUIRED",
            )
            return

        downloader = get_downloader(platform, cookies)

        metadata = downloader.get_metadata(url)
        title = metadata.title if metadata else "Untitled"
        thumbnail = metadata.thumbnail if metadata else ""
        duration = metadata.duration if metadata else 0
        tags = metadata.tags if metadata else []

        db.update_task(task_id, {
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
        })
        _update_task_status(db, task_id, "parsing", 10, f"Found: {title}", user_id)

        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # Phase 2: Download audio (10-25%)
        _update_task_status(db, task_id, "downloading", 12, "Downloading audio...", user_id)

        def audio_progress(pct: float, msg: str):
            if is_video_task_cancelled(task_id):
                raise VideoCancelledException("Cancelled during download")
            job_pct = 12 + pct * 13
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

        # Fill in missing metadata from download info (e.g. BiliBili thumbnail)
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
            db.update_task(task_id, {
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
            })

        _update_task_status(db, task_id, "downloading", 25, "Audio downloaded", user_id)

        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # Phase 2b: Download video if needed for screenshots or video understanding
        video_path = None
        needs_video = "screenshot" in formats or video_understanding
        if needs_video:
            _update_task_status(db, task_id, "downloading", 27, "Downloading video...", user_id)

            def video_progress(pct: float, msg: str):
                if is_video_task_cancelled(task_id):
                    raise VideoCancelledException("Cancelled during video download")
                job_pct = 27 + pct * 3
                _update_task_status(db, task_id, "downloading", job_pct, msg, user_id)

            try:
                video_path = downloader.download_video(url, task_id, progress_callback=video_progress)
            except VideoDownloadError as e:
                logger.warning(f"Video download failed ({e.error_code}), continuing without video: {e}")
                video_path = None

        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        # Phase 3: Transcribe (25-60%)
        _update_task_status(db, task_id, "transcribing", 30, "Starting transcription...", user_id)

        # Try platform subtitles first
        subtitles = downloader.get_subtitles(url, task_id)
        transcript_text = ""
        transcript_segments = []

        if subtitles:
            _update_task_status(db, task_id, "transcribing", 50, "Using platform subtitles...", user_id)
            transcript_segments = subtitles
            transcript_text = " ".join(s["text"] for s in subtitles)
        else:
            # Use existing transcriber
            from transcriber import get_transcriber
            transcriber = get_transcriber()

            last_progress = [30]

            def transcribe_progress(progress: float):
                if is_video_task_cancelled(task_id):
                    raise VideoCancelledException("Cancelled during transcription")
                job_progress = 30 + (progress * 30)
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
                _update_task_status(db, task_id, "failed", 0, "Transcription failed", user_id,
                                    error="Transcription failed")
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
        _update_task_status(db, task_id, "transcribing", 60, "Transcription complete", user_id)

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
                    _update_task_status(db, task_id, "transcribing", 65, "Running vision analysis...", user_id)
                    visual_context = analyze_grids(
                        grids, title=title, model=llm_model,
                    )
            except Exception as e:
                logger.warning(f"Video understanding failed: {e}")

        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
            return

        _update_task_status(db, task_id, "summarizing", 70, "Generating notes...", user_id)

        # Phase 4: Generate notes (70-90%)
        note_summarizer = get_note_summarizer(
            model=llm_model if llm_model else "",
            max_output_tokens=max_output_tokens,
        )

        last_summarize_progress = [70]

        def summarize_progress(chars):
            if is_video_task_cancelled(task_id):
                raise VideoCancelledException("Cancelled during summarization")
            progress_ratio = min(chars / 8000, 1.0)
            job_progress = 70 + (progress_ratio * 20)
            if job_progress - last_summarize_progress[0] >= 1:
                last_summarize_progress[0] = job_progress
                _update_task_status(
                    db, task_id, "summarizing", job_progress,
                    f"Generating notes ({chars} chars)...", user_id,
                )

        markdown = note_summarizer.generate_note(
            title=title,
            transcript_text=transcript_text,
            style=style,
            formats=formats,
            visual_context=visual_context,
            tags=tags,
            extras=extras,
            progress_callback=summarize_progress,
        )

        if not markdown:
            _update_task_status(db, task_id, "failed", 0, "Note generation failed", user_id,
                                error="LLM failed")
            return

        # Phase 5: Post-processing (90-100%)
        _update_task_status(db, task_id, "saving", 92, "Post-processing...", user_id)

        # Extract and capture screenshots if needed
        if "screenshot" in formats and video_path:
            timestamps = extract_timestamps_from_markdown(markdown)
            if timestamps:
                extract_screenshots_batch(str(video_path), timestamps, task_id)
                markdown = replace_screenshot_markers(markdown, task_id)

        # Save result
        db.update_task(task_id, {"markdown": markdown, "status": "success", "progress": 100, "message": "Done"})

        # Save version
        db.add_version(task_id, markdown, style, llm_model)

        _update_task_status(db, task_id, "success", 100, "Notes generated!", user_id)
        logger.info(f"Video note completed: {task_id} ({title})")

    except VideoCancelledException:
        _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
        _clear_cancelled(task_id)
        logger.info(f"Video task cancelled: {task_id}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        if is_video_task_cancelled(task_id):
            _update_task_status(db, task_id, "cancelled", 0, "Cancelled", user_id)
            _clear_cancelled(task_id)
        else:
            _update_task_status(db, task_id, "failed", 0, f"Error: {str(e)}", user_id,
                                error=str(e))


async def process_video_note_async(task_id: str, **kwargs):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        VIDEO_EXECUTOR,
        lambda: process_video_note_sync(task_id, **kwargs),
    )


@router.post("/generate")
async def generate_note(
    background_tasks: BackgroundTasks,
    url: str = Form(""),
    platform: str = Form(""),
    style: str = Form("detailed"),
    formats: str = Form("[]"),
    quality: str = Form("medium"),
    llm_model: str = Form(""),
    extras: str = Form(""),
    video_understanding: bool = Form(False),
    video_interval: int = Form(4),
    grid_cols: int = Form(3),
    grid_rows: int = Form(3),
    max_output_tokens: int = Form(0),
    user: Optional[User] = Depends(get_current_user),
):
    """Start video note generation."""
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    user_id = user.id if user else None
    try:
        fmt_list = json.loads(formats) if isinstance(formats, str) else formats
    except (json.JSONDecodeError, TypeError):
        fmt_list = []

    from video_task_db import get_video_task_db
    db = get_video_task_db()

    task_id = db.create_task({
        "url": url,
        "platform": platform,
        "style": style,
        "formats": fmt_list,
        "quality": quality,
        "model": llm_model,
        "extras": extras,
        "video_understanding": video_understanding,
        "video_interval": video_interval,
        "grid_cols": grid_cols,
        "grid_rows": grid_rows,
        "user_id": user_id,
    })

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
        max_output_tokens=max_output_tokens,
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

    from video_task_db import get_video_task_db
    db = get_video_task_db()

    task_id = db.create_task({
        "url": url,
        "platform": data.get("platform", ""),
        "style": data.get("style", "detailed"),
        "formats": data.get("formats", []),
        "quality": data.get("quality", "medium"),
        "model": data.get("llm_model", ""),
        "extras": data.get("extras", ""),
        "video_understanding": data.get("video_understanding", False),
        "video_interval": data.get("video_interval", 4),
        "grid_cols": data.get("grid_cols", 3),
        "grid_rows": data.get("grid_rows", 3),
        "user_id": user_id,
    })

    background_tasks.add_task(
        process_video_note_async,
        task_id,
        url=url,
        platform=data.get("platform", ""),
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
        max_output_tokens=data.get("max_output_tokens", 0),
    )

    return {"task_id": task_id, "message": "Processing started"}


@router.get("/tasks")
async def list_tasks(user: Optional[User] = Depends(get_current_user)):
    """List all video note tasks."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    tasks = db.list_tasks(user_id)
    return {"tasks": tasks}


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
    """Delete a video note task."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    deleted = db.delete_task(task_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user),
):
    """Retry a failed video note task."""
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    user_id = user.id if user else None
    task = db.get_task(task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    retryable = ("failed", "cancelled", "downloading", "parsing", "transcribing", "summarizing", "saving", "pending")
    if task["status"] not in retryable:
        raise HTTPException(status_code=400, detail=f"Cannot retry task in '{task['status']}' status")

    db.update_task(task_id, {"status": "pending", "progress": 0, "message": "Retrying...", "error": ""})

    background_tasks.add_task(
        process_video_note_async,
        task_id,
        url=task["url"],
        platform=task["platform"],
        style=task["style"],
        formats=task["formats"],
        quality=task["quality"],
        llm_model=task["model"],
        extras=task["extras"],
        video_understanding=task["video_understanding"],
        video_interval=task["video_interval"],
        grid_cols=task["grid_cols"],
        grid_rows=task["grid_rows"],
        user_id=user_id,
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

    _update_task_status(db, task_id, "cancelled", task.get("progress", 0),
                        "Cancelling...", user_id)
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
    if ext not in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    file_id = str(uuid.uuid4())[:12]
    save_path = UPLOAD_DIR / f"{file_id}{ext}"

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "path": str(save_path),
        "size": len(content),
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
