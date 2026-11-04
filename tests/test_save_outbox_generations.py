"""Cross-process and delayed-storage races use synthetic content only."""
import json
import multiprocessing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from api import save_outbox as outbox


def payload(version, attempt):
    return dict(task_id='task', user_id='owner', version_id=version, content='fixture-'+version,
                style='detailed', model='test', backup_created_at=attempt,
                recovery_order={'base_versions': [], 'work_id': 'work', 'work_attempt': attempt})


class Bucket:
    def __init__(self):
        self.objects = {}
        self.before_upload = None
    def upload(self, key, content, **kwargs):
        assert kwargs['file_options']['upsert'] == 'false'
        if self.before_upload:
            hook, self.before_upload = self.before_upload, None
            hook()
        if key in self.objects:
            raise FileExistsError(key)
        self.objects[key] = content
    def download(self, key):
        return self.objects[key]
    def remove(self, keys):
        for key in keys:
            self.objects.pop(key, None)
    def list(self, prefix, options):
        names = sorted(k[len(prefix)+1:] for k in self.objects if k.startswith(prefix+'/'))
        return [{'name': k} for k in names[options['offset']:options['offset']+options['limit']]]


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(outbox, 'ROOT', tmp_path)
    monkeypatch.setattr(outbox, 'USE_SUPABASE', True)
    monkeypatch.setattr('execution_store.enabled', lambda: True)
    store = Mock()
    store.latest.return_value = {'id': 'work', 'attempts': 2}
    monkeypatch.setattr('execution_store.get_store', lambda: store)
    bucket = Bucket()
    monkeypatch.setattr('api.supabase_client.get_supabase_admin_client',
                        lambda: SimpleNamespace(storage=SimpleNamespace(from_=lambda _: bucket)))
    return bucket


def test_old_cleanup_cannot_delete_new_local_or_cloud_backup(storage):
    old, new = payload('old', 1), payload('new', 2)
    outbox.retain(old); outbox.retain(new); outbox.clear(old)
    assert outbox.pending('owner', 'task')['version_id'] == 'new'
    assert outbox._location(new)[0].exists()
    assert outbox._location(new)[1] in storage.objects
    assert outbox._location(old)[1] not in storage.objects


def test_delayed_old_upload_cannot_replace_new_copy(storage):
    old, new = payload('old', 1), payload('new', 2)
    old['backup_created_at'] = 999  # A late old worker's clock is not authority.
    storage.before_upload = lambda: outbox.retain(new)
    outbox.retain(old)
    assert outbox.pending('owner', 'task')['version_id'] == 'new'
    for p in (old, new): outbox._location(p)[0].unlink()
    assert outbox.pending('owner', 'task')['version_id'] == 'new'
    assert len(storage.objects) == 2


def test_same_version_different_attempts_do_not_share_a_key(storage):
    old, new = payload('same-version', 1), payload('same-version', 2)
    outbox.retain(old);outbox.retain(new);outbox.clear(old)
    assert outbox.pending('owner', 'task')['recovery_order']['work_attempt'] == 2


def test_idempotent_retain_and_cleanup(storage):
    new = payload('new', 2)
    outbox.retain(new); outbox.retain(new)
    assert len(storage.objects) == 1
    outbox.clear(new); outbox.clear(new)
    assert not storage.objects


def test_legacy_backups_stay_readable_and_are_never_deleted(storage):
    legacy = payload('legacy', 1);legacy.pop('backup_created_at')
    path = outbox.ROOT/'task.json';path.write_text(json.dumps(legacy))
    storage.objects['pending/owner/task.json'] = json.dumps(legacy).encode()
    outbox.clear(legacy)
    assert path.exists() and 'pending/owner/task.json' in storage.objects
    assert outbox.pending('owner', 'task')['version_id'] == 'legacy'
    with pytest.raises(ValueError):outbox.pending('other', 'task')


def test_paginated_cloud_lookup_finds_current_generation(storage):
    for i in range(102):
        p = payload(str(i), 2 if i == 101 else 1)
        outbox.retain(p);outbox._location(p)[0].unlink()
    assert outbox.pending('owner', 'task')['version_id'] == '101'


def _process(root, old_ready, new_ready, result, older):
    from api import save_outbox
    save_outbox.ROOT = Path(root); save_outbox.USE_SUPABASE = False
    p = payload('old' if older else 'new', 1 if older else 2)
    if not older: assert old_ready.wait(5)
    save_outbox.retain(p)
    if older:
        old_ready.set(); assert new_ready.wait(5);save_outbox.clear(p)
    else:
        new_ready.set()
    result.put(True)


def test_two_processes_old_cleanup_preserves_new_failed_save(tmp_path, monkeypatch):
    monkeypatch.setattr(outbox, 'ROOT', tmp_path)
    monkeypatch.setattr(outbox, 'USE_SUPABASE', False)
    monkeypatch.setattr('execution_store.enabled', lambda: False)
    ctx = multiprocessing.get_context('spawn')
    old_ready, new_ready, result = ctx.Event(), ctx.Event(), ctx.Queue()
    processes = [ctx.Process(target=_process, args=(str(tmp_path),old_ready,new_ready,result,old)) for old in (True,False)]
    try:
        for process in processes: process.start()
        for process in processes:
            process.join(10); assert process.exitcode == 0
        assert result.get(timeout=2) and result.get(timeout=2)
        assert outbox.pending('owner', 'task')['version_id'] == 'new'
    finally:
        for process in processes:
            if process.is_alive():process.terminate();process.join(3)
        result.close()


def test_new_failed_save_remains_recoverable_after_old_cleanup(storage, tmp_path):
    from video_task_db import VideoTaskDB, _SQLiteVideoTaskDB
    from execution_store import Store
    db = VideoTaskDB.__new__(VideoTaskDB)
    db._backend = _SQLiteVideoTaskDB(tmp_path/'notes.sqlite')
    db.create_task({'id': 'task', 'user_id': 'owner', 'status': 'failed'})
    queue = Store(path=db._backend.db_path)
    work = queue.enqueue('owner', 'video', 'task', 'source', {})
    with queue.connection() as conn:
        conn.execute("UPDATE processing_work SET state='failed',attempts=2 WHERE id=?", (work,))
    old, new = payload('old', 1), payload('new', 2)
    for p in (old, new): p['recovery_order']['work_id'] = work
    outbox.retain(old);outbox.retain(new);outbox.clear(old)
    candidate = outbox.pending('owner', 'task')
    expected = db.get_task('task', 'owner')['updated_at']
    assert db.recover_note('task', 'owner', expected, candidate) == 'applied'
    assert db.get_task('task', 'owner')['markdown'] == new['content']
    assert db.get_version('task', 'old') is None
    assert db.get_version('task', 'new')['content'] == new['content']
