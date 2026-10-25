"""Chunk indexes support a single complete introduction without dropping body text."""
from unittest.mock import patch
from types import SimpleNamespace as NS
from note_summarizer import NoteSummarizer
from summarizer import Summarizer
from podcast_prompts import CHUNK_INSTRUCTION


def test_podcast_chunk_uses_extraction_contract_instead_of_repeated_introduction():
    engine=Summarizer(api_key='fixture')
    response=NS(choices=[NS(message=NS(content='{"overview":"source index","topics":["Argument"],"key_points":[{"topic":"Argument","summary":"All details."}],"takeaways":[]}'))])
    with patch.object(engine,'_call_llm_with_retry',return_value=response) as call, patch.object(engine,'_audit_summary',side_effect=lambda summary,*args: summary):
        result=engine._summarize_single('episode','source','Podcast','Episode',source_context={'before':'','after':''})
    assert CHUNK_INSTRUCTION in call.call_args.kwargs['system_prompt']
    assert result.key_points[0].summary=='All details.' and result.takeaways==[]


def test_video_whole_conclusion_sees_every_chunk_and_preserves_detailed_body():
    engine=NoteSummarizer(api_key='fixture')
    chunks=['## A\nFirst detail.\n## AI Summary\nFirst source condition.', '## B\nLast detail.\n## AI Summary\nLast source condition.']
    with patch.object(engine,'_editorial_json',return_value={'overview':'Connected whole-video conclusion.'}) as call:
        result=engine._merge_chunk_notes('Title',chunks,False,whole_summary=True)
    assert 'First source condition.' in call.call_args.args[1] and 'Last source condition.' in call.call_args.args[1]
    assert 'First detail.' in result and 'Last detail.' in result
    assert '## AI Summary\n\nConnected whole-video conclusion.' in result
    assert 'Section conclusions' not in result


def test_video_conclusion_provider_failure_preserves_every_source_index():
    engine=NoteSummarizer(api_key='fixture')
    with patch.object(engine,'_editorial_json',side_effect=TimeoutError):
        result=engine._merge_chunk_notes('Title',['## A\nComplete detail.\n## AI Summary\nSource condition.'],False,whole_summary=True)
    assert 'Complete detail.' in result and 'Source condition.' in result
    assert 'Section conclusions' in result
