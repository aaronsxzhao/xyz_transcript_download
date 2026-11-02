"""Replay explicitly supplied local transcripts; never writes production data.

Uses SUMMARY_TEST_* credentials. Inputs and output notes should remain outside
the repository. Runs share one owner and the production concurrency limits.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_parallel_processing import Store
from api.custom_models import normalize_base_url
from note_summarizer import NoteSummarizer
from processing_execution import Execution, bind
from source_coverage import video_source_text


class Tracker:
    def __init__(self, output):
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.rows = []
        self.active = self.peak = 0
        self.output = output

    def event(self, value):
        with self.lock:
            with (self.output / 'events.jsonl').open('a') as stream:
                stream.write(json.dumps(value, ensure_ascii=False) + '\n')


class Client:
    def __init__(self, raw, tracker, label):
        self.raw, self.tracker, self.label = raw, tracker, label
        self.base_url = raw.base_url
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **options):
        return Client(self.raw.with_options(**options), self.tracker, self.label)

    def create(self, **kwargs):
        payload = json.loads(kwargs['messages'][-1]['content'])
        phase = payload.get('phase') or ('draft' if 'mode' in payload else 'grounding')
        tracker = self.tracker
        with tracker.lock:
            if len(tracker.rows) >= 300 or time.monotonic() - tracker.started > 3600:
                raise RuntimeError('Replay request budget exhausted')
            row = dict(part=self.label, phase=phase, start=time.monotonic()-tracker.started)
            tracker.rows.append(row)
            tracker.active += 1
            tracker.peak = max(tracker.peak, tracker.active)
        tracker.event(dict(event='request_start', **row))
        try:
            response = self.raw.chat.completions.create(**kwargs)
            row.update(status=200, finish_reason=response.choices[0].finish_reason)
            if response.usage:
                row['tokens'] = response.usage.total_tokens
            return response
        except Exception as error:
            row.update(status=getattr(error, 'status_code', None), error_type=type(error).__name__)
            raise
        finally:
            with tracker.lock:
                row['end'] = time.monotonic()-tracker.started
                tracker.active -= 1
            tracker.event(dict(event='request_end', **row))


def run(item, tracker):
    label = item['title'].split(' · ')[-1].split(' ')[0]
    transcript = json.loads(item['transcript_json'])
    source = video_source_text(transcript['text'], transcript['segments'])
    engine = NoteSummarizer(api_key=os.environ['SUMMARY_TEST_API_KEY'],
                           base_url=normalize_base_url(os.environ['SUMMARY_TEST_BASE_URL']),
                           model=os.environ['SUMMARY_TEST_MODEL'])
    raw = engine.client
    engine.client = Client(raw, tracker, label)
    execution = Execution('local-real-replay', item['id'], Store())
    started = time.monotonic()
    result = dict(part=label, title=item['title'], duration=item['duration'], source_characters=len(source),
                  source_sha256=hashlib.sha256(source.encode()).hexdigest())
    tracker.event(dict(event='run_start', part=label))
    try:
        with bind(execution):
            note = engine.generate_note(item['title'], source, style=item['style'], formats=item['formats'],
                                        duration=item['duration'])
        result.update(completed=bool(note), markdown_characters=len(note))
        (tracker.output / (label.replace('/', '-') + '.md')).write_text(note)
    except Exception as error:
        result.update(completed=False, error_type=type(error).__name__, code=getattr(error, 'code', None))
    finally:
        result.update(seconds=round(time.monotonic()-started, 3), execution=execution.snapshot(),
                      generation=engine.generation_report)
        raw.close()
        (tracker.output / (label.replace('/', '-') + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    tracker.event(dict(event='run_end', part=label, seconds=result['seconds'], completed=result['completed']))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    inputs = json.loads(args.input.read_text())
    tracker = Tracker(args.output_dir)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda item: run(item, tracker), inputs))
    (args.output_dir / 'report.json').write_text(json.dumps(dict(runs=results, requests=tracker.rows,
        peak_in_flight=tracker.peak, wall_seconds=time.monotonic()-tracker.started), ensure_ascii=False, indent=2))
    print(json.dumps([dict(part=r['part'], completed=r['completed'], seconds=r['seconds'],
        verification=r['generation'].get('verification', {}).get('status'),
        unresolved_items=r['generation'].get('coverage_ledger', {}).get('unresolved_items')) for r in results]))
    if not all(r['completed'] for r in results):
        raise SystemExit(1)
    # A saved note with review warnings is a completed generation, not a passed
    # quality check. Keep these outcomes distinct for future benchmark runners.
    if not all(r['generation'].get('verification', {}).get('status') == 'model_reviewed'
               and r['generation'].get('coverage_ledger', {}).get('status') == 'model_reviewed'
               for r in results):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
