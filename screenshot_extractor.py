"""
Screenshot extraction from videos using FFmpeg.
Supports single frame extraction and batch extraction at timestamps.
"""

import re
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from config import DATA_DIR
from logger import get_logger

logger = get_logger("screenshot_extractor")

SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

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


def extract_timestamps_from_markdown(markdown: str) -> List[float]:
    """
    Parse *Screenshot-[mm:ss] markers from generated markdown and return timestamps.
    """
    pattern = r'\*Screenshot-\[(\d+):(\d+)\]'
    timestamps = []
    for match in re.finditer(pattern, markdown):
        minutes, seconds = int(match.group(1)), int(match.group(2))
        timestamps.append(minutes * 60 + seconds)
    return timestamps


def replace_screenshot_markers(
    markdown: str,
    task_id: str,
    base_url: str = "/data/screenshots",
) -> str:
    """
    Replace *Screenshot-[mm:ss] markers in markdown with actual image tags.
    """
    def replacer(match):
        minutes, seconds = int(match.group(1)), int(match.group(2))
        ts_str = f"{minutes:02d}-{seconds:02d}"
        filename = f"{task_id}_{ts_str}.jpg"
        screenshot_path = SCREENSHOTS_DIR / filename
        if screenshot_path.exists():
            return f"![Screenshot at {minutes:02d}:{seconds:02d}]({base_url}/{filename})"
        return match.group(0)

    pattern = r'\*Screenshot-\[(\d+):(\d+)\]'
    return re.sub(pattern, replacer, markdown)


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
