"""Account-owned model routing, encrypted persistence, and redacted failures."""
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest

from api.custom_models import ModelConfigurationError, normalize_base_url, resolve_custom, public_model_error

PATCH = {"llm_provider":"custom", "llm_base_url":"https://models.example/v1", "llm_api_key":"private-summary-key", "llm_model":"chat-a",
         "transcription_provider":"custom", "whisper_base_url":"https://audio.example/v1", "whisper_api_key":"private-audio-key", "whisper_model":"speech-a"}


@pytest.mark.asyncio
async def test_save_masks_keys_and_persists_only_ciphertext(client, mock_database):
    response=await client.post('/api/settings',json=PATCH)
    assert response.status_code==200, response.text
    assert 'private-' not in response.text
    public=await client.get('/api/settings')
    assert public.json()['llm_key_saved'] and public.json()['whisper_key_saved']
    assert 'private-' not in public.text
    assert 'api_key' not in public.json()
    with sqlite3.connect(mock_database.db_path) as conn:
        stored=conn.execute('select preferences from user_settings').fetchall()
    assert 'private-' not in str(stored)
    assert '_encrypted' in str(stored)
    assert (await client.post('/api/settings',json={'whisper_model':'speech-b'})).status_code==200
    from api.user_settings import get_user_settings
    assert get_user_settings('local')['llm_api_key']==PATCH['llm_api_key']
    assert get_user_settings('other')['llm_api_key']==''


@pytest.mark.asyncio
async def test_changing_base_url_requires_a_new_key_before_any_probe(client):
    assert (await client.post('/api/settings',json=PATCH)).status_code==200
    with patch('api.custom_models.OpenAI') as sdk:
        result=await client.post('/api/settings/models',json={'kind':'summary','llm_base_url':'https://different.example/v1'})
        assert result.status_code==422
        assert 'Re-enter' in result.text
        sdk.assert_not_called()


@pytest.mark.asyncio
async def test_keys_can_be_removed_and_custom_missing_fields_do_not_silently_fall_back(client):
    assert (await client.post('/api/settings',json=PATCH)).status_code==200
    bad=await client.post('/api/settings',json={'llm_api_key':''})
    assert bad.status_code==422
    assert (await client.post('/api/settings',json={'llm_provider':'server','llm_api_key':''})).status_code==200
    assert not (await client.get('/api/settings')).json()['llm_key_saved']


@pytest.mark.parametrize('kind,prefix',[('summary','llm'),('transcription','whisper')])
def test_custom_settings_use_the_saved_model_and_never_server_credentials(kind,prefix):
    result=resolve_custom(PATCH,kind)
    assert result['model']==PATCH[prefix+'_model']
    assert result['api_key']==PATCH[prefix+'_api_key']
    assert result['base_url']==PATCH[prefix+'_base_url']
    assert result['custom_endpoint']


def test_custom_routing_ignores_stale_browser_model_and_is_never_a_global_transcriber():
    from api.llm_settings import resolve_llm_settings
    from transcriber import get_transcriber
    assert resolve_llm_settings(PATCH,'stale-browser-model')['model']=='chat-a'
    with patch('transcriber.Transcriber') as transcriber:
        get_transcriber('old-whisper',preferences=PATCH)
    transcriber.assert_called_once_with(api_key='private-audio-key',base_url='https://audio.example/v1',model='speech-a',custom_endpoint=True)


@pytest.mark.parametrize('url',['https://key@models.example/v1','https://models.example/v1?key=secret','https://models.example/v1/chat/completions','javascript:alert(1)'])
def test_rejects_invalid_api_roots(url):
    with pytest.raises(ModelConfigurationError):normalize_base_url(url)


@pytest.mark.parametrize('address',['127.0.0.1','10.0.0.1','169.254.169.254','::1'])
def test_cloud_cannot_send_model_keys_to_private_addresses(address):
    from api.custom_models import _check_destination
    with patch('api.custom_models.USE_SUPABASE',True),patch('api.custom_models.socket.getaddrinfo',return_value=[(0,0,0,'',(address,443))]):
        with pytest.raises(ModelConfigurationError):_check_destination(httpx.Request('GET','https://models.example/v1/models'))


@pytest.mark.parametrize('status,word',[(401,'key'),(402,'payment'),(429,'quota'),(404,'endpoint'),(500,'unavailable')])
def test_public_errors_have_actionable_labels_without_provider_body(status,word):
    error=RuntimeError('private-key secret endpoint body');error.status_code=status
    message=public_model_error(error,'summary')
    assert word in message.lower()
    assert 'private-key' not in message


@pytest.mark.asyncio
async def test_model_listing_and_both_probes_use_draft_settings_without_saving(client):
    provider=Mock()
    provider.__enter__=Mock(return_value=provider);provider.__exit__=Mock(return_value=False)
    provider.models.list.return_value=SimpleNamespace(data=[SimpleNamespace(id='chat-z'),SimpleNamespace(id='chat-a')])
    provider.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])
    provider.audio.transcriptions.create.return_value=SimpleNamespace(text='',segments=[])
    with patch('api.custom_models.OpenAI',return_value=provider) as sdk:
        listing=await client.post('/api/settings/models',json={**PATCH,'kind':'summary'})
        assert listing.json()['models']==['chat-a','chat-z']
        assert (await client.post('/api/settings/test-llm',json=PATCH)).status_code==200
        assert (await client.post('/api/settings/test-transcription',json=PATCH)).status_code==200
        assert sdk.call_args.kwargs['api_key']=='private-audio-key'
    assert not (await client.get('/api/settings')).json()['llm_key_saved']
    audio=provider.audio.transcriptions.create.call_args.kwargs
    assert audio['response_format']=='verbose_json' and audio['file'][1].startswith(b'RIFF')


@pytest.mark.asyncio
async def test_provider_failure_never_echoes_key_and_listing_allows_manual_model_fallback(client):
    error=RuntimeError('private-summary-key echoed by provider');error.status_code=404
    with patch('api.model_settings.probe_provider',side_effect=error):
        result=await client.post('/api/settings/models',json={**PATCH,'kind':'summary'})
    assert result.status_code==502
    assert 'manually' in result.text
    assert 'private-summary-key' not in result.text


def test_ciphertext_is_bound_to_owner_and_field():
    from api.model_credentials import encrypt_key,decrypt_key
    value=encrypt_key('a','llm_api_key','secret')
    assert decrypt_key('a','llm_api_key',value)=='secret'
    with pytest.raises(ValueError):decrypt_key('b','llm_api_key',value)
    with pytest.raises(ValueError):decrypt_key('a','whisper_api_key',value)


def test_concurrent_first_local_saves_share_one_complete_encryption_seed(monkeypatch,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import api.model_credentials as credentials
    monkeypatch.delenv('MODEL_CREDENTIAL_KEY',raising=False)
    monkeypatch.setattr(credentials,'SUPABASE_SERVICE_KEY','')
    monkeypatch.setattr(credentials,'DATA_DIR',tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens=list(pool.map(lambda i:credentials.encrypt_key('owner','llm_api_key',str(i)),range(16)))
    assert [credentials.decrypt_key('owner','llm_api_key',token) for token in tokens]==[str(i) for i in range(16)]
    assert len((tmp_path/'.model-credential-key').read_bytes())==32
