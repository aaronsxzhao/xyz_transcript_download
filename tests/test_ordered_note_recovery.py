from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from video_task_db import VideoTaskDB, _SQLiteVideoTaskDB
from api.routers import maintenance

@pytest.fixture
def recovery(tmp_path,monkeypatch):
    db=VideoTaskDB.__new__(VideoTaskDB)
    db._backend=_SQLiteVideoTaskDB(tmp_path/'notes.sqlite')
    db.create_task({'id':'note','user_id':'owner','status':'failed'})
    monkeypatch.setattr('api.save_outbox.ROOT',tmp_path/'outbox')
    monkeypatch.setattr('api.save_outbox.USE_SUPABASE',False)
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr('api.routers.video_notes._invalidate_list_cache',lambda _:None)
    payload=dict(task_id='note',user_id='owner',content='synthetic recovery',version_id='recovery',style='detailed',model='test',warning='',recovery_order={'base_versions':[],'work_id':None})
    return db,payload

def test_recovery_cannot_overwrite_completion_during_backup_read(recovery,monkeypatch):
    db,payload=recovery
    def read(*_):
        db.complete_task('note','newer generation','detailed','test','owner',version_id='newer')
        return payload
    monkeypatch.setattr('api.save_outbox.pending',read)
    with pytest.raises(maintenance.HTTPException) as exc:
        maintenance.retry_save('note',SimpleNamespace(id='owner'))
    assert exc.value.status_code==409
    assert db.get_task('note','owner')['markdown']=='newer generation'
    assert db.get_version('note','recovery') is None

def test_recovery_rejects_older_generation_even_after_newer_task_fails(recovery):
    db,payload=recovery
    db.complete_task('note','newer generation','detailed','test','owner',version_id='newer')
    db.update_task('note',{'status':'pending'})
    db.update_task('note',{'status':'failed'})
    assert db.recover_note('note','owner',db.get_task('note','owner')['updated_at'],payload)=='superseded'
    assert db.get_task('note','owner')['markdown']=='newer generation'

def test_recovery_is_idempotent_and_legacy_copy_is_preserved(recovery):
    db,payload=recovery
    expected=db.get_task('note','owner')['updated_at']
    legacy={k:v for k,v in payload.items() if k!='recovery_order'}
    assert db.recover_note('note','owner',expected,legacy)=='unverified'
    assert db.recover_note('note','owner',expected,payload)=='applied'
    assert db.recover_note('note','owner',db.get_task('note','owner')['updated_at'],payload)=='already_saved'
    assert len(db.get_versions('note'))==1

def test_recovery_rejects_newer_queued_and_failed_attempt(recovery):
    from execution_store import Store
    db,payload=recovery
    store=Store(path=db._backend.db_path)
    work=store.enqueue('owner','video','note','note',{})
    expected=db.get_task('note','owner')['updated_at']
    assert db.recover_note('note','owner',expected,payload)=='busy'
    with store.connection() as conn:conn.execute("UPDATE processing_work SET state='failed' WHERE id=?",(work,))
    assert db.recover_note('note','owner',expected,payload)=='superseded'

def test_recovery_rejects_reclaimed_attempt_of_same_queue_record(recovery):
    from execution_store import Store
    db,payload=recovery
    store=Store(path=db._backend.db_path)
    work=store.enqueue('owner','video','note','note',{})
    payload['recovery_order'].update(work_id=work,work_attempt=1)
    with store.connection() as conn:conn.execute("UPDATE processing_work SET state='failed',attempts=2 WHERE id=?",(work,))
    assert db.recover_note('note','owner',db.get_task('note','owner')['updated_at'],payload)=='superseded'
    assert db.get_version('note','recovery') is None
