import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch, Mock

import pytest

from coverage_ledger import coverage_acceptable, efficient_audit
from reading_delivery import accept_edition, draft_identity
from summary_errors import SummaryOutputError, ProcessingCancelledError
from transcript_reading import source_lines, validate_sections, organize_sections
from processing_parallel import FairSemaphore
from processing_execution import Execution, bind


def candidate(covered=9):
    _, lines = source_lines('A supported claim.\nA meaningful qualification.')
    ranges = [{'start':lines[0].id,'end':lines[-1].id}]
    sections, _ = validate_sections({'sections':[{'heading':'Claim', 'paragraphs':[
        {'text':'A supported claim with its qualification.', 'source_ranges':ranges}]}]}, lines)
    sections[0]['paragraphs'][0]['id'] = 'P1'
    ledger = {'items':[{'id':f'C{i}', 'status':'covered' if i<covered else 'missing',
                       'paragraph_ids':['P1'], 'source_ranges':ranges} for i in range(10)],
              'unresolved_items':10-covered}
    owner = SimpleNamespace(quality_coverage_threshold=.9, generation_report={
        'coverage_ledger':ledger, 'verification':{}, 'provenance':{},
        'grounded_draft_identity':draft_identity(sections,'')})
    return owner, {'sections':sections,'lines':lines,'overview':'','notices':['audit']}


def test_ninety_percent_passes_without_spending_on_last_item():
    owner, edition = candidate()
    with patch('transcript_reading.call_json', side_effect=AssertionError('Unnecessary review')):
        result = accept_edition(owner, edition, 'Title', 'Source', [], 0)
    assert 'unverified' not in result['markdown']
    assert owner.generation_report['delivery']['coverage_ratio'] == .9
    assert owner.generation_report['delivery']['unresolved_items'] == 1


@pytest.mark.parametrize('defect', ['below_threshold','contradicted','source_unchecked','source_validation_failed'])
def test_coverage_threshold_never_overrides_hard_failures(defect):
    owner, edition = candidate(8 if defect=='below_threshold' else 10)
    ledger = owner.generation_report['coverage_ledger']
    if defect=='contradicted': ledger['items'][0]['status']='contradicted'
    if defect=='source_unchecked': ledger['inventory_failed_batches']=1
    if defect=='source_validation_failed': ledger['inventory_validation_failed_batches']=1
    with pytest.raises(SummaryOutputError) as error:
        accept_edition(owner, edition, 'Title', 'Source', [], 0)
    assert error.value.code=='quality'
    assert owner.generation_report['delivery']['status']=='blocked'


def test_changed_final_text_requires_new_grounding_and_cannot_reuse_stale_pass():
    owner, edition = candidate(10)
    edition['sections'][0]['paragraphs'][0]['text']='An unsupported invention.'
    lines=edition['lines']
    response={'checked_source_ids':[line.id for line in lines], 'complete':True,
              'grounded':False, 'unsupported_paragraph_ids':[], 'additions':[]}
    with patch('transcript_reading.call_json', return_value=response) as review:
        with pytest.raises(SummaryOutputError):
            accept_edition(owner, edition, 'Title', 'Source', [], 0)
    assert review.call_count==1


@pytest.mark.parametrize('final_pass', [True, False])
def test_rewritten_paragraph_requires_independent_recheck(final_pass):
    owner, edition=candidate(10)
    owner.generation_report.pop('grounded_draft_identity')
    owner._quality_inventory=({},[])
    ledger=copy.deepcopy(owner.generation_report['coverage_ledger'])
    def response(grounded):
        return {'checked_source_ids':[line.id for line in edition['lines']],
            'complete':True,'grounded':grounded,
            'unsupported_paragraph_ids':[] if grounded else ['P1'],'additions':[]}
    def repair(engine, lines, sections, ids):
        assert ids=={'P1'}
        sections[0]['paragraphs'][0]['text']='A corrected claim with its qualification.'
    with patch('transcript_reading.call_json',side_effect=[response(False),response(final_pass)]) as review, \
         patch('reading_delivery.repair_unsupported',side_effect=repair), \
         patch('coverage_ledger.efficient_audit',return_value=ledger):
        if final_pass:
            result=accept_edition(owner,edition,'Title','Source',[],0)
            assert 'corrected claim' in result['markdown']
        else:
            with pytest.raises(SummaryOutputError):accept_edition(owner,edition,'Title','Source',[],0)
    assert review.call_count==2


def test_independent_matches_overlap_and_threshold_skips_repairs():
    owner, edition = candidate(10)
    owner.quality_coverage_threshold=.9
    sections, lines=edition['sections'],edition['lines']
    inventory=[{'id':f'C{i}', 'kind':'claim','statement':'A claim.',
        'source_ranges':sections[0]['paragraphs'][0]['source_ranges']} for i in range(20)]
    base={'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False}
    barrier=threading.Barrier(2)
    def request(engine, system, payload, validate):
        assert payload['phase']=='match'
        barrier.wait(timeout=3)
        return {'matches':[{'item_id':item['id'], 'status':'missing' if item['id'] in {'C18','C19'} else 'covered',
            'support':[] if item['id'] in {'C18','C19'} else [{'paragraph_id':'P1'}],
            'grounded':True,'duplicate':False} for item in payload['items']]}
    before=copy.deepcopy(sections)
    with patch('coverage_ledger.request', side_effect=request):
        result=efficient_audit(owner, lines, sections, prepared_inventory=(base,inventory))
    assert result['coverage_ratio']==.9 and result['requests']==2
    assert result['status']=='acceptable' and sections==before


def test_fifo_waiter_is_admitted_before_newcomer_and_cancelled_waiter_is_removed():
    semaphore=FairSemaphore(1)
    semaphore.acquire()
    order=[]
    executions=[Execution('owner',str(i),Mock()) for i in range(3)]
    def work(i):
        with bind(executions[i]):
            semaphore.acquire()
            try: order.append(i)
            finally: semaphore.release()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[]
        for i in range(3):
            futures.append(pool.submit(work,i))
            # Condition.wait releases the lock; membership is the actual
            # admission boundary, independent of OS scheduling speed.
            with semaphore.condition:
                assert semaphore.condition.wait_for(lambda:len(semaphore.waiters)==i+1,timeout=2)
        executions[1].cancelled=True
        with pytest.raises(ProcessingCancelledError):futures[1].result(timeout=2)
        semaphore.release()
        futures[0].result(timeout=2); futures[2].result(timeout=2)
    assert order==[0,2] and semaphore.available==1 and not semaphore.waiters


def test_repair_between_chapter_anchors_joins_source_owned_chapter():
    def paragraph(ident,index):return {'id':ident,'indices':[index]}
    baseline=[{'heading':'First','paragraphs':[paragraph('P1',0)]},
              {'heading':'Second','paragraphs':[paragraph('P2',10)]}]
    sections=copy.deepcopy(baseline)+[{'heading':'Repeated first topic','paragraphs':[paragraph('L1',5)]}]
    organized=organize_sections(sections,baseline)
    assert [s['heading'] for s in organized]==['First','Second']
    assert [p['id'] for p in organized[0]['paragraphs']]==['P1','L1']


def test_blocked_candidate_resumes_without_redrafting_or_streaming_partial_text():
    from note_summarizer import NoteSummarizer
    from scripts.validate_parallel_processing import Store
    owner=NoteSummarizer(api_key='synthetic')
    saved_owner, edition=candidate(8)
    calls=[]; previews=[]
    def draft(*args, **kwargs):
        calls.append('draft')
        owner.generation_report.update(copy.deepcopy(saved_owner.generation_report))
        owner._quality_inventory=({'inventory_failed_batches':0,'failed_batches':0,
                                    'terminal_provider_failure':False}, [])
        kwargs['progress'](20,'Unverified intermediate prose')
        return copy.deepcopy(edition)
    store=Store()
    source='A supported claim.\nA meaningful qualification.'
    try:
        with patch('coverage_ledger.build_inventory', return_value=({},[])), \
             patch('transcript_reading._generate_with_inventory', side_effect=draft):
            with bind(Execution('owner','source',store)), pytest.raises(SummaryOutputError):
                owner.generate_note('Title',source,progress_callback=lambda *args:previews.append(args))
            assert all(not event[1] for event in previews)
            recovered=copy.deepcopy(saved_owner.generation_report['coverage_ledger'])
            recovered['items'][8]['status']='covered'
            recovered['unresolved_items']=1
            with patch('coverage_ledger.efficient_audit',return_value=recovered), bind(Execution('owner','source',store)):
                note=owner.generate_note('Title',source)
            assert 'supported claim' in note
            assert calls==['draft']
            assert owner.generation_report['delivery']['status']=='accepted'
            with bind(Execution('owner','source',store)):
                assert owner.generate_note('Title',source)==note
            assert calls==['draft']
    finally:
        owner.client.close()
