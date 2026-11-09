from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from api.routers import video_notes as routes
from bilibili_parts import part_manifest
from video_task_db import VideoTaskDB

BASE='https://www.bilibili.com/video/BVexample'


@pytest.fixture
def collection(tmp_path,monkeypatch):
    db=VideoTaskDB(tmp_path/'collection.db')
    parts=part_manifest({'title':'Collection','videos':3,'pages':[
        {'page':i,'cid':i,'duration':60,'part':f'Chapter {i}'} for i in range(1,4)]},BASE)
    task=db.create_task({'url':BASE+'?p=2','user_id':'owner','platform':'bilibili',
                         'model':'saved-model','formats':['summary','screenshot'],'extras':'Keep examples'})
    db.update_task(task,{'source_metadata':{'bilibili_parts':parts,'bilibili_part':parts[1]}})
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr('execution_store.enabled',lambda:False)
    submit=AsyncMock()
    monkeypatch.setattr(routes,'enqueue_video_note',submit)
    return db,task,SimpleNamespace(id='owner'),submit


def test_status_list_includes_unimported_parts_but_not_other_accounts(collection):
    db,task,user,_=collection
    db.create_task({'url':BASE+'?p=1','platform':'bilibili','user_id':'other','status':'success'})
    result=routes.collection_parts(task,user)['parts']
    assert len(result)==3
    assert result[0]['task_id'] is None and result[0]['status']=='not_started'
    assert result[1]['task_id']==task
    with pytest.raises(HTTPException) as error:
        routes.collection_parts(task,SimpleNamespace(id='other'))
    assert error.value.status_code==404


@pytest.mark.asyncio
async def test_selection_admits_only_selected_part_and_preserves_settings(collection):
    db,task,user,submit=collection
    result=await routes.process_collection_part(task,3,user)
    submit.assert_awaited_once()
    assert submit.call_args.kwargs['url']==BASE+'?p=3'
    assert submit.call_args.kwargs['llm_model']=='saved-model'
    assert submit.call_args.kwargs['extras']=='Keep examples'
    assert submit.call_args.kwargs['formats']==['summary','screenshot']
    assert db.get_task_by_url(BASE+'?p=1','owner') is None
    rows=routes.collection_parts(task,user)['parts']
    assert rows[2]['task_id']==result['task_id'] and rows[2]['status']=='pending'
    db.update_task(result['task_id'],{'status':'success','markdown':'Ready'})
    repeated=await routes.process_collection_part(task,3,user)
    assert repeated['skipped'] is True and repeated['task_id']==result['task_id']
    assert submit.await_count==1


@pytest.mark.asyncio
async def test_uncertain_queue_admission_is_retryable_without_creating_duplicate_tasks(collection):
    db,task,user,submit=collection
    submit.side_effect=TimeoutError('acknowledgement lost')
    with pytest.raises(HTTPException) as error:
        await routes.process_collection_part(task,1,user)
    assert error.value.status_code==503
    child=db.get_task_by_url(BASE+'?p=1','owner')
    submit.side_effect=None
    result=await routes.process_collection_part(task,1,user)
    assert result['task_id']==child['id']
    assert len(db.part_statuses([BASE+'?p=1'],'owner'))==1
    with pytest.raises(HTTPException) as invalid:
        await routes.process_collection_part(task,99,user)
    assert invalid.value.status_code==404


def test_current_part_uses_resolved_identity_even_when_saved_url_is_short(collection):
    db,task,user,_=collection
    metadata=db.get_task(task,'owner')['source_metadata']
    short=db.create_task({'url':'https://b23.tv/short-original','user_id':'owner','platform':'bilibili','status':'success'})
    db.update_task(short,{'source_metadata':metadata})
    parts=routes.collection_parts(short,user)['parts']
    assert parts[1]['task_id']==short
    assert parts[1]['status']=='success'
    assert parts[0]['status']=='not_started'


def test_other_part_directory_finds_legacy_short_link_p1_and_keeps_owner_scope(collection):
    db,task,user,_=collection
    metadata=db.get_task(task,'owner')['source_metadata']
    first={**metadata,'bilibili_part':metadata['bilibili_parts'][0]}
    private=db.create_task({'url':'https://b23.tv/private','user_id':'other','platform':'bilibili','status':'success'})
    db.update_task(private,{'source_metadata':first})
    assert routes.collection_parts(task,user)['parts'][0]['task_id'] is None
    short=db.create_task({'url':'https://b23.tv/legacy','user_id':'owner','platform':'bilibili','status':'success'})
    db.update_task(short,{'source_metadata':first})
    row=routes.collection_parts(task,user)['parts'][0]
    assert row['task_id']==short and row['status']=='success'
    assert db.get_task(short,'owner')['url']=='https://b23.tv/legacy'
    exact=db.create_task({'url':BASE+'?p=1','user_id':'owner','platform':'bilibili','status':'pending'})
    assert routes.collection_parts(task,user)['parts'][0]['task_id']==exact


def test_cloud_part_status_alias_lookup_is_owner_scoped_and_omits_metadata():
    from unittest.mock import MagicMock
    from video_task_db import _SupabaseVideoTaskDB
    backend=_SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    query=MagicMock()
    query.select.return_value=query.eq.return_value=query.in_.return_value=query
    query.execute.side_effect=[SimpleNamespace(data=[]),SimpleNamespace(data=[{
        'id':'short','url':'https://b23.tv/legacy','status':'success','progress':100,'error':'',
        'bilibili_part':{'url':BASE+'?p=1','page':1}}])]
    backend._sb=SimpleNamespace(client=SimpleNamespace(table=lambda _:query))
    db=VideoTaskDB.__new__(VideoTaskDB);db._backend=backend
    rows=db.part_statuses([BASE+'?p=1'],'owner')
    assert rows==[{'id':'short','url':BASE+'?p=1','status':'success','progress':100,'error':''}]
    assert query.eq.call_args_list.count((('user_id','owner'),{}))==2
    query.in_.assert_any_call('source_metadata->bilibili_part->>url',[BASE+'?p=1'])
    query.reset_mock()
    assert db.part_statuses([BASE+'?p=1'],None)==[]
    query.select.assert_not_called()


def test_legacy_directory_discovers_metadata_without_saving_or_processing(collection, monkeypatch):
    from unittest.mock import Mock
    db, task, user, submit = collection
    metadata = db.get_task(task, user.id)['source_metadata']
    db.update_task(task, {'source_metadata': {}, 'status': 'success', 'markdown': 'Saved note'})
    before = db.get_task(task, user.id)
    discover = Mock(return_value=metadata)
    monkeypatch.setattr('bilibili_parts.public_collection_metadata', discover)
    result = routes.collection_parts(task, user)['parts']
    assert len(result) == 3
    assert result[1]['task_id'] == task and result[1]['status'] == 'success'
    assert result[0]['task_id'] is None
    assert db.get_task(task, user.id) == before
    submit.assert_not_called()
    discover.assert_called_once_with(BASE + '?p=2')


def test_legacy_discovery_checks_owner_first(collection, monkeypatch):
    from unittest.mock import Mock
    db, task, user, _ = collection
    db.update_task(task, {'source_metadata': {}})
    discover = Mock()
    monkeypatch.setattr('bilibili_parts.public_collection_metadata', discover)
    with pytest.raises(HTTPException) as error:
        routes.collection_parts(task, SimpleNamespace(id='other'))
    assert error.value.status_code == 404
    discover.assert_not_called()


def test_saved_manifest_does_not_request_upstream(collection, monkeypatch):
    from unittest.mock import Mock
    discover = Mock(side_effect=AssertionError('Unexpected network request'))
    monkeypatch.setattr('bilibili_parts.public_collection_metadata', discover)
    _, task, user, _ = collection
    assert len(routes.collection_parts(task, user)['parts']) == 3
    discover.assert_not_called()


def test_unavailable_legacy_source_keeps_saved_note_and_reports_retry(collection, monkeypatch):
    from unittest.mock import Mock
    import requests
    db, task, user, submit = collection
    db.update_task(task, {'source_metadata': {}, 'status': 'success', 'markdown': 'Saved'})
    before = db.get_task(task, user.id)
    monkeypatch.setattr('bilibili_parts.public_collection_metadata', Mock(side_effect=requests.Timeout()))
    with pytest.raises(HTTPException) as error:
        routes.collection_parts(task, user)
    assert error.value.status_code == 503
    assert db.get_task(task, user.id) == before
    submit.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_selected_processing_uses_same_discovered_manifest(collection, monkeypatch):
    db, task, user, submit = collection
    metadata = db.get_task(task, user.id)['source_metadata']
    db.update_task(task, {'source_metadata': {}})
    monkeypatch.setattr('bilibili_parts.public_collection_metadata', lambda url: metadata)
    await routes.process_collection_part(task, 3, user)
    submit.assert_awaited_once()
    assert submit.call_args.kwargs['url'] == BASE + '?p=3'
    assert db.get_task_by_url(BASE+'?p=1',user.id) is None
    assert db.get_task(task,user.id)['source_metadata'] == {}


def test_discovery_preserves_known_resolved_part_of_legacy_share_url(collection, monkeypatch):
    from unittest.mock import Mock
    db, task, user, _ = collection
    metadata = db.get_task(task,user.id)['source_metadata']
    db.update_task(task, {'url':'https://b23.tv/legacy-share', 'source_metadata':{'bilibili_part':metadata['bilibili_part']}})
    discover = Mock(return_value=metadata)
    monkeypatch.setattr('bilibili_parts.public_collection_metadata',discover)
    result = routes.collection_parts(task,user)['parts']
    discover.assert_called_once_with(BASE+'?p=2')
    assert result[1]['task_id'] == task
