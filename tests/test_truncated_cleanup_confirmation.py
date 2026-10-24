"""Maintenance may only acknowledge confirmed deletions in the reviewed scope."""
from unittest.mock import Mock
import pytest


def item(episode_id):
    return {'episode_id':episode_id,'episode_title':episode_id,'percentage':20}


@pytest.fixture
def cleanup_db(monkeypatch):
    db=Mock()
    db.get_truncated_transcripts.return_value=[item('one'),item('two')]
    db.delete_transcript.return_value=True
    db.delete_summary.return_value=True
    db.has_summary.return_value=False
    monkeypatch.setattr('api.db.get_db',lambda owner:db)
    return db


@pytest.mark.asyncio
async def test_bulk_cleanup_only_deletes_reviewed_items(client,cleanup_db):
    response=await client.post('/api/truncated/cleanup',json={'episode_ids':['one']})
    assert response.status_code==200
    cleanup_db.delete_transcript.assert_called_once_with('one')
    cleanup_db.delete_summary.assert_called_once_with('one')


@pytest.mark.asyncio
async def test_an_explicit_empty_review_does_not_mean_delete_everything(client,cleanup_db):
    response=await client.post('/api/truncated/cleanup',json={'episode_ids':[]})
    assert response.status_code==200
    assert response.json()['deleted']==[]
    cleanup_db.delete_transcript.assert_not_called()


@pytest.mark.asyncio
async def test_rejected_primary_deletion_preserves_summary_and_reports_failure(client,cleanup_db):
    cleanup_db.delete_transcript.return_value=False
    response=await client.post('/api/truncated/cleanup',json={'episode_ids':['one']})
    assert response.status_code==200
    body=response.json()
    assert body['deleted']==[]
    assert body['failed'][0]['episode_id']=='one'
    assert 'confirm' in body['failed'][0]['detail'].lower()
    cleanup_db.delete_summary.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_failure_does_not_hide_successes_or_stop_unrelated_items(client,cleanup_db):
    cleanup_db.get_truncated_transcripts.return_value=[item('rejected'),item('exception'),item('confirmed')]
    cleanup_db.delete_transcript.side_effect=[False,RuntimeError('private storage detail'),True]
    response=await client.post('/api/truncated/cleanup')
    assert response.status_code==200
    body=response.json()
    assert [r['episode_id'] for r in body['deleted']]==['confirmed']
    assert {r['episode_id'] for r in body['failed']}=={'rejected','exception'}
    assert 'private storage detail' not in response.text
    cleanup_db.delete_summary.assert_called_once_with('confirmed')


@pytest.mark.asyncio
async def test_single_rejected_deletion_is_not_a_success(client,cleanup_db):
    cleanup_db.delete_transcript.return_value=False
    response=await client.delete('/api/truncated/one')
    assert response.status_code==503
    cleanup_db.delete_summary.assert_not_called()


@pytest.mark.asyncio
async def test_already_absent_summary_is_not_a_false_cleanup_warning(client,cleanup_db):
    cleanup_db.delete_summary.return_value=False
    response=await client.post('/api/truncated/cleanup',json={'episode_ids':['one']})
    assert response.status_code==200
    assert len(response.json()['deleted'])==1
    assert response.json()['failed']==[]


@pytest.mark.asyncio
async def test_existing_summary_that_was_not_deleted_is_reported_as_partial(client,cleanup_db):
    cleanup_db.delete_summary.return_value=False
    cleanup_db.has_summary.return_value=True
    response=await client.post('/api/truncated/cleanup',json={'episode_ids':['one']})
    body=response.json()
    assert body['deleted'][0]['deleted_transcript'] is True
    assert body['failed'][0]['episode_id']=='one'
    assert 'summary' in body['failed'][0]['detail'].lower()


@pytest.mark.asyncio
async def test_a_repaired_transcript_is_skipped_after_the_review(client,cleanup_db):
    cleanup_db.get_truncated_transcripts.return_value=[]
    response=await client.post('/api/truncated/cleanup',json={'episode_ids':['one']})
    assert response.json()['skipped']==['one']
    cleanup_db.delete_transcript.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_cleanup_and_transcript_only_cleanup_remain_compatible(client,cleanup_db):
    response=await client.post('/api/truncated/cleanup?delete_summaries=false')
    assert response.status_code==200
    assert len(response.json()['deleted'])==2
    cleanup_db.delete_summary.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('body',[{}, {'episode_ids':None}])
async def test_incomplete_review_body_is_not_a_delete_all_request(client,cleanup_db,body):
    response=await client.post('/api/truncated/cleanup',json=body)
    assert response.status_code==422
    cleanup_db.delete_transcript.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('path',['/api/truncated','/api/truncated/cleanup'])
async def test_percentage_thresholds_cannot_accidentally_select_every_transcript(client,cleanup_db,path):
    method=client.get if path=='/api/truncated' else client.post
    response=await method(path+'?threshold=85')
    assert response.status_code==422
    cleanup_db.delete_transcript.assert_not_called()
