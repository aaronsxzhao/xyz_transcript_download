import copy
import json
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


@pytest.mark.parametrize('corrected', [True, False])
def test_unchanged_grounding_repair_is_not_cached_and_gets_one_targeted_retry(corrected):
    from reading_delivery import repair_unsupported
    from scripts.validate_parallel_processing import Store
    _, lines = source_lines('Use python scripts check cloud browser.\n'
                            'Output appearance checks slash cloud browser slash run id slash anonymous.')
    ranges = [{'start':lines[0].id, 'end':lines[1].id}]
    rejected = ('The transcript mentions cloud-browser appearance checks; '
                'it does not clearly specify an output path.')
    sections, _ = validate_sections({'sections':[{'heading':'Browser', 'paragraphs':[
        {'text':rejected, 'source_ranges':ranges}]}]}, lines)
    sections[0]['paragraphs'][0]['id'] = 'L1.8'
    before = copy.deepcopy(sections)
    owner = SimpleNamespace(client=Mock(base_url='https://models.example/v1/'), model='test')
    store = Store()
    requests = []

    def complete(client, model, system, payload, timeout, **kwargs):
        request = json.loads(payload)
        requests.append(request)
        assert [p['id'] for p in request['paragraphs']] == ['L1.8']
        if len(requests) == 2:
            assert not store.values  # No-op provider output was not checkpointed.
            assert request['repair_feedback']
        return {'replacements':[{'id':'L1.8', 'source_ranges':ranges,
            'text':'The output path is appearance checks / cloud browser / run id / anonymous.'
                   if corrected and len(requests) == 2 else rejected.replace(' ', '  ')}]}

    with patch('reading_editor._call_editor', side_effect=complete), bind(Execution('owner','source',store)):
        if corrected:
            repair_unsupported(owner, lines, sections, {'L1.8'})
            assert len(store.values) == 1
            assert sections[0]['paragraphs'][0]['text'].startswith('The output path is')
        else:
            with pytest.raises(SummaryOutputError) as error:
                repair_unsupported(owner, lines, sections, {'L1.8'})
            assert error.value.reason == 'grounding'
            assert not store.values
            assert sections == before
    assert len(requests) == 2


def test_grounding_repair_does_not_add_transport_retries():
    from reading_delivery import repair_unsupported
    owner, edition = candidate(10)
    owner.client = Mock(base_url='https://models.example/v1/')
    owner.model = 'test'
    before = copy.deepcopy(edition['sections'])
    with patch('reading_editor._call_editor', side_effect=TimeoutError) as call:
        with pytest.raises(TimeoutError):
            repair_unsupported(owner, edition['lines'], edition['sections'], {'P1'})
    assert call.call_count == 1
    assert edition['sections'] == before


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


def test_independent_matching_only_checks_overlap_without_mutating_draft():
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
        result=efficient_audit(owner, lines, sections, prepared_inventory=(base,inventory), allow_repairs=False)
    assert result['coverage_ratio']==.9 and result['requests']==2
    assert result['status']=='acceptable' and sections==before


@pytest.mark.parametrize('total,gaps', [(20, 2), (160, 17)])
def test_repairs_complete_one_pass_even_when_initial_or_intermediate_coverage_passes(total, gaps):
    owner, edition = candidate(10)
    inventory = [{'id':f'C{i}', 'kind':'claim', 'source_ranges':[]}
                 for i in range(total)]
    base = {'failed_batches':0, 'inventory_failed_batches':0, 'terminal_provider_failure':False}
    repaired = []
    def audit(engine, lines, sections, *args, inventory, matching_only=False, **kwargs):
        if not matching_only:
            repaired.extend(item['id'] for item in inventory)
        items = [{**item, 'status':'missing' if int(item['id'][1:]) < gaps else 'covered',
                  'paragraph_ids':[]} for item in inventory]
        # Leave one item unresolved: finish the pass without looping to 100%.
        if not matching_only:
            for item in items:
                if item['id'] != 'C0': item['status'] = 'covered'
        return ({**base, 'items':items, 'matching_rows':{}}, inventory)
    with patch('coverage_ledger._audit', side_effect=audit):
        result = efficient_audit(owner, edition['lines'], edition['sections'],
                                prepared_inventory=(base, inventory))
    assert repaired == [f'C{i}' for i in range(gaps)]
    assert result['unresolved_items'] == 1
    assert result['recovery_rounds'] == 1
    assert result['status'] == 'acceptable'


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
             patch('transcript_reading._generate_with_inventory', side_effect=draft), \
             patch('coverage_ledger.efficient_audit', return_value=copy.deepcopy(saved_owner.generation_report['coverage_ledger'])):
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


def test_coverage_failure_explains_cause_without_changing_threshold():
    owner, edition = candidate(8)
    with pytest.raises(SummaryOutputError) as error:
        accept_edition(owner, edition, 'Title', 'Source', [], 0)
    assert error.value.reason == 'coverage'
    assert owner.generation_report['delivery']['coverage_ratio'] == .8
    assert owner.generation_report['delivery']['reason'] == 'coverage'


def test_review_transport_failure_is_not_reported_as_low_coverage():
    owner, edition = candidate(10)
    owner.generation_report.pop('grounded_draft_identity')
    with patch('transcript_reading.call_json', side_effect=TimeoutError('private provider response')):
        with pytest.raises(SummaryOutputError) as error:
            accept_edition(owner, edition, 'Title', 'Source', [], 0)
    assert error.value.reason == 'review'
    assert isinstance(error.value.__cause__, TimeoutError)
    assert 'private' not in str(error.value)
    assert owner.generation_report['delivery']['coverage_ratio'] == 1
    assert owner.generation_report['delivery']['status'] == 'blocked'

@pytest.mark.parametrize('repair_succeeds', [True,False])
def test_final_coverage_gap_gets_one_bounded_repair_and_fresh_grounding(repair_succeeds):
    owner,edition=candidate(8);owner._quality_inventory=({},[])
    def repair(*args,**kwargs):
        edition['sections'][0]['paragraphs'][0]['text']='A corrected and qualified claim.'
        ledger=copy.deepcopy(owner.generation_report['coverage_ledger'])
        if repair_succeeds:ledger['items'][8]['status']='covered'
        return ledger
    review={'checked_source_ids':[line.id for line in edition['lines']],
            'complete':True,'grounded':True,'unsupported_paragraph_ids':[],'additions':[]}
    with patch('coverage_ledger.efficient_audit',side_effect=repair) as audit, \
         patch('transcript_reading.call_json',return_value=review) as check:
        if repair_succeeds:
            accept_edition(owner,edition,'Title','Source',[],0)
            assert owner.generation_report['delivery']['coverage_ratio']==.9
        else:
            with pytest.raises(SummaryOutputError):accept_edition(owner,edition,'Title','Source',[],0)
        assert audit.call_count==1
        assert check.call_count==1


def test_final_coverage_repair_cannot_publish_when_new_prose_fails_grounding():
    owner,edition=candidate(8);owner._quality_inventory=({},[])
    def repair(*args,**kwargs):
        edition['sections'][0]['paragraphs'][0]['text']='Unverified new prose.'
        ledger=copy.deepcopy(owner.generation_report['coverage_ledger'])
        for item in ledger['items']:item['status']='covered'
        return ledger
    rejected={'checked_source_ids':[line.id for line in edition['lines']],
              'complete':True,'grounded':False,'unsupported_paragraph_ids':[],'additions':[]}
    with patch('coverage_ledger.efficient_audit',side_effect=repair) as audit, \
         patch('transcript_reading.call_json',return_value=rejected) as check:
        with pytest.raises(SummaryOutputError) as error:accept_edition(owner,edition,'Title','Source',[],0)
    assert error.value.reason=='grounding' and audit.call_count==1 and check.call_count==1
    assert owner.generation_report['delivery']['status']=='blocked'


@pytest.mark.parametrize('flag',['inventory_failed_batches','terminal_provider_failure','inventory_validation_failed_batches'])
def test_final_repair_never_masks_failed_source_or_provider_checks(flag):
    owner,edition=candidate(8);owner._quality_inventory=({},[])
    owner.generation_report['coverage_ledger'][flag]=1
    with patch('coverage_ledger.efficient_audit',side_effect=AssertionError('Must not mask hard failure')):
        with pytest.raises(SummaryOutputError):accept_edition(owner,edition,'Title','Source',[],0)


def test_contradicted_saved_receipt_requires_source_replacement_not_append_or_stale_pass():
    owner,edition=candidate(10);owner._quality_inventory=({},[])
    owner.generation_report['coverage_ledger']['items'][0]['status']='contradicted'
    repaired=copy.deepcopy(owner.generation_report['coverage_ledger']);repaired['items'][0]['status']='covered'
    review={'checked_source_ids':[line.id for line in edition['lines']],
            'complete':True,'grounded':True,'unsupported_paragraph_ids':[],'additions':[]}
    with patch('reading_delivery.repair_unsupported') as rewrite, \
         patch('coverage_ledger.efficient_audit',return_value=repaired) as audit, \
         patch('transcript_reading.call_json',return_value=review) as check:
        accept_edition(owner,edition,'Title','Source',[],0)
    rewrite.assert_called_once();assert rewrite.call_args.args[-1]=={'P1'}
    assert audit.call_args.kwargs['allow_repairs'] is False
    assert check.call_count==1  # Even a no-op replacement cannot reuse a stale pass.


def test_noop_grounding_repair_cannot_publish_raw_fallback_even_with_passing_ledger():
    owner,edition=candidate(10);owner._quality_inventory=({},[])
    edition['sections'][0]['paragraphs'][0]['raw']=True
    with patch('reading_delivery.repair_unsupported'), \
         patch('coverage_ledger.efficient_audit',return_value=owner.generation_report['coverage_ledger']):
        with pytest.raises(SummaryOutputError) as error:accept_edition(owner,edition,'Title','Source',[],0)
    assert error.value.reason=='grounding'
