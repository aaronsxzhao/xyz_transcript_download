"""An incomplete finalization must leave acknowledged chunks available to retry."""
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import local_media
from api.routers import podcasts, video_notes


@pytest.fixture(params=["audio", "video"])
def finalization(request, monkeypatch, tmp_path, db_interface):
    upload_id = "abcdef12-3456789"
    session = tmp_path / upload_id
    session.mkdir()
    output = tmp_path / "saved"
    output.mkdir()
    metadata = {"user_id": None, "filename": "sample.mp3" if request.param == "audio" else "sample.mp4",
                "ext": ".mp3" if request.param == "audio" else ".mp4", "total_chunks": 2,
                "size": 16, "received_chunks": [0], "received_bytes": 8, "phase": "uploading"}
    meta = session / "meta.json"
    meta.write_text(json.dumps(metadata))
    part = session / "000000.part"
    part.write_bytes(b"original")
    if request.param == "audio":
        monkeypatch.setattr(podcasts, "LOCAL_AUDIO_CHUNK_DIR", tmp_path)
        monkeypatch.setattr(podcasts, "get_local_audio_dir", lambda _: output)
        monkeypatch.setattr(podcasts, "get_db", lambda _: db_interface)
        monkeypatch.setattr(podcasts, "_get_media_duration_seconds", lambda _: 12)
    else:
        monkeypatch.setattr(video_notes, "CHUNK_UPLOAD_DIR", tmp_path)
        monkeypatch.setattr(local_media, "get_local_video_dir", lambda _: output)

    async def complete():
        if request.param == "audio":
            return await podcasts.complete_chunked_audio_upload(upload_id=upload_id, title="", description="", user=None)
        return video_notes.complete_chunked_upload(upload_id=upload_id, user=None)

    return complete, part, meta, output


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing_chunk", "wrong_size", "wrong_index", "empty_chunk"])
async def test_incomplete_finalization_preserves_chunks_and_session(finalization, invalid):
    complete, part, meta, output = finalization
    if invalid == "wrong_size":
        data = json.loads(meta.read_text())
        data["total_chunks"] = 1
        meta.write_text(json.dumps(data))
    elif invalid == "wrong_index":
        (part.parent / "000002.part").write_bytes(b"second!!")
    elif invalid == "empty_chunk":
        (part.parent / "000001.part").touch()
    before = meta.read_bytes()
    with pytest.raises(HTTPException) as error:
        await complete()
    assert error.value.status_code == 400
    assert part.exists(), "Rejected finalization must not destroy acknowledged chunks"
    assert part.read_bytes() == b"original"
    assert meta.read_bytes() == before
    assert list(output.iterdir()) == []


@pytest.mark.asyncio
async def test_missing_chunk_can_be_supplied_and_finalized_without_reuploading_the_first(finalization):
    complete, part, meta, output = finalization
    with pytest.raises(HTTPException) as error:
        await complete()
    assert error.value.status_code == 400
    (part.parent / "000001.part").write_bytes(b"second!!")
    result = await complete()
    path = Path(result.episode.audio_url if hasattr(result, "episode") else result["path"])
    assert path.read_bytes() == b"originalsecond!!"
    assert not part.exists()
    assert list(output.iterdir()) == [path]
