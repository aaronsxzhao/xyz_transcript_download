import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from api import youtube_diagnostics as diagnostic
from api import youtube_diagnostic_worker as worker
from api.routers import cookies as routes
import video_downloader as downloads

COOKIE = '# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\taccount-secret\n'


def test_cookie_files_are_private_independent_and_removed_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, 'DATA_DIR', tmp_path)
    first = downloads.YtdlpDownloader('youtube', COOKIE, False)._get_base_opts()
    second = downloads.YtdlpDownloader('youtube', COOKIE.replace('account-secret','other-secret'), False)._get_base_opts()
    assert not list(tmp_path.iterdir())
    with downloads.account_youtube_dl(first) as one:
        path_one = Path(one.params['cookiefile'])
        assert path_one.stat().st_mode & 0o777 == 0o600
        with pytest.raises(RuntimeError):
            with downloads.account_youtube_dl(second) as two:
                path_two = Path(two.params['cookiefile'])
                assert path_one != path_two
                assert 'account-secret' in path_one.read_text() and 'other-secret' in path_two.read_text()
                assert '_account_cookies' not in one.params
                raise RuntimeError('interrupted')
        assert not path_two.exists()
        assert path_one.exists()
    assert not path_one.exists()
    assert first['_account_cookies'] == COOKIE


@pytest.mark.parametrize('url', ['http://youtube.com/watch?v=BaW_jenozKc','https://youtube.com.evil.test/watch?v=BaW_jenozKc','https://youtube.com@127.0.0.1/watch?v=BaW_jenozKc','https://www.youtube.com:443/watch?v=BaW_jenozKc','file:///etc/passwd','https://youtube.com/playlist?list=x'])
def test_verification_rejects_non_video_or_non_youtube_destinations(url):
    with pytest.raises(ValueError): diagnostic.video_url(url)


@pytest.mark.parametrize('url', ['https://youtu.be/BaW_jenozKc?t=4','https://www.youtube.com/shorts/BaW_jenozKc','https://m.youtube.com/watch?v=BaW_jenozKc&list=ignored'])
def test_verification_canonicalizes_to_one_video(url):
    assert diagnostic.video_url(url) == diagnostic.DEFAULT_VIDEO


@pytest.mark.parametrize('error,code', [('cookies are no longer valid','cookie_expired'),('Sign in to confirm you are not a bot','sign_in_or_bot_challenge'),('HTTP Error 429','rate_limited'),('HTTP Error 403','forbidden'),('certificate verify failed','network_error')])
def test_classification_does_not_echo_provider_details(error,code):
    assert diagnostic.failure_category(error+' secret-token') == code
    assert 'secret-token' not in diagnostic.MESSAGES[code]


def test_owner_cookie_is_used_without_exposure(monkeypatch, caplog):
    manager=Mock();manager.get_cookie.return_value=COOKIE
    get=Mock(return_value=manager)
    monkeypatch.setattr('cookie_manager.get_cookie_manager',get)
    probe=Mock(return_value={'code':'ok','metadata_ok':True,'download_ok':True,'sample_bytes':65536,'stage':'complete'})
    monkeypatch.setattr(diagnostic,'run_probe',probe)
    report=diagnostic.verify_saved_cookie('owner',diagnostic.DEFAULT_VIDEO)
    get.assert_called_once_with('owner')
    manager.get_cookie.assert_called_once_with('youtube',strict=True)
    assert probe.call_args.args==(diagnostic.DEFAULT_VIDEO,COOKIE)
    assert report['download_ok'] and report['reference']
    assert 'account-secret' not in json.dumps(report)+caplog.text


def test_storage_failure_is_not_reported_as_missing_cookies(monkeypatch):
    manager=Mock();manager.get_cookie.side_effect=RuntimeError('private connection detail')
    monkeypatch.setattr('cookie_manager.get_cookie_manager',lambda _:manager)
    report=diagnostic.verify_saved_cookie('owner',diagnostic.DEFAULT_VIDEO)
    assert report['code']=='storage_unavailable'
    assert 'private connection' not in json.dumps(report)


def test_deadline_kills_process_group_and_cleans_cookie_directory(monkeypatch):
    process=Mock(pid=12345)
    def communicate(payload=None,timeout=None):
        if payload:
            assert json.loads(payload)['cookie']==COOKIE
            raise diagnostic.subprocess.TimeoutExpired('probe',timeout)
        return json.dumps({'youtube_probe':True,'stage':'media','metadata_ok':True}),None
    process.communicate.side_effect=communicate
    popen=Mock(return_value=process);kill=Mock()
    monkeypatch.setattr(diagnostic.subprocess,'Popen',popen)
    monkeypatch.setattr(diagnostic.os,'killpg',kill)
    report=diagnostic.run_probe(diagnostic.DEFAULT_VIDEO,COOKIE)
    assert report['code']=='timeout' and report['metadata_ok'] and not report['download_ok']
    kill.assert_called_once_with(12345,diagnostic.signal.SIGKILL)
    assert not Path(popen.call_args.kwargs['env']['TMPDIR']).exists()
    assert 'account-secret' not in str(popen.call_args.args)


@pytest.fixture
def fake_youtube(monkeypatch):
    response=Mock()
    response.headers={'Content-Type':'audio/webm'}
    response.read.return_value=b'\x1aE\xdf\xa3' + b'x'*100
    response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
    ydl=Mock()
    ydl.extract_info.return_value={'id':'test','formats':[{'protocol':'https','url':'https://rr1.googlevideo.com/videoplayback?secret=hidden','acodec':'opus','abr':64}]}
    ydl.urlopen.return_value=response
    context=Mock();context.__enter__=Mock(return_value=ydl);context.__exit__=Mock(return_value=False)
    monkeypatch.setattr(downloads,'account_youtube_dl',lambda opts:context)
    monkeypatch.setattr(worker.shutil,'which',lambda _: '/synthetic/runtime')
    monkeypatch.setattr(worker,'version',lambda _: 'test-version')
    return ydl,response


def test_probe_reads_bounded_media_and_does_not_echo_urls(fake_youtube):
    ydl,response=fake_youtube;reports=[]
    worker.probe(diagnostic.DEFAULT_VIDEO,COOKIE,lambda row:reports.append(dict(row)))
    assert reports[-1]['download_ok']
    response.read.assert_called_once_with(65536)
    assert ydl.urlopen.call_args.args[0].headers['Range']=='bytes=0-65535'
    assert 'secret=hidden' not in json.dumps(reports) and 'account-secret' not in json.dumps(reports)


def test_html_error_page_is_not_download_success(fake_youtube):
    _,response=fake_youtube;response.headers={'Content-Type':'text/html'};response.read.return_value=b'<html>denied</html>'
    reports=[];worker.probe(diagnostic.DEFAULT_VIDEO,COOKIE,lambda row:reports.append(dict(row)))
    assert reports[-1]['code']=='invalid_media' and not reports[-1]['download_ok']


def test_untrusted_media_host_is_not_requested(fake_youtube):
    ydl,_=fake_youtube;ydl.extract_info.return_value['formats'][0]['url']='http://127.0.0.1/private'
    reports=[];worker.probe(diagnostic.DEFAULT_VIDEO,COOKIE,lambda row:reports.append(dict(row)))
    ydl.urlopen.assert_not_called()
    assert reports[-1]['code']=='no_media'


@pytest.mark.asyncio
async def test_endpoint_uses_session_owner_and_throttles_repeated_calls(client,monkeypatch):
    routes._youtube_probe_accounts.clear()
    probe=Mock(return_value={'code':'ok'})
    monkeypatch.setattr(diagnostic,'verify_saved_cookie',probe)
    response=await client.post('/api/cookies/youtube/verify',json={'video_url':diagnostic.DEFAULT_VIDEO})
    assert response.status_code==200
    probe.assert_called_once_with('local',diagnostic.DEFAULT_VIDEO)
    assert (await client.post('/api/cookies/youtube/verify',json={})).status_code==429
    assert (await client.post('/api/cookies/youtube/verify',json={'user_id':'other'})).status_code==422
    routes._youtube_probe_accounts.clear()


@pytest.mark.asyncio
async def test_cloud_verification_requires_login(client,monkeypatch):
    monkeypatch.setattr('api.auth.USE_SUPABASE',True)
    probe=Mock();monkeypatch.setattr(diagnostic,'verify_saved_cookie',probe)
    response=await client.post('/api/cookies/youtube/verify',json={})
    assert response.status_code==401
    probe.assert_not_called()


def test_strict_cookie_read_propagates_storage_failure_without_logging_secrets(caplog):
    from cookie_manager import _SupabaseCookieManager
    manager=object.__new__(_SupabaseCookieManager);manager.user_id='owner';manager.client=Mock()
    manager.client.table.side_effect=RuntimeError('secret-database-detail')
    with pytest.raises(RuntimeError,match='storage unavailable'):manager.get_cookie('youtube',strict=True)
    assert 'secret-database-detail' not in caplog.text


@pytest.mark.parametrize('response', [None, SimpleNamespace(data=None), SimpleNamespace(data={})])
def test_absent_cookie_row_is_missing_not_storage_failure(monkeypatch, response):
    from cookie_manager import _SupabaseCookieManager
    manager = object.__new__(_SupabaseCookieManager)
    manager.user_id = 'owner'
    manager.client = Mock()
    query = manager.client.table.return_value.select.return_value
    query.eq.return_value = query
    query.maybe_single.return_value.execute.return_value = response
    monkeypatch.setattr('cookie_manager.get_cookie_manager', lambda _: manager)
    probe = Mock()
    monkeypatch.setattr(diagnostic, 'run_probe', probe)
    report = diagnostic.verify_saved_cookie('owner', diagnostic.DEFAULT_VIDEO)
    assert report['code'] == 'missing_cookie'
    assert report['cookie_present'] is False
    probe.assert_not_called()
    assert query.eq.call_args_list == [call('user_id', 'owner'), call('platform', 'youtube')]
