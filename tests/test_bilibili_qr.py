"""QR transport errors are bounded, actionable, and never expose login tokens."""
import asyncio
import time
from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi import HTTPException

from api.routers import cookies

BASE='https://passport.bilibili.com/x/passport-login/web/qrcode/'


@pytest.fixture(autouse=True)
def sessions():
    cookies._qr_sessions.clear()
    yield
    cookies._qr_sessions.clear()


@pytest.mark.asyncio
@respx.mock
async def test_valid_qr_response_returns_a_session_before_browser_deadline(client):
    route=respx.get(BASE+'generate').mock(return_value=httpx.Response(200,json={'code':0,'data':{'url':'https://passport.bilibili.com/h5-app/passport/login/scan?qrcode_key=fixture','qrcode_key':'fixture'}}))
    response=await client.get('/api/cookies/bilibili/qr/generate')
    assert response.status_code==200
    assert response.json()['qrcode_key']=='fixture'
    assert cookies._qr_sessions['fixture']['user_id']=='local'
    assert route.calls[0].request.extensions['timeout']['connect']<15
    assert route.calls[0].request.extensions['timeout']['read']<15


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body,needle',[
    (412,'blocked private-token','restricted'),(429,'private-token','restricted'),
    (200,'<html>verification private-token</html>','verification'),(503,'private-token','HTTP 503'),
])
@respx.mock
async def test_failed_upstream_qr_requests_explain_the_next_action_without_provider_content(client,status,body,needle):
    respx.get(BASE+'generate').mock(return_value=httpx.Response(status,text=body))
    response=await client.get('/api/cookies/bilibili/qr/generate')
    assert response.status_code==502
    assert needle in response.json()['detail'] and 'cookie import' in response.json()['detail']
    assert 'private-token' not in response.text
    assert cookies._qr_sessions=={}


@pytest.mark.asyncio
@pytest.mark.parametrize('data',[None,{}, {'url':'','qrcode_key':'fixture'}, {'url':'https://elsewhere.example/login','qrcode_key':'fixture'}])
@respx.mock
async def test_incomplete_qr_payload_does_not_crash_or_display_a_blank_code(client,data):
    respx.get(BASE+'generate').mock(return_value=httpx.Response(200,json={'code':0,'data':data}))
    response=await client.get('/api/cookies/bilibili/qr/generate')
    assert response.status_code==502
    assert 'incomplete QR data' in response.text
    assert cookies._qr_sessions=={}


@pytest.mark.asyncio
@respx.mock
async def test_timeout_is_a_clear_server_error_not_a_generic_browser_timeout(client):
    respx.get(BASE+'generate').mock(side_effect=httpx.ReadTimeout('private-token'))
    response=await client.get('/api/cookies/bilibili/qr/generate')
    assert response.status_code==504
    assert 'Bilibili QR service timed out' in response.text and 'private-token' not in response.text


@pytest.mark.asyncio
async def test_total_request_deadline_includes_a_stalled_response():
    async def slow(*args,**kwargs):await asyncio.sleep(.2)
    original=asyncio.timeout
    with patch.object(cookies.asyncio,'timeout',side_effect=lambda _:original(.01)),patch('httpx.AsyncClient.get',side_effect=slow):
        with pytest.raises(HTTPException) as error:
            await cookies._request_bilibili_qr('generate')
    assert error.value.status_code==504


@pytest.mark.asyncio
@respx.mock
async def test_poll_rejects_upstream_verification_instead_of_waiting_forever(client):
    cookies._qr_sessions['fixture']={'created_at':time.time(),'user_id':'local'}
    respx.get(BASE+'poll').mock(return_value=httpx.Response(200,json={'code':-412,'message':'private-token'}))
    response=await client.get('/api/cookies/bilibili/qr/poll?qrcode_key=fixture')
    assert response.status_code==502 and 'cookie import' in response.text
    assert 'private-token' not in response.text
