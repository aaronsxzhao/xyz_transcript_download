"""Regressions from the three focused-reading production samples."""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from reading_editor import edit_sections
from note_presentation import normalize_media_markers, media_times, localize_note
from note_summarizer import NoteSummarizer
from summarizer import Summarizer, Summary, KeyPoint


def rows():
    return [{'id':f'N{i}', 'topic':f'Argument {i}', 'text':f'Condition {i}.'} for i in range(1,5)]


def reply_for(payload):
    notes=json.loads(payload)['notes']
    return {'paragraphs':[{'heading':'Conditions','text':' '.join(n['text'] for n in notes),
                          'ids':[n['id'] for n in notes],'evidence_id':notes[0]['id']}]}


def test_planning_timeout_still_composes_adjacent_notes_and_preserves_ids():
    calls=[]
    def call(system,payload,timeout):
        calls.append(json.loads(payload))
        if 'index' in calls[-1]: raise TimeoutError('slow planning')
        if 'rewrite' in calls[-1]: return {'complete':True,'grounded':True}
        return reply_for(payload)
    report={}
    result=edit_sections(rows(),call,preserve_order=True,report=report)
    assert len(calls)==3 and len(result)==1
    assert result[0]['ids']==['N1','N2','N3','N4']
    assert report['composed_batches']==1 and report['planning_fallback']=='TimeoutError'


def test_one_chapter_timeout_does_not_skip_later_chapters():
    def call(system,payload,timeout):
        data=json.loads(payload)
        if 'index' in data:
            return {'groups':[{'title':'A','ids':['N1','N2']},{'title':'B','ids':['N3','N4']}]}
        if data['chapter']=='A': raise TimeoutError('slow first chapter')
        if 'rewrite' in data: return {'complete':True,'grounded':True}
        return reply_for(payload)
    report={}; result=edit_sections(rows(),call,report=report)
    assert [p['ids'] for p in result]==[['N1'],['N2'],['N3','N4']]
    assert report['composed_batches']==1 and report['retained_batches']==1


def test_configuration_failure_stops_calls_without_discarding_content():
    class Unauthorized(Exception): status_code=401
    call=Mock(side_effect=Unauthorized())
    result=edit_sections(rows(),call)
    assert call.call_count==1
    assert [p['text'] for p in result]==[p['text'] for p in rows()]


def test_audit_additions_after_chunk_index_are_not_swallowed_by_conclusions():
    from source_coverage import SourceReview
    engine=NoteSummarizer(api_key='fixture')
    review=SourceReview({'body':'## Original\n\nOriginal evidence.\n\n## AI Summary\n\nCore condition.'},
        [{'heading':'Additional condition','text':'New independent limitation.',
          'source_quote':'The earlier condition matters.','timestamp':'01:00'}],{})
    with patch('note_summarizer.audit_source',return_value=review):
        audited=engine._audit_note_verified('[01:00] The earlier condition matters.', 'Draft')
    with patch.object(engine,'_editorial_json',return_value={'overview':'Whole-video conclusion.'}) as call:
        merged=engine._merge_chunk_notes('Title',[audited],False,whole_summary=True)
    assert 'New independent limitation.' in merged
    assert 'New independent limitation.' not in call.call_args.args[1]
    assert merged.index('New independent limitation.')<merged.index('Whole-video conclusion.')


def test_failed_whole_synthesis_keeps_indexes_with_their_own_chunks():
    engine=NoteSummarizer(api_key='fixture')
    chunks=['## Early\n\nEarly evidence.\n\n## AI Summary\n\nEarly condition.',
            '## Late\n\nLate evidence.\n\n## AI Summary\n\nLate condition.']
    with patch.object(engine,'_editorial_json',side_effect=TimeoutError):
        result=engine._merge_chunk_notes('Title',chunks,False,whole_summary=True)
    assert result.index('Early evidence.')<result.index('Early condition.')<result.index('Late evidence.')<result.index('Late condition.')
    assert result.count('Early condition.')==1


def test_media_repair_is_idempotent_and_never_rewrites_code_or_quotations():
    source='*Content-08:09* text\n*Screenshot-12:25\n*Content-[13:47]*\n> *Content-01:00*\n\n```md\nScreenshot-02:00\n```\n\n    Screenshot-03:00\n'
    fixed=normalize_media_markers(source)
    assert '*Content-[08:09] text' in fixed and 'Screenshot-[12:25]' in fixed
    assert media_times(fixed)==[489,745,827]
    assert '> *Content-01:00*' in fixed and 'Screenshot-02:00' in fixed and '    Screenshot-03:00' in fixed
    assert normalize_media_markers(fixed)==fixed
    assert normalize_media_markers('Content-01:99')=='Content-01:99'


def test_only_foreign_heading_is_sent_to_language_repair():
    sent=[]
    def call(system,payload,timeout):
        sent.append(json.loads(payload)['markdown'])
        return {'text':'### Leadership\n'}
    draft='### 领导力\n\nThe original English body has 2 conditions.\n'
    result=localize_note(draft,'The original English speech.',call)
    assert sent==['### 领导力\n']
    assert result=='### Leadership\n\nThe original English body has 2 conditions.\n'


def test_language_timeout_is_local_to_a_section():
    call=Mock(side_effect=[TimeoutError(),{'text':'## Second\n\nSecond condition.\n'}])
    draft='## 第一\n\n第一条件。\n\n## 第二\n\n第二条件。\n'
    result=localize_note(draft,'The original English source.',call)
    assert '第一条件' in result and 'Second condition.' in result and call.call_count==2


def test_merged_podcast_quotes_stay_out_of_body():
    engine=Summarizer(api_key='fixture')
    summary=Summary('ep','Title','Overview',[KeyPoint('A','First condition.','First exact quote.','01:00'),
        KeyPoint('B','Second condition.','Second exact quote.','02:00')],['A','B'],[])
    paragraphs=[{'topic':'Conditions','text':'Both conditions matter.', 'ids':['N1','N2'],'evidence_id':'N2'}]
    with patch('reading_editor.edit_sections',return_value=paragraphs): result=engine._edit_reading(summary)
    assert result.key_points[0].summary=='Both conditions matter.'
    assert result.key_points[0].original_quote=='Second exact quote.'
    assert result.key_points[0].timestamp=='02:00'
    assert summary.key_points[0].original_quote=='First exact quote.'
