"""Bounded live comparison on synthetic text through the PUBLIC generation path.

No production data or credentials are emitted. Requires SUMMARY_TEST_* variables.
The serial control uses the same code/prompts but defers inventory and runs its
batches one at a time. This is a scheduling comparison, not a quality benchmark.
"""
import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processing_execution import Execution, bind
from note_summarizer import NoteSummarizer
from api.custom_models import normalize_base_url


class Store:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()
    def get_checkpoint(self, *key):
        with self.lock: return self.values.get(key)
    def put_checkpoint(self, *args):
        with self.lock: self.values[args[:-1]] = args[-1]


class Calls:
    def __init__(self, maximum=32, seconds=600):
        self.lock = threading.Lock()
        self.rows = []
        self.active = 0
        self.peak = 0
        self.maximum = maximum
        self.deadline = time.monotonic() + seconds


class TrackedClient:
    def __init__(self, raw, calls, label):
        self.raw, self.calls, self.label = raw, calls, label
        self.base_url = raw.base_url
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def with_options(self, **kwargs):
        return TrackedClient(self.raw.with_options(**kwargs), self.calls, self.label)
    def create(self, **kwargs):
        payload = json.loads(kwargs['messages'][-1]['content'])
        phase = payload.get('phase') or ('draft' if 'mode' in payload else 'grounding')
        with self.calls.lock:
            remaining = self.calls.deadline - time.monotonic()
            if len(self.calls.rows) >= self.calls.maximum or remaining <= 0:
                raise RuntimeError('Synthetic validation request budget exhausted')
            row = {'run': self.label, 'phase': phase, 'start': time.monotonic(), 'status': None}
            self.calls.rows.append(row)
            self.calls.active += 1
            self.calls.peak = max(self.calls.peak, self.calls.active)
        try:
            response = self.raw.with_options(timeout=min(90, remaining), max_retries=0).chat.completions.create(**kwargs)
            row['status'] = 200
            if response.usage:
                row['tokens'] = response.usage.total_tokens
            return response
        except Exception as error:
            row['status'] = getattr(error, 'status_code', None)
            row['error_type'] = type(error).__name__
            raise
        finally:
            with self.calls.lock:
                row['end'] = time.monotonic()
                self.calls.active -= 1


@contextmanager
def deferred(function):
    class LazyFuture(Future):
        def result(self, timeout=None):
            if not self.done():
                try: self.set_result(function())
                except BaseException as error: self.set_exception(error)
            return super().result(timeout)
    yield LazyFuture()


def source_text():
    alpha = ('In the synthetic ALPHA-17 pilot, aluminum housing cost 20 dollars per unit compared with 35 dollars for steel. '
             'The lower price required an order of at least 100 units. Durability was not yet measured. '
             'The next step is a 14-day corrosion test; purchasing approval depends on passing that test. '
             'These prototype prices are observations, not a prediction of mass-production costs. ')
    beta = ('In the independent synthetic BETA-29 pilot, the team tested a scheduling change for customer appointments. '
            'Median waiting time fell from 18 minutes to 12 minutes during a two-week trial with 80 appointments. '
            'There was no randomized control group, so the trial cannot establish that the change caused the improvement. '
            'The team will run a controlled comparison before rolling out the change to all customers. ')
    # Repeated spoken explanations exercise >1 normal inventory batch without
    # manufacturing dozens of independent repair obligations.
    text = '\n'.join([alpha] * 18 + [beta] * 18)
    return text


def run(label, source, calls, serial=False, notes_dir=None):
    engine = NoteSummarizer(api_key=os.environ['SUMMARY_TEST_API_KEY'],
                           base_url=normalize_base_url(os.environ['SUMMARY_TEST_BASE_URL']),
                           model=os.environ['SUMMARY_TEST_MODEL'])
    raw = engine.client
    engine.client = TrackedClient(raw, calls, label)
    store = Store()
    execution = Execution('synthetic-owner', label, store)
    started = time.monotonic()
    markers = sorted(set(re.findall(r'\b[A-Z]+-\d+\b', source)))
    report = {'run': label, 'source_sha256': hashlib.sha256(source.encode()).hexdigest()}
    try:
        with bind(execution):
            if serial:
                with patch('processing_parallel.background_work', deferred), patch('processing_parallel.bounded_map', lambda f, items, **kwargs: [f(item) for item in items]):
                    note = engine.generate_note('Two synthetic pilot reports', source, formats=['summary'], duration=3000)
            else:
                note = engine.generate_note('Two synthetic pilot reports', source, formats=['summary'], duration=3000)
        report['first_run_seconds'] = round(time.monotonic()-started, 3)
        if notes_dir:
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / (label + '.txt')).write_text(note)
        ledger = engine.generation_report.get('coverage_ledger', {})
        report.update(completed=True, output_sha256=hashlib.sha256(note.encode()).hexdigest(),
                      sentinel_presence={name: name in note for name in markers},
                      unexpected_sentinels=sorted(set(re.findall(r'\b[A-Z]+-\d+\b', note)) - set(markers)),
                      coverage={key: ledger.get(key) for key in ('status','inventory_batches','requests','failed_batches','unresolved_items')})
        before = sum(row['run'] == label for row in calls.rows)
        resumed = Execution('synthetic-owner', label, store)
        with bind(resumed):
            repeated = engine.generate_note('Two synthetic pilot reports', source, formats=['summary'], duration=3000)
        report.update(resume_identical=note == repeated, resume_new_requests=sum(row['run'] == label for row in calls.rows)-before,
                      checkpoint_hits=resumed.snapshot()['checkpoint_hits'])
    except Exception as error:
        report.update(completed=False, error_type=type(error).__name__, code=getattr(error, 'code', None))
    finally:
        report['wall_seconds_including_resume'] = round(time.monotonic()-started, 3)
        raw.close()
    rows = [row for row in calls.rows if row['run'] == label]
    events = sorted([(row['start'], 1) for row in rows] + [(row['end'], -1) for row in rows])
    current = peak = 0
    for _, change in events:
        current += change; peak = max(peak, current)
    report.update(request_count=len(rows), peak_in_flight=peak,
                  statuses={str(status): sum(row['status']==status for row in rows) for status in {row['status'] for row in rows}},
                  tokens=sum(row.get('tokens', 0) for row in rows),
                  requests=[{'phase': row['phase'], 'seconds': round(row['end']-row['start'], 3), 'status': row['status'], **({'error_type':row['error_type']} if 'error_type' in row else {})} for row in rows])
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--multi-part', action='store_true')
    parser.add_argument('--notes-dir', type=Path)
    args = parser.parse_args()
    if not all(os.environ.get(key) for key in ('SUMMARY_TEST_API_KEY','SUMMARY_TEST_BASE_URL','SUMMARY_TEST_MODEL')):
        raise SystemExit('Synthetic test credentials are not configured')
    calls = Calls()
    source = source_text()
    result = {'scope': 'synthetic transcript; same source and prompts; independent fresh checkpoint stores',
              'source_characters': len(source), 'revision': 'PR211', 'runs': []}
    if args.multi_part:
        variants = [source, source.replace('ALPHA-17', 'GAMMA-31').replace('BETA-29', 'DELTA-43')]
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, f'parallel-part-{index+1}', text, calls, notes_dir=args.notes_dir) for index, text in enumerate(variants)]
            result['runs'] = [future.result() for future in futures]
        result['shared_owner_peak_in_flight'] = calls.peak
        result['two_part_wall_seconds'] = round(time.monotonic()-started, 3)
    else:
        for label, serial in [('serial-control', True), ('parallel', False)]:
            result['runs'].append(run(label, source, calls, serial, args.notes_dir))
            args.output.write_text(json.dumps(result, indent=2))
            print(json.dumps({key: value for key, value in result['runs'][-1].items() if key != 'requests'}), flush=True)
    args.output.write_text(json.dumps(result, indent=2))
    if args.multi_part:
        print(json.dumps({**result, 'runs':[{key:value for key,value in row.items() if key != 'requests'} for row in result['runs']]}), flush=True)
    if not all(row.get('completed') and row.get('resume_identical') and row.get('resume_new_requests') == 0
               and row.get('coverage', {}).get('status') == 'model_reviewed'
               and row.get('coverage', {}).get('unresolved_items') == 0
               and row.get('coverage', {}).get('failed_batches') == 0
               and not row.get('unexpected_sentinels')
               and row.get('peak_in_flight', 0) <= 3
               and all(row.get('sentinel_presence', {}).values()) for row in result['runs']):
        raise SystemExit(1)
    if args.multi_part and result['shared_owner_peak_in_flight'] > 3:
        raise SystemExit(1)



if __name__ == '__main__':
    main()
