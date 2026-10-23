"""Publish upload chunks only after the request has been read successfully."""
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile


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
