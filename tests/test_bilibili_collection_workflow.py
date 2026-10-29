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
