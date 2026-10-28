"""Reading edits keep source ownership in application code, not model grouping."""
import copy
import json
from unittest.mock import Mock, patch

import pytest

from focused_editor import edit_whole_note, _separate_media
from reading_budget import PLAN, make_plan, diagnostics
from summary_errors import ProcessingCancelledError


@pytest.fixture
def plan():
    token=PLAN.set(make_plan('English evidence. '*2000,840,'en'))
    yield
    PLAN.reset(token)


def rows():
    return [{'id':'N1','topic':'Costs','text':'Costs fall only for large orders.','evidence':'large orders'},
            {'id':'N2','topic':'Limit','text':'Durability is untested.','evidence':'untested'}]


def provider(system,payload,timeout):
    data=json.loads(payload)
    if 'rewrite' in data:
        return {'checks':[{'id':g['id'],'complete':True,'grounded':True} for g in data['groups']]}
    return {'sections':[{'id':g['id'],'topic':'Costs and limits','heading':'Conditional cost reduction',
        'text':'Costs fall for large orders; durability remains untested.',
        'evidence_id':g['notes'][-1]['id']} for g in data['groups']]}


def test_two_calls_preserve_sources_and_choose_original_evidence(plan):
    source=rows();before=copy.deepcopy(source);report={}
    call=Mock(side_effect=provider)
    result=edit_whole_note(source,call,report=report)
    assert source==before and result[0]['ids']==['N1','N2']
    assert result[0]['evidence_id']=='N2' and report['target_met']
    assert call.call_count==2
    payload=json.loads(call.call_args_list[0].args[1])
    assert 'evidence' not in payload['groups'][0]['notes'][0]
    assert payload['groups'][0]['notes'][0]['has_original_quote']


def test_actual_reserve_excludes_folded_quotes(plan):
    report={};call=Mock(side_effect=provider)
    edit_whole_note(rows(),call,report=report,reserved_text='Overview '*250+'\n\n> '+'quote '*1000)
    assert report['reserved_units']==250
    assert report['body_budget']==PLAN.get()['target_high']-250


def test_media_and_order_are_owned_by_application(plan):
    source=rows()
    source[0]['text']+='\n*Content-[01:00]\n![Screenshot at 01:00](/data/screenshots/example.jpg)'
    source[1]['text']+='\nScreenshot-[02:00]'
    call=Mock(side_effect=provider)
    result=edit_whole_note(source,call,preserve_order=True)
    from note_presentation import media_times
    assert media_times(result[0]['text'])==[60,60,120]
    for args in call.call_args_list:
        assert '/data/screenshots/' not in args.args[1] and '*Content-' not in args.args[1]


def test_source_blocks_and_prose_links_are_not_media():
    text='> Content-[01:00]\n\n```text\nScreenshot-[02:00]\n```\n\n[Evidence](https://example.com)\n\n*Content-[03:00]'
    prose,media=_separate_media(text)
    assert media==['*Content-[03:00]']
    assert '> Content-[01:00]' in prose and 'Screenshot-[02:00]' in prose
    assert '[Evidence](https://example.com)' in prose


@pytest.mark.parametrize('phase',['compose','review'])
def test_timeout_retains_readable_originals_without_retry_cascade(plan,phase):
    def call(system,payload,timeout):
        if phase=='compose' or 'rewrite' in json.loads(payload):raise TimeoutError()
        return provider(system,payload,timeout)
    request=Mock(side_effect=call);report={}
    result=edit_whole_note(rows(),request,report=report)
    assert [p['text'] for p in result]==[p['text'] for p in rows()]
    assert request.call_count==(1 if phase=='compose' else 2)
    assert report['retained_batches']==1


def test_cancellation_propagates(plan):
    with pytest.raises(ProcessingCancelledError):
        edit_whole_note(rows(),Mock(),checkpoint=Mock(side_effect=ProcessingCancelledError('stop')))


def test_review_can_repair_a_missing_group_in_second_call(plan):
    def call(system,payload,timeout):
        data=json.loads(payload)
        if 'rewrite' not in data:return {'sections':[]}
        assert data['validation_feedback']=={'G1':'missing_or_duplicate_section'}
        fixed=provider(system,json.dumps({'groups':data['groups']}),timeout)
        return {**provider(system,payload,timeout),**fixed}
    request=Mock(side_effect=call)
    result=edit_whole_note(rows(),request)
    assert len(result)==1 and request.call_count==2


def long_source():
    return [{'id':f'N{i}','topic':f'Topic {i}','text':('Important evidence and condition. '*60)} for i in range(30)]


def test_one_failed_group_does_not_discard_other_sections(plan):
    def call(system,payload,timeout):
        response=provider(system,payload,timeout)
        if 'checks' in response:response['checks'][0]['complete']=False
        return response
    source=[dict(row,text=row['text'][:200]) for row in long_source()];report={}
    result=edit_whole_note(source,call,report=report)
    assert [i for p in result for i in p['ids']]==[p['id'] for p in source]
    assert report['batches'][0]['retained_sections']==1
    assert report['batches'][0]['composed_sections']>=1
    assert any('untested' in p['text'] for p in result)


def test_model_reordering_cannot_change_source_order(plan):
    def call(system,payload,timeout):
        response=provider(system,payload,timeout)
        if 'sections' in response:response['sections'].reverse()
        return response
    source=long_source()
    result=edit_whole_note(source,call,preserve_order=True)
    assert [i for p in result for i in p['ids']]==[p['id'] for p in source]


def test_duplicate_group_is_not_arbitrarily_selected(plan):
    def call(system,payload,timeout):
        response=provider(system,payload,timeout)
        if 'sections' in response:response['sections']*=2
        return response
    result=edit_whole_note(rows(),call)
    assert [p['text'] for p in result]==[p['text'] for p in rows()]


@pytest.mark.parametrize('change',['media','quote','url'])
def test_unverified_changes_to_source_artifacts_retain_originals(plan,change):
    source=rows()
    if change=='quote':source[0]['text']+='\n\n> Exact original quotation.'
    if change=='url':source[0]['text']+='\nhttps://example.com/evidence'
    def call(system,payload,timeout):
        response=provider(system,payload,timeout)
        if change=='media' and 'sections' in response:
            response['sections'][0]['text']+='\nScreenshot-[09:00]'
        return response
    result=edit_whole_note(source,call)
    assert [p['text'] for p in result]==[p['text'] for p in source]


def test_over_budget_draft_is_measured_and_sent_for_review(plan):
    def call(system,payload,timeout):
        response=provider(system,payload,timeout)
        if 'sections' in response:response['sections'][0]['text']='Repetition. '*1000
        else:
            data=json.loads(payload)
            assert data['draft_units']['G1']>data['groups'][0]['body_budget']
            response.update(provider(system,json.dumps({'groups':data['groups']}),timeout))
        return response
    report={};result=edit_whole_note(rows(),call,report=report)
    assert report['target_met'] and 'untested' in result[0]['text']


def test_verified_over_budget_prose_is_not_truncated_or_claimed_within_budget(plan):
    def call(system,payload,timeout):
        response=provider(system,payload,timeout)
        if 'sections' in response:response['sections'][0]['text']='Evidence. '*1000
        return response
    report={};result=edit_whole_note(rows(),call,report=report)
    assert not report['target_met'] and result[0]['text'].count('Evidence.')==1000


def test_long_chinese_output_is_split_even_if_request_is_small():
    token=PLAN.set(make_plan('原文内容。'*6000,67*60,'zh'))
    try:
        source=[{'id':f'N{i}','topic':'条件','text':'原文论据与条件。'*60} for i in range(20)]
        calls=[]
        def call(system,payload,timeout):
            data=json.loads(payload);calls.append(data)
            return provider(system,payload,timeout)
        report={};edit_whole_note(source,call,report=report,reserved_text='概览'*300)
        initial=[d for d in calls if 'rewrite' not in d]
        assert len(initial)>1
        assert all(sum(g['body_budget'] for g in d['groups'])<=1200 for d in initial)
        assert sum(g['body_budget'] for d in initial for g in d['groups'])==report['body_budget']
        assert report['model_calls']==len(initial)*2
    finally:PLAN.reset(token)


def test_capacity_limit_never_discards_source(plan):
    from focused_editor import MAX_INPUT_CHARS
    source=rows();source[0]['text']='Evidence. '*MAX_INPUT_CHARS
    call=Mock();report={};result=edit_whole_note(source,call,report=report)
    call.assert_not_called()
    assert [p['text'] for p in result]==[p['text'] for p in source]
    assert report['fallback_reason']=='input_capacity'


def test_original_quotes_never_count_as_reading_prose(plan):
    from summarizer import Summary,KeyPoint
    summary=Summary('id','Title','Overview',[KeyPoint('Topic','Explanation.','quote '*10000,'01:00')],['Topic'],['Takeaway'])
    before=diagnostics(summary,'source',PLAN.get())
    summary.key_points[0].original_quote=''
    assert diagnostics(summary,'source',PLAN.get())==before
    assert before['output_words']==3
    text='# Title\n\n[Title](#title)\n\nActual explanation.\n\n> '+'quote '*10000
    assert diagnostics(text,'source',PLAN.get())['output_words']==3


@pytest.mark.parametrize('video',[False,True])
def test_single_chapter_reaches_editor_and_retains_evidence(plan,video):
    if video:
        from note_summarizer import NoteSummarizer
        engine=NoteSummarizer(api_key='synthetic')
        draft='# Title\n\n## Only chapter\n\n'+'Repetition. '*1000
        with patch.object(engine,'_editorial_json',side_effect=provider) as call:
            result=engine._edit_reading(draft,'Title',False)
            assert 'untested' in result and len(result)<len(draft)
    else:
        from summarizer import Summarizer,Summary,KeyPoint
        engine=Summarizer(api_key='synthetic')
        draft=Summary('id','Title','Overview',[KeyPoint('Topic','Repetition. '*1000,'Quote.','01:00')],['Topic'],[])
        with patch.object(engine,'_editorial_json',side_effect=provider) as call:
            result=engine._edit_reading(draft)
            assert 'untested' in result.key_points[0].summary
            assert result.key_points[0].original_quote=='Quote.'
    assert call.call_count==2


def test_audit_additions_are_ordered_before_grouping(plan):
    from note_summarizer import NoteSummarizer
    from note_presentation import media_times
    engine=NoteSummarizer(api_key='synthetic')
    original='# Title\n\n## Later\n\nLater claim.\n*Content-[02:00]\n\n## Early\n\nOpening premise.\n*Content-[00:10]'
    def call(system,payload,timeout):
        data=json.loads(payload)
        assert [n['topic'] for g in data['groups'] for n in g['notes']]==['Early','Later']
        return provider(system,payload,timeout)
    with patch.object(engine,'_editorial_json',side_effect=call):
        result=engine._edit_reading(original,'Title',False)
    assert media_times(result)==[10,120]
