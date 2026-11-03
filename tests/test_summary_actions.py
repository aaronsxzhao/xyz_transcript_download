"""Summary deletion preserves source data; podcast checkpoints cannot regress."""
from unittest.mock import Mock

import pytest

from api.schemas import ProcessingStatus
from processing_execution import Execution, ProcessingPaused, bind
from summary_errors import ProcessingCancelledError
from video_task_db import _SQLiteVideoTaskDB


def test_video_summary_deletion_retains_source_and_transcript(tmp_path):
    db = _SQLiteVideoTaskDB(tmp_path / 'video.sqlite')
    task = db.create_task({'user_id':'owner','url':'https://example.test/video','title':'Saved source','status':'success'})
    db.update_task(task, {'markdown':'Notes','transcript_json':'{"text":"Transcript"}'})
    db.add_version(task,'Older notes','detailed','model')
    assert db.delete_summary(task,'other') == 'not_found'
    assert db.get_versions(task)
    assert db.delete_summary(task,'owner') == 'applied'
    saved = db.get_task(task,'owner')
    assert saved['status']=='discovered' and saved['markdown']==''
    assert saved['title']=='Saved source' and saved['url']=='https://example.test/video'
    assert saved['transcript']['text']=='Transcript'
    assert db.get_versions(task)==[]
    # Existing retry can reuse the retained transcript and create a fresh version.
    db.update_task(task,{'status':'pending'})
    assert db.get_task(task,'owner')['status']=='pending'


def test_video_summary_deletion_refuses_active_task(tmp_path):
    db = _SQLiteVideoTaskDB(tmp_path / 'video.sqlite')
    task=db.create_task({'user_id':'owner','status':'summarizing'})
    db.add_version(task,'Previous summary')
    assert db.delete_summary(task,'owner')=='busy'
    assert db.get_versions(task)


@pytest.mark.parametrize('outcome,exception',[('lease_rejected',ProcessingPaused),('cancel_requested',ProcessingCancelledError)])
def test_podcast_worker_receipt_stops_old_work(monkeypatch,outcome,exception):
    from api import job_persistence as history
    provider=Mock()
    provider.rpc.return_value.execute.return_value.data=[{'id':'ordered','outcome':outcome}]
    monkeypatch.setattr(history,'USE_SUPABASE',True)
    monkeypatch.setattr(history,'client',lambda:provider)
    job=ProcessingStatus(job_id='ordered',user_id='owner',status='summarizing',revision=3)
    execution=Execution('owner','source',Mock(),queue_id='queue',lease_owner='worker')
    with bind(execution),pytest.raises(exception): history.save_job(job)
    name,params=provider.rpc.call_args.args
    assert name=='save_processing_jobs_ordered'
    assert params['p_work']=='queue' and params['p_worker']=='worker'
    assert params['p_create'] is False


def test_podcast_rejected_snapshot_reconciles_memory(monkeypatch):
    from api import job_persistence as history
    from api.routers import processing
    provider=Mock()
    old=ProcessingStatus(job_id='ordered',user_id='owner',status='summarizing',revision=3)
    winner=old.model_copy(update={'status':'completed','revision':4})
    provider.rpc.return_value.execute.return_value.data=[{'id':'ordered','outcome':'terminal','payload':winner.model_dump()}]
    monkeypatch.setattr(history,'USE_SUPABASE',True)
    monkeypatch.setattr(history,'client',lambda:provider)
    monkeypatch.setattr(processing,'jobs',{'ordered':old})
    history.save_job(old)
    assert processing.jobs['ordered'].status=='completed'
    assert processing.jobs['ordered'].revision==4


@pytest.mark.parametrize('current,next_status',[('completed','transcribing'),('cancelled','completed'),('cancelling','summarizing')])
def test_local_podcast_terminal_state_does_not_regress(monkeypatch,current,next_status):
    from api.routers import processing
    job=ProcessingStatus(job_id='ordered',user_id='owner',status=current,revision=4)
    monkeypatch.setattr(processing,'jobs',{'ordered':job})
    processing.update_job_status('ordered',next_status,50)
    assert job.status==current and job.revision==4
