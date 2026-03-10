"""Helpers for user-owned local media uploads."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Optional

from config import DATA_DIR

LOCAL_PODCAST_PID = "local_uploads"
LOCAL_PODCAST_TITLE = "Local Uploads"
LOCAL_PODCAST_AUTHOR = "You"
LOCAL_PODCAST_DESCRIPTION = "Audio files uploaded from your device."
LOCAL_VIDEO_CHANNEL = "Local Uploads"

LOCAL_AUDIO_DIR = DATA_DIR / "local_audio"
LOCAL_AUDIO_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".wav",
    ".aac",
    ".flac",
    ".ogg",
    ".opus",
    ".mp4",
    ".mpeg",
    ".mpga",
}

LOCAL_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
    ".flv",
    ".wmv",
    ".m4v",
}


def build_local_episode_url(eid: str) -> str:
    return f"local://{eid}"


def is_local_episode_url(value: str) -> bool:
    return bool(value) and value.startswith("local://")


def get_local_episode_id(value: str) -> str:
    return value.replace("local://", "", 1)


def make_local_episode_id() -> str:
    return f"local_{uuid.uuid4().hex[:16]}"


def owner_storage_key(user_id: Optional[str]) -> str:
    raw = (user_id or "local").strip() or "local"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)


def get_local_audio_dir(user_id: Optional[str]) -> Path:
    path = LOCAL_AUDIO_DIR / owner_storage_key(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
