"""Authenticated favorites stay account-bound, paged and safe to re-submit."""
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import httpx
import pytest

from api.routers import bilibili_favorites, video_notes


@pytest.fixture
def upstream(monkeypatch):
    manager = Mock()
    manager.get_cookie.return_value = ".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tsynthetic-cookie"
    factory = Mock(return_value=manager)
    monkeypatch.setattr("cookie_manager.get_cookie_manager", factory)
    real_client = httpx.AsyncClient
    requests = []
    state = {"code":0}
    def handler(request):
        requests.append(request)
        assert request.headers['cookie'] == 'SESSDATA=synthetic-cookie'
        if state['code']:
            return httpx.Response(200, json={"code":state['code']})
        if request.url.path.endswith('/nav'):
            data = {"isLogin":True,"mid":123}
        elif request.url.path.endswith('/list-all'):
            assert request.url.params['up_mid'] == '123'
            data = {"list":[{"id":10,"title":"My folder","media_count":42}]}
        else:
            data = {"has_more":True,"medias":[
                {"bvid":"BV1234567890","title":"A saved video","cover":"https://example.com/cover.jpg","duration":120,"upper":{"name":"Uploader"}},
                {"bvid":"","title":"已失效视频"},
            ]}
        return httpx.Response(200,json={"code":0,"data":data})
    monkeypatch.setattr(bilibili_favorites.httpx,"AsyncClient", lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    return SimpleNamespace(manager=manager,factory=factory,requests=requests,state=state)


@pytest.mark.asyncio
async def test_missing_connection_returns_actionable_error_without_upstream_call(client, upstream):
    upstream.manager.get_cookie.return_value = None
    response = await client.get('/api/bilibili-favorites')
    assert response.status_code == 409
    assert 'Settings' in response.json()['detail']
    assert upstream.requests == []


@pytest.mark.asyncio
async def test_private_folders_are_read_using_only_the_current_accounts_cookie(upstream):
    result = await bilibili_favorites.list_folders(SimpleNamespace(id='owner'))
    upstream.factory.assert_called_once_with('owner')
    assert result['folders'] == [{"id":10,"title":"My folder","count":42}]
    assert 'synthetic-cookie' not in str(result)


@pytest.mark.asyncio
async def test_favorites_are_paged_and_existing_imports_are_marked(client, upstream):
    from video_task_db import get_video_task_db
    # Use the same database fixture installed by the API client.
    get_video_task_db().create_task({"url":"https://www.bilibili.com/video/BV1234567890","platform":"bilibili","status":"success","user_id":"local"})
    response = await client.get('/api/bilibili-favorites/10?page=2')
    assert response.status_code == 200
    body = response.json()
    assert body['page'] == 2 and body['has_more']
    assert body['videos'][0]['imported'] and body['videos'][0]['available']
    assert not body['videos'][1]['available']
    params = upstream.requests[-1].url.params
    assert params['pn']=='2' and params['ps']=='20'


@pytest.mark.asyncio
async def test_another_accounts_folder_cannot_be_read(client, upstream):
    response = await client.get('/api/bilibili-favorites/99')
    assert response.status_code == 404
    assert not any(r.url.path.endswith('/resource/list') for r in upstream.requests)


@pytest.mark.asyncio
async def test_expired_bilibili_login_does_not_look_like_an_empty_folder(client, upstream):
    upstream.state['code'] = -101
    response = await client.get('/api/bilibili-favorites')
    assert response.status_code == 409
    assert 'expired' in response.json()['detail']


@pytest.mark.asyncio
async def test_cloud_requires_our_app_login_even_when_a_cookie_exists(client, app, upstream, monkeypatch):
    from api.auth import get_current_user
    monkeypatch.setitem(app.dependency_overrides,get_current_user,lambda:None)
    monkeypatch.setattr(bilibili_favorites,'USE_SUPABASE',True)
    response = await client.get('/api/bilibili-favorites')
    assert response.status_code == 401
    assert not upstream.requests


@pytest.mark.asyncio
async def test_duplicate_import_preserves_finished_note_and_does_not_schedule_again(client, monkeypatch):
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    url = 'https://www.bilibili.com/video/BV1234567890'
    task = db.create_task({"url":url,"platform":"bilibili","status":"success","user_id":"local"})
    db.update_task(task,{"markdown":"Existing note"})
    worker = AsyncMock()
    monkeypatch.setattr(video_notes,'process_video_note_async',worker)
    response = await client.post('/api/video-notes/generate-json',json={"url":url,"platform":"bilibili","skip_existing":True})
    assert response.json() == {"task_id":task,"skipped":True}
    assert db.get_task(task,'local')['markdown'] == 'Existing note'
    assert db.get_task(task,'local')['status'] == 'success'
    worker.assert_not_called()


@pytest.mark.asyncio
async def test_discovered_video_can_start_but_a_second_import_does_not_restart_it(client, upstream, monkeypatch):
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    url = 'https://www.bilibili.com/video/BV1234567890'
    task = db.create_task({"url":url,"platform":"bilibili","status":"discovered","user_id":"local"})
    response = await client.get('/api/bilibili-favorites/10')
    assert not response.json()['videos'][0]['imported']
    worker = AsyncMock()
    monkeypatch.setattr(video_notes,'process_video_note_async',worker)
    first = await client.post('/api/video-notes/generate-json',json={"url":url,"platform":"bilibili","skip_existing":True})
    second = await client.post('/api/video-notes/generate-json',json={"url":url,"platform":"bilibili","skip_existing":True})
    assert first.json()['task_id'] == task
    assert second.json() == {"task_id":task,"skipped":True}
    worker.assert_awaited_once()


@pytest.mark.asyncio
async def test_submission_confirmation_is_owned_and_never_starts_work(client, monkeypatch):
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    url = 'https://www.bilibili.com/video/BV1234567890'
    other = db.create_task({'url': url, 'user_id': 'other', 'status': 'pending'})
    response = await client.get('/api/video-notes/submission', params={'url':url, 'platform':'bilibili'})
    assert response.json() == {'task_id': None}
    task = db.create_task({'url': url, 'user_id':'local', 'status':'discovered'})
    response = await client.get('/api/video-notes/submission', params={'url':url})
    assert response.json() == {'task_id':None}
    db.update_task(task, {'status':'transcribing'})
    worker = AsyncMock()
    monkeypatch.setattr(video_notes, 'process_video_note_async', worker)
    response = await client.get('/api/video-notes/submission', params={'url':url+'?spm_id=test', 'platform':'bilibili'})
    assert response.json() == {'task_id':task, 'status':'transcribing'}
    worker.assert_not_called()
    assert db.get_task(other, 'other')['status'] == 'pending'


@pytest.mark.asyncio
async def test_channel_read_failure_is_not_a_successful_empty_list(client, monkeypatch):
    from video_task_db import get_video_task_db
    video_notes._list_cache.clear()
    monkeypatch.setattr(get_video_task_db(), 'list_channels_with_stats', Mock(side_effect=RuntimeError('private upstream detail')))
    response = await client.get('/api/video-notes/channels')
    assert response.status_code == 503
    assert 'temporarily unavailable' in response.json()['detail']
    assert 'private upstream detail' not in response.text


@pytest.mark.asyncio
async def test_import_response_finishes_while_processing_is_still_running(client, monkeypatch):
    import asyncio
    from video_task_db import get_video_task_db
    started, release = asyncio.Event(), asyncio.Event()
    async def slow_worker(*args, **kwargs):
        started.set()
        await release.wait()
    monkeypatch.setattr(video_notes, 'process_video_note_async', slow_worker)
    try:
        response = await asyncio.wait_for(client.post('/api/video-notes/generate-json', json={
            'url':'https://www.bilibili.com/video/BV1234567890','platform':'bilibili','skip_existing':True,
        }), timeout=1)
        assert response.status_code == 200
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not release.is_set()
        assert get_video_task_db().get_task(response.json()['task_id'], 'local')['status'] == 'pending'
        assert video_notes._video_workers
    finally:
        release.set()
        await asyncio.gather(*list(video_notes._video_workers))
    assert not video_notes._video_workers
