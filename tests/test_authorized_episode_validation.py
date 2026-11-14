import pytest
from scripts.validate_authorized_episode import (
    Calls, EPISODES, MAX_CALLS, MemoryCheckpoints, TestGuardStopped as GuardStop,
    TrackedClient, enforce_budget,
)
from types import SimpleNamespace


def snapshot(**changes):
    return dict(status='checked', beijing_date='2026-11-14', settled_usd=0, **changes)


@pytest.mark.parametrize('value', [None, -1, float('nan'), float('inf'), 85, 100, True])
def test_budget_fails_closed_for_unreliable_or_exhausted_totals(value):
    with pytest.raises(GuardStop):
        enforce_budget({'status':'checked','beijing_date':'2026-11-14','settled_usd':value}, '2026-11-14', [])


@pytest.mark.parametrize('day,active', [('2026-11-15',[]), ('2026-11-14',[{'state':'running'}])])
def test_new_day_and_any_production_work_stop_paid_admission(day, active):
    with pytest.raises(GuardStop):
        enforce_budget(snapshot(), day, active)


def test_budget_preserves_in_flight_reserve():
    enforce_budget({'status':'checked','beijing_date':'2026-11-14','settled_usd':84.99}, '2026-11-14', [])


def test_rejected_source_is_never_in_test_selection():
    assert '6acfca97e742e36efcc313f6' not in EPISODES
    assert set(EPISODES) == {'6af4bcc53caef3b52f546272','6ac6a657e742e36efcbf74af'}


def test_memory_checkpoints_preserve_request_identity():
    store=MemoryCheckpoints()
    store.put_checkpoint('owner','source','stage','fingerprint', {'validated':True})
    assert store.get_checkpoint('owner','source','stage','fingerprint') == {'validated':True}
    assert store.get_checkpoint('owner','source','stage','changed') is None


def test_actual_http_attempts_are_distinct_from_model_create_calls():
    report={}
    calls=Calls(lambda day:None,report,lambda:None)
    client=TrackedClient(SimpleNamespace(base_url='https://example.invalid',
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:'cached-protocol-result'))),calls)
    assert client.create() == 'cached-protocol-result'
    assert report['model_create_calls'] == 1
    assert 'actual_provider_http_attempts' not in report
    calls.outbound(object())
    assert report['actual_provider_http_attempts'] == 1
    assert calls.active == 0


def test_guard_failure_does_not_enter_provider_or_get_retried_as_exception():
    calls=Calls(lambda day:None,{},lambda:None)
    calls.started=MAX_CALLS
    with pytest.raises(GuardStop):
        calls.admit()
    assert calls.active == 0
    assert not issubclass(GuardStop, Exception)


def test_account_anchor_matches_the_existing_budget_inspection():
    from scripts.validate_authorized_episode import ANCHOR_TASK
    from scripts.inspect_failed_reading import TASKS
    assert ANCHOR_TASK in TASKS


def test_manual_episode_job_preserves_original_ciphertext_workflow():
    import yaml
    from pathlib import Path
    workflow=yaml.safe_load(Path('.github/workflows/review-saved-summary-samples.yml').read_text())
    job=workflow['jobs']['validate-authorized-episode']
    assert "github.event_name == 'workflow_dispatch'" in job['if']
    assert "github.ref == 'refs/heads/codex/summary-handoff-validation'" in job['if']
    assert workflow['jobs']['review']['steps'][-1]['with']['path'] == '/tmp/xyz-review-artifacts/review.enc.json'


@pytest.mark.parametrize('state', ['blocked','running','failed','test_guard_stopped','test_deadline_stopped','not_accepted',None])
def test_incomplete_runs_cannot_produce_successful_job_exit(state):
    from scripts.validate_authorized_episode import result_exit_code
    assert result_exit_code({'terminal_state':state}) != 0


def test_only_accepted_delivery_produces_successful_job_exit():
    from scripts.validate_authorized_episode import result_exit_code
    assert result_exit_code({'terminal_state':'accepted'}) == 0


def test_monitor_transport_retry_never_returns_stale_budget_or_model_calls():
    from urllib.error import HTTPError
    from scripts.validate_authorized_episode import read_monitor
    attempts=[]; waits=[]; report={}
    def read():
        attempts.append(1)
        if len(attempts)==1:
            raise HTTPError('https://example.invalid',429,'private body',{'Retry-After':'3'},None)
        return snapshot()
    assert read_monitor(read,report,waits.append)['settled_usd']==0
    assert waits==[3]
    assert report['monitor']['read_failures']==1
    assert report['last_monitor_error']=={'error_type':'HTTPError','http_status':429}
    assert 'private' not in str(report)


@pytest.mark.parametrize('status', [401,403,429,503])
def test_persistent_monitor_failure_stops_before_paid_admission(status):
    from urllib.error import HTTPError
    from scripts.validate_authorized_episode import read_monitor
    attempts=[]
    def read():
        attempts.append(1)
        raise HTTPError('https://example.invalid',status,'private body',{},None)
    with pytest.raises(GuardStop):
        read_monitor(read,{},lambda delay:None)
    assert len(attempts)==(3 if status in (429,503) else 1)


def test_monitor_does_not_override_excessive_retry_after_or_return_stale_data():
    from urllib.error import HTTPError
    from scripts.validate_authorized_episode import read_monitor
    waits=[]
    def read():
        raise HTTPError('https://example.invalid',429,'private',{'Retry-After':'300'},None)
    with pytest.raises(GuardStop):
        read_monitor(read,{},waits.append)
    assert waits==[]
