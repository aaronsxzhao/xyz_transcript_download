"""Startup must include interrupted jobs older than the recent history window."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from postgrest import SyncPostgrestClient

from api import job_persistence


@pytest.mark.parametrize('older_active', [0, 1, 500, 501])
def test_restore_keeps_recent_history_and_every_older_active_job(monkeypatch, older_active):
    rows = []
    for i in range(602 + older_active):
        status = 'pending' if i == 0 else ('completed' if i < 602 else 'cancelling')
        rows.append({'id': str(i), 'updated_at': (datetime(2026, 10, 20, tzinfo=timezone.utc) - timedelta(minutes=i)).isoformat(),
                     'payload': {'job_id': str(i), 'user_id': 'owner', 'status': status}})
    requests = []
    def serve(request):
        assert request.method == 'GET' and request.url.path == '/rest/v1/processing_jobs'
        requests.append(request)
        params = request.url.params
        filtered = rows
        if params.get('payload->>status'):
            assert params['payload->>status'] == 'not.in.(completed,failed,cancelled)'
            filtered = [r for r in rows if r['payload']['status'] not in {'completed', 'failed', 'cancelled'}]
        start = int(params.get('offset', 0))
        limit = int(params.get('limit', 1000))
        return httpx.Response(200, json=filtered[start:start + limit])
    with httpx.Client(transport=httpx.MockTransport(serve)) as http:
        provider = SyncPostgrestClient('https://fixture.test/rest/v1', http_client=http)
        monkeypatch.setattr(job_persistence, 'USE_SUPABASE', True)
        monkeypatch.setattr(job_persistence, 'client', lambda: SimpleNamespace(table=provider.from_))
        restored = job_persistence.restore_jobs()
    ids = [r['job_id'] for r in restored]
    assert len(ids) == len(set(ids)) == 500 + older_active
    assert set(ids) == {str(i) for i in range(500)} | {str(i) for i in range(602, 602 + older_active)}
    assert all(r.url.params.get('limit') == '500' for r in requests)
    if older_active >= 500:
        assert any(r.url.params.get('offset') == '500' for r in requests)


def test_local_restore_makes_no_cloud_request(monkeypatch):
    monkeypatch.setattr(job_persistence, 'USE_SUPABASE', False)
    monkeypatch.setattr(job_persistence, 'client', lambda: pytest.fail('Local mode must not query cloud jobs'))
    assert job_persistence.restore_jobs() == []


@pytest.mark.parametrize('size', [0, 1, 499])
def test_small_histories_need_only_one_request(monkeypatch, size):
    requests = []
    rows = [{'id': str(i), 'payload': {'job_id': str(i), 'status': 'transcribing'}} for i in range(size)]
    def serve(request):
        requests.append(request)
        return httpx.Response(200, json=rows)
    with httpx.Client(transport=httpx.MockTransport(serve)) as http:
        provider = SyncPostgrestClient('https://fixture.test/rest/v1', http_client=http)
        monkeypatch.setattr(job_persistence, 'USE_SUPABASE', True)
        monkeypatch.setattr(job_persistence, 'client', lambda: SimpleNamespace(table=provider.from_))
        assert job_persistence.restore_jobs() == [r['payload'] for r in rows]
    assert len(requests) == 1
