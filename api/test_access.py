"""Revocable, account-bound diagnostic access; never a Supabase user JWT."""
import asyncio
import hashlib
import logging
import re
from fastapi import HTTPException
from starlette.routing import compile_path

# Exact registered route templates: new endpoints are denied until reviewed.
READ_ROUTES = frozenset({
    '/api/stats', '/api/content-updates', '/api/library', '/api/library/sources',
    '/api/podcasts', '/api/podcasts/content', '/api/podcasts/{pid}',
    '/api/podcasts/{pid}/episodes', '/api/episodes/{eid}',
    '/api/summaries', '/api/summaries/recent', '/api/summaries/{eid}',
    '/api/summaries/{eid}/html', '/api/summaries/{eid}/markdown',
    '/api/transcripts/{eid}', '/api/jobs', '/api/jobs/{job_id}',
    '/api/video-notes/collections/{task_id}/parts', '/api/video-notes/progress',
    '/api/video-notes/tasks', '/api/video-notes/channels', '/api/video-notes/tasks/by-channel',
    '/api/video-notes/recent', '/api/video-notes/tasks/{task_id}',
    '/api/video-notes/tasks/{task_id}/transcript',
    '/api/video-notes/tasks/{task_id}/versions/{version_id}',
    '/api/processing/metrics/{kind}/{task_id}', '/api/settings',
    '/api/cookies', '/api/cookies/{platform}',
})
DIAGNOSTIC_ROUTES = frozenset({
    ('GET', '/api/cookies/bilibili/validate'),
    ('GET', '/api/cookies/douyin/diagnose'),
    ('POST', '/api/cookies/youtube/verify'),
})
MODEL_ROUTES = frozenset({
    '/api/settings/models', '/api/settings/test-llm', '/api/settings/test-transcription',
})
TOKEN_PATTERN = re.compile(r'ptt_[A-Za-z0-9_-]{43}\Z')


_ROUTE_PATTERNS = {
    template: compile_path(template)[0]
    for template in READ_ROUTES | MODEL_ROUTES | {path for _, path in DIAGNOSTIC_ROUTES}
}


def reviewed_route(request):
    # FastAPI 0.143 keeps included routers lazy: scope.route.path is relative
    # to its include prefix. Verify both the public path and the actual matched
    # route shape, so a future static endpoint cannot inherit a parameter route's
    # permissions merely because its URL fits that parameter pattern.
    local_path = getattr(request.scope.get('route'), 'path', None)
    if local_path is None:
        return ''
    for template, pattern in _ROUTE_PATTERNS.items():
        if template.endswith(local_path) and pattern.fullmatch(request.url.path):
            return template
    return ''


def _consume(token, scope, route):
    from api.supabase_client import get_supabase_admin_client
    database = get_supabase_admin_client()
    if database is None:
        raise RuntimeError('Test token registry unavailable')
    return database.rpc('consume_platform_test_token', {
        'p_digest': hashlib.sha256(token.encode()).hexdigest(),
        'p_scope': scope, 'p_route': route,
    }).execute().data


async def authenticate_test_token(request, token):
    from api.auth import User
    if not TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(401, 'Invalid test token')
    route = reviewed_route(request)
    method = request.method
    if method == 'GET' and route in READ_ROUTES:
        scope = 'content:read'
    elif (method, route) in DIAGNOSTIC_ROUTES:
        scope = 'diagnostics:run'
    elif method == 'POST' and route in MODEL_ROUTES:
        scope = 'models:probe'
        # Test credentials can exercise saved configuration, never redirect keys
        # or supply a different model/endpoint. Ordinary user sessions are unchanged.
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, 'Expected a JSON object') from None
        allowed = {'kind'} if route.endswith('/models') else set()
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise HTTPException(403, 'Test probes use saved account model settings only')
    else:
        raise HTTPException(403, 'This operation is outside test token scope')
    try:
        result = await asyncio.to_thread(_consume, token, scope, route)
    except Exception:
        raise HTTPException(503, 'Test token registry temporarily unavailable') from None
    if not isinstance(result, dict) or result.get('status') not in ('ok', 'denied', 'limited'):
        raise HTTPException(401, 'Test token expired, revoked or invalid')
    if result['status'] == 'denied':
        raise HTTPException(403, 'Test token lacks this scope')
    if result['status'] == 'limited':
        raise HTTPException(429, 'Test token diagnostic budget exhausted')
    owner = result.get('owner_id')
    if not isinstance(owner, str) or not re.fullmatch(r'[0-9a-f-]{36}', owner):
        raise HTTPException(503, 'Invalid test token registry response')
    request.state.test_token = True
    logging.getLogger(__name__).info('Platform test access: scope=%s route=%s', scope, route)
    return User(id=owner, email='')
