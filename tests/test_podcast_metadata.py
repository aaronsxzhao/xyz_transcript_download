from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from api.routers import podcasts


@pytest.mark.asyncio
async def test_cloud_podcast_metadata_uses_bounded_owned_index(monkeypatch):
    db = Mock(use_supabase=True)
    db.db.client.rpc.return_value.execute.return_value.data = {
        'podcasts': [{'pid': 'large', 'title': 'Large show', 'episode_count': 20000, 'summarized_count': 16000}],
        'previews': {'large': []},
    }
    monkeypatch.setattr(podcasts, 'get_db', lambda owner: db)
    result = await podcasts.get_podcast('large', SimpleNamespace(id='owner'))
    assert result.episode_count == 20000 and result.summarized_count == 16000
    db.db.client.rpc.assert_called_once_with('podcast_content_index', {
        'owner_id': 'owner', 'preview_limit': 1, 'only_pid': 'large', 'page_offset': 0,
    })
    db.get_episodes_by_podcast.assert_not_called()
    db.get_summary_episode_ids.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_podcast_metadata_does_not_fall_back_to_unowned_records(monkeypatch):
    db = Mock(use_supabase=True)
    db.db.client.rpc.return_value.execute.return_value.data = {'podcasts': [], 'previews': {}}
    monkeypatch.setattr(podcasts, 'get_db', lambda owner: db)
    with pytest.raises(HTTPException) as error:
        await podcasts.get_podcast('other-account-show', SimpleNamespace(id='owner'))
    assert error.value.status_code == 404
    db.get_podcast.assert_not_called()
