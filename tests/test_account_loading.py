from unittest.mock import Mock
import pytest


@pytest.mark.asyncio
async def test_account_storage_error_is_not_an_empty_connection_list(client,monkeypatch):
    manager=Mock();manager.list_cookies.side_effect=RuntimeError('unavailable')
    monkeypatch.setattr('cookie_manager.get_cookie_manager',lambda *args:manager)
    response=await client.get('/api/cookies')
    assert response.status_code==503
    assert 'cookies' not in response.json()


def test_cloud_cookie_listing_propagates_storage_failure():
    from cookie_manager import _SupabaseCookieManager
    backend=object.__new__(_SupabaseCookieManager)
    backend.user_id='owner';backend.client=Mock()
    backend.client.table.side_effect=RuntimeError('unavailable')
    with pytest.raises(RuntimeError,match='storage unavailable'):backend.list_cookies()
