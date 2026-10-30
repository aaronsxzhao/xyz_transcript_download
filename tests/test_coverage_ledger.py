"""Local pipeline guarantees; live semantic regression is recorded separately."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from coverage_ledger import audit, matching_response, inventory_response
from transcript_reading import source_lines, validate_sections, generate
from summary_errors import ProcessingCancelledError

CASES=json.loads((Path(__file__).parent/'fixtures/coverage_ledger/huberman.json').read_text())


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
    assert model.call_count==1 and report['failed_batches']>1 and report['status']=='unverified'
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
