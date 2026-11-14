import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.summary_memory_diagnostics import (
    DiagnosticBoundary, MemoryDiagnostics, aggregate_verdicts, candidate_shape,
    unpack_inventory, validate_verdicts,
)
from scripts.validate_authorized_episode import MemoryCheckpoints, record_provider_error
from transcript_reading import source_lines


def fixture():
    source='The trial lasted exactly twelve minutes.\nThe trial used two cameras.\n'
    _, lines=source_lines(source)
    span=[{'start':lines[0].id,'end':lines[-1].id}]
    paragraphs=[{'id':'P1','text':'The trial used two cameras.','source_ranges':span}]
    items=[{'id':'I1','kind':'condition','statement':'The trial lasted twelve minutes.','source_ranges':span},
           {'id':'I2','kind':'claim','statement':'The trial used two cameras.','source_ranges':span}]
    candidate={'edition':{'sections':[{'heading':'Trial','paragraphs':paragraphs}],'overview':''},
               'report':{'coverage_ledger':{'items':[{'id':'I1','status':'missing'}, {'id':'I2','status':'covered'}]}},
               'inventory':({'inventory_batches':1},items)}
    return source, lines, candidate


def verdicts(request,status='missing'):
    line=request['primary_source'][0]
    return {'samples':[{'sample_id':row['sample_id'],'source_support':'supported',
        'draft_status':status if row['type']=='coverage' else 'covered','reason_class':'quantity_or_time',
        'source_evidence':[{'source_id':line['id'],'quote':line['text'].strip()}],
        'draft_evidence':[{'paragraph_id':'P1','quote':'The trial used two cameras.'}]}
        for row in request['samples']]}


@pytest.mark.parametrize('encoded',[False,True])
def test_candidate_reader_matches_real_saved_report_and_inventory_pair(encoded):
    _,_,payload=fixture()
    if encoded:payload=json.loads(json.dumps(payload))
    assert candidate_shape(payload)=={'candidate_present':True,'paragraph_count':1,
        'inventory_item_count':2,'linked_gap_count':1,'usable':True}
    assert len(unpack_inventory(payload['inventory']))==2
    assert len(unpack_inventory(payload['inventory'][1]))==2


def test_candidate_capture_is_immutable_before_checkpoint_overwrite_and_disposal():
    _,_,payload=fixture();observer=MemoryDiagnostics()
    store=MemoryCheckpoints(observer.capture_payload)
    store.put_checkpoint('owner','source','reading.candidate.v1','identity',payload)
    payload['edition']['sections'][0]['paragraphs'][0]['text']='replacement'
    assert observer.candidate['edition']['sections'][0]['paragraphs'][0]['text']=='The trial used two cameras.'
    observer.clear();store.clear()
    assert observer.candidate is None and observer.grounding==[] and store.values=={}


def test_grounding_capture_precedes_raw_replacement_and_does_not_export_feedback():
    source,_,payload=fixture();observer=MemoryDiagnostics()
    request={'global_draft':payload['edition']['sections'],'global_overview':''}
    observer.observe(request,{'unsupported_paragraph_ids':['P1'],'unsupported_reasons':[{'reason':'private diagnostic prose'}]})
    request['global_draft'][0]['paragraphs'][0]['text']='raw replacement'
    assert observer.grounding[0]['paragraph']['text']=='The trial used two cameras.'
    assert observer.make_request(source)['samples'][0]['type']=='grounding'
    assert 'private diagnostic prose' not in json.dumps(observer.make_request(source))


def test_first_match_stops_before_any_repair_or_delivery_even_with_no_gaps():
    _,lines,payload=fixture();observer=MemoryDiagnostics();engine=SimpleNamespace(_quality_inventory=payload['inventory'])
    with patch('coverage_ledger.efficient_audit',return_value=payload['report']['coverage_ledger']) as operation:
        with pytest.raises(DiagnosticBoundary):
            observer.capture_first_match(engine,lines,payload['edition']['sections'],prepared_inventory=payload['inventory'])
    assert operation.call_args.kwargs['allow_repairs'] is False
    assert observer.candidate is not None


def test_fixed_input_assessments_make_two_real_calls_without_receipt_reuse():
    source,_,payload=fixture();observer=MemoryDiagnostics();observer.capture_payload(payload)
    engine=SimpleNamespace(client=object(),model='synthetic')
    requests=[]
    def judge(client,model,system,payload,timeout,**kwargs):
        requests.append((system,payload,kwargs))
        return verdicts(json.loads(payload))
    with patch('reading_editor._call_editor',side_effect=judge):result=observer.analyze(engine,source)
    assert len(requests)==2 and requests[0]==requests[1]
    assert result['diagnostic_checkpoint_reuse'] is False
    assert result['classification_counts']=={'stable_omission_evidence':1,'stable_covered_control':1}
    assert result['semantic_false_positive_proven'] is False
    assert 'twelve' not in json.dumps(result) and 'cameras' not in json.dumps(result)
    assert all('status' not in sample for sample in json.loads(requests[0][1])['samples'])


def test_same_input_disagreement_is_variation_not_proven_false_positive():
    source,_,payload=fixture();observer=MemoryDiagnostics();observer.capture_payload(payload)
    request=observer.make_request(source)
    first=validate_verdicts(verdicts(request),request)
    second=validate_verdicts(verdicts(request,'covered'),request)
    result=aggregate_verdicts(request['samples'],[first,second])
    assert result['classification_counts']['fixed_input_reviewer_variation']==1
    assert result['semantic_false_positive_proven'] is False


def test_fabricated_evidence_cannot_count_as_supported_omission_or_false_positive():
    source,_,payload=fixture();observer=MemoryDiagnostics();observer.capture_payload(payload)
    request=observer.make_request(source);response=verdicts(request,'covered')
    response['samples'][0]['source_evidence'][0]['quote']='invented private source quote'
    result=validate_verdicts(response,request)
    summary=aggregate_verdicts(request['samples'],[result,result])
    assert summary['classification_counts']['unresolved_invalid_or_missing_citations']==1
    assert 'invented' not in json.dumps(summary)


@pytest.mark.parametrize('change',[lambda d:d['samples'].clear(),
    lambda d:d['samples'][0].update(source_support=['supported']),
    lambda d:d['samples'][0].update(sample_id='S2'),
    lambda d:d['samples'][0].update(reason_class='private source text')])
def test_malformed_or_untrusted_labels_fail_closed(change):
    source,_,payload=fixture();observer=MemoryDiagnostics();observer.capture_payload(payload)
    request=observer.make_request(source);response=verdicts(request);change(response)
    with pytest.raises(ValueError):validate_verdicts(response,request)


def test_400_diagnostic_records_only_known_fields_and_exact_stage():
    report={};error=SimpleNamespace(status_code=400,body={'error':{
        'code':'context_length_exceeded','param':'messages','message':'private body and API key'}})
    record_provider_error(report,{'messages':[{'content':json.dumps({'phase':'grounding','source':'private transcript'})}]},error)
    assert report['model_errors_by_phase']['grounding']=={'count':1,'http_status_counts':{'400':1},
        'code_counts':{'context_length_exceeded':1},'param_counts':{'messages':1}}
    assert 'private' not in json.dumps(report) and 'key' not in json.dumps(report)


@pytest.mark.parametrize('url',['https://different.example/v1','http://api.aipaibox.com/v1',
    'https://api.aipaibox.com:8443/v1','https://user:private@api.aipaibox.com/v1'])
def test_saved_provider_cannot_drift_outside_explicit_destination_consent(url):
    from scripts.validate_authorized_episode import enforce_authorized_destination, TestGuardStopped
    with pytest.raises(TestGuardStopped):enforce_authorized_destination({'base_url':url})


def test_full_generation_and_failed_delivery_are_not_diagnostic_success():
    from scripts.validate_authorized_episode import result_exit_code
    assert result_exit_code({'terminal_state':'memory_diagnostics_complete','quality_acceptance':False})==2


def test_actual_http_ceiling_also_blocks_hidden_extra_dispatch_attempts():
    from scripts.validate_authorized_episode import Calls, TestGuardStopped
    calls=Calls(lambda day:None,{},lambda:None,maximum=1)
    calls.outbound(object())
    with pytest.raises(TestGuardStopped):calls.outbound(object())
    assert calls.http_attempts==1
