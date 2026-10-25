"""A model-only save must not overwrite a concurrently saved credential."""
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest

from api.user_settings import get_user_settings, save_user_settings


def test_concurrent_model_save_preserves_a_new_key(mock_database, monkeypatch):
    import api.user_settings as settings
    monkeypatch.setattr(settings, 'DATABASE_PATH', mock_database.db_path)
    save_user_settings('owner', {'llm_provider':'server'})
    snapshot_read, release, writer_started, writer_finished = (threading.Event() for _ in range(4))
    original = settings._load_preferences
    reads = 0
    def load(owner):
        nonlocal reads
        saved = original(owner)
        if threading.current_thread().name.startswith('stale-save'):
            reads += 1
            if reads == 2:
                snapshot_read.set()
                assert release.wait(5)
        return saved
    monkeypatch.setattr(settings, '_load_preferences', load)
    def key_save():
        writer_started.set()
        try:
            save_user_settings('owner', {'llm_api_key':'synthetic-new-secret'})
        finally:
            writer_finished.set()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='stale-save') as slow, ThreadPoolExecutor(max_workers=1) as fast:
        pending = slow.submit(save_user_settings, 'owner', {'llm_model':'selected-model'})
        try:
            assert snapshot_read.wait(5)
            key = fast.submit(key_save)
            assert writer_started.wait(5)
            writer_finished.wait(1)
        finally:
            release.set()
        pending.result(timeout=5)
        key.result(timeout=5)
    saved = get_user_settings('owner')
    assert saved['llm_api_key'] == 'synthetic-new-secret'
    assert saved['llm_model'] == 'selected-model'


def test_unreadable_key_is_reported_and_its_ciphertext_survives_other_saves(mock_database, monkeypatch):
    import api.user_settings as settings
    monkeypatch.setattr(settings, 'DATABASE_PATH', mock_database.db_path)
    monkeypatch.setenv('MODEL_CREDENTIAL_KEY', 'synthetic-original-seed')
    save_user_settings('owner', {'llm_api_key':'synthetic-secret'})
    encrypted = settings._load_preferences('owner')['llm_api_key_encrypted']
    monkeypatch.setenv('MODEL_CREDENTIAL_KEY', 'synthetic-different-seed')
    result = save_user_settings('owner', {'whisper_model':'other-model'})
    assert result['llm_api_key_error']
    assert settings._load_preferences('owner')['llm_api_key_encrypted'] == encrypted
    monkeypatch.setenv('MODEL_CREDENTIAL_KEY', 'synthetic-original-seed')
    assert get_user_settings('owner')['llm_api_key'] == 'synthetic-secret'


def test_credential_diagnostics_expose_flags_not_keys_or_error_messages():
    from scripts.profile_library import settings_key_status
    result = settings_key_status({'llm_key_saved':True,'whisper_key_saved':False,
        'llm_api_key':'private-key','whisper_key_error':'private diagnostic detail'})
    assert result == {'llm_key_saved':1,'llm_key_error':0,'whisper_key_saved':0,'whisper_key_error':1}
    assert 'private' not in str(result)


def test_an_unreadable_saved_key_cannot_be_reassigned_to_a_new_endpoint():
    from api.model_settings import prepared_settings
    from api.custom_models import ModelConfigurationError
    saved = {'llm_provider':'server','llm_base_url':'https://first.example/v1','llm_api_key':'',
             'llm_api_key_error':'Saved key could not be opened'}
    with patch('api.model_settings.get_user_settings',return_value=saved):
        with pytest.raises(ModelConfigurationError, match='Re-enter'):
            prepared_settings('owner',{'llm_base_url':'https://different.example/v1'})
