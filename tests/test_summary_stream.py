import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import pytest
from summary_errors import SummaryOutputError


def event(text=None, finish=None):
    return NS(choices=[NS(delta=NS(content=text),finish_reason=finish)])


@pytest.mark.parametrize('video',[False,True])
def test_summary_stream_accepts_usage_only_events_and_keeps_all_content(video):
    from summarizer import Summarizer
    from note_summarizer import NoteSummarizer
    subject=(NoteSummarizer if video else Summarizer)(api_key='fixture',base_url='https://api.groq.com/openai/v1',model='openai/gpt-oss-120b')
    create=Mock(return_value=iter([NS(choices=[]),event('first '),NS(choices=[]),event('last','stop'),NS(choices=[])]))
    progress=Mock()
    with patch.object(subject.client.chat.completions,'create',create):
        if video:
            value=subject._call_llm.__wrapped__(subject,'system','user',progress)
        else:
            value=subject._call_llm_with_retry.__wrapped__(subject,'user',progress).choices[0].message.content
    assert value=='first last'
    assert progress.call_count==2
    assert create.call_args.kwargs['max_completion_tokens']==32768
    assert create.call_args.kwargs['reasoning_effort']=='low'


@pytest.mark.parametrize('video',[False,True])
@pytest.mark.parametrize('finish',['length','content_filter'])
def test_incomplete_stream_cannot_be_saved_as_success(video,finish):
    from summarizer import Summarizer
    from note_summarizer import NoteSummarizer
    subject=(NoteSummarizer if video else Summarizer)(api_key='fixture',base_url='https://api.groq.com/openai/v1')
    with patch.object(subject.client.chat.completions,'create',return_value=iter([event('partial',finish)])):
        with pytest.raises(SummaryOutputError):
            if video:subject._call_llm.__wrapped__(subject,'system','user',Mock())
            else:subject._call_llm_with_retry.__wrapped__(subject,'user',Mock())


def test_output_error_is_actionable_and_provider_bodies_stay_private():
    from api.llm_settings import safe_provider_error
    assert 'output limit' in safe_provider_error(SummaryOutputError('length'))
    assert 'invalid summary format' in safe_provider_error(SummaryOutputError('private provider text'))
    assert 'private provider text' not in safe_provider_error(ValueError('private provider text'))
    error=RuntimeError('private provider body');error.status_code=503
    assert 'temporarily unavailable' in safe_provider_error(error)
