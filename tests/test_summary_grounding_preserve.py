import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from coverage_ledger import efficient_audit, matching_response, coverage_acceptable
from transcript_reading import source_lines, batches, validate_sections, generate
from reading_delivery import accept_edition, draft_identity
from summary_errors import SummaryOutputError


def timed_source(count=2170):
    return ''.join(f'[{i//60:02d}:{i%60:02d}] Fact {i}.\n' for i in range(count))


def test_lossless_asr_grouping_reduces_inventory_batches_without_enlarging_limit():
    text=timed_source()
    revision,old=source_lines(text)
    new_revision,new=source_lines(text,compact=True)
    assert revision==new_revision
    assert ''.join(line.text for line in new)==text
    assert len(list(batches(new,12000))) < len(list(batches(old,12000)))
    assert len(new)<len(old)//4
    assert all(len(line.text)<=256 for line in new)
    for line in new:
        _,parts=source_lines(line.text)
        assert parts[0].time==line.time
        assert all(line.time<=part.time<=line.time+15 for part in parts)
    assert all(':g' in line.id for line in new)
    assert not {line.id for line in old}&{line.id for line in new}


@pytest.mark.parametrize('source',['[00:01] One.\n[00:02] Two.\n','Ordinary sentence.\n'*500])
def test_short_or_untimed_sources_keep_original_ids(source):
    assert source_lines(source)==source_lines(source,compact=True)


def scene():
    _,lines=source_lines(''.join(f'Source fact {i}.\n' for i in range(20)))
    items=[];sections=[]
    for i,line in enumerate(lines):
        spans=[{'start':line.id,'end':line.id}]
        section,_=validate_sections({'sections':[{'heading':f'Argument {i}','paragraphs':[
            {'text':f'Fact {i}.','source_ranges':spans}]}]},lines)
        section[0]['paragraphs'][0]['id']=f'P{i}'
        sections.extend(section)
        items.append({'id':f'C{i}','kind':'claim','statement':f'Fact {i}.','source_ranges':spans})
    owner=SimpleNamespace(quality_coverage_threshold=.9,model='test',client=Mock(base_url='https://model.test',options={}))
    prepared=({'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False},items)
    return owner,lines,sections,prepared


def row(item,status='covered',grounded=True,duplicate=False):
    return {'item_id':item['id'],'status':status,'grounded':grounded,'duplicate':duplicate,
        'support':[{'paragraph_id':'P'+item['id'][1:]}] if status=='covered' else []}


@pytest.mark.parametrize('change',['paragraph','item','source','heading','overview','model'])
def test_positive_coverage_certificates_reuse_only_unchanged_obligations_and_support(change):
    owner,lines,sections,prepared=scene();calls=[];later=[False]
    def respond(engine,system,payload,validator):
        assert payload['phase']=='match'
        calls.append([item['id'] for item in payload['items']])
        # Deliberate reviewer instability on unchanged prose. Changed support
        # is genuinely missing; unrelated old positives must not be rerated.
        return {'matches':[row(item,'missing' if later[0] else 'covered') for item in payload['items']]}
    with patch('coverage_ledger.request',side_effect=respond):
        first=efficient_audit(owner,lines,sections,prepared_inventory=prepared,allow_repairs=False)
        assert coverage_acceptable(first)
        later[0]=True;calls.clear();overview=''
        if change=='paragraph':sections[0]['paragraphs'][0]['text']='Fact withdrawn.'
        if change=='item':owner._quality_inventory[1][0]['statement']='A different obligation.'
        if change=='source':lines=[type(line)(line.id,line.text+'Changed.',line.time) for line in lines]
        if change=='heading':sections[0]['heading']='Different scope'
        if change=='overview':overview='A different introduction.'
        if change=='model':owner.model='different'
        # Below-threshold cases may source-verify gaps; keep this test at the
        # initial immutable matching boundary rather than simulating repairs.
        with patch('coverage_ledger._correct_inventory',return_value=[]):
            second=efficient_audit(owner,lines,sections,overview,prepared_inventory=owner._quality_inventory,
                allow_repairs=False,reuse_unchanged_support=True)
    expected=19 if change in ('paragraph','item','heading') else 0
    assert second['reused_covered_receipts']==expected
    if expected:
        assert calls==[['C0']]
        assert second['items'][0]['status']=='missing'
        assert sum(item['status']=='covered' for item in second['items'])==19
    else:
        assert set(sum(calls,[]))=={f'C{i}' for i in range(20)}


def test_known_negative_receipts_are_never_eligible_for_reuse():
    owner,lines,sections,prepared=scene();seen=[]
    def respond(engine,system,payload,validator):
        seen.extend(item['id'] for item in payload['items'])
        return {'matches':[row(item,'missing' if item['id']=='C0' else 'covered') for item in payload['items']]}
    with patch('coverage_ledger.request',side_effect=respond):
        efficient_audit(owner,lines,sections,prepared_inventory=prepared,allow_repairs=False)
        seen.clear()
        report=efficient_audit(owner,lines,sections,prepared_inventory=prepared,allow_repairs=False,reuse_unchanged_support=True)
    assert report['reused_covered_receipts']==19 and seen==['C0']
    assert report['items'][0]['status']=='missing'


def test_reused_coverage_still_requires_whole_draft_source_review_and_rejects_global_contradiction():
    from tests.test_reading_delivery import candidate
    owner,edition=candidate(10)
    # Even if a stale identity claims the current draft already passed, positive
    # coverage certificates cannot substitute for whole-draft source review.
    owner.generation_report['coverage_ledger']['reused_covered_receipts']=10
    rejection={'checked_source_ids':[line.id for line in edition['lines']],
        'complete':True,'grounded':False,'unsupported_paragraph_ids':[],'additions':[]}
    with patch('transcript_reading.call_json',return_value=rejection) as review:
        with pytest.raises(SummaryOutputError):accept_edition(owner,edition,'Title','Source',[],0)
    assert review.call_count==1
    assert json.loads(review.call_args.args[2])['global_draft']
    assert owner.generation_report['delivery']['status']=='blocked'


@pytest.mark.parametrize('grounded,proposed',[(True,False),(False,False),(True,True)])
def test_redundancy_of_existing_prose_is_not_missing_coverage_but_new_duplicates_still_fail(grounded,proposed):
    owner,lines,sections,prepared=scene();item=prepared[1][0]
    draft=[{'heading':'Claim','paragraphs':[{'id':'P0','text':'Fact 0.','raw':False}]}]
    data={'matches':[row(item,grounded=grounded,duplicate=True)],'checked_proposed_paragraph_ids':['P0'] if proposed else []}
    parsed=matching_response(data,[item],draft,['P0'] if proposed else [])
    assert parsed[0]['duplicate'] is proposed
    assert parsed[0]['grounded'] is grounded
    assert parsed[0]['status']=='covered'


def test_archived_candidate_resumes_original_line_layout_instead_of_restarting_or_rebinding():
    from scripts.validate_parallel_processing import Store
    from processing_execution import Execution
    text=timed_source(130);_,old=source_lines(text)
    spans=[{'start':old[0].id,'end':old[-1].id}]
    sections,_=validate_sections({'sections':[{'heading':'Claim','paragraphs':[{'text':'Saved supported prose.','source_ranges':spans}]}]},old)
    sections[0]['paragraphs'][0]['id']='P0'
    saved={'edition':{'sections':sections,'overview':''},'report':{},'inventory':({},[]),'attempt':0}
    execution=Execution('owner','source',Store())
    engine=SimpleNamespace(quality_coverage_threshold=.9,generation_report={})
    def accept(owner,edition,*args):
        assert edition['lines']==old
        assert edition['sections']==sections
        assert owner.generation_report['source_layout']=='original-lines'
        return edition
    with patch('reading_delivery.candidate_checkpoint',return_value=(execution,'key',saved)), \
         patch('reading_delivery.accept_edition',side_effect=accept),patch('reading_delivery.save_candidate'), \
         patch('transcript_reading.call_json',side_effect=AssertionError('Do not regenerate a saved candidate')):
        generate(engine,text,'Title')


def test_same_complete_transcript_uses_shared_core_from_video_and_podcast():
    from summarizer import Summarizer
    from note_summarizer import NoteSummarizer
    from transcriber import Transcript,TranscriptSegment
    source='A supported claim.'
    transcript=Transcript(episode_id='episode',language='en',duration=4,text=source,
        segments=[TranscriptSegment(0,4,source)])
    edition={'lines':source_lines(source)[1],'sections':[],'overview':'','notices':[],'markdown':'Shared accepted result'}
    with patch('transcript_quality.validate_transcript'),patch('transcript_reading.generate',return_value=edition) as shared:
        podcast=Summarizer(api_key='test',base_url='https://model.test',model='test')
        video=NoteSummarizer(api_key='test',base_url='https://model.test',model='test')
        try:
            podcast.summarize(transcript,episode_title='Title')
            assert video.generate_note('Title',source)=='Shared accepted result'
        finally:
            podcast.client.close();video.client.close()
    assert shared.call_count==2
    assert all(call.args[2]=='Title' for call in shared.call_args_list)


def test_archived_checklist_translation_preserves_every_obligation_and_its_full_source():
    from scripts.validate_authorized_episode import translate_archived_inventory,TestGuardStopped
    source=timed_source(130);_,old=source_lines(source);_,new=source_lines(source,compact=True)
    items=[{'id':f'C{i}','kind':'condition','statement':f'Keep condition {i}.',
        'source_ranges':[{'start':old[i].id,'end':old[i+2].id}]} for i in range(100)]
    payload={'inventory':({},items)};before=copy.deepcopy(payload)
    translated=translate_archived_inventory(payload,source)
    assert payload==before and len(translated)==100
    assert [x['statement'] for x in translated]==[x['statement'] for x in items]
    positions={line.id:i for i,line in enumerate(new)}
    for i,item in enumerate(translated):
        span=item['source_ranges'][0]
        evidence=''.join(line.text for line in new[positions[span['start']]:positions[span['end']]+1])
        assert ''.join(line.text for line in old[i:i+3]) in evidence
    with pytest.raises(TestGuardStopped):translate_archived_inventory(payload,'Different source.')


@pytest.mark.parametrize('invalid',[False,True])
def test_independent_fixed_inventory_check_never_changes_obligations_or_adds_repairs(invalid):
    from scripts.validate_authorized_episode import check_frozen_inventory
    owner,lines,sections,prepared=scene();before=copy.deepcopy(prepared[1])
    def respond(engine,system,payload,validator):
        assert payload['phase']=='match'
        return {'matches':[row(item,'contradicted' if invalid else 'covered') for item in payload['items']]}
    with patch('coverage_ledger.request',side_effect=respond):
        checked=check_frozen_inventory(owner,{'lines':lines,'sections':sections,'overview':''},prepared[1])
    assert prepared[1]==before
    assert checked['item_count']==20 and checked['checklist_changed'] is False
    assert checked['accepted'] is (not invalid)


@pytest.mark.parametrize('initial_source_unknown',[False,True])
def test_source_correction_then_coverage_repair_precedes_only_the_final_review(initial_source_unknown):
    from tests.test_reading_delivery import candidate
    owner,edition=candidate(8 if initial_source_unknown else 10)
    owner._quality_inventory=({},[])
    owner.generation_report.pop('grounded_draft_identity')
    if not initial_source_unknown:edition['sections'][0]['paragraphs'][0]['raw']=True
    events=[]
    def rewrite(*args,**kwargs):
        events.append('source_repair')
        paragraph=edition['sections'][0]['paragraphs'][0]
        paragraph.pop('raw',None);paragraph['text']='Correct source claim with preserved qualifications.'
    def audit(*args,**kwargs):
        result=copy.deepcopy(owner.generation_report['coverage_ledger'])
        if kwargs.get('allow_repairs') is False:
            events.append('match_corrected')
            for i,item in enumerate(result['items']):item['status']='covered' if i<8 else 'missing'
        else:
            events.append('coverage_repair')
            result['items'][8]['status']='covered'
            edition['sections'][0]['paragraphs'][0]['text']+=' Essential missing condition restored.'
        return result
    def review(*args,**kwargs):
        events.append('review')
        first_bad=initial_source_unknown and events==['review']
        return {'checked_source_ids':[line.id for line in edition['lines']],
            'complete':True,'grounded':not first_bad,'unsupported_paragraph_ids':['P1'] if first_bad else [],'additions':[]}
    with patch('reading_delivery.repair_unsupported',side_effect=rewrite), \
         patch('coverage_ledger.efficient_audit',side_effect=audit),patch('transcript_reading.call_json',side_effect=review):
        accept_edition(owner,edition,'Title','Source',[],0)
    assert events==(['review'] if initial_source_unknown else [])+[
        'source_repair','match_corrected','coverage_repair','review']
    assert owner.generation_report['delivery']['status']=='accepted'
    assert owner.generation_report['delivery']['coverage_ratio']==.9
