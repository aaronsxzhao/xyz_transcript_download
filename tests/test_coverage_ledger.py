"""Local pipeline guarantees; live semantic regression is recorded separately."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from coverage_ledger import audit, matching_response, inventory_response
from transcript_reading import source_lines, validate_sections, generate
from summary_errors import ProcessingCancelledError

CASES=json.loads((Path(__file__).parent/'fixtures/coverage_ledger/huberman.json').read_text())


def test_coverage_rounds_keep_prior_repairs_when_later_ledger_is_replaced():
    from coverage_ledger import measure_coverage_round
    owner = SimpleNamespace(generation_report={})
    first = {'status':'unverified','initial_unresolved_items':30,'unresolved_items':7,
        'repairs_accepted':23,'repairs_rejected':4,'requests':32,
        'corrected_inventory_items':['private-id'],
        'items':[{'status':'covered','kind':'claim','statement':'private source text'}, {'status':'missing','kind':'example'}]}
    second = {'status':'unverified','initial_unresolved_items':7,'unresolved_items':7,
        'repairs_accepted':0,'repairs_rejected':0,'requests':12,
        'items':[{'status':'covered'}, {'status':'missing'}]}
    owner.generation_report['coverage_ledger'] = measure_coverage_round(owner,'initial',lambda *_: first)
    owner.generation_report['coverage_ledger'] = measure_coverage_round(owner,'after_grounding_repair',lambda *_: second)
    rounds = owner.generation_report['coverage_rounds']
    assert [r['accepted_paragraphs'] for r in rounds] == [23,0]
    assert [r['phase'] for r in rounds] == ['initial','after_grounding_repair']
    assert rounds[0]['status_counts']['missing'] == 1
    assert rounds[0]['unresolved_by_kind']['example'] == 1
    assert rounds[0]['source_corrected_items'] == 1
    assert 'private' not in json.dumps(rounds)
    assert owner.generation_report['coverage_ledger'] is second


def test_interrupted_coverage_round_is_recorded_and_cancellation_propagates():
    from coverage_ledger import measure_coverage_round
    owner = SimpleNamespace(generation_report={})
    def interrupted(*_): raise ProcessingCancelledError('private detail')
    with pytest.raises(ProcessingCancelledError):
        measure_coverage_round(owner,'resume',interrupted)
    assert owner.generation_report['coverage_rounds'][0]['outcome'] == 'interrupted'
    assert owner.generation_report['coverage_rounds'][0]['cancelled'] is True
    assert 'private' not in json.dumps(owner.generation_report)


@pytest.mark.parametrize(('status','grounded','duplicate','prior','expected'), [
    ('covered',True,True,'missing','duplicate_or_no_novelty'),
    ('partial',True,False,'missing','still_partial_or_missing'),
    ('covered',False,False,'missing','ungrounded'),
    ('contradicted',True,False,'missing','contradicted'),
    ('covered',True,False,'covered','no_prior_gap_improved'),
    ('covered',True,False,'missing','joint_dependency_rejected'),
])
def test_repair_rejection_categories_explain_existing_gate(status, grounded, duplicate, prior, expected):
    from coverage_ledger import repair_rejection_reason
    row={'item_id':'C1','status':status,'grounded':grounded,'duplicate':duplicate,
         'support':[{'paragraph_id':'P1'}]}
    assert repair_rejection_reason('P1',[row],{'C1':{'status':prior}},False) == expected
    assert repair_rejection_reason('P1',[row],{'C1':{'status':prior}},True) == 'existing_support_regressed'
    assert repair_rejection_reason('P2',[row],{'C1':{'status':prior}},False) == 'no_matching_support'


def setup_case(case):
    _,lines=source_lines(case['source'])
    ranges=[{'start':lines[0].id,'end':lines[-1].id}]
    sections,_=validate_sections({'sections':[{'heading':'Argument','paragraphs':[
        {'text':case['missing_draft'],'source_ranges':ranges}]}]},lines)
    sections[0]['paragraphs'][0]['id']='P1'
    return lines,sections,ranges


def scripted(case, calls, *, bad_repair=False):
    def request(engine, system, payload, validate):
        calls.append(copy.deepcopy(payload))
        if payload['phase']=='validate_inventory':
            assert 'global_draft' not in payload
            return {'items':[{'id':item['id'],'supported':True} for item in payload['items']]}
        rows=payload['primary_source']
        ranges=[{'start':rows[0]['id'],'end':rows[-1]['id']}]
        if payload['phase']=='inventory':
            assert 'global_draft' not in payload and 'overview' not in payload
            return {'checked_source_ranges':ranges,'items':[{'kind':case['kind'],
                    'statement':case['complete_draft'],'source_ranges':ranges}]}
        if payload['phase']=='repair':
            return {'sections':[{'heading':'Argument','paragraphs':[{
                'text':case['complete_draft'],'source_ranges':ranges}]}]}
        paragraphs=[p for s in payload['global_draft'] for p in s['paragraphs']]
        support=next((p for p in paragraphs if case['complete_draft'] in p['text']),None)
        return {'checked_proposed_paragraph_ids':payload.get('proposed_paragraph_ids',[]),
                'matches':[{'item_id':item['id'],'status':'covered' if support else 'partial',
            'support':[{'paragraph_id':support['id'],'quote':case['complete_draft']}] if support else [],
            'grounded':not bad_repair,'duplicate':False} for item in payload['items']]}
    return request


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['name'])
def test_missing_real_meaning_is_locally_repaired_and_not_added_twice(case):
    lines,sections,_=setup_case(case);calls=[];engine=SimpleNamespace()
    original=sections[0]['paragraphs'][0]['text']
    with patch('coverage_ledger.request',side_effect=scripted(case,calls)):
        report=audit(engine,lines,sections)
        second=audit(engine,lines,sections)
    assert report['status']=='model_reviewed' and report['repairs_accepted']==1
    assert second['repairs_accepted']==0 and second['status']=='model_reviewed'
    assert sections[0]['paragraphs'][0]['text']==original
    assert len(sections)==2
    assert [p['phase'] for p in calls]==['inventory','match','validate_inventory','repair','match','inventory','match']
    assert report['items'][0]['paragraph_ids']==['L1.1']


def test_repair_failing_independent_grounding_is_never_published():
    case=CASES[0];lines,sections,_=setup_case(case);before=copy.deepcopy(sections)
    with patch('coverage_ledger.request',side_effect=scripted(case,[],bad_repair=True)):
        report=audit(SimpleNamespace(),lines,sections)
    assert sections==before and report['repairs_rejected']==2
    assert report['recovery_rounds']==1
    assert report['status']=='unverified' and report['items'][0]['status']=='partial'


def test_final_recovery_repairs_only_remaining_items_without_rebuilding_inventory():
    case=CASES[0];lines,sections,ranges=setup_case(case);calls=[];repairs=[]
    base=scripted(case,calls)
    def respond(engine,system,payload,validator):
        data=base(engine,system,payload,validator)
        if payload['phase']=='repair':
            repairs.append(payload)
            if len(repairs)==1:
                data['sections'][0]['paragraphs'][0]['text']='A still incomplete explanation.'
        return data
    original=copy.deepcopy(sections)
    with patch('coverage_ledger.request',side_effect=respond):
        report=audit(SimpleNamespace(),lines,sections)
    assert report['status']=='model_reviewed' and report['unresolved_items']==0
    assert report['initial_unresolved_items']==1 and report['recovery_rounds']==1
    assert report['repairs_accepted']==1 and report['repairs_rejected']==1
    assert sections[0]==original[0]
    assert sum(p['phase']=='inventory' for p in calls)==1
    assert len(repairs)==2 and repairs[0]['items']==repairs[1]['items']
    assert 'incomplete explanation' not in json.dumps(sections)


def test_transient_matching_failure_can_recover_without_hiding_failure_history():
    case=CASES[0];lines,sections,_=setup_case(case);calls=[];failed=[]
    base=scripted(case,calls)
    def respond(engine,system,payload,validator):
        if payload['phase']=='match' and not failed:
            failed.append(True)
            raise TimeoutError('Synthetic one-time failure')
        return base(engine,system,payload,validator)
    with patch('coverage_ledger.request',side_effect=respond):
        report=audit(SimpleNamespace(),lines,sections)
    assert report['status']=='model_reviewed' and report['failed_batches']==0
    assert report['initial_failed_batches']==1 and report['recovery_rounds']==1
    assert sum(p['phase']=='inventory' for p in calls)==1


def test_later_accepted_addition_resolves_earlier_item_without_another_repair():
    case={'source':'[00:00] First condition.\n[00:01] Second condition.',
          'missing_draft':'An introduction.'}
    lines,sections,ranges=setup_case(case);calls=[]
    def respond(engine,system,payload,validator):
        calls.append(copy.deepcopy(payload))
        if payload['phase']=='validate_inventory':
            return {'items':[{'id':item['id'],'supported':True} for item in payload['items']]}
        if payload['phase']=='inventory':
            return {'checked_source_ranges':ranges,'items':[
                {'kind':'condition','statement':text,'source_ranges':ranges}
                for text in ('First condition.','Second condition.')]}
        if payload['phase']=='repair':
            text='An incomplete addition.' if payload['items'][0]['statement']=='First condition.' else 'First condition. Second condition.'
            return {'sections':[{'heading':'Argument','paragraphs':[{'text':text,'source_ranges':ranges}]}]}
        rows=[]
        for item in payload['items']:
            p=next((p for s in payload['global_draft'] for p in s['paragraphs'] if item['statement'] in p['text']),None)
            rows.append({'item_id':item['id'],'status':'covered' if p else 'missing',
                         'grounded':True,'duplicate':False,
                         'support':[{'paragraph_id':p['id'],'quote':item['statement']}] if p else []})
        return {'checked_proposed_paragraph_ids':payload.get('proposed_paragraph_ids',[]),'matches':rows}
    with patch('coverage_ledger.ITEM_LIMIT',1),patch('coverage_ledger.request',side_effect=respond):
        report=audit(SimpleNamespace(),lines,sections)
    assert report['status']=='model_reviewed' and report['initial_unresolved_items']==1
    assert report['repairs_accepted']==1 and len(sections)==2
    assert sum(p['phase']=='repair' for p in calls)==2
    assert calls[-1]['phase']=='match' and calls[-1]['items'][0]['id']=='C1.1'
    assert report['items'][0]['paragraph_ids']==['L2.1']


@pytest.mark.parametrize('failure',[TimeoutError(),ProcessingCancelledError()])
def test_inventory_failures_are_explicit_and_cancellation_propagates(failure):
    lines,sections,_=setup_case(CASES[0]);before=copy.deepcopy(sections)
    with patch('coverage_ledger.request',side_effect=failure):
        if isinstance(failure,ProcessingCancelledError):
            with pytest.raises(ProcessingCancelledError):audit(SimpleNamespace(),lines,sections)
        else:
            result=audit(SimpleNamespace(),lines,sections)
            assert result['failed_batches']==1 and result['status']=='unverified'
    assert sections==before


def test_transient_inventory_failure_recovers_before_matching():
    case=CASES[0]
    lines,sections,_=setup_case(case)
    calls=[]
    respond=scripted(case,calls)
    attempts=0
    def intermittent(engine,system,payload,validate):
        nonlocal attempts
        if payload['phase']=='inventory':
            attempts+=1
            if attempts==1:raise TimeoutError('temporary provider timeout')
        return respond(engine,system,payload,validate)
    with patch('coverage_ledger.request',side_effect=intermittent):
        result=audit(SimpleNamespace(),lines,sections)
    assert attempts==2
    assert result['status']=='model_reviewed'
    assert result['inventory_failed_batches']==0
    assert result['inventory_transport_retries']==1
    assert result['inventory_recovered_batches']==1
    assert result['covered_items']==1


def test_persistent_inventory_timeout_is_bounded_and_never_certified():
    lines,sections,_=setup_case(CASES[0])
    before=copy.deepcopy(sections)
    with patch('coverage_ledger.request',side_effect=TimeoutError()) as model:
        result=audit(SimpleNamespace(),lines,sections)
    assert model.call_count==2
    assert result['status']=='unverified'
    assert result['inventory_failed_batches']==1
    assert result['inventory_recovered_batches']==0
    assert sections==before


def test_invalid_inventory_splits_only_failed_batch_and_covers_every_line():
    case=CASES[0];lines,sections,_=setup_case(case)
    calls=[];respond=scripted(case,calls)
    inventories=[]
    def provider(engine,system,payload,validate):
        if payload['phase']=='inventory':
            ids=[line['id'] for line in payload['primary_source']]
            inventories.append(ids)
            if len(ids)==len(lines):raise ValueError('Invalid source receipts')
        return respond(engine,system,payload,validate)
    with patch('coverage_ledger.request',side_effect=provider):
        result=audit(SimpleNamespace(),lines,sections)
    assert result['status']=='model_reviewed'
    assert result['inventory_split_retries']==1
    assert result['inventory_recovered_batches']==1
    assert inventories[2]+inventories[3]==[line.id for line in lines]
    assert result['inventory_failed_batches']==0


def test_failed_split_never_certifies_missing_source_and_records_safe_range():
    lines,sections,_=setup_case(CASES[0])
    with patch('coverage_ledger.request',side_effect=ValueError('Private provider output')) as provider:
        result=audit(SimpleNamespace(),lines,sections)
    assert provider.call_count==3
    assert result['status']=='unverified' and result['inventory_failed_batches']==1
    assert result['inventory_failures']==[{'batch':1,'start':lines[0].id,'end':lines[-1].id,'error_type':'ValueError'}]
    assert 'Private provider output' not in json.dumps(result)


def test_inventory_retry_does_not_repeat_successful_source_batches():
    case=CASES[0]
    lines,sections,_=setup_case(case)
    attempts={}
    calls=[]
    respond=scripted(case,calls)
    def intermittent(engine,system,payload,validate):
        if payload['phase']=='inventory':
            identity=payload['primary_source'][0]['id']
            attempts[identity]=attempts.get(identity,0)+1
            if len(attempts)==2 and attempts[identity]==1:
                raise ConnectionError('transient disconnect')
        return respond(engine,system,payload,validate)
    with patch('coverage_ledger.SOURCE_LIMIT',100),patch('coverage_ledger.request',side_effect=intermittent):
        result=audit(SimpleNamespace(),lines,sections)
    assert len(attempts)>2
    assert list(attempts.values()).count(2)==1
    assert all(count in (1,2) for count in attempts.values())
    assert result['inventory_failed_batches']==0
    assert result['inventory_recovered_batches']==1


@pytest.mark.parametrize('damage',['missing_item','duplicate_item','unknown_paragraph','raw_fallback'])
def test_same_topic_or_invalid_receipts_cannot_certify_coverage(damage):
    items=[{'id':'C1'}];draft=[{'paragraphs':[{'id':'P1','text':'Internal reward helps.','raw':damage=='raw_fallback'}]}]
    row={'item_id':'C1','status':'covered','grounded':True,'duplicate':False,
         'support':[{'paragraph_id':'invented' if damage=='unknown_paragraph' else 'P1'}]}
    data={'matches':[] if damage=='missing_item' else [row,row] if damage=='duplicate_item' else [row]}
    with pytest.raises(ValueError):matching_response(data,items,draft)


def test_inventory_requires_receipts_for_every_source_line():
    lines,_,ranges=setup_case(CASES[0])
    with pytest.raises(ValueError):
        inventory_response({'checked_source_ranges':[{'start':lines[0].id,'end':lines[0].id}],'items':[]},lines)


@pytest.mark.parametrize('mode',['single','segmented'])
def test_public_pipeline_includes_ledger_without_an_extra_drafting_pass(mode):
    from tests.test_transcript_reading import provider
    case=CASES[0];calls=[];ledger_calls=[]
    engine=SimpleNamespace(generation_mode=mode,chunk_chars=1000,generation_report={})
    with patch('transcript_reading.call_json',side_effect=provider(calls)),patch('coverage_ledger.request',side_effect=scripted(case,ledger_calls)):
        result=generate(engine,case['source'],'Title',formats=['link','screenshot'])
    assert engine.generation_report['coverage_ledger']['repairs_accepted']==1
    assert case['complete_draft'] in result['markdown']
    assert sum('mode' in call for call in calls)==engine.generation_report['generation_requests']
    if mode=='single':assert engine.generation_report['generation_requests']==1


def test_invalid_inventory_is_not_cached_and_valid_inventory_is_reused():
    from coverage_ledger import request
    from processing_execution import Execution,bind
    class Store:
        def __init__(self):self.values={}
        def get_checkpoint(self,*args):return self.values.get(args)
        def put_checkpoint(self,*args):self.values[args[:-1]]=args[-1]
    lines,_,ranges=setup_case(CASES[0]);store=Store()
    engine=SimpleNamespace(model='synthetic',client=SimpleNamespace(base_url='https://example.test/v1'))
    valid={'checked_source_ranges':ranges,'items':[]}
    with bind(Execution('owner','source',store)),patch('reading_editor._call_editor',side_effect=[{},valid]) as model:
        with pytest.raises(ValueError):request(engine,'inventory',{'primary_source':[]},lambda data:inventory_response(data,lines))
        request(engine,'inventory',{'primary_source':[]},lambda data:inventory_response(data,lines))
        request(engine,'inventory',{'primary_source':[]},lambda data:inventory_response(data,lines))
    assert model.call_count==2 and len(store.values)==1


def test_inventory_owns_all_source_once_and_matching_sees_later_answers():
    case={'source':'[00:00] Does the intervention always work?\n'+('Context about this question.\n'*120)+
          '[10:00] It works only when pressure remains below 5 kPa for 10 seconds.',
          'missing_draft':'It works only when pressure remains below 5 kPa for 10 seconds.',
          'complete_draft':'It works only when pressure remains below 5 kPa for 10 seconds.','kind':'condition'}
    lines,sections,_=setup_case(case);calls=[]
    def response(engine,system,payload,validator):
        if payload['phase']=='match':
            assert case['complete_draft'] in json.dumps(payload['global_draft'])
        return scripted(case,calls)(engine,system,payload,validator)
    with patch('coverage_ledger.SOURCE_LIMIT',1000),patch('coverage_ledger.request',side_effect=response):
        report=audit(SimpleNamespace(),lines,sections)
    inventories=[call for call in calls if call['phase']=='inventory']
    assert len(inventories)>1
    assert ''.join(row['text'] for call in inventories for row in call['primary_source'])==case['source']
    assert all(call['phase']=='inventory' for call in calls[:len(inventories)])
    assert report['status']=='model_reviewed' and report['repairs_accepted']==0


@pytest.mark.parametrize('damage',['duplicate','extra_unchecked_paragraph'])
def test_candidate_cannot_publish_repeated_or_unchecked_claims(damage):
    case=CASES[0];lines,sections,_=setup_case(case);before=copy.deepcopy(sections);calls=[]
    def response(engine,system,payload,validator):
        if payload['phase']=='verify_repair_delta':
            data={'paragraphs':[{'id':p['id'],'grounded':True,'adds_material_meaning':False,
                                'contradicts_existing':False} for p in payload['proposed_paragraphs']]}
            validator(data)
            return data
        data=scripted(case,calls)(engine,system,payload,validator)
        if payload['phase']=='repair' and damage=='extra_unchecked_paragraph':
            extra=copy.deepcopy(data['sections'][0]['paragraphs'][0]);extra['text']='An unrelated unsupported claim.'
            data['sections'][0]['paragraphs'].append(extra)
        if payload['phase']=='match' and payload.get('proposed_paragraph_ids') and damage=='duplicate':
            for row in data['matches']:row['duplicate']=True
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert report['repairs_rejected']>0
    assert 'An unrelated unsupported claim.' not in json.dumps(sections)
    if damage=='duplicate':
        assert sections==before and report['status']=='unverified'
    else:
        assert report['repairs_accepted']==1 and case['complete_draft'] in json.dumps(sections)


def test_contradiction_is_explicit_and_never_patched_by_appending_its_opposite():
    case=CASES[1];lines,sections,_=setup_case(case);calls=[]
    def response(engine,system,payload,validator):
        data=scripted(case,calls)(engine,system,payload,validator)
        if payload['phase']=='match':data['matches'][0]['status']='contradicted'
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert report['items'][0]['status']=='contradicted' and report['status']=='unverified'
    assert not any(call['phase']=='repair' for call in calls)


def test_provider_configuration_failure_stops_all_remaining_inventory_calls():
    error=RuntimeError('private provider response');error.status_code=401
    lines,sections,_=setup_case(CASES[0])
    with patch('coverage_ledger.SOURCE_LIMIT',100),patch('coverage_ledger.request',side_effect=error) as model:
        report=audit(SimpleNamespace(),lines,sections)
    assert 1 <= model.call_count <= 2 and report['failed_batches']>1 and report['status']=='unverified'
    assert 'private' not in json.dumps(report)


def test_json_mode_is_explicit_in_every_request():
    from coverage_ledger import request
    engine=SimpleNamespace(model='synthetic',client=SimpleNamespace(base_url='https://example.test/v1'))
    with patch('reading_editor.call_editor',return_value={}) as call:
        request(engine,'Inventory without format words',{},lambda value:None)
    assert 'Return valid JSON only.' in call.call_args.args[2]


def test_invented_excerpt_boundary_is_not_an_omission_to_add():
    case=CASES[0];lines,sections,_=setup_case(case);before=copy.deepcopy(sections)
    def response(engine,system,payload,validator):
        assert payload['phase']=='inventory'
        rows=payload['primary_source'];ranges=[{'start':rows[0]['id'],'end':rows[-1]['id']}]
        return {'checked_source_ranges':ranges,'items':[{'kind':'condition',
            'statement':'The excerpt ends before describing the answer.','source_ranges':ranges}]}
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert sections==before and report['ignored_boundary_items']==0
    assert report['inventory_failed_batches']==1 and report['validation_retries']==1
    assert report['status']=='unverified' and report['repairs_accepted']==0


def test_valid_inventory_cannot_smuggle_boundary_commentary_in_its_repair():
    case=CASES[0];lines,sections,_=setup_case(case);before=copy.deepcopy(sections);calls=[]
    def response(engine,system,payload,validator):
        data=scripted(case,calls)(engine,system,payload,validator)
        if payload['phase']=='repair':
            data['sections'][0]['paragraphs'][0]['text']='The excerpt ends before explaining the mechanism.'
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert sections==before and report['status']=='unverified'
    assert report['failed_batches']==1


def test_descriptive_category_variations_do_not_discard_valid_evidence():
    lines,_,ranges=setup_case(CASES[0])
    data={'checked_source_ranges':ranges,'items':[
        {'kind':'example','statement':'The experiment has a stated outcome.','source_ranges':ranges},
        {'kind':'objection','statement':'The speaker raises a limitation.','source_ranges':ranges},
        {'kind':'interpretation','statement':'A source-backed claim.','source_ranges':ranges}]}
    assert [item['kind'] for item in inventory_response(data,lines)]==['example','disagreement','claim']


def test_one_unresolved_item_does_not_discard_an_independently_valid_repair():
    case=CASES[0];lines,sections,_=setup_case(case);calls=[]
    def response(engine,system,payload,validator):
        data=scripted(case,calls)(engine,system,payload,validator)
        if payload['phase']=='inventory':
            other=copy.deepcopy(data['items'][0]);other['statement']='Another genuinely missing condition.'
            data['items'].append(other)
        if payload['phase']=='match':
            row=data['matches'][-1]
            row.update(status='missing',support=[])
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert report['repairs_accepted']==1 and report['unresolved_items']==1
    assert report['status']=='unverified'
    assert case['complete_draft'] in json.dumps(sections)


@pytest.mark.parametrize('text',[
    'The thought is unfinished in the source.',
    'The source ends before supplying the answer.',
    'The provided text stops here.',
    'The explanation remains incomplete in the provided text.',
])
def test_paraphrased_excerpt_boundary_is_not_published_as_source_fact(text):
    from coverage_ledger import boundary_commentary
    assert boundary_commentary(text)


def test_internal_support_allows_paraphrase_and_discards_legacy_quotation():
    draft=[{'paragraphs':[{'id':'P1','text':'He returned to school and learned neuroscience.'}]}]
    data={'matches':[{'item_id':'C1','status':'covered','grounded':True,'duplicate':False,
                     'support':[{'paragraph_id':'P1','quote':'He returned to school.'}]}]}
    matching_response(data,[{'id':'C1'}],draft)
    assert data['matches'][0]['support']==[{'paragraph_id':'P1'}]


@pytest.mark.parametrize('checked',[None,[],['unknown'],['L1','L1']])
def test_repair_matching_requires_every_proposed_paragraph_to_be_inspected(checked):
    draft=[{'paragraphs':[{'id':'L1','text':'A supported experimental result.'}]}]
    data={'checked_proposed_paragraph_ids':checked,'matches':[{
        'item_id':'C1','status':'covered','grounded':True,'duplicate':False,
        'support':[{'paragraph_id':'L1','quote':'A supported experimental result.'}]}]}
    with pytest.raises(ValueError,match='proposed-paragraph'):
        matching_response(data,[{'id':'C1'}],draft,['L1'])
    data['checked_proposed_paragraph_ids']=['L1']
    assert matching_response(data,[{'id':'C1'}],draft,['L1'])[0]['status']=='covered'
    data['matches'][0]['support'][0]['paragraph_id']='invented'
    with pytest.raises(ValueError,match='Unknown'):
        matching_response(data,[{'id':'C1'}],draft,['L1'])


def test_invalid_check_retries_once_with_feedback_without_regenerating_body():
    case=CASES[0];lines,sections,_=setup_case(case);calls=[]
    sections[0]['paragraphs'][0]['text']=case['complete_draft']
    attempts=[]
    def response(engine,system,payload,validator):
        attempts.append(payload)
        if len(attempts)==1:return {}
        return scripted(case,calls)(engine,system,payload,validator)
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert report['validation_retries']==1 and report['status']=='model_reviewed'
    assert 'validation_feedback' in attempts[1] and report['repairs_accepted']==0


def test_source_only_recheck_corrects_an_invented_inventory_condition():
    truth='Participants preferred stimulation producing frustration and mild anger; the speaker connects this to dopamine reward.'
    false=truth+' This happened when stimulation was unavailable.'
    case={'source':'[00:00] '+truth,'missing_draft':'Stimulation can feel rewarding.'}
    lines,sections,ranges=setup_case(case);calls=[]
    def response(engine,system,payload,validator):
        calls.append(copy.deepcopy(payload))
        if payload['phase']=='inventory':
            return {'checked_source_ranges':ranges,'items':[{'kind':'claim','statement':false,'source_ranges':ranges}]}
        if payload['phase']=='validate_inventory':
            assert 'global_draft' not in payload and 'overview' not in payload
            assert payload['items'][0]['original_source'][0]['id']==lines[0].id
            return {'items':[{'id':payload['items'][0]['id'],'supported':False,
                             'reason':'The source does not say stimulation was unavailable.',
                             'statement':truth,'source_ranges':ranges}]}
        if payload['phase']=='repair':
            return {'sections':[{'heading':'Evidence','paragraphs':[{'text':truth,'source_ranges':ranges}]}]}
        p=next((p for s in payload['global_draft'] for p in s['paragraphs'] if p['text']==truth),None)
        covered=p and payload['items'][0]['statement']==truth
        return {'checked_proposed_paragraph_ids':payload['proposed_paragraph_ids'],'matches':[{
            'item_id':payload['items'][0]['id'],'status':'covered' if covered else 'partial',
            'grounded':True,'duplicate':False,'support':[{'paragraph_id':p['id'],'quote':truth}] if covered else []}]}
    with patch('coverage_ledger.request',side_effect=response):
        report=audit(SimpleNamespace(),lines,sections)
    assert report['status']=='model_reviewed' and report['unresolved_items']==0
    assert report['corrected_inventory_items']==['C1.1']
    assert report['repairs_accepted']==1 and len(sections)==2
    assert 'unavailable' not in json.dumps(sections)
    assert sum(p['phase']=='validate_inventory' for p in calls)==1


def test_source_correction_cannot_escape_its_original_source_context():
    case=CASES[0];lines,sections,_=setup_case(case);before=copy.deepcopy(sections)
    calls=[];base=scripted(case,calls,bad_repair=True)
    def response(engine,system,payload,validator):
        if payload['phase']=='validate_inventory':
            return {'items':[{'id':payload['items'][0]['id'],'supported':False,'reason':'Synthetic correction',
                             'statement':'An invented claim.','source_ranges':[{'start':'unknown','end':'unknown'}]}]}
        return base(engine,system,payload,validator)
    with patch('coverage_ledger.request',side_effect=response):
        report=audit(SimpleNamespace(),lines,sections)
    assert sections==before and report['status']=='unverified'
    assert report['inventory_validation_failed_batches']==2 and not report['corrected_inventory_items']
    assert not any(call['phase']=='repair' for call in calls)


@pytest.mark.parametrize('kind,compressible',[('example',True),('claim',True),('experiment',False),('condition',False),('disagreement',False),('procedure',False),('counterexample',False)])
def test_only_source_verified_incidental_context_can_skip_repair(kind,compressible):
    case={**CASES[0],'kind':kind}
    if compressible:
        case.update(source='[00:00] Attention can be practiced during daily activities, such as washing a blue coffee mug.',
                    missing_draft='Practice attention during everyday activities.',
                    complete_draft='The illustrative coffee mug was blue.')
    lines,sections,_=setup_case(case);calls=[]
    base=scripted(case,calls)
    def response(engine,system,payload,validator):
        if payload['phase']=='validate_inventory':
            assert 'global_draft' not in payload
            assert all(item['reported_gap']=='The illustrative mug was blue.' for item in payload['items'])
            return {'items':[{'id':item['id'],'supported':True,'material':False,
                             'material_reason':'An interchangeable illustrative detail, with no change to the explanation.'}
                            for item in payload['items']]}
        result=base(engine,system,payload,validator)
        if payload['phase']=='match':
            for row in result['matches']:row['missing_meaning']='The illustrative mug was blue.'
        return result
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert report['status']=='model_reviewed' and report['unresolved_items']==0
    assert report['context_only_items']==int(compressible)
    if compressible:assert report['items'][0]['compression_reason']
    assert report['covered_items']==int(not compressible)
    assert report['repairs_accepted']==int(not compressible)
    assert not report['corrected_inventory_items']
    assert any(c['phase']=='repair' for c in calls) is not compressible


@pytest.mark.parametrize('reassessment',['partial','contradicted','ungrounded'])
def test_append_only_repair_preserves_existing_support_but_rejects_contradiction(reassessment):
    case={**CASES[0],'source':'[00:00] Existing supported argument.\n'+CASES[0]['source'],
          'missing_draft':'Existing supported argument.'}
    lines,sections,ranges=setup_case(case);base=scripted(case,[])
    def response(engine,system,payload,validator):
        data=base(engine,system,payload,validator)
        if payload['phase']=='inventory':
            data['items'].append({'kind':'claim','statement':case['missing_draft'],'source_ranges':ranges})
        if payload['phase']=='match':
            old=next(row for row in data['matches'] if row['item_id']=='C1.2')
            proposed=bool(payload['proposed_paragraph_ids'])
            old.update(status=reassessment if proposed and reassessment!='ungrounded' else 'covered',
                       support=[{'paragraph_id':'P1'}],grounded=not(proposed and reassessment=='ungrounded'),duplicate=False)
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert sections[0]['paragraphs'][0]['text']==case['missing_draft']
    if reassessment=='partial':
        assert report['status']=='model_reviewed' and report['repairs_accepted']==1
        assert report['items'][1]['paragraph_ids']==['P1']
    else:
        assert report['status']=='unverified' and report['repairs_accepted']==0
        assert len(sections)==1


def test_repair_can_abstain_without_hiding_an_unresolved_gap():
    case=CASES[0];lines,sections,_=setup_case(case);before=copy.deepcopy(sections)
    base=scripted(case,[])
    def response(engine,system,payload,validator):
        if payload['phase']=='repair':return {'sections':[]}
        return base(engine,system,payload,validator)
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert sections==before and report['status']=='unverified'
    assert report['unresolved_items']==1 and report['failed_batches']==0
    assert report['repairs_accepted']==0 and report['validation_retries']==0


def test_boundary_commentary_retry_preserves_the_real_claim_instead_of_dropping_it():
    case=CASES[0];lines,sections,_=setup_case(case);base=scripted(case,[]);attempts=[]
    def response(engine,system,payload,validator):
        data=base(engine,system,payload,validator)
        if payload['phase']=='inventory':
            attempts.append(payload)
            if len(attempts)==1:data['items'][0]['statement']+=' The statement is unfinished in the source.'
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert len(attempts)==2 and 'validation_feedback' in attempts[1]
    assert report['status']=='model_reviewed' and report['covered_items']==1
    assert report['repairs_accepted']==1 and report['validation_retries']==1
    assert not report['ignored_boundary_items'] and not report['failed_batches']


@pytest.mark.parametrize('new_fact_grounded',[True,False])
def test_shared_context_does_not_discard_grounded_new_information(new_fact_grounded):
    case={'source':'[00:00] Existing context.\n[00:01] An essential condition.',
          'missing_draft':'Existing context.', 'complete_draft':'Existing context. An essential condition.', 'kind':'condition'}
    lines,sections,ranges=setup_case(case);base=scripted(case,[])
    def response(engine,system,payload,validator):
        data=base(engine,system,payload,validator)
        if payload['phase']=='inventory':
            data['items'].append({'kind':'claim','statement':case['missing_draft'],'source_ranges':ranges})
        if payload['phase']=='match':
            proposed=payload['proposed_paragraph_ids']
            condition,context=data['matches']
            condition['grounded']=new_fact_grounded if proposed else True
            context.update(status='covered',grounded=True,duplicate=bool(proposed),
                           support=[{'paragraph_id':proposed[0] if proposed else 'P1'}])
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert report['repairs_accepted']==int(new_fact_grounded)
    if new_fact_grounded:
        assert report['status']=='model_reviewed' and report['covered_items']==2
        assert report['items'][1]['context_overlap'] is True
    else:
        assert report['status']=='unverified' and len(sections)==1


@pytest.mark.parametrize('support_shape',['joint','new_only'])
@pytest.mark.parametrize('novel,grounded,contradicts', [
    (True,True,False), (False,True,False), (True,False,False), (True,True,True)])
def test_duplicate_flag_requires_independent_delta_verification(novel,grounded,contradicts,support_shape):
    case={'source':'[00:00] The program starts.\n[00:01] Approval is required in January.',
          'missing_draft':'The program starts.',
          'complete_draft':'Approval is required in January.', 'kind':'condition'}
    lines,sections,ranges=setup_case(case);base=scripted(case,[]);verified=[]
    def response(engine,system,payload,validator):
        if payload['phase']=='verify_repair_delta':
            verified.append(payload)
            assert all(p['id']=='P1' for s in payload['existing_draft'] for p in s['paragraphs'])
            data={'paragraphs':[{'id':p['id'],'grounded':grounded,
                'adds_material_meaning':novel,'contradicts_existing':contradicts}
                for p in payload['proposed_paragraphs']]}
            validator(data)
            return data
        data=base(engine,system,payload,validator)
        if payload['phase']=='match' and payload.get('proposed_paragraph_ids'):
            for row in data['matches']:
                new_support=[{'paragraph_id':payload['proposed_paragraph_ids'][0]}]
                row.update(duplicate=True,support=([{'paragraph_id':'P1'}] if support_shape=='joint' else [])+new_support)
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert verified
    assert report['repairs_accepted']==int(novel and grounded and not contradicts)
    assert (len(sections)>1)==(novel and grounded and not contradicts)


@pytest.mark.parametrize('failure',['malformed','transport'])
def test_new_only_duplicate_fails_closed_when_independent_review_fails(failure):
    case={'source':'[00:00] The program starts.\n[00:01] Approval is required in January.',
          'missing_draft':'The program starts.',
          'complete_draft':'Approval is required in January.', 'kind':'condition'}
    lines,sections,_=setup_case(case);before=copy.deepcopy(sections);base=scripted(case,[]);checks=[]
    def response(engine,system,payload,validator):
        if payload['phase']=='verify_repair_delta':
            checks.append(True)
            if failure=='transport': raise TimeoutError()
            data={'paragraphs':[]}
            validator(data)
            return data
        data=base(engine,system,payload,validator)
        if payload['phase']=='match' and payload.get('proposed_paragraph_ids'):
            for row in data['matches']:
                row.update(duplicate=True,support=[{'paragraph_id':payload['proposed_paragraph_ids'][0]}])
        return data
    with patch('coverage_ledger.request',side_effect=response):report=audit(SimpleNamespace(),lines,sections)
    assert checks and report['status']=='unverified' and sections==before


def test_final_readonly_audit_source_checks_new_incidental_gap_without_adding_prose():
    from coverage_ledger import efficient_audit
    case={'source':'[00:00] An effective method, illustrated by another incidental biography.',
          'missing_draft':'An effective method.', 'complete_draft':'An effective method.', 'kind':'example'}
    lines,sections,ranges=setup_case(case);before=copy.deepcopy(sections);phases=[]
    inventory=[{'id':'C1','kind':'example','statement':case['source'],'source_ranges':ranges}]
    def response(engine,system,payload,validator):
        phases.append(payload['phase'])
        if payload['phase']=='validate_inventory':
            assert payload['items'][0]['reported_gap']=='Another incidental biography.'
            return {'items':[{'id':'C1','supported':True,'material':False,
                'material_reason':'Interchangeable illustration; essential method is unchanged.'}]}
        assert payload['phase']=='match'
        return {'matches':[{'item_id':'C1','status':'partial','grounded':True,'duplicate':False,
            'support':[{'paragraph_id':'P1'}],'missing_meaning':'Another incidental biography.'}]}
    owner=SimpleNamespace(quality_coverage_threshold=.9)
    with patch('coverage_ledger.request',side_effect=response):
        report=efficient_audit(owner,lines,sections,prepared_inventory=({'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False},inventory),allow_repairs=False)
    assert 'validate_inventory' in phases and 'repair' not in phases
    assert report['items'][0]['status']=='context_only' and sections==before


def test_source_validation_reuses_only_identical_affirmative_receipts_across_batches():
    from coverage_ledger import _correct_inventory
    case={'source':'[00:00] The source describes a supported condition.', 'missing_draft':'A draft.'}
    lines,_,ranges=setup_case(case)
    items=[{'id':f'C{i}','kind':'claim','statement':f'Supported claim {i}',
            'source_ranges':ranges} for i in range(3)]
    owner=SimpleNamespace(model='model-a'); calls=[]
    def response(_engine,_system,payload,_validator):
        calls.append([item['id'] for item in payload['items']])
        return {'items':[{'id':item['id'],'supported':True,'material':True}
                         for item in payload['items']]}
    def report():return {'requests':0,'inventory_validation_failed_batches':0,'terminal_provider_failure':False}
    with patch('coverage_ledger.request',side_effect=response):
        assert not _correct_inventory(owner,lines,items[:2],report(),None,None,
            [{'item_id':'C0','missing_meaning':'Condition A'}, {'item_id':'C1','missing_meaning':'Condition B'}])
        result=report()
        assert not _correct_inventory(owner,lines,[items[1],items[0],items[2]],result,None,None,
            [{'item_id':'C0','missing_meaning':'Condition A'}, {'item_id':'C1','missing_meaning':'Changed condition'}])
        assert result['inventory_receipts_reused']==1
        assert calls==[['C0','C1'],['C1','C2']]
        result=report();progress=Mock()
        _correct_inventory(owner,lines,[items[0]],result,progress,None,
            [{'item_id':'C0','missing_meaning':'Condition A'}])
        assert result['inventory_receipts_reused']==1 and result['requests']==0
        assert calls==[['C0','C1'],['C1','C2']] and progress.call_count==1
        owner.model='model-b'
        _correct_inventory(owner,lines,[items[0]],report(),None,None,
            [{'item_id':'C0','missing_meaning':'Condition A'}])
        assert calls[-1]==['C0']
        changed=copy.deepcopy(items[0]);changed['statement']='A different claim'
        owner.model='model-a'
        _correct_inventory(owner,lines,[changed],report(),None,None,
            [{'item_id':'C0','missing_meaning':'Condition A'}])
        assert calls[-1]==['C0'] and len(calls)==4
        from transcript_reading import SourceLine
        changed_lines=[SourceLine(line.id,'Different source context.',line.time) for line in lines]
        _correct_inventory(owner,changed_lines,[items[0]],report(),None,None,
            [{'item_id':'C0','missing_meaning':'Condition A'}])
        assert calls[-1]==['C0'] and len(calls)==5


@pytest.mark.parametrize('receipt', ['incidental','invalid','corrected'])
def test_source_validation_never_reuses_incidental_invalid_or_corrected_receipts(receipt):
    from coverage_ledger import _correct_inventory
    case={'source':'[00:00] A source detail.', 'missing_draft':'A draft.'}
    lines,_,ranges=setup_case(case)
    item={'id':'C0','kind':'claim','statement':'A source detail','source_ranges':ranges}
    owner=SimpleNamespace(model='model-a');calls=[]
    def response(_engine,_system,payload,_validator):
        calls.append(1)
        if receipt=='invalid':return {'items':[]}
        if receipt=='corrected':return {'items':[{'id':'C0','supported':False,
            'reason':'Unsupported synthetic wording','statement':'A corrected source detail.',
            'source_ranges':ranges}]}
        return {'items':[{'id':'C0','supported':True,'material':False,'material_reason':'Incidental'}]}
    with patch('coverage_ledger.request',side_effect=response):
        for _ in range(2):
            report={'requests':0,'inventory_validation_failed_batches':0,'terminal_provider_failure':False}
            _correct_inventory(owner,lines,[item],report,None,None)
    assert len(calls)==2


@pytest.mark.parametrize('outcome', ['recover','timeout','non_retryable'])
def test_transient_repair_failure_retries_only_the_failed_batch(outcome):
    from coverage_ledger import efficient_audit
    case=CASES[0];lines,sections,ranges=setup_case(case)
    owner=SimpleNamespace(quality_coverage_threshold=.9,model='model-a')
    inventory=[{'id':'C1','kind':case['kind'],'statement':case['complete_draft'],
                'source_ranges':ranges}]
    calls=[];base=scripted(case,calls);attempts=[]
    def response(engine,system,payload,validator):
        if payload['phase']=='repair':
            attempts.append(1)
            if outcome=='non_retryable': raise PermissionError('synthetic failure')
            if outcome=='timeout' or len(attempts)==1: raise TimeoutError('synthetic timeout')
        return base(engine,system,payload,validator)
    with patch('coverage_ledger.request',side_effect=response):
        report=efficient_audit(owner,lines,sections,
            prepared_inventory=({'failed_batches':0,'inventory_failed_batches':0,
                                 'terminal_provider_failure':False},inventory))
    if outcome=='recover':
        assert report['status']=='model_reviewed' and report['repairs_accepted']==1
        assert [call['phase'] for call in calls].count('match')==2
        assert report['repair_transport_retries']==1
    else:
        assert report['status']=='unverified' and report['repairs_accepted']==0
    assert len(attempts)==(1 if outcome=='non_retryable' else 2)

@pytest.mark.parametrize('damage',['missing','extra','duplicate','non_boolean','unknown'])
def test_delta_receipt_must_cover_exact_proposals_with_explicit_booleans(damage):
    from coverage_ledger import delta_response
    row={'id':'L1','grounded':True,'adds_material_meaning':True,'contradicts_existing':False}
    rows=[row]
    if damage=='missing':rows=[]
    if damage=='extra':rows.append({**row,'id':'L2'})
    if damage=='duplicate':rows.append(dict(row))
    if damage=='non_boolean':row['adds_material_meaning']=1
    if damage=='unknown':row['id']='P1'
    with pytest.raises(ValueError):delta_response({'paragraphs':rows},[{'id':'L1'}])


def test_provider_524_receipt_keeps_status_without_raw_provider_response():
    import httpx
    from openai import InternalServerError
    lines, sections, _ = setup_case(CASES[0])
    response = httpx.Response(524, request=httpx.Request('POST','https://provider.example/v1/chat/completions'))
    error = InternalServerError('private provider detail',response=response,body={'secret':'not retained'})
    with patch('coverage_ledger.request',side_effect=error) as request:
        result = audit(SimpleNamespace(), lines, sections)
    assert request.call_count == 2
    assert result['inventory_failures'][0]['http_status'] == 524
    assert result['inventory_failures'][0]['error_type'] == 'InternalServerError'
    assert result['status'] == 'unverified'
    assert 'private provider detail' not in str(result) and 'secret' not in str(result)
