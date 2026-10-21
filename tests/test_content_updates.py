import sqlite3
from api.content_updates import list_updates, dismiss_updates, install_sqlite_updates


def test_discoveries_survive_reload_and_dismissal_only_affects_selected_items(mock_database,create_test_podcast,create_test_episode):
    from api.main import _new_episodes_cache, _store_new_episodes_cache
    create_test_podcast();create_test_episode()
    path=mock_database.db_path
    rows=list_updates('local',path)
    assert [row['item_key'] for row in rows]==['podcast:test-episode-456']
    _store_new_episodes_cache('local',[]);_new_episodes_cache.clear()
    assert list_updates('local',path)==rows
    assert list_updates('another-owner',path)==[]
    dismiss_updates('another-owner',[rows[0]['item_key']],path)
    assert list_updates('local',path)==rows
    dismiss_updates('local',[rows[0]['item_key']],path)
    assert list_updates('local',path)==[]
    create_test_episode(override={'eid':'new-episode'})
    assert [row['item_key'] for row in list_updates('local',path)]==['podcast:new-episode']


def test_video_updates_remain_dismissed_after_metadata_changes(tmp_path):
    from video_task_db import VideoTaskDB
    db=VideoTaskDB(tmp_path/'video.db')
    task=db.create_task({'title':'A new video','user_id':'owner','status':'discovered','channel':'Channel'})
    rows=list_updates('owner',tmp_path/'video.db')
    assert rows[0]['kind']=='video'
    dismiss_updates('owner',[rows[0]['item_key']],tmp_path/'video.db')
    db.update_task(task,{'title':'Updated title','channel':'Updated channel'})
    assert list_updates('owner',tmp_path/'video.db')==[]
    assert list_updates('other-owner',tmp_path/'video.db')==[]


def test_deleting_episode_removes_notification(mock_database,create_test_podcast,create_test_episode):
    create_test_podcast();create_test_episode()
    mock_database.delete_episode('test-episode-456')
    assert list_updates('local',mock_database.db_path)==[]


async def test_updates_endpoint_persists_dismissal(client,mock_database,create_test_podcast,create_test_episode,monkeypatch):
    import config
    monkeypatch.setattr(config,'DATABASE_PATH',mock_database.db_path)
    create_test_podcast();create_test_episode()
    response=await client.get('/api/content-updates')
    assert response.status_code==200
    keys=[item['item_key'] for item in response.json()['items']]
    assert keys==['podcast:test-episode-456']
    assert (await client.post('/api/content-updates/dismiss',json={'keys':keys})).status_code==200
    assert (await client.get('/api/content-updates')).json()=={'items':[]}
    assert (await client.post('/api/content-updates/dismiss',json={'keys':['a']*101})).status_code==422


def test_closing_snapshot_clears_backlog_beyond_first_page_and_preserves_newer_rows(tmp_path):
    from datetime import datetime
    path=tmp_path/'updates.db'
    with sqlite3.connect(path) as conn:
        install_sqlite_updates(conn)
        conn.executemany('INSERT INTO content_updates(user_id,item_key,kind,title,source_id,created_at) VALUES (?,?,?,?,?,?)',
            [('owner',f'podcast:{i}','podcast',f'Episode {i}','show','2026-10-21T01:00:00Z') for i in range(250)])
        conn.execute("INSERT INTO content_updates(user_id,item_key,kind,title,source_id,created_at) VALUES ('other','podcast:private','podcast','Private','show','2026-10-21T01:00:00Z')")
    snapshot=list_updates('owner',path)
    assert len(snapshot)==100
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO content_updates(user_id,item_key,kind,title,source_id,created_at) VALUES ('owner','podcast:new','podcast','New','show','2026-10-21T01:00:01Z')")
    dismiss_updates('owner',[r['item_key'] for r in snapshot],path,before=datetime.fromisoformat('2026-10-21T01:00:00+00:00'))
    assert [r['item_key'] for r in list_updates('owner',path)]==['podcast:new']
    assert [r['item_key'] for r in list_updates('other',path)]==['podcast:private']


async def test_dismiss_endpoint_accepts_snapshot_cutoff_and_keeps_legacy_contract(client,mock_database,create_test_podcast,create_test_episode,monkeypatch):
    import config
    monkeypatch.setattr(config,'DATABASE_PATH',mock_database.db_path)
    create_test_podcast();create_test_episode()
    snapshot=(await client.get('/api/content-updates')).json()
    assert snapshot['dismiss_before']
    assert (await client.post('/api/content-updates/dismiss',json={'keys':[],'before':snapshot['dismiss_before']})).status_code==200
    assert (await client.get('/api/content-updates')).json()=={'items':[]}
    assert (await client.post('/api/content-updates/dismiss',json={'before':'not-a-date'})).status_code==422
    assert (await client.post('/api/content-updates/dismiss',json={'before':'2026-10-21T00:00:00'})).status_code==422


def test_cloud_dismissal_is_one_owner_filtered_patch_without_a_page_limit(monkeypatch):
    import config
    import httpx
    from datetime import datetime
    from supabase import create_client
    from supabase.client import ClientOptions
    from api.supabase_http import SupabaseHTTPClient
    calls=[]
    def upstream(request):
        calls.append(request)
        return httpx.Response(204)
    with SupabaseHTTPClient(transport=httpx.MockTransport(upstream)) as http:
        sdk=create_client('https://example.supabase.co','test-service-key',options=ClientOptions(httpx_client=http,auto_refresh_token=False,persist_session=False))
        monkeypatch.setattr(config,'USE_SUPABASE',True)
        monkeypatch.setattr('api.supabase_client.get_supabase_admin_client',lambda:sdk)
        before=datetime.fromisoformat('2026-10-21T01:00:00.123456+00:00')
        dismiss_updates('owner',['podcast:first-page'],before=before)
    assert len(calls)==1
    request=calls[0]
    assert request.method=='PATCH'
    assert dict(request.url.params)=={'user_id':'eq.owner','dismissed_at':'is.null','created_at':'lte.'+before.isoformat()}
    assert request.headers['prefer']=='return=minimal'
