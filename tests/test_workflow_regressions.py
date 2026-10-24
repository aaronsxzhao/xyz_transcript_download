"""Cover the retry, preservation, discovery, and pagination failures from review."""
import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.schemas import ProcessingStatus


@pytest.mark.asyncio
async def test_retried_job_is_visible_and_cancellable_by_its_owner(client, create_test_podcast, create_test_episode):
    from api.routers import processing
    create_test_podcast()
    create_test_episode()
    processing.jobs["old-job"] = ProcessingStatus(job_id="old-job", user_id="local", status="failed", episode_id="test-episode-456")
    response = await client.post("/api/jobs/old-job/retry")
    assert response.status_code == 200
    job_id = response.json()["new_job_id"]
    job = await client.get(f"/api/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["user_id"] == "local"
    assert (await client.post(f"/api/jobs/{job_id}/cancel")).status_code == 200


@pytest.mark.asyncio
async def test_regeneration_preserves_the_previous_summary_and_owner(client, create_test_podcast, create_test_episode, create_test_transcript, create_test_summary):
    from api.routers import processing
    create_test_podcast()
    create_test_episode()
    create_test_transcript()
    previous = create_test_summary()
    response = await client.post("/api/episodes/test-episode-456/resummarize", json={})
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    assert (await client.get(f"/api/jobs/{job_id}")).json()["user_id"] == "local"
    processing.process_episode_async.assert_awaited_once()
    assert processing.process_episode_async.call_args.kwargs["resummarize"] is True
    processing.jobs[job_id].status = "failed"
    assert (await client.get("/api/summaries/test-episode-456")).json()["overview"] == previous["overview"]


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel", "transcribe-only"])
def test_reusing_a_transcript_needs_no_audio_and_preserves_failures(outcome, db_interface, create_test_podcast, create_test_episode, sample_transcript_data, sample_summary_data):
    from api.db import TranscriptData, SummaryData
    from api.routers import processing
    from summarizer import Summary, KeyPoint
    create_test_podcast()
    create_test_episode()
    transcript = TranscriptData(**{**sample_transcript_data,"text":sample_transcript_data["text"] * 10})
    previous = SummaryData(**sample_summary_data)
    db_interface.save_transcript(transcript)
    db_interface.save_summary(previous)
    job_id = "reuse-" + outcome
    processing.jobs[job_id] = ProcessingStatus(job_id=job_id, user_id="local", status="pending")
    summarizer = Mock()
    summarizer.summarize.return_value = Summary(previous.episode_id, "New title", "New overview", [KeyPoint("Topic", "Point", "", "")], [], [])
    if outcome == "failure":
        summarizer.summarize.return_value = None
    elif outcome == "cancel":
        def cancel(*args, **kwargs):
            processing.cancelled_jobs.add(job_id)
            kwargs["progress_callback"](100)
        summarizer.summarize.side_effect = cancel
    try:
        with patch.object(processing, "get_db", return_value=db_interface), \
             patch("api.user_settings.get_user_settings", return_value={}), \
             patch("downloader.get_downloader", side_effect=AssertionError("No audio should be downloaded")), \
             patch("summarizer.get_summarizer", return_value=summarizer), \
             patch("transcriber.get_transcriber") as transcriber, \
             patch.object(processing, "notify_discord"):
            processing.process_episode_sync(job_id, "local://test-episode-456", transcribe_only=outcome == "transcribe-only", user_id="local", resummarize=True)
        assert processing.jobs[job_id].status == {"success": "completed", "failure": "failed", "cancel": "cancelled", "transcribe-only": "completed"}[outcome]
        assert db_interface.get_summary(previous.episode_id).overview == ("New overview" if outcome == "success" else previous.overview)
        transcriber.assert_not_called()
        if outcome == "transcribe-only":
            summarizer.summarize.assert_not_called()
    finally:
        processing.jobs.pop(job_id, None)
        processing.cancelled_jobs.discard(job_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('platform',['apple','spotify'])
async def test_global_updates_use_apple_feed_and_skip_local_uploads(platform):
    from api.main import _scan_podcasts_for_new_episodes
    db = Mock()
    db.get_all_podcasts.return_value = [
        SimpleNamespace(pid="apple-show", title="Apple", platform=platform, feed_url="https://example.com/feed.xml"),
        SimpleNamespace(pid="local_uploads", title="Local", platform="local"),
    ]
    with patch("apple_podcasts_client.get_episodes_from_feed", return_value=[]) as feed, patch("xyz_client.get_client") as xyz:
        assert await _scan_podcasts_for_new_episodes(db) == (0, [])
    feed.assert_called_once_with("https://example.com/feed.xml", "apple-show", 50)
    xyz.assert_not_called()


@pytest.mark.asyncio
async def test_scheduled_cloud_updates_scan_each_subscription_owner():
    import api.main as main
    provider = Mock()
    provider.get_subscription_user_ids.return_value = ["owner-a", "owner-b"]
    try:
        with patch("config.USE_SUPABASE", True), patch("api.supabase_db.get_supabase_database", return_value=provider), \
             patch("api.db.get_db", side_effect=lambda owner: owner), \
             patch.object(main, "_scan_podcasts_for_new_episodes", AsyncMock(side_effect=[(1, [{"eid": "a"}]), (1, [{"eid": "b"}])])) as scan:
            await main.check_subscription_owners()
        assert scan.call_args_list[0].args[0] == "owner-a"
        assert scan.call_args_list[1].args[0] == "owner-b"
        assert main._new_episodes_cache["owner-a"]["episodes"] == [{"eid": "a"}]
        assert main._new_episodes_cache["owner-b"]["episodes"] == [{"eid": "b"}]
    finally:
        main._new_episodes_cache.clear()


@pytest.mark.asyncio
async def test_episode_pages_cover_all_stored_episodes(client, create_test_podcast, create_test_episode):
    create_test_podcast()
    for i in range(60):
        create_test_episode(override={"eid": f"episode-{i}"})
    first = await client.get("/api/podcasts/test-podcast-123/episodes")
    second = await client.get("/api/podcasts/test-podcast-123/episodes?offset=50&limit=50")
    first_ids = {ep["eid"] for ep in first.json()}
    second_ids = {ep["eid"] for ep in second.json()}
    assert len(first_ids) == 50 and len(second_ids) == 10
    assert not first_ids & second_ids
    assert len(first_ids | second_ids) == 60
    assert all(ep["status"] == "pending" for ep in first.json())
    assert (await client.get("/api/podcasts/test-podcast-123/episodes?offset=-1")).status_code == 422
    assert (await client.get("/api/podcasts/test-podcast-123/episodes?limit=0")).status_code == 422


@pytest.mark.asyncio
async def test_channels_without_thumbnails_still_load(client):
    from video_task_db import get_video_task_db
    get_video_task_db().create_task({"user_id": "local", "channel": "Fixture channel", "platform": "youtube", "url": "fixture://video"})
    response = await client.get("/api/video-notes/channels")
    assert response.status_code == 200
    assert response.json()["channels"][0]["channel"] == "Fixture channel"


@pytest.mark.asyncio
async def test_cancel_then_retry_does_not_cancel_or_overwrite_the_new_video_run(client):
    from api.routers import video_notes
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    task_id = db.create_task({"user_id": "local", "url": "fixture://video", "platform": "youtube",
                              "title": "Fixture", "thumbnail": "https://example.com/thumb.jpg", "formats": ["summary"]})
    db.update_task(task_id, {"transcript_json": json.dumps({"text": "A saved transcript. " * 10, "segments": []}), "markdown": "Previous note"})
    db.add_version(task_id, "Previous note")
    started, release = threading.Event(), threading.Event()
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            started.set()
            if not release.wait(5):
                raise TimeoutError("Test retry was not queued")
            kwargs["progress_callback"](100, "Superseded partial note")
            return "Superseded note"
        return "Replacement note"
    summarizer = Mock()
    summarizer.generate_note.side_effect = generate
    attempt = video_notes._new_video_attempt(task_id)
    with patch("note_summarizer.get_note_summarizer", return_value=summarizer):
        first = asyncio.create_task(video_notes.process_video_note_async(task_id, url="fixture://video", platform="youtube", style="detailed",
            formats=["summary"], quality="medium", llm_model="test", extras="", video_understanding=False,
            video_interval=4, grid_cols=3, grid_rows=3, user_id="local", attempt_id=attempt))
        try:
            assert await asyncio.to_thread(started.wait, 3)
            assert (await client.post(f"/api/video-notes/tasks/{task_id}/cancel")).status_code == 200
            retry = asyncio.create_task(client.post(f"/api/video-notes/tasks/{task_id}/retry", json={}))
            for _ in range(100):
                if video_notes._video_attempts[task_id] > attempt:
                    break
                await asyncio.sleep(0.01)
            assert video_notes._video_attempts[task_id] > attempt
        finally:
            release.set()
        await first
        assert (await retry).status_code == 200
        # Submission now acknowledges queue admission before media work ends.
        await asyncio.gather(*list(video_notes._video_workers))
    task = db.get_task(task_id, "local")
    assert task["status"] == "success"
    assert task["markdown"] == "Replacement note"
    assert {version["content"] for version in db.get_versions(task_id)} == {"Previous note", "Replacement note"}
    assert len(calls) == 2


@pytest.mark.parametrize('transcribe_only', [False, True])
def test_failed_transcript_save_cannot_report_completion_or_generate_a_summary(
    transcribe_only, db_interface, create_test_podcast, create_test_episode, sample_transcript_data, monkeypatch,
):
    from api.routers import processing
    from transcriber import Transcript
    create_test_podcast()
    create_test_episode()
    source = Transcript(sample_transcript_data['episode_id'], 'en', 3600, sample_transcript_data['text'] * 10, [])
    engine = Mock()
    engine.transcribe.return_value = source
    job_id = 'failed-source-save-' + str(transcribe_only)
    processing.jobs[job_id] = ProcessingStatus(job_id=job_id, user_id='local', status='pending')
    monkeypatch.setattr(db_interface, 'save_transcript', Mock(return_value=False))
    try:
        with patch.object(processing, 'get_db', return_value=db_interface), \
             patch('api.user_settings.get_user_settings', return_value={}), \
             patch('config.WHISPER_MODE', 'api'), \
             patch('downloader.get_downloader') as downloader, \
             patch('transcriber.get_transcriber', return_value=engine), \
             patch('summarizer.get_summarizer') as summarizer, \
             patch.object(processing, 'notify_discord') as notify:
            downloader.return_value.download.return_value = 'fixture-audio'
            from summarizer import Summary, KeyPoint
            summarizer.return_value.summarize.return_value = Summary(
                source.episode_id, 'New note', 'Overview', [KeyPoint('Topic', 'Detail', 'test transcript', '')], ['Topic'], [])
            processing.process_episode_sync(job_id, 'local://test-episode-456', transcribe_only=transcribe_only, user_id='local')
        assert processing.jobs[job_id].status == 'failed'
        assert 'save' in processing.jobs[job_id].message.lower()
        summarizer.assert_not_called()
        notify.assert_not_called()
    finally:
        processing.jobs.pop(job_id, None)
