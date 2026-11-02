"""Exercise the public pipeline under contention and injected provider failures."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from openai import RateLimitError
import pytest

from note_summarizer import NoteSummarizer
from processing_execution import Execution, bind
from summary_errors import ProcessingCancelledError


class Store:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()
        self.after_save = lambda key, value: None
    def get_checkpoint(self, *key):
        with self.lock: return self.values.get(key)
    def put_checkpoint(self, *args):
        with self.lock: self.values[args[:-1]] = args[-1]
        self.after_save(args[:-1], args[-1])


class Provider:
    def __init__(self, fault=None):
        self.lock = threading.Lock()
        self.fault = fault
        self.injected = False
        self.calls = []
        self.active = self.peak = 0
        self.owner_active = {}
        self.owner_peak = {}
    def engine(self, owner, part):
        engine = NoteSummarizer(api_key='synthetic', base_url='https://synthetic.example/v1', model='synthetic')
        engine.client.close()
        engine.client = Mock(base_url='https://synthetic.example/v1')
        def create(**kwargs):
            payload = json.loads(kwargs['messages'][1]['content'])
            rows = payload.get('primary_source', [])
            phase = payload.get('phase') or ('draft' if 'mode' in payload else 'grounding')
            with self.lock:
                self.calls.append((owner, part, phase, json.dumps(payload, sort_keys=True)))
                self.active += 1
                self.peak = max(self.peak, self.active)
                self.owner_active[owner] = self.owner_active.get(owner, 0)+1
                self.owner_peak[owner] = max(self.owner_peak.get(owner, 0), self.owner_active[owner])
                inject = self.fault and phase == 'inventory' and not self.injected
                if inject: self.injected = True
            try:
                time.sleep(.02 if phase == 'inventory' else .03)
                if inject:
                    if self.fault == 'timeout': raise TimeoutError('Synthetic timeout')
                    response = httpx.Response(429, request=httpx.Request('POST','https://synthetic.example/v1'))
                    raise RateLimitError('Synthetic rate limit', response=response, body=None)
                spans = [{'start': rows[0]['id'], 'end': rows[-1]['id']}]
                if phase == 'inventory':
                    data = {'checked_source_ranges': spans, 'items': [{'kind':'claim', 'statement':rows[0]['text'], 'source_ranges':spans}]}
                elif phase == 'draft':
                    data = {'sections':[{'heading':part, 'paragraphs':[{'text':f'{part} claim with its condition.', 'source_ranges':spans}]}]}
                elif phase == 'match':
                    paragraph = payload['global_draft'][0]['paragraphs'][0]
                    assert part in paragraph['text'], 'A draft leaked between sources'
                    data = {'checked_proposed_paragraph_ids':[], 'matches':[{'item_id':item['id'], 'status':'covered', 'support':[{'paragraph_id':paragraph['id']}], 'grounded':True, 'duplicate':False} for item in payload['items']]}
                else:
                    data = {'checked_source_ids':[row['id'] for row in rows], 'complete':True, 'grounded':True, 'unsupported_paragraph_ids':[], 'additions':[]}
                return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(data)))])
            finally:
                with self.lock:
                    self.active -= 1
                    self.owner_active[owner] -= 1
        engine.client.with_options.return_value.chat.completions.create.side_effect = create
        return engine


@pytest.mark.parametrize('fault', [None, '429', 'timeout'])
@pytest.mark.parametrize('distinct_owners', [False, True])
def test_multiple_parts_limits_recovery_and_source_isolation(monkeypatch, fault, distinct_owners):
    import coverage_ledger
    monkeypatch.setattr(coverage_ledger, 'SOURCE_LIMIT', 1)
    provider, store = Provider(fault), Store()
    def process(index):
        owner = f'owner-{index % 2}' if distinct_owners else 'same-owner'
        part = f'PART-{index}'
        engine = provider.engine(owner, part)
        source = f'{part} claim.\n{part} condition.'
        with bind(Execution(owner, part, store)):
            note = engine.generate_note(part, source)
        assert engine.generation_report['coverage_ledger']['status'] == 'model_reviewed'
        return owner, part, source, engine, note
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(process, range(4)))
    assert provider.peak <= 4
    assert max(provider.owner_peak.values()) <= 3
    assert provider.peak >= 2
    assert provider.active == 0
    calls = len(provider.calls)
    assert calls == 20 + bool(fault)  # 5 distinct successful requests per source.
    for owner, part, source, engine, note in results:
        assert part in note and all(f'PART-{other}' not in note for other in range(4) if f'PART-{other}' != part)
        resumed = Execution(owner, part, store)
        with bind(resumed):
            assert engine.generate_note(part, source) == note
        assert resumed.snapshot()['checkpoint_hits'] == 5
    assert len(provider.calls) == calls
    from processing_parallel import _OWNER_SLOTS
    assert not _OWNER_SLOTS


def test_cancel_after_checkpoint_then_resume_without_repeating_saved_request(monkeypatch):
    import coverage_ledger
    monkeypatch.setattr(coverage_ledger, 'SOURCE_LIMIT', 1)
    provider, store = Provider(), Store()
    engine = provider.engine('owner', 'PART-CANCEL')
    execution = Execution('owner', 'cancel-source', store)
    def cancel_after_inventory(key, value):
        if 'checked_source_ranges' in value:
            execution.cancelled = True
    store.after_save = cancel_after_inventory
    source = 'PART-CANCEL claim.\nPART-CANCEL condition.'
    with bind(execution), pytest.raises(ProcessingCancelledError):
        engine.generate_note('PART-CANCEL', source)
    assert provider.active == 0
    saved = list(store.values.values())
    assert saved and any('checked_source_ranges' in value for value in saved)
    completed_inventory = [value['checked_source_ranges'] for value in saved if 'checked_source_ranges' in value]
    before = len(provider.calls)
    store.after_save = lambda key, value: None
    resumed = Execution('owner', 'cancel-source', store)
    with bind(resumed):
        note = engine.generate_note('PART-CANCEL', source)
    assert 'PART-CANCEL' in note
    assert resumed.snapshot()['checkpoint_hits'] == len(saved)
    for _, _, phase, payload in provider.calls[before:]:
        if phase == 'inventory':
            rows = json.loads(payload)['primary_source']
            assert [{'start':rows[0]['id'], 'end':rows[-1]['id']}] not in completed_inventory
    assert provider.active == 0
