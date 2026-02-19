"""
Multimodal video understanding via grid-based frame extraction and GPT vision analysis.
Extracts frames at intervals, assembles into grids, and sends to a vision-capable LLM.
"""

import base64
import io
import math
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from config import DATA_DIR, LLM_API_KEY, LLM_BASE_URL
from logger import get_logger

logger = get_logger("video_understanding")

GRIDS_DIR = DATA_DIR / "grids"
GRIDS_DIR.mkdir(parents=True, exist_ok=True)

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    import shutil
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"


def extract_frames(
    video_path: str,
    interval: int = 4,
    max_frames: int = 200,
) -> List[Tuple[float, Path]]:
    """
    Extract frames from a video at regular intervals.

    Args:
        video_path: Path to video file.
        interval: Seconds between frames.
        max_frames: Maximum number of frames to extract.

    Returns:
        List of (timestamp_seconds, frame_path) tuples.
    """
    from screenshot_extractor import get_video_duration

    duration = get_video_duration(video_path)
    if duration <= 0:
        logger.error(f"Could not determine video duration: {video_path}")
        return []

    frames_dir = GRIDS_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)

    timestamps = []
    t = 0.0
    while t < duration and len(timestamps) < max_frames:
        timestamps.append(t)
        t += interval

    results = []
    for ts in timestamps:
        h = int(ts // 3600)
        m = int((ts % 3600) // 60)
        s = ts % 60
        ts_str = f"{h:02d}:{m:02d}:{s:06.3f}"
        frame_name = f"frame_{int(ts)}.jpg"
        frame_path = frames_dir / frame_name

        if not frame_path.exists():
            try:
                cmd = [
                    FFMPEG_PATH,
                    "-ss", ts_str,
                    "-i", str(video_path),
                    "-frames:v", "1",
                    "-q:v", "3",
                    "-y",
                    str(frame_path),
                ]
                subprocess.run(cmd, capture_output=True, timeout=15)
            except Exception:
                continue

        if frame_path.exists():
            results.append((ts, frame_path))

    return results


def create_grid_image(
    frames: List[Tuple[float, Path]],
    grid_cols: int = 3,
    grid_rows: int = 3,
    cell_width: int = 320,
    cell_height: int = 240,
    task_id: str = "",
    grid_index: int = 0,
) -> Optional[Path]:
    """
    Assemble frames into a grid image with timestamp labels.

    Args:
        frames: List of (timestamp, frame_path) tuples.
        grid_cols: Number of columns in the grid.
        grid_rows: Number of rows in the grid.
        cell_width: Width of each cell in pixels.
        cell_height: Height of each cell in pixels.
        task_id: Task identifier for filename.
        grid_index: Grid index for filename.

    Returns:
        Path to the saved grid image, or None on failure.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow is required for grid image creation")
        return None

    label_height = 24
    total_cell_h = cell_height + label_height
    canvas_w = grid_cols * cell_width
    canvas_h = grid_rows * total_cell_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 30))
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    for idx, (ts, frame_path) in enumerate(frames):
        if idx >= grid_cols * grid_rows:
            break
        row = idx // grid_cols
        col = idx % grid_cols
        x = col * cell_width
        y = row * total_cell_h

        try:
            img = Image.open(frame_path)
            img = img.resize((cell_width, cell_height), Image.LANCZOS)
            canvas.paste(img, (x, y))
        except Exception:
            continue

        m = int(ts // 60)
        s = int(ts % 60)
        label = f"{m:02d}:{s:02d}"
        draw.rectangle([x, y + cell_height, x + cell_width, y + total_cell_h], fill=(0, 0, 0))
        draw.text((x + 5, y + cell_height + 4), label, fill=(255, 255, 255), font=font)

    output_path = GRIDS_DIR / f"{task_id}_grid_{grid_index}.jpg"
    canvas.save(output_path, "JPEG", quality=85)
    return output_path


def extract_frame_grids(
    video_path: str,
    task_id: str,
    interval: int = 4,
    grid_cols: int = 3,
    grid_rows: int = 3,
) -> List[Path]:
    """
    Extract frames and create grid images from a video.

    Returns:
        List of paths to grid images.
    """
    cells_per_grid = grid_cols * grid_rows
    frames = extract_frames(video_path, interval)
    if not frames:
        return []

    grids = []
    for i in range(0, len(frames), cells_per_grid):
        batch = frames[i:i + cells_per_grid]
        grid_path = create_grid_image(
            batch,
            grid_cols=grid_cols,
            grid_rows=grid_rows,
            task_id=task_id,
            grid_index=i // cells_per_grid,
        )
        if grid_path:
            grids.append(grid_path)

    return grids


def _image_to_base64(image_path: Path) -> str:
    """Convert an image file to base64 string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_grids(
    grid_paths: List[Path],
    title: str = "",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> str:
    """
    Send grid images to a vision-capable LLM for analysis.

    Args:
        grid_paths: List of grid image paths.
        title: Video title for context.
        api_key: LLM API key.
        base_url: LLM API base URL.
        model: Vision model to use.

    Returns:
        Visual understanding text from the LLM.
    """
    from openai import OpenAI

    api_key = api_key or LLM_API_KEY
    base_url = base_url or LLM_BASE_URL
    model = model or "gpt-4o"

    if not api_key:
        logger.error("No API key for vision analysis")
        return ""

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    content_parts = [
        {
            "type": "text",
            "text": (
                f"以下是视频「{title}」的截帧画面网格图。每个小格右下角标注了对应时间戳。\n"
                "请根据这些画面，描述视频的主要视觉内容、场景变化、关键画面信息。"
                "尽量覆盖所有时间段，关注文字、图表、人物表情和动作变化。\n"
                "请用中文回答。"
            ),
        }
    ]

    for grid_path in grid_paths[:5]:
        b64 = _image_to_base64(grid_path)
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64}",
                "detail": "low",
            },
        })

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content_parts}],
            max_tokens=2000,
            temperature=0.3,
        )
        result = response.choices[0].message.content or ""
        logger.info(f"Vision analysis completed: {len(result)} chars")
        return result
    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return ""
