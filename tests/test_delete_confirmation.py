"""A rejected primary deletion must not report success or destroy related files."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.routers import episodes, podcasts, summaries, transcripts


@pytest.mark.asyncio
@pytest.mark.parametrize('router,path,lookup,remove', [
    (podcasts, '/api/podcasts/confirmation-show', 'get_podcast', 'delete_podcast'),
    (episodes, '/api/episodes/confirmation-episode', 'get_episode', 'delete_episode'),
    (transcripts, '/api/transcripts/confirmation-episode', 'has_transcript', 'delete_transcript'),
    (summaries, '/api/summaries/confirmation-episode', 'has_summary', 'delete_summary'),
])
async def test_rejected_delete_is_not_a_success(client, monkeypatch, tmp_path, router, path, lookup, remove):
    audio = tmp_path / 'uploads' / 'recording.mp3'
    audio.parent.mkdir()
    audio.write_bytes(b'original audio')
    fast = audio.with_name('recording_fast.mp3')
    fast.write_bytes(b'fast audio')
    record = SimpleNamespace(eid='confirmation-episode', pid=episodes.LOCAL_PODCAST_PID,
                             title='Confirmation show', audio_url=str(audio))
    db = Mock()
    getattr(db, lookup).return_value = record
    getattr(db, remove).return_value = False
    monkeypatch.setattr(router, 'get_db', lambda owner: db)
    monkeypatch.setattr(episodes, 'DATA_DIR', tmp_path)
    response = await client.delete(path)
    assert response.status_code == 503
    assert 'confirm' in response.json()['detail'].lower()
    if router is episodes:
        db.delete_transcript.assert_not_called()
        db.delete_summary.assert_not_called()
    assert audio.read_bytes() == b'original audio'
    assert fast.read_bytes() == b'fast audio'


@pytest.mark.asyncio
async def test_confirmed_episode_delete_tolerates_cascaded_children(client, monkeypatch, tmp_path):
    audio = tmp_path / 'recording.mp3'
    audio.write_bytes(b'original audio')
    fast = audio.with_name('recording_fast.mp3')
    fast.write_bytes(b'fast audio')
    db = Mock()
    db.get_episode.return_value = SimpleNamespace(eid='confirmation-episode', pid=episodes.LOCAL_PODCAST_PID,
                                                 title='Confirmation show', audio_url=str(audio))
    db.delete_episode.return_value = True
    # A cloud foreign-key cascade can already have removed these records.
    db.delete_transcript.return_value = False
    db.delete_summary.return_value = False
    monkeypatch.setattr(episodes, 'get_db', lambda owner: db)
    monkeypatch.setattr(episodes, 'DATA_DIR', tmp_path)
    response = await client.delete('/api/episodes/confirmation-episode')
    assert response.status_code == 200
    assert not audio.exists() and not fast.exists()
