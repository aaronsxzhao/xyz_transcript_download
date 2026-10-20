"""Serve only generated images; cloud image URLs grant access to one file."""
import asyncio
import tempfile
from typing import Callable

import hashlib
import hmac
import os
import re
import secrets
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from fastapi import HTTPException

from config import DATA_DIR, GENERATED_MEDIA_RETENTION_DAYS, SUPABASE_SERVICE_KEY, SUPABASE_URL, USE_SUPABASE

_MEDIA_URL = re.compile(r"/data/(screenshots|thumbnails)/([a-zA-Z0-9_.-]+\.(?:jpg|jpeg|png|webp))(?:\?[^\s)\"'<>]*)?")


@lru_cache(maxsize=1)
def _signing_key() -> bytes:
    configured = os.getenv("MEDIA_SIGNING_KEY")
    if configured:
        return configured.encode()
    if SUPABASE_SERVICE_KEY:
        return hmac.new(SUPABASE_SERVICE_KEY.encode(), b"xyz-generated-media-v1", hashlib.sha256).digest()
    key_path = DATA_DIR / ".media-signing-key"
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return key_path.read_bytes()
    with os.fdopen(fd, "wb") as stream:
        key = secrets.token_bytes(32)
        stream.write(key)
    return key


def media_file(folder: str, filename: str) -> Path:
    if folder not in {"screenshots", "thumbnails"} or not re.fullmatch(r"[a-zA-Z0-9_.-]+\.(jpg|jpeg|png|webp)", filename):
        raise HTTPException(status_code=404, detail="File not found")
    root = (DATA_DIR / folder).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="File not found")
    return path


def _signature(path: str, expires: int) -> str:
    return hmac.new(_signing_key(), f"{path}:{expires}".encode(), hashlib.sha256).hexdigest()


def verify_media_signature(path: str, expires: int, signature: str) -> bool:
    return expires > time.time() and hmac.compare_digest(_signature(path, expires), signature)


def sign_media_urls(value, task_id: str = ""):
    """Sign only an owned task's generated files, never arbitrary Markdown paths."""
    if not USE_SUPABASE:
        return value
    if isinstance(value, dict):
        owner_task_id = task_id or value.get("id", "")
        return {key: sign_media_urls(item, owner_task_id) for key, item in value.items()}
    if isinstance(value, list):
        return [sign_media_urls(item, task_id) for item in value]
    if not isinstance(value, str) or not task_id:
        return value
    if SUPABASE_URL:
        # Old notes may still contain public Storage URLs. Serve them through the
        # same file-specific link after the buckets become private.
        base = SUPABASE_URL.rstrip('/') + '/storage/v1/object/public/'
        value = value.replace(base + 'screenshots/', '/data/screenshots/').replace(base + 'thumbnails/', '/data/thumbnails/')

    def replace(match):
        folder, filename = match.group(1, 2)
        if not (filename.startswith(task_id + "_") or filename == task_id + ".jpg"):
            return match.group(0)
        path = f"/data/{folder}/{filename}"
        # Matches generated media's existing retention window, including exports.
        expires = int(time.time() // 86400) * 86400 + max(GENERATED_MEDIA_RETENTION_DAYS, 2) * 86400
        return path + "?" + urlencode({"expires": expires, "signature": _signature(path, expires)})

    return _MEDIA_URL.sub(replace, value)


# Private bounded read-through cache. Files remain behind signature validation;
# this directory is never mounted as public static storage.
_MEDIA_CACHE_BYTES = 256 * 1024 * 1024
_MEDIA_CACHE_TTL = 86400
_downloads: dict[tuple[str, str], asyncio.Task] = {}


def _read_or_download(folder: str, filename: str, download: Callable[[str], bytes]) -> bytes:
    media_file(folder, filename)  # Validate even when called outside the HTTP route.
    directory = DATA_DIR / ".media-cache" / folder
    cached = directory / filename
    try:
        if time.time() - cached.stat().st_mtime < _MEDIA_CACHE_TTL:
            return cached.read_bytes()
    except OSError:
        pass
    content = download(filename)
    if not content:
        raise ValueError("Empty generated image")
    if len(content) > 16 * 1024 * 1024:
        return content
    temporary = None
    try:
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(cached)
        files = []
        for entry in (DATA_DIR / ".media-cache").glob("*/*"):
            try:
                stat = entry.stat()
                files.append((stat.st_mtime, stat.st_size, entry))
            except OSError:
                pass
        total = sum(size for _, size, _ in files)
        for modified, size, entry in sorted(files):
            if total <= _MEDIA_CACHE_BYTES and time.time() - modified < _MEDIA_CACHE_TTL:
                break
            try:
                entry.unlink(); total -= size
            except OSError:
                pass
    except OSError:
        # A full/unwritable disk must not prevent a successfully fetched image.
        pass
    finally:
        if temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return content


async def load_cloud_media(folder: str, filename: str, download: Callable[[str], bytes]) -> bytes:
    key = (folder, filename)
    task = _downloads.get(key)
    if task is None:
        task = asyncio.create_task(asyncio.to_thread(_read_or_download, folder, filename, download))
        _downloads[key] = task
        def completed(done):
            if _downloads.get(key) is done:
                _downloads.pop(key, None)
            if not done.cancelled():
                done.exception()  # Retrieve errors even when every HTTP waiter disconnected.
        task.add_done_callback(completed)
    return await asyncio.shield(task)
