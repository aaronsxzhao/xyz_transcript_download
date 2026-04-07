"""
Screenshot extraction from videos using FFmpeg.
Supports single frame extraction and batch extraction at timestamps.
When SUPABASE_STORAGE_ENABLED is enabled, screenshots are uploaded to
Supabase Storage so they remain accessible regardless of which server
processed the video.
"""

import re
import json
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from config import DATA_DIR, USE_SUPABASE_STORAGE
from logger import get_logger

logger = get_logger("screenshot_extractor")

SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

THUMBNAILS_DIR = DATA_DIR / "thumbnails"
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

_SUPABASE_BUCKET = "screenshots"
_SUPABASE_THUMB_BUCKET = "thumbnails"


def _get_supabase_storage_client():
    """Return the admin client for Storage operations when configured."""
    try:
        from api.supabase_client import get_supabase_admin_client
        return get_supabase_admin_client()
    except Exception:
        return None


def _ensure_supabase_bucket(client, bucket_name: str):
    """Create the storage bucket if it doesn't exist."""
    try:
        client.storage.get_bucket(bucket_name)
    except Exception:
        try:
            client.storage.create_bucket(
                bucket_name,
                options={"public": True, "file_size_limit": 2 * 1024 * 1024},
            )
            logger.info(f"Created Supabase storage bucket: {bucket_name}")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Could not create bucket '{bucket_name}': {e}")


def _upload_to_supabase(local_path: Path, bucket: str, remote_name: str) -> Optional[str]:
    """Upload a file to Supabase Storage and return its public URL."""
    if not USE_SUPABASE_STORAGE:
        return None
    try:
        client = _get_supabase_storage_client()
        if not client:
            return None
        _ensure_supabase_bucket(client, bucket)
        with open(local_path, "rb") as f:
            data = f.read()
        client.storage.from_(bucket).upload(
            remote_name, data,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
        url = client.storage.from_(bucket).get_public_url(remote_name)
        return url
    except Exception as e:
        logger.warning(f"Supabase upload failed for {remote_name}: {e}")
        return None


def _iter_bucket_objects(client, bucket: str, limit: int = 100):
    """Yield all top-level objects from a bucket."""
    offset = 0
    while True:
        page = client.storage.from_(bucket).list(
            "",
            {
                "limit": limit,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if not page:
            break
        for item in page:
            yield item
        if len(page) < limit:
            break
        offset += len(page)


def _delete_supabase_objects(client, bucket: str, object_names: List[str]) -> int:
    """Delete objects from a Storage bucket in small batches."""
    deleted = 0
    for start in range(0, len(object_names), 100):
        chunk = object_names[start:start + 100]
        if not chunk:
            continue
        try:
            client.storage.from_(bucket).remove(chunk)
            deleted += len(chunk)
        except Exception as e:
            logger.warning(f"Failed to delete {len(chunk)} object(s) from bucket '{bucket}': {e}")
    return deleted


def delete_task_assets(task_id: str) -> dict:
    """Delete screenshots and thumbnails for a video task from local disk and Supabase."""
    screenshot_files = [path for path in SCREENSHOTS_DIR.glob(f"{task_id}_*.jpg") if path.is_file()]
    thumbnail_files = [
        path for path in (
            THUMBNAILS_DIR / f"{task_id}.jpg",
            THUMBNAILS_DIR / f"{task_id}_cover.jpg",
        )
        if path.exists() and path.is_file()
    ]

    local_deleted = 0
    for path in [*screenshot_files, *thumbnail_files]:
        try:
            path.unlink(missing_ok=True)
            local_deleted += 1
        except Exception as e:
            logger.warning(f"Failed to delete local asset {path.name}: {e}")

    remote_deleted = 0
    client = _get_supabase_storage_client()
    if client:
        try:
            screenshot_names = [
                item.get("name", "")
                for item in _iter_bucket_objects(client, _SUPABASE_BUCKET)
                if str(item.get("name", "")).startswith(f"{task_id}_")
            ]
            remote_deleted += _delete_supabase_objects(client, _SUPABASE_BUCKET, screenshot_names)
        except Exception as e:
            logger.warning(f"Failed to inspect screenshot bucket for task {task_id}: {e}")

        try:
            thumbnail_names = {f"{task_id}.jpg", f"{task_id}_cover.jpg"}
            matches = [
                item.get("name", "")
                for item in _iter_bucket_objects(client, _SUPABASE_THUMB_BUCKET)
                if item.get("name") in thumbnail_names
            ]
            remote_deleted += _delete_supabase_objects(client, _SUPABASE_THUMB_BUCKET, matches)
        except Exception as e:
            logger.warning(f"Failed to inspect thumbnail bucket for task {task_id}: {e}")

    return {
        "task_id": task_id,
        "local_deleted": local_deleted,
        "remote_deleted": remote_deleted,
    }


def _parse_object_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse common Supabase/object timestamp formats into UTC datetimes."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _object_created_at(item: dict) -> Optional[datetime]:
    """Best-effort extraction of object creation/update timestamp."""
    metadata = item.get("metadata") or {}
    candidates = (
        item.get("created_at"),
        item.get("updated_at"),
        item.get("last_accessed_at"),
        metadata.get("created_at"),
        metadata.get("updated_at"),
        metadata.get("lastModified"),
        metadata.get("last_modified"),
    )
    for candidate in candidates:
        parsed = _parse_object_datetime(candidate)
        if parsed:
            return parsed
    return None


def cleanup_expired_assets(retention_days: int, now: Optional[datetime] = None) -> dict:
    """Delete local and remote generated media older than the retention window."""
    if retention_days <= 0:
        return {
            "retention_days": retention_days,
            "cutoff": None,
            "local_deleted": 0,
            "remote_deleted": 0,
            "remote_skipped_unknown_age": 0,
        }

    now_utc = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=retention_days)
    local_deleted = 0

    for directory in (SCREENSHOTS_DIR, THUMBNAILS_DIR):
        for path in directory.glob("*.jpg"):
            try:
                modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if modified_at < cutoff:
                    path.unlink(missing_ok=True)
                    local_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to inspect/delete expired local asset {path.name}: {e}")

    remote_deleted = 0
    remote_skipped_unknown_age = 0
    client = _get_supabase_storage_client()
    if client:
        for bucket in (_SUPABASE_BUCKET, _SUPABASE_THUMB_BUCKET):
            try:
                to_delete: List[str] = []
                for item in _iter_bucket_objects(client, bucket):
                    created_at = _object_created_at(item)
                    if not created_at:
                        remote_skipped_unknown_age += 1
                        continue
                    if created_at < cutoff and item.get("name"):
                        to_delete.append(item["name"])
                remote_deleted += _delete_supabase_objects(client, bucket, to_delete)
            except Exception as e:
                logger.warning(f"Failed to cleanup expired assets from bucket '{bucket}': {e}")

    return {
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "local_deleted": local_deleted,
        "remote_deleted": remote_deleted,
        "remote_skipped_unknown_age": remote_skipped_unknown_age,
    }

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    import shutil
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format for FFmpeg."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _format_display_time(seconds: float) -> str:
    """Convert seconds to mm:ss display format."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def extract_screenshot(
    video_path: str,
    timestamp: float,
    task_id: str,
) -> Optional[str]:
    """
    Extract a single screenshot from a video at a given timestamp.

    Returns:
        Filename of the saved screenshot (relative to screenshots dir), or None on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error(f"Video file not found: {video_path}")
        return None

    filename = f"{task_id}_{_format_display_time(timestamp).replace(':', '-')}.jpg"
    output_path = SCREENSHOTS_DIR / filename

    if output_path.exists():
        return filename

    try:
        duration = get_video_duration(str(video_path))
        seek_ts = max(0.0, timestamp)
        if duration > 0:
            seek_ts = min(seek_ts, max(0.0, duration - 0.5))

        attempts = [
            ["-ss", _format_timestamp(seek_ts), "-i", str(video_path)],
            ["-i", str(video_path), "-ss", _format_timestamp(seek_ts)],
        ]
        if seek_ts > 0.5:
            retry_ts = max(0.0, seek_ts - 0.5)
            attempts.extend([
                ["-ss", _format_timestamp(retry_ts), "-i", str(video_path)],
                ["-i", str(video_path), "-ss", _format_timestamp(retry_ts)],
            ])

        for args in attempts:
            cmd = [
                FFMPEG_PATH,
                *args,
                "-frames:v", "1",
                "-q:v", "2",
                "-y",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                if USE_SUPABASE_STORAGE:
                    _upload_to_supabase(output_path, _SUPABASE_BUCKET, filename)
                return filename

        logger.error(f"Screenshot extraction failed at {timestamp}s: {result.stderr[:200]}")
        return None
    except Exception as e:
        logger.error(f"Screenshot extraction error: {e}")
        return None


def extract_screenshots_batch(
    video_path: str,
    timestamps: List[float],
    task_id: str,
) -> List[Tuple[float, Optional[str]]]:
    """
    Extract screenshots at multiple timestamps.

    Returns:
        List of (timestamp, filename_or_none) tuples.
    """
    results = []
    seen = set()
    for ts in timestamps:
        if ts in seen:
            continue
        seen.add(ts)
        filename = extract_screenshot(video_path, ts, task_id)
        results.append((ts, filename))
    return results


def _parse_timestamp_str(time_str: str) -> float:
    """Parse a timestamp string (H:MM:SS, MM:SS, or SS) into total seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return float(parts[0])


# Matches Screenshot-[MM:SS] or Screenshot-[H:MM:SS] with optional surrounding *, backticks
# Also matches the bracket-less form Screenshot-MM:SS that LLMs sometimes generate
_SCREENSHOT_PATTERN = re.compile(r'`?\*?Screenshot-(?:\[(\d+(?::\d+){1,2})\]|(\d+(?::\d+){1,2}))\*?`?')


def extract_timestamps_from_markdown(markdown: str) -> List[float]:
    """Parse Screenshot-[timestamp] markers from generated markdown and return timestamps."""
    timestamps = []
    for match in _SCREENSHOT_PATTERN.finditer(markdown):
        ts_str = match.group(1) or match.group(2)
        timestamps.append(_parse_timestamp_str(ts_str))
    return timestamps


def replace_screenshot_markers(
    markdown: str,
    task_id: str,
    base_url: str = "/data/screenshots",
) -> str:
    """Replace Screenshot-[timestamp] markers in markdown with actual image tags.

    In Supabase storage mode, uses public Supabase Storage URLs so
    screenshots are accessible regardless of which server processed the video.
    """
    supabase_base = None
    if USE_SUPABASE_STORAGE:
        try:
            client = _get_supabase_storage_client()
            if client:
                supabase_base = client.storage.from_(_SUPABASE_BUCKET).get_public_url("").rstrip("/")
        except Exception:
            pass

    def replacer(match):
        ts_str = match.group(1) or match.group(2)
        total_seconds = _parse_timestamp_str(ts_str)
        m = int(total_seconds // 60)
        s = int(total_seconds % 60)
        ts_str = f"{m:02d}-{s:02d}"
        filename = f"{task_id}_{ts_str}.jpg"
        screenshot_path = SCREENSHOTS_DIR / filename
        if screenshot_path.exists():
            if supabase_base:
                return f"![Screenshot at {m:02d}:{s:02d}]({supabase_base}/{filename})"
            return f"![Screenshot at {m:02d}:{s:02d}]({base_url}/{filename})"
        return match.group(0)

    return _SCREENSHOT_PATTERN.sub(replacer, markdown)


_CONTENT_LINK_PATTERN = re.compile(r'\*Content-\[(\d+(?::\d+){1,2})\]')

_PLATFORM_URL_TEMPLATES = {
    "bilibili": "https://www.bilibili.com/video/{video_id}?t={seconds}",
    "youtube": "https://www.youtube.com/watch?v={video_id}&t={seconds}s",
    "douyin": "https://www.douyin.com/video/{video_id}",
    "kuaishou": "https://www.kuaishou.com/short-video/{video_id}",
}


def _extract_video_id(url: str, platform: str) -> str:
    """Best-effort extraction of video ID from URL."""
    if platform == "bilibili":
        m = re.search(r'/(BV[\w]+)', url)
        return m.group(1) if m else ""
    elif platform == "youtube":
        m = re.search(r'(?:v=|youtu\.be/)([\w-]+)', url)
        return m.group(1) if m else ""
    elif platform == "douyin":
        m = re.search(r'/video/(\d+)', url)
        return m.group(1) if m else ""
    elif platform == "kuaishou":
        m = re.search(r'/short-video/([\w]+)', url)
        return m.group(1) if m else ""
    return ""


def replace_content_markers(
    markdown: str,
    video_url: str,
    platform: str,
) -> str:
    """Replace *Content-[mm:ss] markers with clickable links to the original video."""
    video_id = _extract_video_id(video_url, platform)
    url_template = _PLATFORM_URL_TEMPLATES.get(platform)

    def replacer(match):
        total_seconds = int(_parse_timestamp_str(match.group(1)))
        m = int(total_seconds // 60)
        s = int(total_seconds % 60)
        display = f"{m:02d}:{s:02d}"

        if url_template and video_id:
            link = url_template.format(video_id=video_id, seconds=total_seconds)
            return f"[▶ 原片 @ {display}]({link})"
        return f"[▶ {display}]"

    return _CONTENT_LINK_PATTERN.sub(replacer, markdown)


def get_video_duration(video_path: str) -> float:
    """Get the duration of a video file in seconds."""
    try:
        cmd = [
            FFMPEG_PATH, "-i", str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        match = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", result.stderr)
        if match:
            h, m, s, cs = match.groups()
            return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0
    except Exception:
        pass
    return 0.0


def extract_first_frame_thumbnail(video_path: str, task_id: str) -> Optional[str]:
    """
    Extract the first frame of a video as a thumbnail.
    Tries multiple seek positions and falls back to no-seek if needed.

    Returns:
        URL path to the thumbnail (e.g. /data/thumbnails/abc123.jpg), or None on failure.
    """
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        logger.error(f"Video file not found for thumbnail: {video_path}")
        return None

    # Skip audio-only files
    suffix = video_path_obj.suffix.lower()
    if suffix in ('.mp3', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.flac', '.wma'):
        logger.info(f"Skipping thumbnail extraction for audio file: {suffix}")
        return None

    filename = f"{task_id}.jpg"
    output_path = THUMBNAILS_DIR / filename

    if output_path.exists() and output_path.stat().st_size > 0:
        return f"/data/thumbnails/{filename}"

    # Try multiple seek positions: 1s, 0s (first frame), 3s
    for seek in ["00:00:01.000", "00:00:00.000", "00:00:03.000"]:
        try:
            cmd = [
                FFMPEG_PATH,
                "-ss", seek,
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                "-vf", "scale=640:-2",
                "-y",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"Extracted thumbnail for {task_id} at seek={seek}")
                if USE_SUPABASE_STORAGE:
                    public_url = _upload_to_supabase(output_path, _SUPABASE_THUMB_BUCKET, filename)
                    if public_url:
                        return public_url
                return f"/data/thumbnails/{filename}"
        except subprocess.TimeoutExpired:
            logger.warning(f"Thumbnail extraction timed out at seek={seek}")
        except Exception as e:
            logger.warning(f"Thumbnail extraction attempt failed at seek={seek}: {e}")

    # Clean up empty output file if any
    if output_path.exists() and output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)

    logger.warning(f"All thumbnail extraction attempts failed for {task_id}")
    return None


def extract_embedded_thumbnail(video_path: str, task_id: str) -> Optional[str]:
    """
    Extract embedded cover art / attached picture from a media file.

    Returns:
        URL path to the thumbnail (e.g. /data/thumbnails/abc123_cover.jpg), or None on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error(f"Video file not found for embedded thumbnail: {video_path}")
        return None

    filename = f"{task_id}_cover.jpg"
    output_path = THUMBNAILS_DIR / filename
    if output_path.exists() and output_path.stat().st_size > 0:
        return f"/data/thumbnails/{filename}"

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        data = json.loads(probe.stdout or "{}")
        streams = data.get("streams") or []
        attached_stream = next(
            (
                stream for stream in streams
                if stream.get("codec_type") == "video"
                and (stream.get("disposition") or {}).get("attached_pic") == 1
            ),
            None,
        )
        if not attached_stream:
            return None

        stream_index = attached_stream.get("index")
        if stream_index is None:
            return None

        cmd = [
            FFMPEG_PATH,
            "-i",
            str(video_path),
            "-map",
            f"0:{stream_index}",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            if USE_SUPABASE_STORAGE:
                _upload_to_supabase(output_path, _SUPABASE_THUMB_BUCKET, filename)
            logger.info(f"Extracted embedded cover thumbnail for {task_id}")
            return f"/data/thumbnails/{filename}"
    except Exception as e:
        logger.warning(f"Embedded thumbnail extraction failed for {task_id}: {e}")
    return None
