import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from scripts.review_saved_model_samples import generate_case, write_review


def saved_settings(monkeypatch, key='saved-private-key'):
    from api import user_settings
    settings = dict(llm_provider='custom', llm_base_url='https://models.example/v1',
                    llm_model='selected-model', llm_api_key=key)
    monkeypatch.setattr(user_settings, 'get_user_settings', lambda owner: settings)
    return settings


def test_unreadable_saved_key_cannot_fall_back_to_a_server_provider(monkeypatch):
    from api.custom_models import ModelConfigurationError
    saved_settings(monkeypatch, key='')
    with pytest.raises(ModelConfigurationError, match='save the API key'):
        generate_case('owner', 'podcast', 'episode')


def test_podcast_review_uses_saved_provider_and_does_not_persist(monkeypatch):
    from api import db
    import summarizer
    saved_settings(monkeypatch)
    database = Mock()
    database.get_episode.return_value = NS(pid='show', title='Original title')
    database.get_transcript.return_value = NS(language='en',duration=60,text='Actual source.',segments=[dict(start=0,end=60,text='Actual source.')])
    database.get_podcast.return_value = NS(title='Show')
    monkeypatch.setattr(db, 'get_db', lambda owner: database)
    result = summarizer.Summary('episode','Original title','Overview',[],[],[])
    engine = Mock(); engine.summarize.return_value = result
    constructor = Mock(return_value=engine)
    monkeypatch.setattr(summarizer, 'Summarizer', constructor)
    output = generate_case('owner', 'podcast', 'episode')
    constructor.assert_called_once_with(api_key='saved-private-key',base_url='https://models.example/v1',model='selected-model',custom_endpoint=True)
    assert output['model']=='selected-model' and output['result']['title']=='Original title'
    assert 'saved-private-key' not in json.dumps(output)
    assert {call[0] for call in database.method_calls} == {'get_episode','get_transcript','get_podcast'}
    engine.save_summary.assert_not_called()
    engine.client.close.assert_called_once()


@pytest.mark.parametrize('normalized', [False, True])
def test_video_review_is_owner_scoped_and_never_updates_the_task(monkeypatch, normalized):
    import video_task_db, note_summarizer
    saved_settings(monkeypatch)
    database = Mock()
    database.get_task.return_value = dict(title='Video',style='detailed',formats=['summary'],duration=60,
        transcript_json=json.dumps(dict(text='Actual source.',segments=[dict(start=0,end=60,text='Actual source.')],duration=60)))
    if normalized:
        from api.supabase_db import SupabaseDatabase
        database.get_task.return_value = SupabaseDatabase._video_task_to_dict(database.get_task.return_value)
        assert 'transcript_json' not in database.get_task.return_value
    monkeypatch.setattr(video_task_db,'get_video_task_db',lambda:database)
    engine=Mock();engine.generate_note.return_value='# Video\n\nGenerated review.'
    constructor=Mock(return_value=engine)
    monkeypatch.setattr(note_summarizer,'NoteSummarizer',constructor)
    progress=Mock()
    result=generate_case('owner','video','task',progress=progress)
    database.get_task.assert_called_once_with('task','owner')
    assert [call[0] for call in database.method_calls]==['get_task']
    assert result['result'].startswith('# Video') and result['provider']=='saved_custom'
    assert constructor.call_args.kwargs['api_key']=='saved-private-key'
    assert engine.generate_note.call_args.kwargs['progress_callback'] is progress
    engine.client.close.assert_called_once()


def test_review_file_is_private_and_cannot_overwrite_an_existing_sample(tmp_path):
    target=tmp_path/'sample.json'
    write_review(target,{'result':'Private notes'})
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_review(target,{'result':'Replacement'})
    assert json.loads(target.read_text())=={'result':'Private notes'}
