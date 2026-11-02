import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from processing_execution import Execution, bind
from processing_parallel import bounded_map, background_work, check_cancelled, model_slot
from summary_errors import ProcessingCancelledError


def test_bounded_map_overlaps_and_preserves_order_and_execution_context():
    from processing_execution import CURRENT
    barrier = threading.Barrier(2)
    execution = Execution('owner', 'source', Mock())
    def one(value):
        assert CURRENT.get() is execution
        barrier.wait(timeout=2)
        return value
    with bind(execution):
        assert bounded_map(one, [3, 2, 1, 0]) == [3, 2, 1, 0]


def test_terminal_result_stops_admitting_remaining_work():
    started = []
    def one(value):
        started.append(value)
        return value
    result = bounded_map(one, range(100), stop_when=lambda value: True)
    assert len(started) <= 2 and len(result) <= 2


def test_background_failure_joins_and_stops_worker_before_returning():
    entered = threading.Event()
    exited = threading.Event()
    def work():
        entered.set()
        try:
            while True:
                check_cancelled()
                exited.wait(.01)
        finally:
            exited.set()
    with pytest.raises(ValueError):
        with background_work(work):
            assert entered.wait(2)
            raise ValueError('Draft failed')
    assert exited.is_set()


def test_model_gate_bounds_same_owner_across_tasks_and_releases_cancelled_waiters():
    entered = threading.Barrier(4)
    release = threading.Event()
    waiting = Execution('same-owner', 'waiting', Mock())
    def occupy(index):
        with bind(Execution('same-owner', str(index), Mock())), model_slot():
            entered.wait(timeout=2)
            assert release.wait(3)
    with ThreadPoolExecutor(max_workers=4) as pool:
        holders = [pool.submit(occupy, i) for i in range(3)]
        entered.wait(timeout=2)
        def fourth():
            with bind(waiting), model_slot():
                pytest.fail('A fourth call acquired the same owner slot')
        future = pool.submit(fourth)
        waiting.cancelled = True
        with pytest.raises(ProcessingCancelledError):
            future.result(timeout=2)
        release.set()
        for future in holders:
            future.result(timeout=2)
    from processing_parallel import _OWNER_SLOTS
    assert 'same-owner' not in _OWNER_SLOTS


def test_inventory_batches_overlap_keep_source_ids_and_do_not_see_draft(monkeypatch):
    import coverage_ledger as ledger
    from transcript_reading import source_lines
    _, lines = source_lines('First claim.\nSecond claim.')
    monkeypatch.setattr(ledger, 'SOURCE_LIMIT', 1)
    barrier = threading.Barrier(2)
    def request(engine, system, payload, validator):
        assert payload['phase'] == 'inventory' and 'global_draft' not in payload
        barrier.wait(timeout=2)
        rows = payload['primary_source']
        spans = [{'start': rows[0]['id'], 'end': rows[-1]['id']}]
        return {'checked_source_ranges': spans, 'items': [{'kind': 'claim', 'statement': rows[0]['text'], 'source_ranges': spans}]}
    monkeypatch.setattr(ledger, 'request', request)
    report, items = ledger.build_inventory(SimpleNamespace(), lines)
    assert report['requests'] == 2 and report['failed_batches'] == 0
    assert [item['id'] for item in items] == ['C1.1', 'C2.2']
    assert [item['source_ranges'][0]['start'] for item in items] == [line.id for line in lines]


def test_generation_and_inventory_overlap_and_prepared_results_are_consumed(monkeypatch):
    import coverage_ledger as ledger
    import transcript_reading as reading
    barrier = threading.Barrier(2)
    prepared = ({'inventory_batches': 1}, [])
    def inventory(*args, **kwargs):
        barrier.wait(timeout=2)
        return prepared
    def generate(*args, **kwargs):
        barrier.wait(timeout=2)
        return {'joined': args[5].result(timeout=2)}
    monkeypatch.setattr(ledger, 'build_inventory', inventory)
    monkeypatch.setattr(reading, '_generate_with_inventory', generate)
    result = reading.generate(SimpleNamespace(generation_mode='single'), 'Source text', 'Title')
    assert result == {'joined': prepared}


def test_real_generation_reuses_parallel_inventory_checkpoints(monkeypatch):
    import json
    from note_summarizer import NoteSummarizer
    import coverage_ledger as ledger
    monkeypatch.setattr(ledger, 'SOURCE_LIMIT', 1)
    barrier = threading.Barrier(3)  # Two inventory calls plus the draft.
    owner = NoteSummarizer(api_key='synthetic')
    owner.client = Mock(base_url='https://model.example/v1')
    calls = []
    class Store:
        def __init__(self): self.values = {}
        def get_checkpoint(self, *key): return self.values.get(key)
        def put_checkpoint(self, *args): self.values[args[:-1]] = args[-1]
    def complete(**kwargs):
        payload = json.loads(kwargs['messages'][1]['content'])
        calls.append(payload)
        rows = payload.get('primary_source', [])
        spans = [{'start': rows[0]['id'], 'end': rows[-1]['id']}]
        if payload.get('phase') == 'inventory':
            barrier.wait(timeout=3)
            data = {'checked_source_ranges': spans, 'items': [{'kind': 'claim', 'statement': rows[0]['text'], 'source_ranges': spans}]}
        elif 'mode' in payload:
            barrier.wait(timeout=3)
            data = {'sections': [{'heading': 'Argument', 'paragraphs': [{'text': 'Supported argument with an essential condition.', 'source_ranges': spans}]}]}
        elif payload.get('phase') == 'match':
            paragraph = payload['global_draft'][0]['paragraphs'][0]
            data = {'checked_proposed_paragraph_ids': [], 'matches': [{'item_id': item['id'], 'status': 'covered', 'support': [{'paragraph_id': paragraph['id']}], 'grounded': True, 'duplicate': False} for item in payload['items']]}
        else:
            data = {'checked_source_ids': [row['id'] for row in rows], 'complete': True, 'grounded': True, 'unsupported_paragraph_ids': [], 'additions': []}
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(data)))])
    owner.client.with_options.return_value.chat.completions.create.side_effect = complete
    store = Store()
    with bind(Execution('owner', 'source', store)):
        first = owner.generate_note('Title', 'A supported argument.\nAn essential condition.')
    count = len(calls)
    resumed = Execution('owner', 'source', store)
    with bind(resumed):
        second = owner.generate_note('Title', 'A supported argument.\nAn essential condition.')
    assert first == second and len(calls) == count == 5
    assert resumed.snapshot()['checkpoint_hits'] == 5
    assert owner.generation_report['coverage_ledger']['status'] == 'model_reviewed'
