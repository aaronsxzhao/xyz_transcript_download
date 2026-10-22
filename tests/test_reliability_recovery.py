"""Durability, recovery exports, password privacy, and owner boundaries."""
import hashlib
import io
import json
import threading
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from fastapi import HTTPException
from video_task_db import VideoTaskDB, _SQLiteVideoTaskDB, _SupabaseVideoTaskDB


@pytest.fixture
def note_db(tmp_path, monkeypatch):
    import api.save_outbox as outbox
    import video_task_db
    monkeypatch.setattr(outbox, 'ROOT', tmp_path / 'outbox')
    monkeypatch.setattr(outbox, 'USE_SUPABASE', False)
    facade = VideoTaskDB.__new__(VideoTaskDB)
    facade._backend = _SQLiteVideoTaskDB(tmp_path / 'notes.sqlite')
    facade.create_task({'id': 'note-one', 'user_id': 'local', 'platform': 'youtube', 'title': 'Private note'})
    facade.update_task('note-one', {'markdown': 'original', 'status': 'saving'})
    monkeypatch.setattr(video_task_db, '_video_task_db', facade)
    monkeypatch.setattr(video_task_db, 'get_video_task_db', lambda: facade)
    return facade


def test_final_note_and_version_are_atomic_and_retry_is_idempotent(note_db):
    note_db.complete_task('note-one', '# Final note', 'detailed', 'paid-model', 'local', version_id='version-one')
    note_db.complete_task('note-one', '# Final note', 'detailed', 'paid-model', 'local', version_id='version-one')
    assert note_db.get_task('note-one', 'local')['status'] == 'success'
    assert len(note_db.get_versions('note-one')) == 1
    assert note_db.get_version('note-one', 'version-one')['content'] == '# Final note'
    with pytest.raises(ValueError):
        note_db.complete_task('note-one', 'wrong content', 'detailed', 'paid-model', 'local', version_id='version-one')
    assert note_db.get_task('note-one', 'local')['markdown'] == '# Final note'


def test_failed_final_save_rolls_back_version_and_keeps_recovery_copy(note_db):
    from api.save_outbox import pending
    with note_db._backend._conn() as conn:
        conn.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON video_tasks BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        conn.commit()
    with pytest.raises(Exception):
        note_db.complete_task('note-one', 'recoverable', 'detailed', 'model', 'local', version_id='retry-me')
    assert note_db.get_task('note-one', 'local')['markdown'] == 'original'
    assert note_db.get_versions('note-one') == []
    assert pending('local', 'note-one')['content'] == 'recoverable'
    with pytest.raises(ValueError):
        pending('different-owner', 'note-one')


def test_completion_cannot_modify_other_owner(note_db):
    with pytest.raises(ValueError):
        note_db.complete_task('note-one', 'other', 'detailed', 'model', 'someone-else')
    assert note_db.get_task('note-one', 'local')['markdown'] == 'original'


def test_cloud_failed_rpc_never_exposes_success(tmp_path, monkeypatch):
    import api.save_outbox as outbox
    monkeypatch.setattr(outbox, 'ROOT', tmp_path)
    monkeypatch.setattr(outbox, 'USE_SUPABASE', False)
    backend = _SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    backend._lock = threading.Lock()
    backend._cache = {'task': {'status': 'saving', 'markdown': 'old'}}
    backend.flush_task = Mock()
    backend._sb = SimpleNamespace(client=Mock())
    backend._sb.client.rpc.return_value.execute.side_effect = RuntimeError('Unavailable')
    db = VideoTaskDB.__new__(VideoTaskDB); db._backend = backend
    with pytest.raises(RuntimeError):
        db.complete_task('task', 'new', 'detailed', 'model', 'owner')
    assert backend._cache['task'] == {'status': 'saving', 'markdown': 'old'}
    assert outbox.pending('owner', 'task')['content'] == 'new'


@pytest.mark.asyncio
async def test_portable_zip_contains_only_owned_frames_and_reports_missing(client, note_db, monkeypatch):
    from api.routers import maintenance
    content = '# Private\n![frame](https://storage.example/storage/v1/object/public/screenshots/note-one_00-10.jpg)\n![missing](/data/screenshots/note-one_00-20.jpg?signature=abc)\n![external](https://example.com/other_00-10.jpg)'
    note_db.update_task('note-one', {'markdown': content, 'status': 'success'})
    image = Mock(side_effect=lambda name: b'image-bytes' if name.endswith('00-10.jpg') else (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(maintenance, '_image', image)
    r = await client.get('/api/maintenance/notes/note-one/bundle')
    assert r.status_code == 200 and 'no-store' in r.headers['cache-control']
    assert r.headers['x-missing-images'] == '1'
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        assert archive.read('images/note-one_00-10.jpg') == b'image-bytes'
        assert '(images/note-one_00-10.jpg)' in archive.read('note.md').decode()
        assert '(images/note-one_00-20.jpg)' in archive.read('note.md').decode()
        assert json.loads(archive.read('manifest.json'))['missing_images'] == ['note-one_00-20.jpg']
    assert image.call_count == 2
    note_db.create_task({'id': 'not-yours', 'user_id': 'other'})
    assert (await client.get('/api/maintenance/notes/not-yours/bundle')).status_code == 404
    assert (await client.post('/api/maintenance/notes/not-yours/repair-media')).status_code == 404
    assert (await client.post('/api/maintenance/notes/not-yours/retry-save')).status_code == 404


@pytest.mark.asyncio
async def test_retry_save_recovers_without_model_call(client, note_db):
    from api.save_outbox import retain
    retain(dict(task_id='note-one', content='recovered note', style='detailed', model='model', user_id='local', warning='', version_id='stable-retry'))
    note_db.update_task('note-one', {'status': 'failed'})
    r = await client.post('/api/maintenance/notes/note-one/retry-save')
    assert r.status_code == 200
    assert note_db.get_task('note-one', 'local')['markdown'] == 'recovered note'
    assert len(note_db.get_versions('note-one')) == 1


@pytest.mark.asyncio
async def test_retry_save_preserves_newer_completed_note(client, note_db):
    from api.save_outbox import retain
    retain(dict(task_id='note-one', content='old pending', style='detailed', model='model', user_id='local', warning='', version_id='older'))
    note_db.update_task('note-one', {'status': 'success', 'markdown': 'newer saved note'})
    r = await client.post('/api/maintenance/notes/note-one/retry-save')
    assert r.status_code == 409
    assert note_db.get_task('note-one', 'local')['markdown'] == 'newer saved note'


def test_screenshot_failure_has_visible_partial_result(note_db, monkeypatch):
    from api.routers import maintenance
    note_db.update_task('note-one', {'markdown': '![f](/data/screenshots/note-one_00-10.jpg)'})
    monkeypatch.setattr(maintenance, '_existing', lambda: set())
    monkeypatch.setattr(maintenance, '_save_report', Mock())
    with patch('video_downloader.get_downloader') as downloader:
        downloader.return_value.download_video.side_effect = RuntimeError('auth failed')
        maintenance._repair(note_db.get_task('note-one', 'local'), 'local', 'key')
    report = maintenance._save_report.call_args.args[1]
    assert report['status'] == 'failed'
    assert 'Reconnect' in report['message']
    assert note_db.get_task('note-one', 'local')['markdown'].startswith('![f]')


def test_password_range_check_never_sends_password_or_full_hash():
    from api.passwords import validate_new_password
    password = 'Strong unique test password 897!'
    digest = hashlib.sha1(password.encode()).hexdigest().upper()
    response = Mock(text=digest[5:] + ':12\n')
    with patch('api.passwords.httpx.get', return_value=response) as get:
        with pytest.raises(HTTPException) as err:
            validate_new_password(password)
    assert err.value.status_code == 400
    url = get.call_args.args[0]
    assert url.endswith('/' + digest[:5]) and digest not in url and password not in url
    with patch('api.passwords.httpx.get', side_effect=httpx.ConnectError('offline')):
        with pytest.raises(HTTPException) as err:
            validate_new_password(password)
    assert err.value.status_code == 503


@pytest.mark.asyncio
async def test_reset_provider_error_is_not_reported_as_success(client):
    provider = Mock(); provider.auth.reset_password_email.side_effect = RuntimeError('provider unavailable')
    with patch('api.routers.auth_router.USE_SUPABASE', True), patch('api.routers.auth_router.get_supabase_client', return_value=provider):
        r = await client.post('/api/auth/password-reset', json={'email': 'recovery-test@example.com'})
    assert r.status_code == 503 and 'provider unavailable' not in r.text


def test_restart_marks_active_videos_failed_without_clearing_content():
    from api import job_persistence
    client = Mock()
    with patch.object(job_persistence, 'USE_SUPABASE', True), patch.object(job_persistence, 'client', return_value=client):
        job_persistence.reconcile_video_jobs()
    updates = client.table.return_value.update.call_args.args[0]
    assert updates['status'] == 'failed'
    assert 'markdown' not in updates and 'transcript_json' not in updates


def test_missing_screenshot_references_survive_until_a_media_retry(tmp_path, monkeypatch):
    import screenshot_extractor
    monkeypatch.setattr(screenshot_extractor, 'SCREENSHOTS_DIR', tmp_path)
    markdown = screenshot_extractor.replace_screenshot_markers('Keep this idea. Screenshot-[01:25]', 'task-id', keep_missing=True)
    assert 'Keep this idea.' in markdown and '/data/screenshots/task-id_01-25.jpg' in markdown
    from api.routers.maintenance import references
    assert references(markdown, 'task-id') == {'task-id_01-25.jpg': 85}


@pytest.mark.asyncio
async def test_cloud_history_failure_keeps_new_job_retryable_without_blocking_loop(monkeypatch):
    from api.routers import processing
    from api.schemas import ProcessingStatus
    import asyncio
    loop_thread = threading.get_ident()
    observed = []
    def fail(job):
        observed.append(threading.get_ident())
        raise RuntimeError('Cloud unavailable')
    monkeypatch.setattr('api.job_persistence.save_job', fail)
    job = ProcessingStatus(job_id='job', user_id='owner', status='pending', source_url='https://www.xiaoyuzhoufm.com/episode/example')
    with pytest.raises(HTTPException) as err:
        await processing._persist_new_job(job)
    assert err.value.status_code == 503 and job.status == 'failed'
    assert observed[0] != loop_thread
    assert job.source_url.endswith('/example')


@pytest.mark.asyncio
async def test_slow_episode_lookup_does_not_pause_the_website(client):
    import asyncio
    entered, release = threading.Event(), threading.Event()
    loop_thread = threading.get_ident()
    observed = []
    def lookup(url):
        observed.append(threading.get_ident()); entered.set(); release.wait(2)
        return None
    # Admission now reads saved metadata only; a slow database read must still
    # run off the event loop while other pages remain responsive.
    with patch('api.routers.processing.get_db') as database:
        database.return_value.get_episode.side_effect = lookup
        pending = asyncio.create_task(client.post('/api/process', json={'episode_url': 'https://www.xiaoyuzhoufm.com/episode/slow'}))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            response = await asyncio.wait_for(client.get('/api/health'), timeout=.3)
            assert response.status_code == 200 and observed[0] != loop_thread
        finally:
            release.set()
            await pending


def test_late_checkpoint_cannot_resurrect_deleted_job_history(monkeypatch):
    from api import job_persistence
    from api.schemas import ProcessingStatus
    provider = Mock()
    monkeypatch.setattr(job_persistence, 'USE_SUPABASE', True)
    monkeypatch.setattr(job_persistence, 'client', lambda: provider)
    job = ProcessingStatus(job_id='deleted-history-check', user_id='owner', status='transcribing')
    try:
        job_persistence.delete_job(job.job_id, job.user_id)
        job_persistence.save_job(job)
        assert provider.table.return_value.upsert.call_count == 0
        provider.table.return_value.delete.return_value.eq.assert_called_once_with('id', job.job_id)
    finally:
        job_persistence._deleted.discard(job.job_id)


@pytest.mark.asyncio
async def test_retry_preserves_regeneration_intent_and_model_choice(client):
    from api.routers import processing
    from api.schemas import ProcessingStatus
    from api.auth import User
    from fastapi import BackgroundTasks
    processing.jobs['old-attempt'] = ProcessingStatus(job_id='old-attempt', user_id='local', status='failed',
        source_url='apple://saved-episode', resummarize=True, llm_model='original-paid-model')
    background = BackgroundTasks()
    result = await processing.retry_job('old-attempt', background, User(id='local', email='local@localhost'))
    retried = processing.jobs[result['new_job_id']]
    assert retried.resummarize and retried.llm_model == 'original-paid-model'
    assert background.tasks[0].kwargs['resummarize'] is True
    assert background.tasks[0].kwargs['llm_model'] == 'original-paid-model'
