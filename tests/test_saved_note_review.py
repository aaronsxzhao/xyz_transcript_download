import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest

from saved_note_review import needs_review, snapshot_key, review_saved_note
from summary_errors import _EN_NOTICES, ProcessingCancelledError


def task():
    return {'id':'note', 'user_id':'owner', 'status':'success', 'platform':'bilibili', 'url':'https://example.com',
            'markdown':_EN_NOTICES['audit']+'\n\n# Saved note\n\nArgument.\n\n![Screenshot](/image.png)',
            'transcript_json':json.dumps({'text':'Argument.', 'segments':[{'text':'Argument.','start':0,'end':60}]}),
            'duration':60, 'style':'detailed', 'model':'saved-model'}


@pytest.fixture
def setup(monkeypatch):
    original=task();db=Mock();db.get_task.return_value=original
    store=Mock();store.get_checkpoint.return_value=None
    engine=Mock()
    monkeypatch.setattr('execution_store.get_store',lambda:store)
    monkeypatch.setattr('api.user_settings.get_user_settings',lambda owner:{})
    monkeypatch.setattr('api.llm_settings.resolve_llm_settings',lambda settings:{})
    monkeypatch.setattr('note_summarizer.NoteSummarizer',lambda **kwargs:engine)
    return original,db,store,engine


def test_only_unfinished_notice_enables_retry():
    assert needs_review(task()['markdown'])
    assert not needs_review(_EN_NOTICES['coverage_gap']+'\n\nBody')
    assert not needs_review('Quoted warning later\n\n'+task()['markdown'])


def test_complete_review_keeps_prose_media_and_other_notices(setup,monkeypatch):
    original,db,store,engine=setup
    original['markdown']=_EN_NOTICES['grounding']+'\n\n'+original['markdown']
    result={'complete':True,'checks':[{'chunk':1,'complete':True}],'additions':[], 'source_chunks':1,'resumed_chunks':0}
    reviewer=Mock(return_value=result);monkeypatch.setattr('saved_note_review.review_document',reviewer)
    review_saved_note(db,'note','owner',snapshot_key(original),Mock(),Mock(),'Screenshots need repair')
    saved=db.complete_task.call_args.args
    assert saved[1]==original['markdown'].replace(_EN_NOTICES['audit']+'\n\n','')
    assert saved[-1]=='Screenshots need repair'
    assert reviewer.call_args.kwargs['checkpoint'] and reviewer.call_args.kwargs['progress']
    assert store.put_checkpoint.call_count==2
    engine.client.close.assert_called_once()


def test_incomplete_review_checkpoints_but_never_replaces_note(setup,monkeypatch):
    original,db,store,engine=setup
    result={'complete':False,'checks':[{'chunk':1,'complete':False}], 'additions':[], 'source_chunks':1,'resumed_chunks':0}
    monkeypatch.setattr('saved_note_review.review_document',Mock(return_value=result))
    with pytest.raises(ValueError,match='still incomplete'):
        review_saved_note(db,'note','owner',snapshot_key(original),Mock(),Mock())
    db.complete_task.assert_not_called()
    assert store.put_checkpoint.call_args.args[-1]['complete'] is False
    engine.client.close.assert_called_once()


def test_changed_source_or_note_is_not_overwritten(setup,monkeypatch):
    original,db,store,engine=setup
    changed={**original,'markdown':'Newer note'}
    db.get_task.side_effect=[original,changed]
    monkeypatch.setattr('saved_note_review.review_document',Mock(return_value={
        'complete':True,'checks':[],'additions':[], 'source_chunks':1,'resumed_chunks':0}))
    with pytest.raises(ValueError,match='changed during review'):
        review_saved_note(db,'note','owner',snapshot_key(original),Mock(),Mock())
    db.complete_task.assert_not_called()


def test_cancellation_never_saves_a_review(setup):
    original,db,store,engine=setup
    with pytest.raises(ProcessingCancelledError):
        review_saved_note(db,'note','owner',snapshot_key(original),Mock(),Mock(side_effect=ProcessingCancelledError()))
    db.complete_task.assert_not_called()
    engine.client.close.assert_called_once()


@pytest.mark.asyncio
async def test_endpoint_checks_owner_and_enqueues_review_only(monkeypatch):
    from api.routers import video_notes
    original=task();db=Mock();db.get_task.return_value=original
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr('execution_store.enabled',lambda:False)
    enqueue=AsyncMock();monkeypatch.setattr(video_notes,'enqueue_video_note',enqueue)
    await video_notes.retry_coverage_review('note',SimpleNamespace(id='owner'))
    db.get_task.assert_called_once_with('note','owner')
    payload=enqueue.call_args.kwargs
    assert payload['coverage_review']==snapshot_key(original) and payload['user_id']=='owner'
    assert 'markdown' not in db.update_task.call_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize('original,code',[(None,404),({**task(),'status':'summarizing'},409),({**task(),'markdown':'Done'},400)])
async def test_endpoint_rejects_missing_running_or_reviewed_notes(monkeypatch,original,code):
    from fastapi import HTTPException
    from api.routers import video_notes
    db=Mock();db.get_task.return_value=original
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr('execution_store.enabled',lambda:False)
    with pytest.raises(HTTPException) as error:
        await video_notes.retry_coverage_review('note',SimpleNamespace(id='other-owner'))
    assert error.value.status_code==code
    db.update_task.assert_not_called()
