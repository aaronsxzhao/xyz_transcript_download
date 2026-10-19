"""Large notes remain lightweight until transcripts/history are requested."""
import json
import threading
from unittest.mock import Mock, patch
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_note_load_excludes_large_transcript_and_historical_content(client):
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    task_id = db.create_task({"user_id": "local", "url": "fixture://large-note", "platform": "youtube"})
    transcript = {"text": "Synthetic transcript " * 20000, "duration": 30000,
                  "segments": [{"start": i * 4, "end": i * 4 + 4, "text": f"Segment {i} content"} for i in range(7555)]}
    db.update_task(task_id, {"markdown": "# Latest note\n" * 100, "transcript_json": json.dumps(transcript)})
    versions = [db.add_version(task_id, "Historical note " * 4000) for _ in range(4)]
    full = await client.get(f"/api/video-notes/tasks/{task_id}")
    compact = await client.get(f"/api/video-notes/tasks/{task_id}?view=note")
    assert full.status_code == compact.status_code == 200
    assert len(compact.content) < len(full.content) * 0.05
    assert compact.json()["markdown"] == full.json()["markdown"]
    assert compact.json().get("transcript") is None
    assert all("content" not in version for version in compact.json()["versions"])
    assert (await client.get(f"/api/video-notes/tasks/{task_id}/transcript")).json()["transcript"] == transcript
    saved = await client.get(f"/api/video-notes/tasks/{task_id}/versions/{versions[0]}")
    assert saved.json()["content"] == "Historical note " * 4000


@pytest.mark.asyncio
async def test_lazy_note_endpoints_enforce_task_and_version_ownership(client, app):
    from api.auth import get_current_user, User
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    first = db.create_task({"user_id": "local", "url": "fixture://first"})
    second = db.create_task({"user_id": "local", "url": "fixture://second"})
    version = db.add_version(second, "Private second version")
    assert (await client.get(f"/api/video-notes/tasks/{first}/versions/{version}")).status_code == 404
    app.dependency_overrides[get_current_user] = lambda: User(id="different-user", email="other@example.com")
    try:
        for suffix in ("?view=note", "/transcript", f"/versions/{version}"):
            assert (await client.get(f"/api/video-notes/tasks/{second}{suffix}")).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_cloud_task_cache_does_not_expose_another_accounts_note():
    from video_task_db import _SupabaseVideoTaskDB
    db = _SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    db._lock = threading.Lock()
    db._cache = {"private": {"id": "private", "user_id": "owner-a", "markdown": "Secret note", "transcript_json": "{}"}}
    db._sb = Mock()
    db._sb.get_video_task.return_value = None
    assert db.get_task("private", "owner-b") is None
    assert db.get_task("private", "owner-b", include_transcript=False) is None
    assert db.get_task("private", "owner-a")["markdown"] == "Secret note"


def test_queue_cache_merges_only_list_metadata():
    from video_task_db import _SupabaseVideoTaskDB
    db = _SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    db._lock = threading.Lock()
    db._dirty = {}
    db._cache = {"active": {"id": "active", "user_id": "owner", "status": "summarizing", "markdown": "Large note", "transcript_json": json.dumps({"text": "Large transcript"})}}
    rows = db._merge_cached_task_list([], user_id="owner", limit=10)
    assert len(rows) == 1
    assert not rows[0].get("transcript")
    assert not rows[0].get("markdown")


@pytest.mark.asyncio
async def test_episode_page_never_loads_all_library_summaries(client, create_test_podcast, create_test_episode):
    create_test_podcast()
    create_test_episode()
    with patch("api.db.DatabaseInterface.get_all_summaries", side_effect=AssertionError("Page must not read every summary")):
        response = await client.get("/api/podcasts/test-podcast-123/episodes")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_sqlite_channel_list_never_contains_note_or_transcript_text(tmp_path):
    from video_task_db import VideoTaskDB
    db = VideoTaskDB(tmp_path / "library.db")
    task_id = db.create_task({"user_id": "owner", "url": "fixture://video", "channel": "Channel", "platform": "youtube"})
    db.update_task(task_id, {"markdown": "Large note", "transcript_json": '{"text":"Large transcript"}'})
    for rows in (db.list_tasks("owner"), db.list_tasks_by_channel("Channel", "youtube", "owner")):
        assert len(rows) == 1
        assert "Large transcript" not in str(rows)
        assert "Large note" not in str(rows)


def test_cloud_episode_annotations_are_page_scoped_and_use_counts():
    from api.supabase_db import SupabaseDatabase
    db = SupabaseDatabase.__new__(SupabaseDatabase)
    transcripts, summaries = Mock(), Mock()
    for query in (transcripts, summaries):
        query.select.return_value = query.eq.return_value = query.in_.return_value = query
    transcripts.execute.return_value = SimpleNamespace(data=[{"episode_id": "visible"}])
    summaries.execute.return_value = SimpleNamespace(data=[{"episode_id": "visible", "topics": ["Topic"], "summary_key_points": [{"count": 55}]}])
    db.client = Mock()
    db.client.table.side_effect = lambda table: transcripts if table == "transcripts" else summaries
    result = db.get_episode_annotations("owner", ["visible"])
    assert result["visible"] == {"has_transcript": True, "has_summary": True, "topics_count": 1, "key_points_count": 55}
    for query in (transcripts, summaries):
        query.eq.assert_called_once_with("user_id", "owner")
        query.in_.assert_called_once_with("episode_id", ["visible"])
