"""Model formatting errors must not throw away otherwise readable content."""
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from summarizer import Summarizer,extract_json_from_response
from summary_errors import DELIVERY_WARNING,SummaryOutputError


@pytest.mark.parametrize('raw',[
    'Here is the result:\n```json\n{"overview":"Text }, ] with braces { and escaped \\\"quotes\\\"", "key_points":[],}\n```',
    '{"overview":"Text }, ] with braces { and escaped \\\"quotes\\\"", "key_points":[],}',
])
def test_repairs_only_json_packaging_and_preserves_string_content(raw):
    data=extract_json_from_response(raw)
    assert data['overview']=='Text }, ] with braces { and escaped "quotes"'
    assert data['key_points']==[]


@pytest.mark.parametrize('points',[
    [{'topic':'A','summary':'First detail'},None,{'topic':'B','text':'Second detail'}],
    {'A':'First detail','B':'Second detail'},
    ['First detail','Second detail'],
])
def test_compatible_point_shapes_keep_every_readable_item(points):
    summary=Summarizer._parse_summary({'data':{'overview':'Overview','key_points':points,'topics':'Original heading','takeaways':None}},'episode','Title')
    assert [point.summary for point in summary.key_points]==['First detail','Second detail']
    assert 'Original heading' in summary.topics


def test_format_normalization_keeps_markdown_code_indentation():
    body='    # source comment\n    print(42)'
    result=Summarizer._parse_summary({'overview':'Overview','key_points':[{'topic':'Code','summary':body}]},'episode','Title')
    assert result.key_points[0].summary==body


@pytest.mark.parametrize('content',['# Readable notes\n\nKeep the original explanation.', '{"overview":"Overview only","topics":null,"key_points":null}', json.dumps('Readable model prose')])
def test_delivers_readable_prose_or_overview_without_requiring_valid_points(content):
    engine=Summarizer(api_key='fixture')
    response=NS(choices=[NS(message=NS(content=content))])
    with patch.object(engine,'_call_llm_with_retry',return_value=response):
        result=engine._summarize_single('episode','Source '*400,'Show','Title')
    assert result.key_points and DELIVERY_WARNING in result.overview
    assert any(word in result.key_points[0].summary for word in ('Readable','Overview only'))
    assert result.key_points[0].original_quote==''


def test_a_broken_outer_document_cannot_silently_become_just_one_nested_point():
    content='{"overview":"Keep this introduction","key_points":[{"summary":"Nested detail"}]'
    with pytest.raises(json.JSONDecodeError):extract_json_from_response(content)
    engine=Summarizer(api_key='fixture')
    with patch.object(engine,'_call_llm_with_retry',return_value=NS(choices=[NS(message=NS(content=content))])):
        result=engine._summarize_single('episode','Source','Show','Title')
    assert 'Keep this introduction' in result.key_points[0].summary
    assert 'Nested detail' in result.key_points[0].summary


@pytest.mark.parametrize('content',[{},[],{'key_points':{'topic':'Only metadata'}}])
def test_metadata_only_output_still_is_not_a_readable_summary(content):
    with pytest.raises(SummaryOutputError):Summarizer._parse_summary(content,'episode','Title')
