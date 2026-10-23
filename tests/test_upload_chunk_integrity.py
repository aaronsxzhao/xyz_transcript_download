"""A failed/retried request must not corrupt an acknowledged upload chunk."""
import asyncio
import json

import pytest
from fastapi import HTTPException

from api.routers import podcasts, video_notes


@pytest.fixture(params=["audio", "video"])
def upload(request, monkeypatch, tmp_path):
    upload_id = "abcdef12-3456789"
    session = tmp_path / upload_id
    session.mkdir()
    meta_path = session / "meta.json"
    meta_path.write_text(json.dumps({
        "user_id": None, "total_chunks": 1, "size": 8,
        "received_chunks": [0], "received_bytes": 8,
    }))
    part = session / "000000.part"
    part.write_bytes(b"original")
    if request.param == "audio":
        monkeypatch.setattr(podcasts, "LOCAL_AUDIO_CHUNK_DIR", tmp_path)
        endpoint = podcasts.upload_local_audio_chunk
    else:
        monkeypatch.setattr(video_notes, "CHUNK_UPLOAD_DIR", tmp_path)
        endpoint = video_notes.upload_video_chunk
    return endpoint, upload_id, part, meta_path


class Chunk:
    def __init__(self, pieces):
        self.pieces = iter(pieces)
        self.closed = False

    async def read(self, size):
        value = next(self.pieces, b"")
        if isinstance(value, BaseException):
            raise value
        return value

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [OSError("connection lost"), asyncio.CancelledError()])
async def test_interrupted_retry_preserves_acknowledged_chunk(upload, failure):
    endpoint, upload_id, part, meta_path = upload
    before = meta_path.read_bytes()
    chunk = Chunk([b"partial", failure])
    with pytest.raises(type(failure)):
        await endpoint(upload_id=upload_id, index=0, chunk=chunk, user=None)
    assert part.read_bytes() == b"original"
    assert meta_path.read_bytes() == before
    assert sorted(p.name for p in part.parent.iterdir()) == ["000000.part", "meta.json"]
    assert chunk.closed


@pytest.mark.asyncio
async def test_empty_retry_preserves_acknowledged_chunk(upload):
    endpoint, upload_id, part, meta_path = upload
    before = meta_path.read_bytes()
    with pytest.raises(HTTPException) as error:
        await endpoint(upload_id=upload_id, index=0, chunk=Chunk([]), user=None)
    assert error.value.status_code == 400
    assert part.read_bytes() == b"original"
    assert meta_path.read_bytes() == before


@pytest.mark.asyncio
async def test_overlapping_retries_publish_whole_chunks_and_correct_byte_count(upload):
    endpoint, upload_id, part, meta_path = upload
    paused = asyncio.Event()
    resume = asyncio.Event()

    class SlowChunk(Chunk):
        async def read(self, size):
            if not paused.is_set():
                paused.set()
                await resume.wait()
            return await super().read(size)

    slow = asyncio.create_task(endpoint(
        upload_id=upload_id, index=0, chunk=SlowChunk([b"last"]), user=None,
    ))
    await paused.wait()
    try:
        assert part.read_bytes() == b"original"
        await endpoint(upload_id=upload_id, index=0, chunk=Chunk([b"first retry"]), user=None)
        assert part.read_bytes() == b"first retry"
    finally:
        resume.set()
        await slow
    assert part.read_bytes() == b"last"
    meta = json.loads(meta_path.read_text())
    assert meta["received_chunks"] == [0]
    assert meta["received_bytes"] == 4
