"""Publish upload chunks only after the request has been read successfully."""
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile


def validated_upload_parts(session_dir: Path, total_chunks: int, expected_size: int) -> list[Path]:
    """Reject incomplete sessions before assembly can consume their chunks."""
    parts = sorted(session_dir.glob("*.part"))
    if not parts:
        raise HTTPException(status_code=400, detail="No uploaded chunks found")
    if total_chunks > 0 and (
        len(parts) != total_chunks or
        any(part.name != f"{index:06d}.part" for index, part in enumerate(parts))
    ):
        raise HTTPException(status_code=400, detail="Upload incomplete: missing or unexpected chunks")
    sizes = [part.stat().st_size for part in parts]
    if any(size <= 0 for size in sizes):
        raise HTTPException(status_code=400, detail="Uploaded chunk is empty")
    size = sum(sizes)
    if expected_size > 0 and size != expected_size:
        raise HTTPException(
            status_code=400,
            detail=f"Upload incomplete: expected {expected_size} bytes, received {size} bytes",
        )
    return parts


async def save_upload_chunk(chunk: UploadFile, part_path: Path) -> tuple[int, int]:
    """Return (new size, replaced size), leaving an earlier chunk intact on failure.

    Each request has its own temporary file so overlapping retries cannot write
    into the same inode. Publish and inspect the replaced size without an await
    between them; the caller can then update its byte count synchronously.
    """
    temporary_path = None
    size = 0
    try:
        try:
            with tempfile.NamedTemporaryFile(
                dir=part_path.parent, prefix=f".{part_path.name}.", suffix=".tmp", delete=False,
            ) as output:
                temporary_path = Path(output.name)
                while data := await chunk.read(1024 * 1024):
                    output.write(data)
                    size += len(data)
        finally:
            await chunk.close()

        if size <= 0:
            raise HTTPException(status_code=400, detail="Uploaded chunk is empty")
        previous_size = part_path.stat().st_size if part_path.exists() else 0
        os.replace(temporary_path, part_path)
        return size, previous_size
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
