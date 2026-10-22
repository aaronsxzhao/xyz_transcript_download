"""Coverage-preserving podcast editing and backwards-compatible exports."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import pytest
from summarizer import Summarizer, Summary, KeyPoint, merge_summaries
from summary_errors import SummaryOutputError


def note(points, overview='### 核心结论\n- Supply is conditional.\n\n### 节目概览\nAn introduction.', topics=None):
    return Summary('episode','Original title',overview,points,topics or list(dict.fromkeys(p.topic for p in points)),['Track realized production.'])


def point(text, topic='原有大标题', quote='source', timestamp='00:30:00'):
    return KeyPoint(topic,text,quote,timestamp)


def response(data):
    return NS(choices=[NS(message=NS(content=json.dumps(data)))])


def subject():
    return Summarizer(api_key='fixture',base_url='https://api.groq.com/openai/v1')


def test_refinement_keeps_all_same_chapter_claims_and_their_own_evidence():
    accurate=note([point('#### 库存\n\n12%, excluding China.','原有大标题','first quote'),point('#### 消费\n\nConditional on B50.','原有大标题','second quote')])
    fast=note([point('#### 库存\n\n12%, excluding China.','原有大标题','first quote'),point('A distinct historical case.')])
    merged=merge_summaries(fast,accurate)
    assert [p.summary for p in merged.key_points]==[p.summary for p in accurate.key_points]+['A distinct historical case.']
    assert [p.original_quote for p in merged.key_points[:2]]==['first quote','second quote']


def test_synthesis_changes_outline_without_dropping_or_rewriting_details():
    first=note([point('#### 基准\n\n1 percentage point; 20%.')])
    second=note([point('#### 极端\n\n1.5 percentage points; if crop loss occurs.','价格弹性')])
    data={'overview':'### 核心结论\n- One episode.\n\n### 节目概览\nA coherent introduction.','topic_groups':[{'topic':'原有大标题','sources':['1:0','0:0']}],'takeaways':['Check forecast conditions.']}
    s=subject()
    with patch.object(s,'_call_llm_with_retry',return_value=response(data)) as call:
        merged=s._merge_summaries('episode','Original title',[first,second])
    assert merged.title=='Original title'
    assert merged.topics==['原有大标题']
    assert [p.summary for p in merged.key_points]==[first.key_points[0].summary,second.key_points[0].summary]
    assert [p.original_quote for p in merged.key_points]==['source','source']
    assert [p.timestamp for p in merged.key_points]==['00:30:00','00:30:00']
    assert 'source' not in call.call_args.args[0].split('<chunk_outlines>')[1] # quotes never rewritten
    assert merged.overview.count('coherent introduction')==1
    assert 'not extracting' in call.call_args.kwargs['system_prompt']


@pytest.mark.parametrize('ids',[['0:0'],['0:0','0:0','1:0'],['0:0','2:0'],[{}]])
def test_missing_duplicate_or_unknown_chapter_ids_cannot_be_saved(ids):
    s=subject()
    data={'overview':'Intro','topic_groups':[{'topic':'Chapter','sources':ids}],'takeaways':[]}
    with patch.object(s,'_call_llm_with_retry',return_value=response(data)):
        with pytest.raises(SummaryOutputError):
            s._merge_summaries('episode','Title',[note([point('A')]),note([point('B')])])


def test_one_chunk_avoids_an_extra_model_call_and_restores_episode_identity():
    s=subject()
    with patch.object(s,'_call_llm_with_retry') as llm:
        result=s._merge_summaries('episode','Original title',[note([point('Complete detail')])])
    llm.assert_not_called()
    assert result.episode_id=='episode' and result.title=='Original title'


def test_regeneration_supplies_existing_titles_and_keeps_markdown_and_qualifiers():
    s=subject()
    data={'overview':'### 核心结论\n- Conditional.\n\n### 节目概览\nOverview.','topics':['原有大标题'],'key_points':[{'topic':'原有大标题','summary':'#### 价格情景\n\n**1 个百分点**；全球不含中国。','original_quote':'source','timestamp':''}],'takeaways':['Check the forecast.']}
    with patch.object(s,'_call_llm_with_retry',return_value=response(data)) as llm, patch.object(s, '_audit_summary', side_effect=lambda summary, source, callback: summary):
        result=s._summarize_single('episode','source','podcast','Original title',existing_topics=['原有大标题'])
    assert '原有大标题' in llm.call_args.args[0]
    assert result.key_points[0].summary==data['key_points'][0]['summary']
    assert result.key_points[0].timestamp==''


def test_source_timestamps_are_absolute_and_unsegmented_text_is_not_lost():
    from transcriber import Transcript, TranscriptSegment
    t=Transcript('episode','zh',3700,'甲乙丙',[TranscriptSegment(0,1,'甲'),TranscriptSegment(1,2,'乙'),TranscriptSegment(3601,3602,'丙')])
    marked=Summarizer._transcript_text(t)
    assert '[00:00:00] 甲' in marked and '\n乙\n[01:00:01] 丙' in marked
    t.text+='附加内容'
    assert Summarizer._transcript_text(t)==t.text


def test_html_and_markdown_exports_keep_hierarchy_and_escape_untrusted_content():
    from viewer import export_html, export_markdown
    n=note([point('#### 模型\n\n**1 个百分点**。\n\n|范围|值|\n|---|---|\n|不含中国|12%|\n\n<script>bad()</script>')])
    html=export_html(n)
    assert '<h4>模型</h4>' in html and '<table>' in html
    assert '<strong>1 个百分点</strong>' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '<details class="quote">' in html and '00:30:00' in html
    md=export_markdown(n)
    assert '#### 模型' in md and '**#### 模型' not in md


def test_refinement_does_not_discard_distinct_evidence_for_the_same_claim():
    merged=merge_summaries(note([point('A claim',quote='Additional example')]),note([point('A claim',quote='Original example')]))
    assert [p.original_quote for p in merged.key_points]==['Original example','Additional example']


def test_chinese_emphasis_renders_without_altering_original_quotes_or_code():
    from viewer import export_html, normalize_summary_markdown
    text='**供需是基础。**天气是催化。\n\n`**原样。**代码`'
    assert normalize_summary_markdown(text)=='**供需是基础**。天气是催化。\n\n`**原样。**代码`'
    html=export_html(note([point(text,quote='**原话。**不能改')]))
    assert '<strong>供需是基础</strong>。天气是催化。' in html
    assert '<blockquote>**原话。**不能改</blockquote>' in html
