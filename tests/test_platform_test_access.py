"""Scoped tokens cannot become ordinary sessions or mutate production content."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport
from api.auth import get_current_user

TOKEN = 'ptt_' + 'a'*43
OWNER = '800a86dd-a1b8-4322-8212-a3dcf13f8806'


def app_for(path, method='GET'):
    app = FastAPI()
    async def endpoint(user=Depends(get_current_user)):
        return {'owner':user.id}
    app.add_api_route(path, endpoint, methods=[method])
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize('path,method,body,allowed',[
    ('/api/podcasts','GET',None,True),
    ('/api/library','GET',None,True),
    ('/api/video-notes/tasks','GET',None,True),
    ('/api/settings/models','POST',{'kind':'summary'},True),
    ('/api/settings/models','POST',{'kind':'summary','llm_base_url':'https://evil.example'},False),
    ('/api/settings/test-llm','POST',{},True),
    ('/api/cookies/youtube/verify','POST',{},True),
    ('/api/cookies/bilibili/validate','GET',None,True),
    ('/api/settings','POST',{},False),
    ('/api/cookies/bilibili/qr/generate','GET',None,False),
    ('/api/maintenance/backup','GET',None,False),
    ('/api/video-notes/tasks','DELETE',None,False),
    ('/api/auth/me','GET',None,False),
    ('/api/future-route','GET',None,False),
])
async def test_exact_route_and_method_allowlist(path,method,body,allowed):
    with patch('api.auth.USE_SUPABASE',True), patch('api.test_access._consume', return_value={'status':'ok','owner_id':OWNER}) as consume, patch('api.auth.verify_jwt_token_async') as jwt:
        async with AsyncClient(transport=ASGITransport(app=app_for(path,method)),base_url='http://test') as client:
            response=await client.request(method,path,json=body,headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code == (200 if allowed else 403)
    if allowed: assert response.json()=={'owner':OWNER}
    else: consume.assert_not_called()
    jwt.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('result,status', [({'status':'invalid'},401), ({'status':'denied'},403), ({'status':'limited'},429), (None,401)])
async def test_revocation_expiry_scopes_and_quota_fail_closed(result,status):
    with patch('api.auth.USE_SUPABASE',True), patch('api.test_access._consume',return_value=result):
        async with AsyncClient(transport=ASGITransport(app=app_for('/api/stats')),base_url='http://test') as client:
            response=await client.get('/api/stats',headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code==status


@pytest.mark.asyncio
async def test_storage_outage_never_falls_back_to_jwt():
    with patch('api.auth.USE_SUPABASE',True), patch('api.test_access._consume',side_effect=RuntimeError('secret')), patch('api.auth.verify_jwt_token_async') as jwt:
        async with AsyncClient(transport=ASGITransport(app=app_for('/api/stats')),base_url='http://test') as client:
            response=await client.get('/api/stats',headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code==503 and 'secret' not in response.text
    jwt.assert_not_called()


@pytest.mark.asyncio
async def test_normal_session_still_uses_jwt():
    with patch('api.auth.USE_SUPABASE',True), patch('api.auth.verify_jwt_token_async',return_value={'sub':OWNER}), patch('api.test_access._consume') as consume:
        async with AsyncClient(transport=ASGITransport(app=app_for('/api/stats')),base_url='http://test') as client:
            response=await client.get('/api/stats',headers={'Authorization':'Bearer ordinary-session'})
    assert response.status_code==200
    consume.assert_not_called()


def test_token_file_is_private_and_matches_registered_digest(tmp_path, monkeypatch, capsys):
    import hashlib
    import json
    from scripts.create_platform_test_token import main
    path=tmp_path/'credential'
    monkeypatch.setattr('sys.argv',['create-token','--owner',OWNER,'--output',str(path)])
    main()
    metadata=json.loads(capsys.readouterr().out)
    token=path.read_text()
    assert token.startswith('ptt_') and len(token)==47
    assert path.stat().st_mode & 0o777 == 0o600
    assert metadata['token_digest']==hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(metadata)
    with pytest.raises(FileExistsError): main()


@pytest.mark.asyncio
@pytest.mark.parametrize('prefix,path,method,payload', [
    ('/api/podcasts','', 'GET', None),
    ('/api/library','', 'GET', None),
    ('/api/video-notes','/tasks', 'GET', None),
    ('/api/video-notes','/tasks/{task_id}/versions/{version_id}', 'GET', None),
    ('/api/settings','/models', 'POST', {'kind':'summary'}),
    ('/api/cookies','/youtube/verify', 'POST', {}),
])
async def test_included_router_prefixes_use_canonical_reviewed_paths(prefix,path,method,payload):
    from fastapi import APIRouter
    app=FastAPI()
    router=APIRouter()
    async def endpoint(user=Depends(get_current_user)):
        return {'owner':user.id}
    router.add_api_route(path,endpoint,methods=[method])
    app.include_router(router,prefix=prefix)
    target=(prefix+path).replace('{task_id}','fixture').replace('{version_id}','version')
    with patch('api.auth.USE_SUPABASE',True), patch('api.test_access._consume',return_value={'status':'ok','owner_id':OWNER}) as consume:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            response=await client.request(method,target,json=payload,headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code==200, response.text
    assert consume.call_args.args[2]==prefix+path


@pytest.mark.asyncio
async def test_future_static_route_does_not_inherit_dynamic_route_permission():
    from fastapi import APIRouter
    app=FastAPI()
    router=APIRouter()
    async def secret_endpoint(user=Depends(get_current_user)):
        raise AssertionError('Unreviewed route must not execute')
    router.add_api_route('/tasks/new-sensitive-endpoint',secret_endpoint,methods=['GET'])
    app.include_router(router,prefix='/api/video-notes')
    with patch('api.auth.USE_SUPABASE',True), patch('api.test_access._consume') as consume:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            response=await client.get('/api/video-notes/tasks/new-sensitive-endpoint',headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code==403
    consume.assert_not_called()
