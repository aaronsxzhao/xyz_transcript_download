import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from source_review_adjudication import adjudicate
from transcript_reading import source_lines, serialize, call_json, REVIEW
from summary_errors import SummaryOutputError, ProcessingCancelledError


def scene():
    _,lines=source_lines('The trial used two cameras.\nIt ran only at night.')
    spans=[{'start':lines[0].id,'end':lines[-1].id}]
    text='The trial used two cameras. It ran only at night.'
    request={'primary_source':serialize(lines),'global_draft':[{'heading':'Trial',
        'paragraphs':[{'id':'P1','text':text,'source_ranges':spans}]}],'global_overview':''}
    response={'checked_source_ranges':spans,'complete':True,'grounded':False,
        'unsupported_paragraph_ids':['P1'],'additions':[],
        'unsupported_reasons':[{'id':'P1','reason':'Untrusted claim about cameras.'}]}
    owner=SimpleNamespace(client=Mock(),model='test',quality_coverage_threshold=.9,generation_report={})
    segments=[{'text':'The trial used two cameras. ','verdict':'supported','source_ranges':[spans[0]]},
              {'text':'It ran only at night.','verdict':'supported','source_ranges':[spans[0]]}]
    return owner,lines,request,response,{'paragraphs':[{'id':'P1','segments':segments}]}


@pytest.mark.parametrize('verdict',['supported','unsupported','uncertain'])
def test_every_assertion_needs_positive_source_support_to_withdraw_flag(verdict):
    owner,lines,request,response,result=scene();before=copy.deepcopy((request,response))
    result['paragraphs'][0]['segments'][1]['verdict']=verdict
    def complete(*args,**kwargs):
        payload=json.loads(args[3]);assert payload['phase']=='adjudicate_grounding'
        assert payload['draft']==request['global_draft'] and payload['primary_source']==request['primary_source']
        kwargs['response_validator'](result)
        return result
    with patch('reading_editor.call_editor',side_effect=complete) as check:
        actual=adjudicate(owner,lines,request,response)
    assert check.call_count==1 and (request,response)==before
    assert actual['grounded'] is (verdict=='supported')
    assert actual['unsupported_paragraph_ids']==([] if verdict=='supported' else ['P1'])
    assert 'coverage_ledger' not in owner.generation_report


@pytest.mark.parametrize('defect',['omitted_clause','reordered','unknown_source','reversed_source',
    'missing_source','duplicate_id','missing_id','unknown_id','invalid_verdict'])
def test_incomplete_or_invalid_adjudication_keeps_original_veto(defect):
    owner,lines,request,response,result=scene();row=result['paragraphs'][0];segment=row['segments'][0]
    if defect=='omitted_clause':row['segments'].pop()
    elif defect=='reordered':row['segments'].reverse()
    elif defect=='unknown_source':segment['source_ranges'][0]['start']='unknown'
    elif defect=='reversed_source':segment['source_ranges']=[{'start':lines[-1].id,'end':lines[0].id}]
    elif defect=='missing_source':segment['source_ranges']=[]
    elif defect=='duplicate_id':result['paragraphs'].append(copy.deepcopy(row))
    elif defect=='missing_id':result['paragraphs']=[]
    elif defect=='unknown_id':row['id']='P2'
    elif defect=='invalid_verdict':segment['verdict']='probably'
    with patch('reading_editor.call_editor',return_value=result):actual=adjudicate(owner,lines,request,response)
    assert actual==response and owner.generation_report['source_adjudications'][0]['invalid_checks']==1


def test_no_rejection_or_unlocated_veto_spends_no_extra_call():
    owner,lines,request,response,_=scene();response['unsupported_paragraph_ids']=[]
    with patch('reading_editor.call_editor',side_effect=AssertionError('No identified assertion')):
        assert adjudicate(owner,lines,request,response)==response
    assert not response['grounded']


@pytest.mark.parametrize('error',[ProcessingCancelledError(),SummaryOutputError('capacity'),RuntimeError('implementation fault')])
def test_cancel_capacity_and_implementation_failures_are_not_cleared(error):
    owner,lines,request,response,_=scene()
    with patch('reading_editor.call_editor',side_effect=error),pytest.raises(type(error)):
        adjudicate(owner,lines,request,response)


def test_actual_global_review_is_adjudicated_before_return_and_final_gate():
    owner,lines,request,response,result=scene()
    with patch('reading_editor._call_editor',side_effect=[response,result]) as model:
        actual=call_json(owner,REVIEW,json.dumps(request),240)
    assert model.call_count==2 and actual['grounded'] and not actual['unsupported_paragraph_ids']


def test_latest_rejected_wording_replaces_previously_repaired_diagnostic_sample():
    from scripts.summary_memory_diagnostics import MemoryDiagnostics
    owner,lines,request,response,_=scene();observer=MemoryDiagnostics()
    observer.observe(request,response)
    request['global_draft'][0]['paragraphs'][0]['text']='A later, different assertion.'
    observer.observe(request,response)
    assert len(observer.grounding)==1
    assert observer.grounding[0]['paragraph']['text']=='A later, different assertion.'
    observer.clear();assert not observer.grounding
