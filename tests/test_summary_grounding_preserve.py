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


def test_lossless_asr_grouping_reduces_metadata_without_enlarging_source_work_scopes():
    from transcript_reading import source_work_batches,serialize
    text=timed_source()
    revision,old=source_lines(text)
    new_revision,new=source_lines(text,compact=True)
    assert revision==new_revision
    assert ''.join(line.text for line in new)==text
    assert len(list(batches(new,12000))) < len(list(batches(old,12000)))
    assert len(json.dumps(serialize(new)))<len(json.dumps(serialize(old)))
    # Fewer IDs must not make each checklist extraction read several times
    # more meaning. Preserve the old fragment ownership budget independently.
    grouped_parts=list(source_work_batches(new,12000))
    assert len(grouped_parts)>=len(list(batches(old,12000)))
    assert ''.join(line.text for part in grouped_parts for line in part)==text
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


@pytest.mark.parametrize('change',['render_annotations','local_qualification'])
def test_support_binding_tracks_meaningful_local_context_not_renderer_annotations(change):
    owner,lines,sections,prepared=scene();seen=[]
    def respond(engine,system,payload,validator):
        seen.extend(item['id'] for item in payload['items'])
        return {'matches':[row(item) for item in payload['items']]}
    with patch('coverage_ledger.request',side_effect=respond):
        efficient_audit(owner,lines,sections,prepared_inventory=prepared,allow_repairs=False)
        seen.clear()
        if change=='render_annotations':
            for section in sections:section['paragraphs'][0]['frame_time']=None
        else:
            sections[0]['paragraphs'].append({**copy.deepcopy(sections[0]['paragraphs'][0]),
                'id':'QUALIFIER','text':'The previous claim has a different scope.'})
        report=efficient_audit(owner,lines,sections,prepared_inventory=prepared,
            allow_repairs=False,reuse_unchanged_support=True)
    assert report['reused_covered_receipts']==(20 if change=='render_annotations' else 19)
    assert seen==([] if change=='render_annotations' else ['C0'])


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


@pytest.mark.parametrize('result',['approved','capacity','rejected'])
def test_single_mode_final_review_reads_whole_source_with_only_explicit_capacity_fallback(result):
    from tests.test_reading_delivery import candidate
    owner,edition=candidate(10);owner.generation_mode='single'
    owner.generation_report.pop('grounded_draft_identity');seen=[]
    def review(*args):
        request=json.loads(args[2]);seen.append(request)
        if len(seen)==1 and result=='capacity':raise SummaryOutputError('capacity')
        return {'checked_source_ids':[row['id'] for row in request['primary_source']],
            'complete':True,'grounded':result!='rejected','unsupported_paragraph_ids':[],'additions':[]}
    with patch('transcript_reading.batches',return_value=[[edition['lines'][0]],[edition['lines'][1]]]), \
         patch('transcript_reading.call_json',side_effect=review):
        if result=='rejected':
            with pytest.raises(SummaryOutputError):accept_edition(owner,edition,'Title','Source',[],0)
        else:accept_edition(owner,edition,'Title','Source',[],0)
    assert len(seen[0]['primary_source'])==2
    assert len(seen)==(3 if result=='capacity' else 1)
    assert bool(owner.generation_report.get('final_source_capacity_fallback'))==(result=='capacity')
    if result=='capacity':
        assert {row['id'] for request in seen[1:] for row in request['primary_source']}=={line.id for line in edition['lines']}
    if result=='rejected':assert owner.generation_report['delivery']['status']=='blocked'


def test_final_source_review_sees_the_actual_rendered_chapter_scope_and_order():
    from tests.test_reading_delivery import candidate
    owner,edition=candidate(8);owner._quality_inventory=({},[]);reviewed=[]
    def repair(*args,**kwargs):
        paragraph=copy.deepcopy(edition['sections'][0]['paragraphs'][0]);paragraph['id']='NEW'
        paragraph['indices']=[0]
        args[2].append({'heading':'Temporary repair heading','paragraphs':[paragraph]})
        ledger=copy.deepcopy(owner.generation_report['coverage_ledger']);ledger['items'][8]['status']='covered'
        return ledger
    def review(*args):
        request=json.loads(args[2]);reviewed.append(request['global_draft'])
        assert all(section['heading']!='Temporary repair heading' for section in request['global_draft'])
        return {'checked_source_ids':[line.id for line in edition['lines']],
            'complete':True,'grounded':True,'unsupported_paragraph_ids':[],'additions':[]}
    with patch('coverage_ledger.efficient_audit',side_effect=repair),patch('transcript_reading.call_json',side_effect=review):
        result=accept_edition(owner,edition,'Title','Source',[],0)
    from transcript_reading import public_draft
    assert len(reviewed)==1 and reviewed[0]==public_draft(result['sections'])
    assert 'Temporary repair heading' not in result['markdown']


def test_changed_chapter_scope_cannot_reuse_a_pass_for_identical_paragraph_text():
    from tests.test_reading_delivery import candidate
    owner,edition=candidate(10)
    edition['sections'][0]['heading']='Unsupported universal scope'
    rejected={'checked_source_ids':[line.id for line in edition['lines']],
        'complete':True,'grounded':False,'unsupported_paragraph_ids':[],'additions':[]}
    with patch('transcript_reading.call_json',return_value=rejected) as review:
        with pytest.raises(SummaryOutputError):accept_edition(owner,edition,'Title','Source',[],0)
    assert review.call_count==1
    assert owner.generation_report['delivery']['status']=='blocked'


@pytest.mark.parametrize('outcome',['restored','still_missing','unsupported_old_claim','invalid_receipt','owned_raw'])
def test_local_source_rewrite_is_atomic_and_preserves_independently_supported_meaning(outcome):
    from reading_delivery import repair_unsupported
    _,lines=source_lines('Treatment helped only adults at the low dose.\nFollow-up lasted two weeks.')
    spans=[{'start':lines[0].id,'end':lines[-1].id}]
    sections,_=validate_sections({'sections':[{'heading':'Treatment','paragraphs':[
        {'text':'Treatment helps everybody. Follow-up lasted two weeks.','source_ranges':spans}]}]},lines)
    sections[0]['paragraphs'][0]['id']='P0';before=copy.deepcopy(sections)
    if outcome=='owned_raw':
        sections[0]['paragraphs'][0].update(raw=True,text=''.join(line.text for line in lines))
        before=copy.deepcopy(sections)
    item={'id':'C0','kind':'condition','statement':'Follow-up lasted '+('three' if outcome=='unsupported_old_claim' else 'two')+' weeks.',
        'source_ranges':[{'start':lines[1].id,'end':lines[1].id}]}
    owner=SimpleNamespace(client=Mock(base_url='https://model.test'),model='test',_quality_inventory=({},[item]),
        generation_report={'coverage_ledger':{'items':[] if outcome=='owned_raw' else [
            {'id':'C0','status':'covered','paragraph_ids':['P0']}]}})
    calls=[];repairs=[0]
    def complete(client,model,system,payload,timeout,**kwargs):
        request=json.loads(payload);calls.append(request)
        if request['phase']=='repair_grounding':
            repairs[0]+=1
            if repairs[0]==2:assert request['repair_feedback']['missing_obligations'][0]['id']=='C0'
            text='Treatment helped only adults at the low dose.'
            if outcome=='owned_raw':text='Only adults benefited at the low dose.'
            if repairs[0]==2 and outcome in ('restored','owned_raw'):text+=' Follow-up lasted two weeks.'
            return {'replacements':[{'id':'P0','text':text,'source_ranges':spans}]}
        assert request['phase']=='verify_grounding_preservation'
        assert sections==before  # No tentative rewrite is committed.
        text=''.join(p['text'] for section in request['global_draft'] for p in section['paragraphs'])
        return {'obligations':[{'id':'UNKNOWN' if outcome=='invalid_receipt' else 'C0',
            'source_supported':outcome!='unsupported_old_claim',
            'before_covered':outcome!='owned_raw','after_covered':'Follow-up lasted two weeks.' in text,
            'source_evidence':[{'start':lines[1].id,'end':lines[1].id}]}]}
    with patch('reading_editor._call_editor',side_effect=complete):
        if outcome in ('still_missing','invalid_receipt'):
            with pytest.raises(SummaryOutputError):repair_unsupported(owner,lines,sections,{'P0'})
            assert sections==before
        else:
            repair_unsupported(owner,lines,sections,{'P0'})
            text=sections[0]['paragraphs'][0]['text']
            assert 'everybody' not in text and 'three weeks' not in text
            if outcome=='restored':assert 'Follow-up lasted two weeks.' in text
            if outcome=='owned_raw':
                assert 'Follow-up lasted two weeks.' not in text
                assert owner.generation_report['grounding_preservation_checks'][0]['preexisting_uncovered']==1
    assert repairs[0]==(2 if outcome in ('restored','still_missing') else 1)
    assert len(calls)==repairs[0]*2+(1 if outcome=='invalid_receipt' else 0)
    assert owner._quality_inventory[1]==[item]  # No obligation was deleted or simplified.


def test_preservation_evidence_cannot_bridge_a_gap_not_supplied_to_the_reviewer():
    from reading_delivery import check_grounding_preservation
    owner,lines,sections,prepared=scene();owner.generation_report={}
    obligation={'id':'C','statement':'Both source facts matter.','source_ranges':[
        {'start':lines[0].id,'end':lines[0].id},{'start':lines[-1].id,'end':lines[-1].id}]}
    def complete(client,model,system,payload,timeout,**kwargs):
        request=json.loads(payload)
        assert lines[10].id not in {line['id'] for line in request['primary_source']}
        return {'obligations':[{'id':'C','source_supported':True,'before_covered':True,'after_covered':True,
            'source_evidence':[{'start':lines[0].id,'end':lines[-1].id}]}]}
    with patch('reading_editor._call_editor',side_effect=complete):
        with pytest.raises(SummaryOutputError) as error:
            check_grounding_preservation(owner,lines,sections,{}, {'P0':[obligation]})
    assert error.value.reason=='source_review'


@pytest.mark.parametrize('source_claim_wrong',[True,False])
def test_verify_contradicted_obligation_before_rewriting_correct_source_prose(source_claim_wrong):
    from coverage_ledger import _audit
    _,lines=source_lines('Only adults respond at the low dose.')
    spans=[{'start':lines[0].id,'end':lines[-1].id}]
    sections,_=validate_sections({'sections':[{'heading':'Treatment','paragraphs':[
        {'text':'Only adults respond at the low dose.' if source_claim_wrong else 'Only children respond.',
         'source_ranges':spans}]}]},lines)
    sections[0]['paragraphs'][0]['id']='P0';before=copy.deepcopy(sections);phases=[]
    item={'id':'C','kind':'claim','statement':'All ages respond.' if source_claim_wrong else 'Only adults respond at the low dose.',
        'source_ranges':spans}
    def respond(engine,system,payload,validator):
        phases.append(payload['phase'])
        if payload['phase']=='validate_inventory':
            assert payload['items'][0]['reported_status']=='contradicted'
            return {'items':[{'id':'C','supported':not source_claim_wrong,'material':False,'material_reason':'Do not hide the conflict.',
                **({'reason':'The source limits this to adults.','statement':'Only adults respond at the low dose.',
                    'source_ranges':spans} if source_claim_wrong else {})}]}
        assert payload['phase']=='match'  # Never append an opposite assertion.
        covered=source_claim_wrong and payload['items'][0]['statement'].startswith('Only adults')
        return {'matches':[{'item_id':'C','status':'covered' if covered else 'contradicted',
            'support':[{'paragraph_id':'P0'}],'grounded':True,'duplicate':False}]}
    with patch('coverage_ledger.request',side_effect=respond):
        ledger,items=_audit(SimpleNamespace(),lines,sections,inventory=[item])
    assert sections==before
    assert phases==['match','validate_inventory']+(['match'] if source_claim_wrong else [])
    assert ledger['contradiction_obligations_validated']==1
    assert bool(items[0].get('material',True))  # Never compress away a conflict.
    assert coverage_acceptable(ledger) is source_claim_wrong


def test_failed_contradiction_source_check_cannot_authorize_a_prose_rewrite():
    from tests.test_reading_delivery import candidate
    owner,edition=candidate(10);owner._quality_inventory=({},[])
    owner.generation_report['coverage_ledger']['items'][0]['status']='contradicted'
    owner.generation_report['coverage_ledger']['inventory_validation_failed_batches']=1
    with patch('reading_delivery.repair_unsupported',side_effect=AssertionError('Unchecked checklist is not source truth')):
        with pytest.raises(SummaryOutputError) as error:accept_edition(owner,edition,'Title','Source',[],0)
    assert error.value.reason=='source_review'


def test_matching_contradiction_captures_original_prose_even_when_grounded_flag_is_true():
    from scripts.summary_memory_diagnostics import MemoryDiagnostics
    owner,lines,sections,prepared=scene();item=prepared[1][0]
    draft=[{'heading':'Claim','paragraphs':[{'id':'P0','text':'Original source-supported prose.',
        'source_ranges':item['source_ranges'],'raw':False}]}]
    observer=MemoryDiagnostics()
    rejection=row(item,'contradicted',grounded=True)
    rejection['support']=[{'paragraph_id':'P0'}]
    observer.observe_matching({'items':[item],'global_draft':draft},
        {'matches':[rejection]})
    draft[0]['paragraphs'][0]['text']='A later correction.'
    assert observer.grounding[0]['paragraph']['text']=='Original source-supported prose.'
    assert observer.grounding[0]['matching_contradiction'] is True
    observer.clear();assert observer.grounding==[]


def test_incomplete_large_source_inventory_blocks_draft_without_spending_a_generation_call():
    from concurrent.futures import Future
    from transcript_reading import _generate_with_inventory
    source='A supported argument.\nAn essential condition.';revision,lines=source_lines(source)
    ready=Future();ready.set_result(({'inventory_batches':2,'inventory_failed_batches':1},[]))
    owner=SimpleNamespace(generation_mode='single',quality_coverage_threshold=.9,generation_report={})
    with patch('coverage_ledger.SOURCE_LIMIT',1), \
         patch('transcript_reading.call_json',side_effect=AssertionError('No drafting against incomplete source inventory')):
        with pytest.raises(SummaryOutputError) as error:
            _generate_with_inventory(owner,source,'Title',revision,lines,ready,formats=(),style='detailed',
                extras='',visual_context='',tags=(),progress=None,duration=0,stage_callback=None)
    assert error.value.reason=='source_review'
    assert owner.generation_report['delivery']['status']=='blocked'


@pytest.mark.parametrize('first_reply',['rejected','raw'])
def test_raw_fallback_correction_targets_original_rejection_and_cannot_replay_it_unchanged(first_reply):
    from reading_delivery import remember_source_rejection,repair_unsupported,save_candidate
    from scripts.validate_parallel_processing import Store
    from processing_execution import Execution
    _,lines=source_lines('Only adults respond at the low dose.')
    spans=[{'start':lines[0].id,'end':lines[0].id}]
    bad='Every age responds at any dose.'
    sections,_=validate_sections({'sections':[{'heading':'Scope','paragraphs':[{'text':bad,'source_ranges':spans}]}]},lines)
    sections[0]['paragraphs'][0]['id']='P0'
    owner=SimpleNamespace(client=Mock(base_url='https://model.test'),model='test',generation_report={},_quality_inventory=({},[]))
    remember_source_rejection(owner,sections,{'P0'},{'P0':['The scope and dose are unsupported.']})
    sections[0]['paragraphs'][0].update(text=lines[0].text,raw=True)
    remember_source_rejection(owner,sections,{'P0'},{'P0':['A later source slice sees only raw fallback.']})
    store=Store();execution=Execution('owner','source',store)
    save_candidate(execution,'key',owner,{'sections':sections,'overview':''})
    assert bad not in json.dumps(list(store.values.values()))  # Context stays RAM-only.
    calls=[]
    def complete(client,model,system,payload,timeout,**kwargs):
        request=json.loads(payload);calls.append(request)
        assert request['paragraphs'][0]['rejected_text']==bad
        assert request['paragraphs'][0]['review_feedback']==['The scope and dose are unsupported.']
        return {'replacements':[{'id':'P0','text':(bad if first_reply=='rejected' else lines[0].text) if len(calls)==1 else 'At the low dose, the response applies only to adults.',
            'source_ranges':spans}]}
    with patch('reading_editor._call_editor',side_effect=complete):repair_unsupported(owner,lines,sections,{'P0'})
    assert len(calls)==2
    assert owner._source_rejection_context=={}
    assert owner.generation_report['grounding_repair_sizes'][0]['original_rejections_used']==1
    assert bad not in json.dumps(owner.generation_report)


@pytest.mark.parametrize('result',['resolved','still_rejected','unchanged_version'])
def test_new_locatable_final_source_rejection_uses_only_existing_late_correction_budget(result):
    from tests.test_reading_delivery import candidate
    owner,edition=candidate(10);owner._quality_inventory=({},[])
    edition['sections'][0]['paragraphs'][0]['raw']=True
    repairs=[];reviews=[]
    def rewrite(*args,**kwargs):
        paragraph=args[2][0]['paragraphs'][0];paragraph.pop('raw',None)
        repairs.append(paragraph['text'])
        if result!='unchanged_version':paragraph['text']+=' corrected'
    def review(*args):
        reviews.append(json.loads(args[2]))
        good=result=='resolved' and len(reviews)>1
        return {'checked_source_ids':[line.id for line in edition['lines']],
            'complete':True,'grounded':good,'unsupported_paragraph_ids':[] if good else ['P1'],'additions':[]}
    ledger=copy.deepcopy(owner.generation_report['coverage_ledger'])
    with patch('reading_delivery.repair_unsupported',side_effect=rewrite), \
         patch('coverage_ledger.efficient_audit',return_value=ledger),patch('transcript_reading.call_json',side_effect=review):
        if result=='resolved':accept_edition(owner,edition,'Title','Source',[],0)
        else:
            with pytest.raises(SummaryOutputError):accept_edition(owner,edition,'Title','Source',[],0)
    assert len(repairs)==(1 if result=='unchanged_version' else 2)
    assert len(reviews)==(1 if result=='unchanged_version' else 2)
    assert owner.generation_report['late_contradiction_repair_attempts']==(0 if result=='unchanged_version' else 1)
    if result!='unchanged_version':assert owner.generation_report['late_contradiction_repair_origin']=='final_source_review'
    assert owner.generation_report['delivery']['status']==('accepted' if result=='resolved' else 'blocked')


@pytest.mark.parametrize('before_covered,after_covered,expected_losses',[
    (True,False,1),(True,True,0),(False,False,0),(False,True,0)])
def test_preservation_compares_original_rejected_prose_and_counts_only_new_loss(before_covered,after_covered,expected_losses):
    from reading_delivery import check_grounding_preservation,remember_source_rejection
    owner,lines,sections,prepared=scene();owner.generation_report={}
    before=copy.deepcopy(sections)
    remember_source_rejection(owner,sections,{'P0'})
    sections[0]['paragraphs'][0].update(raw=True,text=lines[0].text)
    owner._source_correction_overview='An existing supported opening.'
    replacement=copy.deepcopy(before[0]['paragraphs'][0]);replacement['text']='Corrected factual claim.'
    def complete(client,model,system,payload,timeout,**kwargs):
        request=json.loads(payload)
        assert request['previous_draft'][0]['paragraphs'][0]['text']==before[0]['paragraphs'][0]['text']
        assert request['previous_draft'][0]['paragraphs'][0]['raw'] is False
        assert request['global_draft'][0]['paragraphs'][0]['text']=='Corrected factual claim.'
        assert request['previous_draft'][-1]==request['global_draft'][-1]
        return {'obligations':[{'id':'C0','source_supported':True,'before_covered':before_covered,
            'after_covered':after_covered,'source_evidence':prepared[1][0]['source_ranges']}]}
    with patch('reading_editor._call_editor',side_effect=complete):
        losses=check_grounding_preservation(owner,lines,sections,{'P0':replacement},{'P0':[prepared[1][0]]})
    assert len(losses)==expected_losses
    check=owner.generation_report['grounding_preservation_checks'][0]
    assert check['preexisting_uncovered']==int(not before_covered and not after_covered)
    assert check['newly_covered']==int(not before_covered and after_covered)
    assert check['missing_supported']==expected_losses
    assert sections[0]['paragraphs'][0]['raw'] is True
    assert prepared[1][0]['statement']=='Fact 0.'


@pytest.mark.parametrize('case',['valid','missing','unknown','duplicate','unsupported','false_conflict','bad_evidence'])
def test_private_draft_map_requires_every_source_obligation_without_certifying_coverage(case):
    from transcript_reading import validate_obligation_map
    owner,lines,sections,prepared=scene();items=prepared[1][:2]
    data={'sections':[{'heading':'Scope','paragraphs':[{'text':'A thematic mention.',
        'source_ranges':items[0]['source_ranges'],'obligation_ids':['C0','C1']}]}]}
    paragraph=data['sections'][0]['paragraphs'][0]
    if case=='missing':paragraph['obligation_ids']=['C0']
    if case=='unknown':paragraph['obligation_ids']=['C0','invented']
    if case=='duplicate':paragraph['obligation_ids']=['C0','C0','C1']
    if case in ('unsupported','false_conflict','bad_evidence'):
        paragraph['obligation_ids']=['C0']
        data['source_conflicts']=[{'obligation_id':'C1','source_ranges':items[1]['source_ranges']}]
        if case=='false_conflict':paragraph['obligation_ids'].append('C1')
        if case=='bad_evidence':data['source_conflicts'][0]['source_ranges']=[{'start':'unknown','end':'unknown'}]
    if case in ('valid','unsupported'):
        result=validate_obligation_map(data,items,lines)
        assert result['semantic_coverage_certified'] is False
        assert result['supplied']==2
        assert result['mapped']==(1 if case=='unsupported' else 2)
        assert prepared[1][:2]==items  # No item is changed or removed.
    else:
        with pytest.raises(SummaryOutputError) as error:validate_obligation_map(data,items,lines)
        assert error.value.reason=='obligation_map'


@pytest.mark.parametrize('extra',['material','background','failed'])
@pytest.mark.parametrize('all_units_cited',[False,True])
def test_source_inventory_reviews_meaning_once_without_draft_or_inventory_deletion(extra,all_units_cited):
    from coverage_ledger import build_inventory
    owner,lines,_,_=scene();lines=lines[:4];requests=[]
    def parts(owned,limit):return [owned[start:start+2] for start in range(0,len(owned),2)]
    def respond(engine,system,payload,validator):
        requests.append(copy.deepcopy(payload));rows=payload['primary_source']
        assert payload['phase']=='inventory' and 'global_draft' not in payload
        supplement=payload.get('source_inventory_completeness_check',False)
        if supplement and extra=='failed':raise RuntimeError('synthetic source scan failure')
        known={span['start'] for item in payload.get('known_source_obligations',[]) for span in item['source_ranges']}
        selected=[row for row in rows if row['id'] not in known] if supplement and extra=='material' else [] if supplement else rows[:1]
        data={'checked_source_ranges':[{'start':rows[0]['id'],'end':rows[-1]['id']}],
            'items':[{'kind':'condition','statement':line['text'],
                'source_ranges':[{'start':line['id'],'end':rows[-1]['id'] if not supplement and all_units_cited else line['id']}]} for line in selected]}
        if supplement and extra=='material':
            prior=payload['known_source_obligations'][0]
            data['items'].append({key:prior[key] for key in ('kind','statement','source_ranges')})
        validator(data);return data
    with patch('transcript_reading.source_work_batches',side_effect=parts),patch('coverage_ledger.request',side_effect=respond):
        report,items=build_inventory(owner,lines)
    scans=[request for request in requests if request.get('source_inventory_completeness_check')]
    assert len(scans)==1  # Never recursively re-scan a valid empty result.
    assert {row['id'] for row in scans[0]['primary_source']}=={line.id for line in lines}
    assert len(scans[0]['known_source_obligations'])==2
    assert report['inventory_unclaimed_units']==(0 if all_units_cited else 2)
    assert report['inventory_supplement_batches']==1
    assert len(items)==(4 if extra=='material' else 2)
    assert report.get('inventory_supplement_exact_repeats',0)==int(extra=='material')
    assert items[:2][0]['source_ranges']==[{'start':lines[0].id,'end':lines[1 if all_units_cited else 0].id}]
    assert bool(report['inventory_failed_batches'])==(extra=='failed')
    assert report['inventory_unclaimed_units_reviewed']==(0 if extra=='failed' or all_units_cited else 2)
    assert report['inventory_completeness_units_reviewed']==(0 if extra=='failed' else 4)
    assert len({item['id'] for item in items})==len(items)


def test_unclaimed_source_scan_cannot_cite_across_unprovided_units():
    from coverage_ledger import _audit
    owner,lines,_,_=scene();owned=[lines[0],lines[2]]
    def invalid(engine,system,payload,validator):
        rows=payload['primary_source']
        data={'checked_source_ranges':[{'start':rows[0]['id'],'end':rows[-1]['id']}],
            'items':[{'kind':'claim','statement':'A synthetic claim.',
                'source_ranges':[{'start':lines[0].id,'end':lines[2].id}]}]}
        validator(data);return data
    with patch('coverage_ledger.request',side_effect=invalid):
        report,items=_audit(owner,lines,[],inventory_only=True,
            inventory_parts=[(0,0,owned)],inventory_context=[])
    assert report['inventory_failed_batches'] and not items


def test_private_obligation_map_cannot_supply_missing_semantic_coverage():
    from transcript_reading import validate_obligation_map
    from coverage_ledger import _audit,coverage_acceptable
    owner,lines,sections,prepared=scene();items=prepared[1][:2]
    sections=sections[:1];sections[0]['paragraphs'][0]['text']='Only a broad topic mention.'
    data={'sections':[{'heading':'Topic','paragraphs':[{'text':'Only a broad topic mention.',
        'obligation_ids':['C0','C1'],'source_ranges':items[0]['source_ranges']}]}]}
    assert validate_obligation_map(data,items,lines)['mapped']==2
    def match(engine,system,payload,validator):
        assert all('obligation_ids' not in paragraph for section in payload['global_draft'] for paragraph in section['paragraphs'])
        return {'matches':[row(item,'missing') for item in items]}
    with patch('coverage_ledger.request',side_effect=match):
        ledger,_=_audit(owner,lines,sections,inventory=items,matching_only=True)
    assert len(ledger['items'])==2 and all(item['status']=='missing' for item in ledger['items'])
    assert not coverage_acceptable(ledger)


@pytest.mark.parametrize('formats',[('screenshot',),('link',),('summary','screenshot','link')])
def test_video_media_retains_original_event_level_ids_and_timestamps(formats):
    text=timed_source();owner=SimpleNamespace(generation_mode='single',generation_report={})
    def inspect(engine,source,title,revision,lines,*args,**kwargs):return {'lines':lines}
    with patch('coverage_ledger.build_inventory',return_value=({},[])),patch('transcript_reading._generate_with_inventory',side_effect=inspect):
        edition=generate(owner,text,'Title',formats=formats)
    assert len(edition['lines'])==2170
    assert edition['lines']==source_lines(text)[1]
    assert all(':g' not in line.id for line in edition['lines'])
    assert owner.generation_report['source_layout']=='original-lines'
