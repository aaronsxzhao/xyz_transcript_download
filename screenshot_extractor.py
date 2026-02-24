"""
Screenshot extraction from videos using FFmpeg.
Supports single frame extraction and batch extraction at timestamps.
When USE_SUPABASE is enabled, screenshots are uploaded to Supabase Storage
so they remain accessible regardless of which server processed the video.
"""

import re
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from config import DATA_DIR, USE_SUPABASE
from logger import get_logger

logger = get_logger("screenshot_extractor")

SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

THUMBNAILS_DIR = DATA_DIR / "thumbnails"
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

_SUPABASE_BUCKET = "screenshots"
_SUPABASE_THUMB_BUCKET = "thumbnails"


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
    if not USE_SUPABASE:
        return None
    try:
        from api.supabase_client import get_supabase_admin_client
        client = get_supabase_admin_client()
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
        cmd = [
            FFMPEG_PATH,
            "-ss", _format_timestamp(timestamp),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            "-y",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode == 0 and output_path.exists():
            if USE_SUPABASE:
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
    for ts in timestamps:
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
_SCREENSHOT_PATTERN = re.compile(r'`?\*?Screenshot-\[(\d+(?::\d+){1,2})\]\*?`?')


def extract_timestamps_from_markdown(markdown: str) -> List[float]:
    """Parse Screenshot-[timestamp] markers from generated markdown and return timestamps."""
    timestamps = []
    for match in _SCREENSHOT_PATTERN.finditer(markdown):
        timestamps.append(_parse_timestamp_str(match.group(1)))
    return timestamps


def replace_screenshot_markers(
    markdown: str,
    task_id: str,
    base_url: str = "/data/screenshots",
) -> str:
    """Replace Screenshot-[timestamp] markers in markdown with actual image tags.

    In Supabase mode, uses public Supabase Storage URLs so screenshots
    are accessible regardless of which server processed the video.
    """
    supabase_base = None
    if USE_SUPABASE:
        try:
            from api.supabase_client import get_supabase_admin_client
            client = get_supabase_admin_client()
            if client:
                supabase_base = client.storage.from_(_SUPABASE_BUCKET).get_public_url("").rstrip("/")
        except Exception:
            pass

    def replacer(match):
        total_seconds = _parse_timestamp_str(match.group(1))
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
                if USE_SUPABASE:
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
