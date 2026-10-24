"""Deliver useful generated content when editorial checks fail; never fake success."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch

import pytest

from summarizer import Summarizer,Summary,KeyPoint
from transcriber import Transcript
from note_summarizer import NoteSummarizer
from summary_errors import SummaryOutputError,ProcessingCancelledError,DELIVERY_WARNING


def draft():
    return Summary('episode','Title','Available overview',[KeyPoint('Chapter','Generated detail','Real source.','')],['Chapter'],['Keep this'])


@pytest.mark.parametrize('error',[SummaryOutputError('coverage'),RuntimeError('private-provider-error'),json.JSONDecodeError('bad','x',0)])
def test_podcast_returns_generated_draft_when_audit_fails(error):
    engine=Summarizer(api_key='fixture')
    value=draft()
    response=NS(choices=[NS(message=NS(content=json.dumps({'overview':value.overview,'topics':value.topics,'takeaways':value.takeaways,'key_points':[vars(value.key_points[0])]})))])
    with patch.object(engine,'_call_llm_with_retry',return_value=response),patch.object(engine,'_audit_summary',side_effect=error):
        result=engine._summarize_single('episode','[00:01:00] Real source.','Show','Title')
    assert result.key_points[0].summary=='Generated detail'
    assert result.key_points[0].original_quote=='Real source.'
    assert result.key_points[0].timestamp=='00:01:00'
    assert DELIVERY_WARNING in result.overview
    assert 'private-provider-error' not in result.overview


def test_audit_failure_cannot_turn_generated_paraphrase_into_a_verbatim_quote():
    engine=Summarizer(api_key='fixture')
    response=NS(choices=[NS(message=NS(content=json.dumps({'overview':'Overview','topics':['A'],'takeaways':[],'key_points':[{'topic':'A','summary':'Available detail','original_quote':'Invented source quote','timestamp':'99:99'}]})))])
    with patch.object(engine,'_call_llm_with_retry',return_value=response),patch.object(engine,'_audit_summary',side_effect=SummaryOutputError('coverage')):
        result=engine._summarize_single('episode','Real source.','Show','Title')
    assert result.key_points[0].summary=='Available detail'
    assert result.key_points[0].original_quote==result.key_points[0].timestamp==''


def test_podcast_keeps_other_parts_and_original_source_for_a_failed_chunk():
    engine=Summarizer(api_key='fixture');engine.chunk_chars=12
    transcript=Transcript('episode','en',30,'first sourceSECOND SOURCE',[])
    with patch.object(engine,'_summarize_single',side_effect=[SummaryOutputError('invalid'),draft()]),patch.object(engine,'_call_llm_with_retry',side_effect=RuntimeError('merge failed')):
        result=engine._summarize_long_transcript(transcript,'Show','Title')
    assert DELIVERY_WARNING in result.overview
    assert any('first source' in point.summary for point in result.key_points)
    assert any(point.summary=='Generated detail' for point in result.key_points)
    assert any('原始转写' in topic for topic in result.topics)


def test_merge_failure_or_notice_cannot_discard_earlier_details():
    engine=Summarizer(api_key='fixture')
    first=draft();second=draft();second.key_points=[KeyPoint('B','Second detail','','')]
    with patch.object(engine,'_call_llm_with_retry',side_effect=RuntimeError('provider unavailable')):
        result=engine._merge_summaries('episode','Title',[first,second])
    assert [p.summary for p in result.key_points]==['Generated detail','Second detail']
    assert DELIVERY_WARNING in result.overview


@pytest.mark.parametrize('video',[False,True])
def test_audit_is_a_single_best_effort_pass_without_receipt_repair(video):
    engine=(NoteSummarizer if video else Summarizer)(api_key='fixture')
    callback=Mock(return_value='{"coverage":[]}')
    if video:
        with patch.object(engine,'_call_llm',callback):
            result=engine._audit_note('Real source.','Available video draft')
        assert 'Available video draft' in result and DELIVERY_WARNING in result
    else:
        callback.return_value=NS(choices=[NS(message=NS(content='{"coverage":[]}'))])
        with patch.object(engine,'_call_llm_with_retry',callback):
            with pytest.raises(SummaryOutputError):engine._audit_summary(draft(),'Real source.')
    assert callback.call_count==1


@pytest.mark.parametrize('video',[False,True])
def test_cancellation_is_not_reported_as_a_delivered_summary(video):
    engine=(NoteSummarizer if video else Summarizer)(api_key='fixture')
    with patch.object(engine,'_audit_note_verified' if video else '_merge_summaries_verified',side_effect=ProcessingCancelledError('stop')):
        with pytest.raises(ProcessingCancelledError):
            if video:engine._audit_note('source','draft')
            else:engine._merge_summaries('episode','Title',[draft()])


def test_no_generated_podcast_content_still_reports_generation_failure():
    engine=Summarizer(api_key='fixture')
    with patch.object(engine,'_summarize_single',return_value=None):
        assert engine._summarize_long_transcript(Transcript('episode','en',10,'Source',[]),'Show','Title') is None


def test_processing_cancellation_during_draft_audit_propagates():
    class CancelledException(Exception):
        pass
    engine=Summarizer(api_key='fixture')
    value=draft()
    response=NS(choices=[NS(message=NS(content=json.dumps({'overview':value.overview,'topics':value.topics,'takeaways':[],'key_points':[vars(value.key_points[0])]})))])
    with patch.object(engine,'_call_llm_with_retry',return_value=response),patch.object(engine,'_audit_summary',side_effect=CancelledException('stop')):
        with pytest.raises(CancelledException):engine._summarize_single('episode','source','Show','Title')
