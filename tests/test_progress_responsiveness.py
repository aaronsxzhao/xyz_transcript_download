"""Progress stays small and account scoped; slow mutations cannot freeze page reads."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['retry', 'channels', 'cookies', 'notion'])
async def test_slow_action_keeps_other_pages_responsive(client, kind):
    started, release = threading.Event(), threading.Event()
    database = Mock()
    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(3), 'An action blocked the event loop'
        return None if kind in {'retry', 'notion'} else [] if kind == 'channels' else ''
    if kind == 'retry':
        database.get_task.side_effect = blocked
        request = lambda: client.post('/api/video-notes/tasks/missing/retry', json={})
        target = 'video_task_db.get_video_task_db'
    elif kind == 'channels':
        database.get_distinct_channels.side_effect = blocked
        request = lambda: client.post('/api/video-notes/check-channels', json={})
        target = 'video_task_db.get_video_task_db'
    elif kind == 'cookies':
        database.get_cookie.side_effect = blocked
        request = lambda: client.get('/api/cookies/bilibili/validate')
        target = 'cookie_manager.get_cookie_manager'
    else:
        database.get_task.side_effect = blocked
        request = lambda: client.post('/api/notion/export', headers={'X-Notion-Key':'synthetic'}, json={'task_id':'missing','parent_page_id':'page'})
        target = 'video_task_db.get_video_task_db'
    with patch(target, return_value=database):
        pending = asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(started.wait, 1)
            # Both navigation HTML and authenticated page data must keep running.
            health, settings = await asyncio.wait_for(asyncio.gather(client.get('/api/health'), client.get('/api/settings')), .5)
            assert health.status_code == settings.status_code == 200
        finally:
            release.set()
            response = await pending
            assert response.status_code == (404 if kind in {'retry', 'notion'} else 200)


def test_cloud_progress_queries_are_bounded_and_owner_scoped():
    from api.supabase_db import SupabaseDatabase
    from api.supabase_http import SupabaseHTTPClient
    from supabase import create_client
    from supabase.client import ClientOptions
    requests = []
    def upstream(request):
        requests.append(request)
        status = request.url.params.get('status', '')
        rows = [{'id':'running','status':'summarizing'}] if status.startswith('not.') else [{'id':'done','status':'success'}] if status else [{'id':'older-completion','status':'failed'}]
        return httpx.Response(200, json=rows)
    with SupabaseHTTPClient(transport=httpx.MockTransport(upstream)) as http:
        db = SupabaseDatabase.__new__(SupabaseDatabase)
        db.client = create_client('https://example.supabase.co', 'synthetic', options=ClientOptions(httpx_client=http, auto_refresh_token=False, persist_session=False))
        rows = db.list_video_progress('owner', ['older-completion'])
        assert {row['id'] for row in rows} == {'running','done','older-completion'}
    assert len(requests) == 3
    assert all(request.url.params['user_id'] == 'eq.owner' for request in requests)
    assert [request.url.params.get('limit') for request in requests] == ['200','10',None]
    assert all(not {'markdown','transcript_json','extras'} & set(request.url.params['select'].split(',')) for request in requests)


@pytest.mark.asyncio
async def test_progress_never_returns_other_accounts_tasks_or_note_bodies(client, app):
    from api.auth import get_current_user, User
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    mine = db.create_task({'url':'fixture://mine','user_id':'local','status':'summarizing','markdown':'private note'})
    other = db.create_task({'url':'fixture://other','user_id':'someone-else','status':'summarizing'})
    result = (await client.get('/api/video-notes/progress?known='+other)).json()['tasks']
    assert mine in {row['id'] for row in result} and other not in {row['id'] for row in result}
    assert 'private note' not in str(result)
    app.dependency_overrides[get_current_user] = lambda: User('empty-account', '')
    try:
        assert (await client.get('/api/video-notes/progress?known='+mine)).json() == {'tasks':[]}
    finally:
        app.dependency_overrides.clear()


def test_cached_video_progress_has_a_new_utc_version_before_database_flush(monkeypatch):
    import threading
    from datetime import datetime
    from unittest.mock import Mock
    from video_task_db import _SupabaseVideoTaskDB
    db=_SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    db._lock=threading.Lock();db._dirty={}
    db._cache={'video':{'id':'video','user_id':'owner','status':'pending','updated_at':'2026-01-01T00:00:00+00:00'}}
    db._should_flush=lambda *_:False
    db.update_task('video',{'status':'summarizing','progress':55,'message':'Writing notes'})
    task=db._cache['video']
    assert task['status']=='summarizing'
    assert datetime.fromisoformat(task['updated_at']).utcoffset().total_seconds()==0
    assert datetime.fromisoformat(task['updated_at'])>datetime.fromisoformat('2026-01-01T00:00:00+00:00')
    assert db._dirty['video']['updated_at']==task['updated_at']
    db._sb=Mock();db._last_flush={}
    db.flush_task('video')
    assert db._sb.update_video_task.call_args.args[1]['updated_at']==task['updated_at']


def test_video_database_flush_preserves_the_progress_event_version():
    from api.supabase_db import SupabaseDatabase
    from unittest.mock import Mock
    db=SupabaseDatabase.__new__(SupabaseDatabase);db.client=Mock()
    timestamp='2026-10-26T15:46:28.948908+00:00'
    db.update_video_task('video',{'status':'summarizing','updated_at':timestamp})
    assert db.client.table.return_value.update.call_args.args[0]['updated_at']==timestamp


@pytest.mark.asyncio
async def test_live_status_responses_are_never_cacheable(client):
    for path in ('/api/jobs','/api/video-notes/progress'):
        response=await client.get(path)
        assert response.status_code==200
        assert response.headers['cache-control']=='private, no-store'


@pytest.mark.asyncio
async def test_video_websocket_progress_excludes_reading_payloads(monkeypatch):
    from api.routers import video_notes
    from unittest.mock import AsyncMock
    broadcast=AsyncMock();monkeypatch.setattr(video_notes.manager,'broadcast_to_user',broadcast)
    await video_notes.broadcast_video_job('test',{'id':'test','status':'summarizing','progress':75,
        'updated_at':'2026-10-26T10:00:00+00:00','markdown':'private body'*10000,
        'transcript_json':'private transcript','versions':[{'content':'private version'}],'extras':'private options'},'owner')
    sent,owner=broadcast.call_args.args
    assert owner=='owner' and sent['task']['status']=='summarizing'
    assert len(str(sent))<1000 and 'private' not in str(sent)


def test_newer_database_progress_is_not_replaced_by_an_older_process_cache():
    from video_task_db import _SupabaseVideoTaskDB
    db=_SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    db._lock=threading.Lock();db._dirty={}
    db._cache={'task':{'id':'task','user_id':'owner','status':'pending','updated_at':'2026-10-26T10:00:00+00:00'}}
    rows=db._merge_cached_task_list([{'id':'task','status':'success','progress':100,'updated_at':'2026-10-26T10:00:05+00:00'}],user_id='owner',limit=10)
    assert rows[0]['status']=='success' and rows[0]['progress']==100


@pytest.mark.asyncio
async def test_socket_disconnect_during_auth_does_not_send_a_second_close():
    from api.routers.processing import websocket_progress
    from starlette.websockets import WebSocketDisconnect
    from unittest.mock import AsyncMock
    socket=SimpleNamespace(accept=AsyncMock(),receive_json=AsyncMock(side_effect=WebSocketDisconnect()),close=AsyncMock())
    await websocket_progress(socket,token=None)
    socket.close.assert_not_called()
