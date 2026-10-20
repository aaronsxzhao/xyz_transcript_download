"""Timing diagnostics remain bounded, anonymous in payload, and account scoped."""
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from api.auth import User, get_current_user
from api.routers.performance import router, _samples


@pytest.mark.asyncio
async def test_browser_timings_reject_content_and_separate_accounts():
    app = FastAPI()
    app.include_router(router, prefix='/timings')
    owner = ["private-owner-one"]
    app.dependency_overrides[get_current_user] = lambda: User(owner[0], "unused@localhost")
    _samples.clear()
    record = {"page": "episodes", "elapsed_ms": 9000, "first_paint_ms": 700, "document_ms": 1000, "api_ms": 4000, "cached": False}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(65):
            assert (await client.post('/timings', json=record)).status_code == 204
        data = (await client.get('/timings')).json()
        assert data["pages"]["episodes"]["samples"] == 64
        assert data["pages"]["episodes"]["first_paint_ms"] == 700
        assert owner[0] not in str(data) and "unused@localhost" not in str(data)
        assert (await client.post('/timings', json={**record, "url": "private-url"})).status_code == 422
        assert (await client.post('/timings', json={**record, "page": "private-url"})).status_code == 422
        owner[0] = "second"
        assert (await client.get('/timings')).json() == {"pages": {}}
    _samples.clear()


@pytest.mark.asyncio
async def test_browser_timings_require_authentication(monkeypatch):
    monkeypatch.setattr('api.auth.USE_SUPABASE', True)
    app = FastAPI()
    app.include_router(router, prefix='/timings')
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get('/timings')).status_code == 401
        assert (await client.post('/timings', json={"page": "videos", "elapsed_ms": 1, "document_ms": 1, "api_ms": 1, "cached": False})).status_code == 401


@pytest.mark.asyncio
async def test_slow_and_failed_settings_visits_are_not_hidden_by_cached_revisit():
    app = FastAPI()
    app.include_router(router, prefix='/timings')
    app.dependency_overrides[get_current_user] = lambda: User('owner', '')
    _samples.clear()
    base = {'page': 'settings', 'document_ms': 0, 'api_ms': 0, 'server_ms': 0, 'cached': False}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for elapsed, outcome in [(10000, 'slow'), (10001, 'error'), (3, 'ready')]:
            assert (await client.post('/timings', json={**base, 'elapsed_ms': elapsed, 'outcome': outcome})).status_code == 204
        result = (await client.get('/timings')).json()['pages']['settings']
        assert result['worst_ms'] == 10001
        assert result['error_count'] == result['slow_count'] == 1
        assert result['samples'] == 3 and result['elapsed_ms'] == 3
    _samples.clear()
