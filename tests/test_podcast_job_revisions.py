"""A job snapshot has the same ordering version in HTTP, WS and persistence."""
import json
from unittest.mock import AsyncMock

import pytest

from api.routers import processing
from api.schemas import ProcessingStatus


@pytest.mark.asyncio
async def test_status_revision_survives_http_websocket_and_saved_history(client, monkeypatch, tmp_path):
    monkeypatch.setattr(processing, "JOBS_FILE", tmp_path / "jobs.json")
    job = ProcessingStatus(job_id="revision-job", user_id="local", status="pending")
    monkeypatch.setattr(processing, "jobs", {job.job_id:job})
    monkeypatch.setattr(processing, "get_main_loop", lambda: None)
    broadcast = AsyncMock()
    monkeypatch.setattr(processing.manager, "broadcast_to_user", broadcast)
    processing.update_job_status(job.job_id, "transcribing", 40, "Working")
    older = (await client.get(f"/api/jobs/{job.job_id}")).json()
    processing.update_job_status(job.job_id, "completed", 100, "Done")
    newer = (await client.get(f"/api/jobs/{job.job_id}")).json()
    assert newer.get("revision", 0) > older.get("revision", 0) > 0
    await processing.broadcast_status(job.job_id)
    payload = broadcast.call_args.args[0]["job"]
    saved = json.loads((tmp_path / "jobs.json").read_text())[job.job_id]
    assert payload["revision"] == saved["revision"] == newer["revision"]


def test_restart_failure_is_newer_than_saved_in_progress_status(monkeypatch, tmp_path):
    from api import schemas
    monkeypatch.setattr(schemas.time, "time_ns", lambda: 20000)
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"interrupted":{
        "job_id":"interrupted", "user_id":"local", "status":"transcribing", "revision":12,
    }}))
    monkeypatch.setattr(processing, "JOBS_FILE", path)
    monkeypatch.setattr(processing, "jobs", {})
    processing._load_jobs_from_file()
    recovered = processing.jobs["interrupted"].model_dump()
    assert recovered["status"] == "failed"
    # The tab may have seen revision 19 after the last durable checkpoint (12).
    assert recovered.get("revision", 0) > 19


def test_job_revisions_still_advance_if_the_clock_moves_backwards(monkeypatch):
    from api import schemas
    monkeypatch.setattr(schemas.time, "time_ns", lambda: 1000)
    job = ProcessingStatus(job_id="clock", status="pending", revision=20)
    job.advance_revision()
    assert job.revision == 21
