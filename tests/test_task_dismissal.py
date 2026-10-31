import pytest
from video_task_db import VideoTaskDB


def test_dismissal_survives_new_database_instance_and_preserves_note(tmp_path):
    path=tmp_path/'tasks.db'
    db=VideoTaskDB(path)
    task=db.create_task({'user_id':'owner','title':'Note','status':'success','markdown':'Saved content'})
    db.update_task(task,{'markdown':'Saved content'})
    db.dismiss_task(task,'owner')
    second=VideoTaskDB(path)
    row=second.get_task(task,'owner')
    assert row['task_dismissed'] and row['markdown']=='Saved content'
    assert next(t for t in second.list_progress_tasks('owner') if t['id']==task)['task_dismissed']
    second.update_task(task,{'title':'Updated metadata'})
    assert second.get_task(task,'owner')['task_dismissed']
    second.update_task(task,{'status':'pending','progress':0})
    assert not second.get_task(task,'owner')['task_dismissed']
    second.update_task(task,{'status':'success'})
    assert not second.get_task(task,'owner')['task_dismissed']


def test_dismissal_checks_owner_and_rejects_active_tasks(tmp_path):
    db=VideoTaskDB(tmp_path/'tasks.db')
    task=db.create_task({'user_id':'owner','status':'failed'})
    with pytest.raises(LookupError):db.dismiss_task(task,'other')
    assert not db.get_task(task,'owner')['task_dismissed']
    db.update_task(task,{'status':'summarizing','progress':70})
    with pytest.raises(ValueError):db.dismiss_task(task,'owner')
    assert not db.get_task(task,'owner')['task_dismissed']


@pytest.mark.asyncio
async def test_dismissal_api_persists_without_deleting_content(client):
    from video_task_db import get_video_task_db
    db=get_video_task_db()
    task=db.create_task({'user_id':'local','status':'failed','markdown':'Keep this'})
    db.update_task(task,{'markdown':'Keep this'})
    response=await client.post(f'/api/video-notes/tasks/{task}/dismiss')
    assert response.status_code==200,response.text
    assert response.json()['task_dismissed']
    assert 'markdown' not in response.json()
    assert db.get_task(task,'local')['markdown']=='Keep this'
    assert (await client.post(f'/api/video-notes/tasks/{task}/dismiss')).status_code==200
    other=db.create_task({'user_id':'other','status':'failed'})
    assert (await client.post(f'/api/video-notes/tasks/{other}/dismiss')).status_code==404


def test_cloud_acknowledgement_is_owner_and_attempt_scoped():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from video_task_db import _SupabaseVideoTaskDB
    backend=object.__new__(_SupabaseVideoTaskDB)
    query=Mock()
    query.update.return_value=query
    query.eq.return_value=query
    query.execute.return_value=SimpleNamespace(data=[{'updated_at':'server-stamp'}])
    backend._sb=SimpleNamespace(client=SimpleNamespace(table=lambda name:query),
        get_video_task=Mock(return_value={'id':'v','status':'failed','updated_at':'attempt-stamp'}))
    db=object.__new__(VideoTaskDB);db._backend=backend
    assert db.dismiss_task('v','owner')['updated_at']=='server-stamp'
    backend._sb.get_video_task.assert_called_once_with('v','owner',include_transcript=False)
    assert [call.args for call in query.eq.call_args_list]==[
        ('id','v'),('user_id','owner'),('status','failed'),('updated_at','attempt-stamp')]
    # A concurrent retry changes the snapshot; never acknowledge that new attempt.
    query.execute.return_value=SimpleNamespace(data=[])
    with pytest.raises(ValueError,match='Task changed'):
        db.dismiss_task('v','owner')
