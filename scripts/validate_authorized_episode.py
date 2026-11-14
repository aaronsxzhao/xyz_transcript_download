"""Isolated full-episode summary test. Never exports source, notes or credentials.

The previously rejected 6acfca97 input is deliberately excluded. Existing account
content is read only; request checkpoints live only in process memory. This is
not production queue acceptance. Invoke through the existing maintenance runner.
"""
import contextlib
import io
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
EPISODES = ('6af4bcc53caef3b52f546272', '6ac6a657e742e36efcbf74af')
# Same dedicated test-account anchor as the existing billing inspection.
ANCHOR_TASK = '25b33b27-b86e-442b-90f3-10473289c252'
# Exact historical task already returned by the authorized source inspection.
SOURCE_TASK = '63208f3e-1150-4d04-aafa-83f49a772878'
DAILY_LIMIT = 100
SETTLED_STOP = 85  # Reserve US$15 for in-flight calls and billing lag.
MAX_CALLS = 160
ZONE = timezone(timedelta(hours=8))


class TestGuardStopped(BaseException):
    """A test safety stop must escape application recovery/retry handlers."""


def enforce_budget(snapshot, day, active_work):
    if (snapshot.get('status') != 'checked' or snapshot.get('beijing_date') != day
            or active_work or type(snapshot.get('settled_usd')) not in (int,float)
            or not math.isfinite(snapshot['settled_usd'])
            or not 0 <= snapshot['settled_usd'] < SETTLED_STOP):
        raise TestGuardStopped('budget_or_queue_unavailable')


class MemoryCheckpoints:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()

    def get_checkpoint(self, *key):
        with self.lock:
            return self.values.get(key)

    def put_checkpoint(self, *args):
        with self.lock:
            self.values[args[:-1]] = args[-1]


class Calls:
    def __init__(self, guard, report, publish):
        self.guard, self.report, self.publish = guard, report, publish
        self.lock = threading.RLock()
        self.active = self.started = 0
        self.http_attempts = 0
        self.day = str(datetime.now(ZONE).date())

    def admit(self):
        with self.lock:
            if self.started >= MAX_CALLS:
                raise TestGuardStopped('request_guard')
            self.guard(self.day)
            self.started += 1
            self.active += 1
            self.report['peak_model_concurrency'] = max(self.report.get('peak_model_concurrency', 0), self.active)

    def outbound(self, request):
        # Count actual HTTP dispatch attempts separately from logical stages and
        # create() calls. Never retain headers, URL, body, response or exceptions.
        with self.lock:
            self.http_attempts += 1
            self.report['actual_provider_http_attempts'] = self.http_attempts


class TrackedClient:
    def __init__(self, raw, calls):
        self.raw, self.calls = raw, calls
        self.base_url = raw.base_url
        self.options = getattr(raw, 'options', {})
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **options):
        return TrackedClient(self.raw.with_options(**options), self.calls)

    def create(self, **kwargs):
        self.calls.admit()
        started = time.monotonic()
        ok = False
        try:
            result = self.raw.chat.completions.create(**kwargs)
            ok = True
            return result
        finally:
            with self.calls.lock:
                self.calls.active -= 1
                self.calls.report['model_create_calls'] = self.calls.started
                self.calls.report['failed_model_create_calls'] = self.calls.report.get('failed_model_create_calls', 0) + int(not ok)
                self.calls.report['provider_request_seconds_sum'] = round(self.calls.report.get('provider_request_seconds_sum', 0) + time.monotonic()-started, 3)
                self.calls.publish()

    def close(self):
        self.raw.close()


def child(destination):
    from api.supabase_client import get_supabase_admin_client
    from api.supabase_db import get_supabase_database
    from api.user_settings import get_user_settings, _load_preferences
    from api.llm_settings import resolve_llm_settings
    from api.custom_models import custom_http_client
    from processing_execution import Execution, bind
    from scripts.inspect_failed_reading import inspect_budget, safe_report
    from summarizer import Summarizer
    from transcriber import Transcript, TranscriptSegment
    from transcript_quality import validate_transcript
    from unittest.mock import patch
    database = get_supabase_admin_client()
    owners = database.table('processing_work').select('user_id').eq('task_id', ANCHOR_TASK).limit(2).execute().data or []
    if len(owners) != 1:
        raise TestGuardStopped('test_account_not_unique')
    owner = owners[0]['user_id']
    preferences = _load_preferences(owner)
    settings = get_user_settings(owner)
    if settings.get('llm_provider') != 'custom':
        raise TestGuardStopped('saved_provider_not_custom')
    seed = os.environ.get('MODEL_CREDENTIAL_KEY') or os.environ['SUPABASE_SERVICE_KEY']
    report = {'revision':os.environ.get('GITHUB_SHA'), 'environment':'isolated Actions runner; real model; memory checkpoints; no production queue',
              'production_writes':False, 'account_authentication':'authorized server maintenance bindings; not a user login',
              'daily_limit_usd':DAILY_LIMIT, 'settled_stop_usd':SETTLED_STOP, 'in_flight_reserve_usd':15,
              'request_limit':MAX_CALLS, 'actual_provider_http_attempts':0, 'terminal_state':'preflight',
              'checkpoint_policy':'request-fingerprinted Execution with empty in-memory store',
              'excluded_previously_rejected_episode':True, 'account_anchor':'existing_readonly_billing_diagnostic'}
    def publish():
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(json.dumps(report))
        temporary.replace(destination)
    def guard(day):
        try:
            budget = inspect_budget(preferences, owner, seed)
            active = database.table('processing_work').select('state').in_('state', ['queued','running']).limit(1).execute().data or []
        except Exception:
            raise TestGuardStopped('budget_or_queue_unavailable') from None
        report['budget'] = {k:budget[k] for k in ('status','beijing_date','settled_usd','scope') if k in budget}
        report['budget']['daily_limit_usd'] = DAILY_LIMIT
        report['budget']['active_work_found'] = bool(active)
        enforce_budget(budget, day, active)
    guard(str(datetime.now(ZONE).date()))
    # Read only a different explicitly authorized episode. No rejected source is
    # selected, loaded, split, transformed or routed through another executor.
    available = database.table('transcripts').select('episode_id').eq('user_id', owner).in_('episode_id', list(EPISODES)).execute().data or []
    eid = next((eid for eid in EPISODES if any(row['episode_id'] == eid for row in available)), None)
    source_owner = owner
    if not eid:
        # Keep the provider bound to the dedicated billing account. A separately
        # authorized source may belong to another account; resolve only the exact
        # known task and URL, never search arbitrary users or use their settings.
        eid = EPISODES[1]
        source_rows = (database.table('processing_work').select('user_id')
            .eq('task_id', SOURCE_TASK).eq('kind','podcast')
            .eq('payload->>episode_url', 'https://www.xiaoyuzhoufm.com/episode/'+eid)
            .limit(2).execute().data or [])
        if len(source_rows) != 1:
            report.update(terminal_state='blocked', blocker='authorized_source_binding_unavailable')
            publish()
            return
        source_owner = source_rows[0]['user_id']
        report['source_binding'] = 'exact previously authorized historical task and episode URL; read only'
        report['source_and_billing_account_same'] = source_owner == owner
    record = get_supabase_database().get_transcript(source_owner, eid)
    if record is None:
        report.update(terminal_state='blocked', blocker='authorized_alternate_transcript_unavailable')
        publish()
        return
    transcript = Transcript(eid, record.language, record.duration, record.text,
                           [TranscriptSegment(**segment) for segment in record.segments])
    validate_transcript(transcript)
    report.update(episode_id=eid, source_segments=len(transcript.segments), source_characters=len(transcript.text),
                  source_duration_seconds=transcript.duration, transcript_structural_validation='passed',
                  manual_transcript_readability='not_reviewed', manual_summary_readability='not_reviewed')
    resolved = resolve_llm_settings(settings)
    import hashlib
    report['model_settings_fingerprint'] = hashlib.sha256(json.dumps({k:resolved[k] for k in ('model','model_options') if k in resolved},sort_keys=True).encode()).hexdigest()
    calls = Calls(guard, report, publish)
    http = custom_http_client()
    http.event_hooks.setdefault('request', []).append(calls.outbound)
    with patch('api.custom_models.custom_http_client', return_value=http):
        engine = Summarizer(**resolved, generation_mode=settings.get('summary_generation_mode','single'))
    engine.client = TrackedClient(engine.client, calls)
    execution = Execution('isolated-authorized-test', eid, MemoryCheckpoints())
    report['terminal_state'] = 'running'
    publish()
    started = time.monotonic()
    try:
        with bind(execution):
            summary = engine.summarize(transcript, episode_title='Authorized complete podcast validation')
        accepted = bool(summary) and engine.generation_report.get('delivery', {}).get('status') == 'accepted'
        report['terminal_state'] = 'accepted' if accepted else 'not_accepted'
        if summary:
            report['summary_structure'] = {'overview_characters':len(summary.overview), 'key_points':len(summary.key_points), 'topics':len(summary.topics)}
    except TestGuardStopped:
        report['terminal_state'] = 'test_guard_stopped'
    except Exception as error:
        report.update(terminal_state='failed', error_type=type(error).__name__)
    finally:
        report['wall_seconds'] = round(time.monotonic()-started, 3)
        report['generation'] = safe_report(engine.generation_report)
        ledger = engine.generation_report.get('coverage_ledger') or {}
        report['reuse_and_retry'] = {key:ledger[key] for key in ('inventory_receipts_reused','repair_transport_retries','validation_retries','inventory_transport_retries','requests') if type(ledger.get(key)) in (int,float)}
        snapshot = execution.snapshot()
        report['execution'] = {key:snapshot[key] for key in ('stages','checkpoint_hits','wall_seconds') if key in snapshot}
        engine.client.close()
        try:
            guard(calls.day)
        except TestGuardStopped:
            report['final_budget_guard_passed'] = False
        else:
            report['final_budget_guard_passed'] = True
        publish()


def main():
    logging.disable(logging.CRITICAL)
    if len(sys.argv)>1 and sys.argv[1]=='--child':
        destination = Path(sys.argv[2])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                child(destination)
            except BaseException as error:
                report = json.loads(destination.read_text()) if destination.exists() else {'production_writes':False,'actual_provider_http_attempts':0}
                report.update(terminal_state='blocked', error_type=type(error).__name__)
                destination.write_text(json.dumps(report))
        return
    from scripts.diagnose_deployment import oci_json
    with tempfile.TemporaryDirectory() as temporary:
        containers = oci_json(['container-instances','container-instance','get','--container-instance-id',os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"') or []
        bindings = None
        for container in containers:
            row = oci_json(['container-instances','container','get','--container-id',container], 'data."environment-variables"') or {}
            if row.get('SUPABASE_URL') and row.get('SUPABASE_SERVICE_KEY'):
                bindings = {key:value for key,value in row.items() if key.startswith('SUPABASE_') or key in ('USE_SUPABASE','MODEL_CREDENTIAL_KEY')}
                break
        if not bindings:
            print(json.dumps({'terminal_state':'blocked','blocker':'existing_bindings_unavailable'}))
            return
        destination = Path(temporary)/'aggregate.json'
        process = subprocess.Popen([sys.executable,__file__,'--child',str(destination)],
            env={**os.environ,**bindings,'XYZ_DATA_DIR':temporary,'DISCORD_WEBHOOK_URL':'','PYTHONPATH':'.'},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started = last_report = time.monotonic()
        timed_out = False
        while process.poll() is None:
            if time.monotonic()-started >= 3600:
                process.kill()
                process.wait()
                timed_out = True
                break
            if destination.exists() and time.monotonic()-last_report >= 30:
                progress = json.loads(destination.read_text())
                print(json.dumps({'episode_validation_progress':{key:progress[key] for key in
                    ('terminal_state','episode_id','source_segments','actual_provider_http_attempts',
                     'model_create_calls','peak_model_concurrency','budget') if key in progress}}),flush=True)
                last_report = time.monotonic()
            time.sleep(1)
        if not destination.exists():
            print(json.dumps({'terminal_state':'blocked','blocker':'child_report_unavailable'}))
            return
        if timed_out:
            report = json.loads(destination.read_text())
            report['terminal_state'] = 'test_deadline_stopped'
            report['full_episode_acceptance'] = False
            destination.write_text(json.dumps(report))
        # The child writes only the explicit aggregate report. No raw child
        # stdout, stderr, model output or source leaves its temporary process.
        print(json.dumps({'authorized_episode_validation':json.loads(destination.read_text())}))


if __name__=='__main__':
    main()
