import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from video_task_db import _SupabaseVideoTaskDB
from processing_execution import Execution, ProcessingPaused, bind
from summary_errors import ProcessingCancelledError


def backend():
    db = _SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    db._lock = threading.Lock()
    db._cache = {}; db._dirty = {}; db._last_flush = {}
    db._sb = Mock()
    db._sb.update_video_task.return_value = 'applied'
    return db


def test_delayed_write_cannot_overtake_cancellation_and_other_tasks_keep_running():
    db = backend()
    started, release, cancelling = threading.Event(), threading.Event(), threading.Event()
    saved = {}; order = []
    def write(task, fields):
        if task == 'task' and fields['status'] == 'summarizing':
            started.set()
            assert release.wait(3)
        saved.setdefault(task, {}).update(fields)
        order.append((task, fields['status']))
        return 'applied'
    db._sb.update_video_task.side_effect = write
    def cancel():
        cancelling.set()
        db.update_task('task', {'status':'cancelled', 'progress':0})
    with ThreadPoolExecutor(3) as pool:
        old = pool.submit(db.update_task, 'task', {'status':'summarizing', 'title':'kept'})
        assert started.wait(2)
        new = pool.submit(cancel)
        assert cancelling.wait(2)
        try:
            pool.submit(db.update_task, 'other', {'status':'pending'}).result(timeout=1)
            assert not new.done()
        finally:
            release.set()
        old.result(); new.result()
    assert [state for task, state in order if task=='task'] == ['summarizing', 'cancelled']
    assert saved['task']['status'] == db._cache['task']['status'] == 'cancelled'
    assert saved['task']['title'] == 'kept' and not db._dirty


@pytest.mark.parametrize('outcome', ['stale', 'terminal', 'not_found'])
def test_rejected_patch_drops_optimistic_cache_and_is_not_retried(outcome):
    db = backend()
    db._sb.update_video_task.return_value = outcome
    db.update_task('task', {'status':'summarizing'})
    assert 'task' not in db._cache and 'task' not in db._dirty
    db.flush_task('task')
    assert db._sb.update_video_task.call_count == 1


def test_transport_failure_retains_patch_but_cancellation_wins_on_retry():
    db = backend()
    db._sb.update_video_task.side_effect = [RuntimeError('temporary'), 'applied']
    db.update_task('task', {'status':'summarizing', 'title':'kept'})
    assert db._dirty['task']['status'] == 'summarizing'
    db.update_task('task', {'status':'cancelled'})
    sent = db._sb.update_video_task.call_args.args[1]
    assert sent['status'] == 'cancelled' and sent['title'] == 'kept'
    assert not db._dirty


@pytest.mark.parametrize('outcome,exception', [('lease_rejected', ProcessingPaused),
                                              ('cancel_requested', ProcessingCancelledError)])
def test_fenced_worker_stops_without_requeueing_old_patch(outcome, exception):
    db = backend()
    db._sb.update_video_task.return_value = outcome
    execution = Execution('owner','source',Mock(),queue_id='work',lease_owner='worker')
    with bind(execution), pytest.raises(exception):
        db.update_task('task', {'status':'summarizing'})
    assert not db._dirty and not db._cache
    assert execution.cancelled == (outcome == 'cancel_requested')


def test_cloud_write_passes_lease_and_preserves_event_version():
    from api.supabase_db import SupabaseDatabase
    db = SupabaseDatabase.__new__(SupabaseDatabase)
    db.client = Mock()
    db.client.rpc.return_value.execute.return_value.data = 'applied'
    execution = Execution('owner','source',Mock(),queue_id='work',lease_owner='worker')
    with bind(execution):
        assert db.update_video_task('task', {'status':'summarizing', 'updated_at':'2026-01-01T00:00:00Z'}) == 'applied'
    name, params = db.client.rpc.call_args.args
    assert name == 'update_video_task_ordered'
    assert params['p_work']=='work' and params['p_worker']=='worker' and params['p_user']=='owner'
    assert params['p_patch']['updated_at']=='2026-01-01T00:00:00Z'


def test_worker_terminal_recovery_carries_identity_and_ignores_reclaimed_work(monkeypatch):
    from api.worker import Worker
    from processing_execution import CURRENT
    worker = Worker.__new__(Worker)
    worker.store = Mock(); worker.ident = 'old-worker'
    captured = []
    def update(*args):
        captured.append(CURRENT.get())
        raise ProcessingPaused()
    monkeypatch.setattr('video_task_db.get_video_task_db', lambda: SimpleNamespace(update_task=update))
    worker.sync_terminal({'id':'work', 'user_id':'owner', 'kind':'video', 'task_id':'task', 'payload':{}}, 'failed')
    assert captured[0].queue_id=='work' and captured[0].lease_owner=='old-worker'


def test_cancel_response_uses_persisted_success_when_final_save_wins(monkeypatch):
    from api.routers import video_notes
    db = Mock()
    db.get_task.side_effect = [{'status':'summarizing'}, {'status':'success'}]
    db.update_task.return_value = 'terminal'
    monkeypatch.setattr('video_task_db.get_video_task_db', lambda: db)
    monkeypatch.setattr('execution_store.enabled', lambda: False)
    try:
        result = video_notes.cancel_task('synthetic', SimpleNamespace(id='owner'))
        assert result['status'] == 'success'
    finally:
        video_notes._cancelled_tasks.discard('synthetic')


def test_cancellation_during_terminal_recovery_saves_cancelled(monkeypatch):
    from api.worker import Worker
    worker = Worker.__new__(Worker)
    worker.store = Mock(); worker.ident = 'worker'
    db = Mock()
    db.update_task.side_effect = [ProcessingCancelledError('Cancelled'), None]
    monkeypatch.setattr('video_task_db.get_video_task_db', lambda: db)
    worker.sync_terminal({'id':'work', 'user_id':'owner', 'kind':'video', 'task_id':'task', 'payload':{}}, 'failed')
    assert db.update_task.call_args.args[1]['status'] == 'cancelled'


@pytest.mark.parametrize('outcome', ['terminal', 'not_found'])
def test_terminal_domain_rejection_releases_worker_without_overwriting_notes(monkeypatch, outcome):
    from api.worker import Worker
    from processing_execution import ProcessingStopped
    db = backend()
    db._sb.update_video_task.return_value = outcome
    worker = Worker(store=Mock())
    execution = Execution('owner', 'source', worker.store, queue_id='work', lease_owner=worker.ident)
    work_after_rejection = Mock()
    def process(task, **kwargs):
        db.update_task(task, {'status':'summarizing'})
        work_after_rejection()
    monkeypatch.setattr('api.routers.video_notes.process_video_note_sync', process)
    worker.sync_terminal = Mock()
    try:
        worker.run({'id':'work', 'task_id':'task', 'user_id':'owner', 'kind':'video',
                    'state':'running', 'payload':{}, 'attempts':1}, execution)
    finally:
        worker.pool.shutdown()
    work_after_rejection.assert_not_called()
    worker.sync_terminal.assert_not_called()
    assert worker.store.finish.call_args.args[2] == 'cancelled'
    assert not db._cache and not db._dirty


def test_stale_progress_does_not_stop_valid_worker():
    db = backend()
    db._sb.update_video_task.return_value = 'stale'
    execution = Execution('owner','source',Mock(),queue_id='work',lease_owner='worker')
    with bind(execution):
        assert db.update_task('task', {'status':'summarizing'}) == 'stale'
