"""Public reading pipelines: whole-source ownership, recovery and evidence gates."""
import json
from types import SimpleNamespace
from unittest.mock import patch, Mock

import pytest

from transcript_reading import generate, source_lines, validate_sections, batches
from summary_errors import ProcessingCancelledError, SummaryOutputError


def engine(mode='single', limit=8000):
    return SimpleNamespace(generation_mode=mode, chunk_chars=limit, generation_report={})


def section(rows, text='A complete claim, with its condition.', frame=None):
    return {'heading':'Claim and condition','paragraphs':[{'text':text,
        'source_ranges':[{'start':rows[0]['id'],'end':rows[-1]['id']}],
        'screenshot_source_id':frame}]}


def provider(calls):
    def call(owner, system, payload, timeout):
        data=json.loads(payload);calls.append(data)
        if 'global_draft' in data and 'primary_source' not in data:
            return {'overview':'A conditional answer.'}
        rows=data['primary_source']
        if 'global_draft' in data:
            return {'checked_source_ids':[r['id'] for r in rows], 'complete':True,
                    'grounded':True,'unsupported_paragraph_ids':[],'additions':[]}
        return {'sections':[section(rows)], 'overview':'A conditional answer.'}
    return call


def test_long_source_default_is_one_generation_and_never_loses_the_tail():
    text=('An important detail with its condition. \n'*4000)+'\nUNMATCHED 最后一句。 '
    calls=[];owner=engine(limit=1000)
    with patch('transcript_reading.call_json',side_effect=provider(calls)):
        result=generate(owner,text,'Title')
    drafts=[c for c in calls if 'mode' in c]
    assert len(drafts)==1
    assert ''.join(r['text'] for r in drafts[0]['primary_source'])==text
    assert 'complete claim' in result['markdown']
    assert owner.generation_report['actual_mode']=='single'
    assert owner.generation_report['generation_requests']==1
    assert owner.generation_report['implicit_fallback'] is False


def test_explicit_segmented_has_lossless_ownership_and_reviews_global_answers():
    text='[00:00] What is the method?\n'+('Context and qualification.\n'*90)+'[02:10] The method is to calm down before listening.\n'
    calls=[];owner=engine('segmented',1000)
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        request=calls[-1]
        if 'mode' in request:
            result['sections'][0]['paragraphs'][0]['text']='The method is to calm down.' if 'method is' in ''.join(r['text'] for r in request['primary_source']) else 'The question concerns listening.'
        elif 'primary_source' in request:
            assert 'The method is to calm down.' in json.dumps(request['global_draft'])
        return result
    with patch('transcript_reading.call_json',side_effect=call):result=generate(owner,text,'Title')
    drafts=[c for c in calls if 'mode' in c]
    assert len(drafts)>1
    assert ''.join(r['text'] for c in drafts for r in c['primary_source'])==text
    assert drafts[0]['boundary_context']['after']
    assert 'The method is to calm down.' in result['markdown']
    assert 'Section conclusions' not in result['markdown']


@pytest.mark.parametrize('error',[RuntimeError('context capacity'),SummaryOutputError('length'),ProcessingCancelledError('stop')])
def test_single_failure_never_silently_segments_or_returns_partial_notes(error):
    owner=engine(limit=1)
    with patch('transcript_reading.call_json',side_effect=error) as call:
        with pytest.raises(type(error)):generate(owner,'Complete source. '*2000,'Title')
    assert call.call_count==1 and owner.generation_report['actual_mode']=='single'


@pytest.mark.parametrize('kind',['unknown','reversed','outside_part'])
def test_bad_paragraph_evidence_is_rejected(kind):
    _,lines=source_lines('First sentence.\nSecond sentence.\nThird sentence.')
    data={'sections':[section([{'id':x.id} for x in lines])]}
    span=data['sections'][0]['paragraphs'][0]['source_ranges'][0]
    allowed=None
    if kind=='unknown':span['end']='made-up'
    if kind=='reversed':span.update(start=lines[-1].id,end=lines[0].id)
    if kind=='outside_part':allowed={lines[0].id,lines[-1].id}
    with pytest.raises(SummaryOutputError):validate_sections(data,lines,allowed)


def test_frame_must_belong_to_its_paragraph_not_merely_the_whole_document():
    text='[07:11] School transfer.\n[08:33] Taken to the facility.\n[08:59] The first night was frightening.\n'
    calls=[];owner=engine()
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'mode' in calls[-1]:
            rows=calls[-1]['primary_source']
            result['sections']=[section(rows[1:],frame=rows[0]['id'])]
        return result
    with patch('transcript_reading.call_json',side_effect=call):result=generate(owner,text,'Title',formats=['screenshot'])
    assert 'Screenshot-' not in result['markdown']
    assert 'failed source validation' in result['markdown']
    assert owner.generation_report['provenance']['blocked_media']==1


def test_media_times_are_resolved_from_source_and_not_model_text():
    text='[08:33] Taken to the facility.\n[08:59] The first night was frightening.\n'
    calls=[];owner=engine()
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'mode' in calls[-1]:
            rows=calls[-1]['primary_source'];result['sections']=[section(rows,frame=rows[-1]['id'])]
        return result
    with patch('transcript_reading.call_json',side_effect=call):
        result=generate(owner,text,'Title',formats=['screenshot','link','toc'],duration=600)
    assert 'Screenshot-[08:59]' in result['markdown']
    assert '*Content-[08:33]' in result['markdown']
    assert owner.generation_report['provenance']['screenshots'][0]['time']==539


@pytest.mark.parametrize('body',['Screenshot-[07:11]','![made up](https://example.com/x.jpg)','<img src="x">','## Sneaky heading'])
def test_generated_prose_cannot_smuggle_unvalidated_media_or_structure(body):
    _,lines=source_lines('Actual source.')
    with pytest.raises(SummaryOutputError):validate_sections({'sections':[section([{'id':lines[0].id}],body)]},lines)


def test_missing_review_receipts_keep_draft_with_unverified_notice():
    calls=[];owner=engine()
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'global_draft' in calls[-1]:result['checked_source_ids']=[]
        return result
    with patch('transcript_reading.call_json',side_effect=call):result=generate(owner,'Original claim.','Title')
    assert 'complete claim' in result['markdown'] and 'Completeness is unverified' in result['markdown']
    assert owner.generation_report['verification']['status']=='unverified'


def test_cancellation_in_verification_propagates_without_delivering_draft():
    calls=[]
    def call(owner,system,payload,timeout):
        if 'global_draft' in json.loads(payload):raise ProcessingCancelledError()
        return provider(calls)(owner,system,payload,timeout)
    with patch('transcript_reading.call_json',side_effect=call):
        with pytest.raises(ProcessingCancelledError):generate(engine(),'Original source.','Title')


@pytest.mark.parametrize('video',[True,False])
def test_public_engines_use_linked_pipeline_without_second_editorial_rewrite(video):
    calls=[]
    from note_summarizer import NoteSummarizer
    from summarizer import Summarizer
    from transcriber import Transcript,TranscriptSegment
    owner=NoteSummarizer(api_key='synthetic') if video else Summarizer(api_key='synthetic')
    with patch('transcript_reading.call_json',side_effect=provider(calls)),patch.object(owner,'_edit_reading') as edit:
        if video:result=owner.generate_note('Title','[00:01] Complete source sentence.')
        else:
            with patch('transcript_quality.validate_transcript'):
                result=owner.summarize(Transcript('ep','en',60,'Complete source sentence.',
                    [TranscriptSegment(1,4,'Complete source sentence.')]),episode_title='Title')
            assert result.key_points[0].original_quote=='Complete source sentence.'
            assert result.key_points[0].timestamp=='00:00:01'
    assert result and owner.generation_report['generation_requests']==1
    edit.assert_not_called()


def test_preference_defaults_to_single_and_accepts_only_explicit_modes():
    from api.model_settings import prepared_settings
    from api.custom_models import ModelConfigurationError
    with patch('api.model_settings.get_user_settings',return_value={'llm_provider':'server'}):
        assert prepared_settings('owner',{'summary_generation_mode':'segmented'})[1]['summary_generation_mode']=='segmented'
        with pytest.raises(ModelConfigurationError):prepared_settings('owner',{'summary_generation_mode':'auto'})


def test_global_review_addition_uses_contiguous_original_evidence():
    text='[00:01] A claim.\n[00:04] Only under this condition.\n'
    calls=[];owner=engine()
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'global_draft' in calls[-1]:
            rows=calls[-1]['primary_source']
            result['additions']=[section(rows,'The claim requires this condition.')]
        return result
    with patch('transcript_reading.call_json',side_effect=call):result=generate(owner,text,'Title')
    assert result['markdown'].count('The claim requires this condition.')==1
    assert owner.generation_report['verification']['missing_material_additions']==1


def test_review_ranges_must_cover_the_whole_primary_source():
    calls=[];owner=engine()
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'global_draft' in calls[-1]:
            rows=calls[-1]['primary_source'];result.pop('checked_source_ids')
            result['checked_source_ranges']=[{'start':rows[0]['id'],'end':rows[0]['id']}]
        return result
    with patch('transcript_reading.call_json',side_effect=call):result=generate(owner,'First.\nLast.','Title')
    assert 'Completeness is unverified' in result['markdown']
    assert owner.generation_report['verification']['unresolved']==1


def test_completed_generation_and_review_resume_from_request_checkpoints():
    from note_summarizer import NoteSummarizer
    from processing_execution import Execution,bind
    owner=NoteSummarizer(api_key='synthetic')
    class Store:
        def __init__(self):self.values={}
        def get_checkpoint(self,*key):return self.values.get(key)
        def put_checkpoint(self,*args):self.values[args[:-1]]=args[-1]
    store=Store();execution=Execution('owner','source',store)
    calls=[]
    def complete(**kwargs):
        response=provider(calls)(owner,kwargs['messages'][0]['content'],kwargs['messages'][1]['content'],120)
        assert kwargs['max_completion_tokens']==16384
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(response)))])
    owner.client=Mock(base_url='https://models.example/v1/')
    owner.client.with_options.return_value.chat.completions.create.side_effect=complete
    with bind(execution):
        first=owner.generate_note('Title','A supported argument.\nAn essential condition.')
        second=owner.generate_note('Title','A supported argument.\nAn essential condition.')
    assert first==second and len(calls)==2
    assert execution.snapshot()['checkpoint_hits']==2
    assert len(store.values)==2


def test_only_review_can_partition_after_an_explicit_capacity_rejection():
    calls=[];rejected=[False];owner=engine(limit=1000)
    def call(owner,system,payload,timeout):
        request=json.loads(payload)
        if 'global_draft' in request and not rejected[0]:
            rejected[0]=True
            raise SummaryOutputError('capacity')
        return provider(calls)(owner,system,payload,timeout)
    with patch('transcript_reading.call_json',side_effect=call):
        result=generate(owner,'[00:01] A source sentence.\n'*120,'Title')
    assert sum('mode' in request for request in calls)==1
    assert owner.generation_report['generation_requests']==1
    assert owner.generation_report['actual_mode']=='single'
    check=owner.generation_report['verification']
    assert check['review_capacity_fallback'] and check['review_parts']>1
    assert check['unresolved']==0 and 'Completeness is unverified' not in result['markdown']


def test_provider_errors_are_redacted_and_terminal_even_in_segmented_mode():
    from note_summarizer import NoteSummarizer
    from transcript_reading import ReadingProviderError
    error=RuntimeError('private-key provider response body')
    error.status_code=401
    owner=NoteSummarizer(api_key='synthetic',generation_mode='segmented')
    owner.chunk_chars=1000
    with patch('reading_editor.call_editor',side_effect=error) as call:
        with pytest.raises(ReadingProviderError) as caught:
            owner.generate_note('Title','Original source.\n'*200)
    assert 'private-key' not in str(caught.value) and 'response body' not in str(caught.value)
    assert call.call_count==1


def test_invalid_source_response_is_not_saved_as_a_completed_checkpoint():
    from reading_editor import call_editor
    from processing_execution import Execution,bind
    class Store:
        def get_checkpoint(self,*args):return None
        def put_checkpoint(self,*args):pytest.fail('Invalid evidence must not be cached')
    execution=Execution('owner','source',Store())
    def invalid(data):raise SummaryOutputError('invalid')
    with bind(execution),patch('reading_editor._call_editor',return_value={'sections':[]}):
        with pytest.raises(SummaryOutputError):
            call_editor(Mock(base_url='https://models.example/v1'),'model','system','payload',20,
                        response_validator=invalid,validation_version='source-linked-v1')


def test_unsupported_wording_is_replaced_by_original_source_not_just_a_notice():
    calls=[];owner=engine()
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'global_draft' in calls[-1]:
            result.update(grounded=False,unsupported_paragraph_ids=['P1','overview'])
        else:
            result['overview']='Unsupported opening.'
            result['sections'][0]['paragraphs'][0]['text']='An unsupported attribution.'
        return result
    with patch('transcript_reading.call_json',side_effect=call):
        result=generate(owner,'[00:01] What was actually said.','Title',formats=['summary'])
    assert 'An unsupported attribution.' not in result['markdown']
    assert 'Unsupported opening.' not in result['markdown']
    assert '> [00:01] What was actually said.' in result['markdown']
    assert 'replaced with their original transcript evidence' in result['markdown']
    assert owner.generation_report['verification']['original_source_fallback_ids']==['P1']


def test_missing_optional_frame_uses_a_genuine_chapter_evidence_anchor():
    calls=[];owner=engine()
    with patch('transcript_reading.call_json',side_effect=provider(calls)):
        result=generate(owner,'[08:33] The facility event.\n[08:59] The first night.','Title',formats=['screenshot'])
    assert 'Screenshot-[08:33]' in result['markdown']
    frames=owner.generation_report['provenance']['screenshots']
    assert frames[0]['selection']=='chapter_source_anchor'
    assert owner.generation_report['provenance']['chapter_source_anchor_frames']==1


def test_out_of_duration_playback_is_suppressed_in_final_and_progress():
    calls=[]; previews=[]
    with patch('transcript_reading.call_json', side_effect=provider(calls)):
        result=generate(engine(), '[20:00] Real words with corrupt timing.', 'Title',
                        formats=['link','screenshot'], duration=30,
                        progress=lambda chars, text='', *args: previews.append(text))
    assert '*Content-[' not in result['markdown']
    assert 'Screenshot-[' not in result['markdown']
    assert all('*Content-[' not in preview for preview in previews)


def test_malformed_review_does_not_partially_change_the_draft():
    calls=[]
    def call(owner, system, payload, timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'global_draft' in calls[-1]:
            result.update(grounded=False, unsupported_paragraph_ids=['P1'],
                          additions=[{'heading':'Broken', 'paragraphs':[]}])
        return result
    with patch('transcript_reading.call_json', side_effect=call):
        result=generate(engine(),'Actual evidence.', 'Title')
    assert 'A complete claim' in result['markdown']
    assert 'Completeness is unverified' in result['markdown']
    assert not result['sections'][0]['paragraphs'][0].get('raw')


def test_invalid_review_is_retried_while_completed_generation_is_reused():
    from note_summarizer import NoteSummarizer
    from processing_execution import Execution, bind
    class Store:
        def __init__(self): self.values={}
        def get_checkpoint(self,*key): return self.values.get(key)
        def put_checkpoint(self,*args): self.values[args[:-1]]=args[-1]
    owner=NoteSummarizer(api_key='synthetic')
    owner.client=Mock(base_url='https://models.example/v1/')
    calls=[]; reviews=[]
    def complete(**kwargs):
        response=provider(calls)(owner,kwargs['messages'][0]['content'],kwargs['messages'][1]['content'],120)
        if 'global_draft' in calls[-1]:
            reviews.append(response)
            if len(reviews)==1: response['checked_source_ids']=[]
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(response)))])
    owner.client.with_options.return_value.chat.completions.create.side_effect=complete
    store=Store()
    with bind(Execution('owner','source',store)):
        first=owner.generate_note('Title','Actual evidence.')
        second=owner.generate_note('Title','Actual evidence.')
    assert 'Completeness is unverified' in first
    assert 'Completeness is unverified' not in second
    assert len(calls)==3 and len(reviews)==2 and len(store.values)==2


def test_podcast_disjoint_evidence_is_not_spliced_into_one_verbatim_quote():
    from summarizer import Summarizer
    from transcriber import Transcript, TranscriptSegment
    source=['First supported claim.', 'Intervening qualification.', 'Later supported claim.']
    transcript=Transcript('disjoint','en',90,' '.join(source),
                          [TranscriptSegment(i*30,(i+1)*30,text) for i,text in enumerate(source)])
    calls=[]
    def call(owner,system,payload,timeout):
        result=provider(calls)(owner,system,payload,timeout)
        if 'mode' in calls[-1]:
            rows=calls[-1]['primary_source']
            result['sections'][0]['paragraphs'][0]['source_ranges']=[
                {'start':rows[2]['id'],'end':rows[2]['id']},
                {'start':rows[0]['id'],'end':rows[0]['id']}]
        return result
    with patch('transcript_reading.call_json', side_effect=call):
        result=Summarizer(api_key='synthetic').summarize(transcript)
    assert result.key_points[0].original_quote==source[0]
    assert result.key_points[0].timestamp=='00:00:00'


def test_raw_disjoint_source_fallback_marks_the_omission():
    from transcript_reading import source_excerpt
    _, lines=source_lines('First sentence.\nIntervening sentence.\nLast sentence.')
    assert source_excerpt([0,2],lines)=='First sentence.\n\n\n[…]\n\nLast sentence.'
