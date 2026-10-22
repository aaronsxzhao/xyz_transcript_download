"""Submitting a job must not wait for provider metadata fetched by its worker."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import BackgroundTasks

from api.routers import processing
from api.schemas import ProcessRequest


@pytest.fixture
def admission(monkeypatch):
    db = Mock()
    db.get_episode.return_value = None
    provider = Mock()
    provider.get_episode_by_share_url.side_effect = AssertionError('Provider fetch belongs in the worker')
    get_db = Mock(return_value=db)
    persist = AsyncMock()
    monkeypatch.setattr(processing, 'jobs', {})
    monkeypatch.setattr(processing, 'get_db', get_db)
    monkeypatch.setattr(processing, '_persist_new_job', persist)
    monkeypatch.setattr(processing, '_save_jobs_to_file', Mock())
    monkeypatch.setattr(processing, '_cleanup_old_jobs', Mock())
    monkeypatch.setattr(processing, 'broadcast_status', AsyncMock())
    monkeypatch.setattr('xyz_client.get_client', lambda: provider)
    return db, provider, get_db, persist


@pytest.mark.asyncio
async def test_new_public_episode_is_queued_without_a_provider_fetch(admission):
    db, provider, get_db, persist = admission
    background = BackgroundTasks()
    url = 'https://www.xiaoyuzhoufm.com/episode/69b1512984bce022f9ea354c?from=share'
    result = await processing.process_episode(ProcessRequest(episode_url=url, llm_model='selected-model'), background, SimpleNamespace(id='owner'))
    provider.get_episode_by_share_url.assert_not_called()
    assert result['episode_id'] == '69b1512984bce022f9ea354c'
    assert result['episode_title'] is None
    get_db.assert_called_once_with('owner')
    saved = processing.jobs[result['job_id']]
    persist.assert_awaited_once_with(saved)
    assert saved.status == 'pending' and saved.source_url == url
    assert saved.user_id == 'owner' and saved.llm_model == 'selected-model'
    assert len(background.tasks) == 1
    assert background.tasks[0].func is processing.process_episode_async
    assert background.tasks[0].args[1] == url


@pytest.mark.asyncio
@pytest.mark.parametrize('url', [
    'https://www.xiaoyuzhoufm.com/episode/69b1512984bce022f9ea354c',
    'apple://saved-episode',
    'local://saved-episode',
])
async def test_admission_retains_the_saved_owned_title(admission, url):
    db, provider, _, _ = admission
    db.get_episode.return_value = SimpleNamespace(eid='saved-episode', title='Saved title')
    result = await processing.process_episode(ProcessRequest(episode_url=url), BackgroundTasks(), SimpleNamespace(id='owner'))
    assert result['episode_title'] == 'Saved title'
    assert result['episode_id'] == 'saved-episode'
    provider.get_episode_by_share_url.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['https://example.com/shared-link', 'https://elsewhere.example/episode/12345', 'http://['])
async def test_unrecognized_share_link_is_left_for_the_worker_to_resolve(admission, url):
    db, provider, _, _ = admission
    background = BackgroundTasks()
    result = await processing.process_episode(ProcessRequest(episode_url=url), background, SimpleNamespace(id='owner'))
    provider.get_episode_by_share_url.assert_not_called()
    db.get_episode.assert_not_called()
    assert result['episode_id'] is None
    assert background.tasks[0].args[1] == url
