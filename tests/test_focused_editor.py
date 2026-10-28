import copy
import json
from unittest.mock import Mock

import pytest

from focused_editor import edit_whole_note
from reading_budget import PLAN, make_plan, diagnostics
from summary_errors import ProcessingCancelledError


@pytest.fixture
def plan():
    token = PLAN.set(make_plan('English evidence. '*2000, 840, 'en'))
    yield
    PLAN.reset(token)


def rows():
    return [{'id':'N1','topic':'Costs','text':'Costs fall only for large orders.', 'evidence':'large orders'},
            {'id':'N2','topic':'Limit','text':'Durability is untested.', 'evidence':'untested'}]


def paragraph(text='Costs fall for large orders; durability remains untested.'):
    return {'heading':'Lower cost is conditional','topic':'Costs and limits','text':text,
            'ids':['N1','N2'],'evidence_id':'N2'}


def test_whole_document_two_calls_and_preserves_input(plan):
    source=rows();before=copy.deepcopy(source);report={}
    call=Mock(side_effect=[{'paragraphs':[paragraph()]},{'complete':True,'grounded':True}])
    result=edit_whole_note(source,call,report=report)
    assert len(result)==1 and 'untested' in result[0]['text'] and source==before
    assert call.call_count==2 and report['target_met']
    assert len(json.loads(call.call_args_list[0].args[1])['notes'])==2


def test_length_repair_uses_same_review_call(plan):
    call=Mock(side_effect=[{'paragraphs':[paragraph('A long repetitive sentence. '*300)]},
        {'complete':True,'grounded':True,'paragraphs':[paragraph()]}])
    report={};result=edit_whole_note(rows(),call,report=report)
    assert call.call_count==2 and report['review_repairs']==1 and report['target_met']
    assert 'untested' in result[0]['text']
    assert json.loads(call.call_args_list[1].args[1])['draft_units']>680


def test_unresolved_length_is_not_recorded_as_success(plan):
    call=Mock(side_effect=[{'paragraphs':[paragraph('Repetition. '*900)]},
                          {'complete':True,'grounded':True}])
    report={};edit_whole_note(rows(),call,report=report)
    assert report['budget_unresolved'] and not report['target_met']
    assert call.call_count==2


def test_failure_does_not_start_per_chapter_retry_cascade(plan):
    call=Mock(side_effect=TimeoutError());report={}
    result=edit_whole_note(rows(),call,report=report)
    assert [p['text'] for p in result]==[p['text'] for p in rows()]
    assert call.call_count==1 and not report['target_met']


def test_cancel_propagates(plan):
    with pytest.raises(ProcessingCancelledError):
        edit_whole_note(rows(),Mock(),checkpoint=Mock(side_effect=ProcessingCancelledError('stop')))


@pytest.mark.parametrize('change',['missing_id','missing_condition','missing_media','reordered'])
def test_invalid_rewrite_retains_readable_originals(plan,change):
    source=rows();source[0]['text']+='\n*Content-[01:00]';source[1]['text']+='\nScreenshot-[02:00]'
    p=paragraph('Costs fall for large orders; durability remains untested.\n*Content-[01:00]\nScreenshot-[02:00]')
    review={'complete':True,'grounded':True}
    if change=='missing_id':p['ids']=['N2']
    if change=='missing_condition':review['complete']=False
    if change=='missing_media':p['text']=p['text'].replace('Screenshot-[02:00]','')
    if change=='reordered':p['text']=p['text'].replace('*Content-[01:00]\nScreenshot-[02:00]','Screenshot-[02:00]\n*Content-[01:00]')
    result=edit_whole_note(source,Mock(side_effect=[{'paragraphs':[p]},review]),preserve_order=True)
    assert [r['text'] for r in result]==[r['text'] for r in source]


def test_application_preserves_markers_without_model_copying(plan):
    source=rows();source[0]['text']+='\n*Content-[01:00]';source[1]['text']+='\nScreenshot-[02:00]'
    p=paragraph()
    result=edit_whole_note(source,Mock(side_effect=[{'paragraphs':[p]},{'complete':True,'grounded':True}]),preserve_order=True)
    assert len(result)==1 and '*Content-[01:00]' in result[0]['text']


def test_folded_evidence_never_inflates_podcast_reading_time(plan):
    from summarizer import Summary, KeyPoint
    summary=Summary('id','Title','Overview',[KeyPoint('Topic','Explanation.','quote '*10000,'01:00')],['Topic'],['Takeaway'])
    before=diagnostics(summary,'source',PLAN.get())
    summary.key_points[0].original_quote=''
    assert diagnostics(summary,'source',PLAN.get())==before
    assert before['output_words']==3


def test_markdown_quotations_and_toc_excluded(plan):
    text='# Title\n\n[Title](#title)\n\nActual explanation.\n\n> '+('quote '*10000)
    assert diagnostics(text,'source',PLAN.get())['output_words']==3


def test_prose_containing_internal_link_is_still_reading_content(plan):
    text='See [conditions](#conditions) before drawing a conclusion.\n\n[Conditions](#conditions)'
    assert diagnostics(text,'source',PLAN.get())['output_words']==6


def test_oversized_input_keeps_every_note_without_provider_calls(plan):
    from focused_editor import MAX_INPUT_CHARS
    source=rows();source[0]['text']='Evidence. '*MAX_INPUT_CHARS
    call=Mock();report={}
    result=edit_whole_note(source,call,report=report)
    call.assert_not_called()
    assert [p['text'] for p in result]==[p['text'] for p in source]
    assert report['fallback_reason']=='input_capacity' and not report['target_met']


@pytest.mark.parametrize('video',[False,True])
def test_single_long_chapter_reaches_whole_editor(plan,video):
    from unittest.mock import patch
    if video:
        from note_summarizer import NoteSummarizer
        engine=NoteSummarizer(api_key='synthetic')
        draft='# Title\n\n## Only chapter\n\n'+'Repetitive explanation. '*1000
        response=paragraph();response.update(ids=['N1'],evidence_id='N1')
        with patch.object(engine,'_editorial_json',side_effect=[{'paragraphs':[response]},{'complete':True,'grounded':True}]) as call:
            result=engine._edit_reading(draft,'Title',False)
            assert 'untested' in result and len(result)<len(draft)
    else:
        from summarizer import Summarizer, Summary, KeyPoint
        engine=Summarizer(api_key='synthetic')
        draft=Summary('id','Title','Overview',[KeyPoint('Topic','Repetition. '*1000,'Quote.','01:00')],['Topic'],[])
        response=paragraph();response.update(ids=['N1'],evidence_id='N1')
        with patch.object(engine,'_editorial_json',side_effect=[{'paragraphs':[response]},{'complete':True,'grounded':True}]) as call:
            result=engine._edit_reading(draft)
            assert 'untested' in result.key_points[0].summary
            assert result.key_points[0].original_quote=='Quote.'
    assert call.call_count==2


def test_actual_intro_reserve_excludes_quotes(plan):
    report = {}
    call = Mock(side_effect=[{'paragraphs':[paragraph()]}, {'complete':True,'grounded':True}])
    edit_whole_note(rows(), call, report=report,
                    reserved_text=('Overview '*250)+'\n\n> '+('quote '*1000))
    assert report['reserved_units'] == 250
    assert report['body_budget'] == PLAN.get()['target_high'] - 250
    assert json.loads(call.call_args_list[0].args[1])['body_budget'] == report['body_budget']


def test_repeated_original_media_is_restored_exactly(plan):
    source = rows()
    source[0]['text'] += '\n*Content-[01:00]\n*Content-[01:00]'
    source[1]['text'] += '\nScreenshot-[02:00]'
    p = paragraph()
    result = edit_whole_note(source, Mock(side_effect=[{'paragraphs':[p]}, {'complete':True,'grounded':True}]), preserve_order=True)
    assert len(result) == 1


def test_large_note_uses_bounded_batches_with_one_shared_budget(plan):
    source = [{'id':f'N{i}', 'topic':f'Topic {i}', 'text':'Evidence and condition. '*160} for i in range(24)]
    calls = []
    def call(system, payload, timeout):
        body = json.loads(payload)
        calls.append(body)
        if 'rewrite' in body:
            return {'complete':True,'grounded':True}
        batch = body['notes']
        return {'paragraphs':[{'topic':'Evidence','heading':'Conditions','text':'Evidence under conditions.',
            'ids':[r['id'] for r in batch], 'evidence_id':batch[0]['id']}]}
    report = {}
    result = edit_whole_note(source, call, preserve_order=True, report=report, reserved_text='Overview '*200)
    compositions = [body for body in calls if 'rewrite' not in body]
    assert 2 <= len(compositions) <= 4
    assert sum(body['body_budget'] for body in compositions) == PLAN.get()['target_high'] - 200
    assert all(len(body['document_outline']) == 24 for body in compositions)
    assert [i for p in result for i in p['ids']] == [r['id'] for r in source]
    assert report['model_calls'] == len(compositions)*2
    assert report['target_met']


def test_review_repairs_cannot_drop_or_reassign_media(plan):
    source = rows()
    source[0]['text'] += '\n![Screenshot at 01:00](/data/screenshots/example_01-00.jpg)'
    source[1]['text'] += '\n*Content-[02:00]'
    call = Mock(side_effect=[{'paragraphs':[paragraph()]},
        {'complete':True,'grounded':True,'paragraphs':[paragraph('Lower costs require large orders; durability has not been tested.')]}])
    result = edit_whole_note(source,call,preserve_order=True)
    assert '/data/screenshots/example_01-00.jpg' in result[0]['text']
    assert result[0]['text'].index('01:00') < result[0]['text'].index('02:00')
    for args in call.call_args_list:
        assert '/data/screenshots/' not in args.args[1]
        assert '*Content-' not in args.args[1]


def test_media_extraction_preserves_quoted_markers_and_prose_links():
    from focused_editor import _separate_media
    original = '> Content-[01:00]\n\n```text\nScreenshot-[02:00]\n```\n\n[Evidence](https://example.com)\n\n*Content-[03:00]'
    prose, media = _separate_media(original)
    assert media == ['*Content-[03:00]']
    assert '> Content-[01:00]' in prose and 'Screenshot-[02:00]' in prose
    assert '[Evidence](https://example.com)' in prose


def test_reference_typo_repaired_in_existing_review_budget(plan):
    invalid = paragraph(); invalid['ids'] = ['N1','N3']
    call = Mock(side_effect=[{'paragraphs':[invalid]},
        {'complete':True,'grounded':True,'paragraphs':[paragraph()]}])
    report = {}
    result = edit_whole_note(rows(),call,report=report)
    assert len(result) == 1 and result[0]['ids'] == ['N1','N2']
    assert report['draft_validation'] == 'source_references'
    assert call.call_count == 2
    assert json.loads(call.call_args_list[1].args[1])['validation_feedback'] == 'source_references'
