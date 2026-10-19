"""Recover terminated reads without replaying writes or leaking account data."""
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from api.supabase_http import SupabaseHTTPClient


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_interrupted_database_read_recovers_once_with_same_owner(method):
    calls = []
    def upstream(request):
        calls.append((request.method, str(request.url), request.headers['authorization']))
        if len(calls) == 1:
            raise httpx.RemoteProtocolError('ConnectionTerminated', request=request)
        return httpx.Response(200, json=[])
    with SupabaseHTTPClient(transport=httpx.MockTransport(upstream)) as client:
        response = client.request(method, 'https://example.supabase.co/rest/v1/summaries?user_id=eq.owner',
                                  headers={'Authorization': 'Bearer private-service-key'})
    assert response.status_code == 200 and len(calls) == 2
    assert calls[0] == calls[1]


@pytest.mark.parametrize('method,path', [('POST', '/rest/v1/summaries'), ('PATCH', '/rest/v1/video_tasks'),
                                        ('DELETE', '/rest/v1/episodes'), ('POST', '/auth/v1/token'),
                                        ('POST', '/storage/v1/object/media'), ('GET', '/storage/v1/object/media')])
def test_writes_authentication_and_storage_are_never_replayed(method, path):
    calls = []
    def upstream(request):
        calls.append(request)
        raise httpx.RemoteProtocolError('interrupted', request=request)
    with SupabaseHTTPClient(transport=httpx.MockTransport(upstream)) as client:
        with pytest.raises(httpx.RemoteProtocolError):
            client.request(method, 'https://example.supabase.co' + path)
    assert len(calls) == 1


def test_repeated_disconnect_and_timeout_stop_without_retry_loop():
    for error_type, expected in [(httpx.ReadError, 2), (httpx.ReadTimeout, 1)]:
        calls = []
        def upstream(request):
            calls.append(request)
            raise error_type('unavailable', request=request)
        with SupabaseHTTPClient(transport=httpx.MockTransport(upstream)) as client:
            with pytest.raises(error_type):
                client.get('https://example.supabase.co/rest/v1/summaries')
        assert len(calls) == expected


def test_sdk_parallel_reads_preserve_filters_headers_and_storage_timeout():
    from supabase import create_client
    from supabase.client import ClientOptions
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json=[{'id': 1}])
    with SupabaseHTTPClient(transport=httpx.MockTransport(upstream)) as http:
        sdk = create_client('https://example.supabase.co', 'private-key', options=ClientOptions(
            httpx_client=http, auto_refresh_token=False, persist_session=False))
        def query(owner):
            return sdk.table('summaries').select('id').eq('user_id', owner).execute().data
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert list(pool.map(query, map(str, range(32)))) == [[{'id': 1}]] * 32
        assert {r.url.params['user_id'] for r in calls} == {'eq.' + str(i) for i in range(32)}
        assert all(r.headers['authorization'] == 'Bearer private-key' for r in calls)
        assert all(r.extensions['timeout']['read'] == 6 for r in calls)
        http.get('https://example.supabase.co/storage/v1/object/media')
        assert calls[-1].extensions['timeout']['read'] == 60
