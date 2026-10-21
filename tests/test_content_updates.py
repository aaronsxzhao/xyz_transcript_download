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
