"""Exercise yt-dlp transport selection and actual HTTP downloads without a CDN."""
import threading
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from yt_dlp.downloader import get_suitable_downloader
from yt_dlp.downloader.dash import DashSegmentsFD
from yt_dlp.downloader.hls import HlsFD
from yt_dlp.downloader.http import HttpFD

import video_downloader as module


@pytest.mark.parametrize('platform', ['bilibili', 'youtube'])
@pytest.mark.parametrize('protocol,expected', [
    ('https', HttpFD), ('m3u8_native', HlsFD), ('http_dash_segments', DashSegmentsFD),
])
def test_metadata_and_subtitle_options_stay_native(monkeypatch, platform, protocol, expected):
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/synthetic/bin/' + name)
    opts = module.YtdlpDownloader(platform, use_saved_cookies=False)._get_base_opts()
    info = {'url': 'https://media.example.test/file', 'protocol': protocol}
    assert get_suitable_downloader(info, opts) is expected
    assert opts['concurrent_fragment_downloads'] == 8


@pytest.mark.parametrize('platform,aria_success', [('bilibili', False), ('youtube', False), ('youtube', True)])
def test_real_transfer_prefers_native_on_bilibili_and_recovers_from_broken_aria2(monkeypatch, tmp_path, platform, aria_success):
    # This is a byte transport fixture, not a model/media decoding test.
    content = b'\x00\x00\x00\x18ftypmp42' + bytes(range(256)) * 1024
    requests = []

    class Media(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Media)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(module, 'VIDEO_DIR', tmp_path)
    # Production URL checks reject loopback; only this controlled fixture skips
    # normalization. Public-source validation is covered separately.
    monkeypatch.setattr(module, 'normalize_video_url', lambda url, platform: url)
    executable = tmp_path / 'bin' / 'aria2c'
    executable.parent.mkdir()
    marker = tmp_path / 'aria-attempts'
    executable.write_text(f'''#!{sys.executable}
import sys
from pathlib import Path
if '-v' in sys.argv:
    print('aria2 version 1.0')
    sys.exit(0)
Path({str(marker)!r}).write_text('attempted')
directory = Path(sys.argv[sys.argv.index('--dir') + 1])
name = sys.argv[sys.argv.index('--out') + 1]
target = directory / name
if {aria_success!r}:
    import urllib.request
    with urllib.request.urlopen(sys.argv[-1]) as response:
        target.write_bytes(response.read())
    sys.exit(0)
target.write_bytes(b'broken segmented bytes')
Path(str(target) + '.aria2').write_bytes(b'control')
sys.exit(22)
''')
    executable.chmod(0o755)
    monkeypatch.setenv('PATH', str(executable.parent) + os.pathsep + os.environ.get('PATH', ''))
    # An old segmented download can contain holes despite its apparent size.
    (tmp_path / 'native.mp4.part').write_bytes(b'broken segmented bytes')
    (tmp_path / 'native.mp4.part.aria2').write_bytes(b'control')
    progress = []
    try:
        downloader = module.YtdlpDownloader(platform, use_saved_cookies=False)
        path = downloader.download_video(f'http://127.0.0.1:{server.server_port}/source.mp4', 'native',
                                         progress_callback=lambda pct, message: progress.append((pct, message)))
        assert path == tmp_path / 'native.mp4'
        assert path.read_bytes() == content
        assert not (tmp_path / 'native.mp4.part.aria2').exists()
        assert requests and all(path == '/source.mp4' for path in requests)
        assert progress and progress[-1][0] == 1
        assert marker.exists() == (platform == 'youtube')
        assert not (tmp_path / '.native.aria2').exists()
        if platform == 'youtube':
            assert downloader._aria2_failed == (not aria_success)
            assert any('switching to native' in message for _, message in progress) == (not aria_success)
    finally:
        server.shutdown()
        server.server_close()


def test_cleanup_only_removes_this_tasks_aria2_parts(tmp_path):
    files = ['retry.faudio.m4a.part', 'retry.faudio.m4a.part.aria2',
             'retry.fvideo.mp4.part', 'retry.mp3',
             'another.mp4.part', 'another.mp4.part.aria2']
    for name in files:
        (tmp_path / name).write_bytes(b'keep')
    module.YtdlpDownloader._discard_aria2_partials(tmp_path, 'retry')
    assert {path.name for path in tmp_path.iterdir()} == set(files[2:])


def fake_downloads(monkeypatch, tmp_path, failures):
    """Keep extraction/postprocessing mocked; exercise the public media methods."""
    calls = []
    info = {'title': 'Synthetic source', 'duration': 1}
    monkeypatch.setattr(module, 'VIDEO_DIR', tmp_path)
    monkeypatch.setattr(module, 'VIDEO_AUDIO_DIR', tmp_path)
    monkeypatch.setattr(module, 'normalize_video_url', lambda url, platform: url)
    real_which = module.shutil.which
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/synthetic/aria2c' if name == 'aria2c' else real_which(name))

    class Download:
        def __init__(self, opts): self.opts = opts
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def perform(self, extension):
            calls.append(self.opts)
            failure = failures.pop(0) if failures else None
            if failure:
                raise failure
            Path(self.opts['outtmpl'].replace('%(ext)s', extension)).write_bytes(b'complete')
        def extract_info(self, *_args, **_kwargs):
            self.perform('mp3')
            return info
        def download(self, *_args): self.perform('mp4')
    monkeypatch.setattr(module.yt_dlp, 'YoutubeDL', Download)
    return calls, info


@pytest.mark.parametrize('audio', [False, True])
def test_aria2_recovers_to_native_once_and_stays_disabled_for_next_phase(monkeypatch, tmp_path, audio):
    calls, info = fake_downloads(monkeypatch, tmp_path, [module.yt_dlp.utils.DownloadError('ERROR: aria2c exited with code 22')])
    downloader = module.YtdlpDownloader('youtube', use_saved_cookies=False)
    method = downloader.download_audio if audio else downloader.download_video
    assert method('https://source.example/video', 'first').read_bytes() == b'complete'
    assert [opts['external_downloader'] for opts in calls] == [
        {'http': 'aria2c', 'default': 'native'}, {'default': 'native'}]
    for key in ['format', 'progress_hooks', 'postprocessors']:
        assert calls[0].get(key) == calls[1].get(key)
    assert calls[0]['external_downloader_args']['aria2c'][:4] == ['-x', '4', '-s', '4']
    assert [opts['retries'] for opts in calls] == [1, 3]
    assert all(opts['socket_timeout'] == 20 for opts in calls)
    second_phase = downloader.download_video if audio else downloader.download_audio
    assert second_phase('https://source.example/video', 'second').read_bytes() == b'complete'
    assert calls[-1]['external_downloader'] == {'default': 'native'}
    if audio:
        assert downloader._last_info == info


@pytest.mark.parametrize('audio', [False, True])
def test_native_transfer_failure_can_use_aria2_without_reusing_native_partial(monkeypatch, tmp_path, audio):
    error = module.yt_dlp.utils.DownloadError('Unable to download video data: Connection reset by peer')
    calls, _ = fake_downloads(monkeypatch, tmp_path, [error])
    (tmp_path / 'retry.mp4.part').write_bytes(b'native contiguous prefix')
    downloader = module.YtdlpDownloader('bilibili', use_saved_cookies=False)
    method = downloader.download_audio if audio else downloader.download_video
    assert method('https://source.example/video', 'retry').read_bytes() == b'complete'
    assert calls[0]['external_downloader'] == {'default': 'native'}
    assert calls[1]['external_downloader'] == {'http': 'aria2c', 'default': 'native'}
    assert Path(calls[1]['outtmpl']).parent == tmp_path / '.retry.aria2'
    assert (tmp_path / 'retry.mp4.part').read_bytes() == b'native contiguous prefix'
    assert not (tmp_path / '.retry.aria2').exists()


@pytest.mark.parametrize('message', [
    'HTTP Error 403: Sign in', 'HTTP Error 429: Too many requests',
    'Private video', 'Video unavailable', 'Requested format is not available',
    'Postprocessing: ffmpeg failed', 'Unable to download webpage: Connection reset',
    'Unable to download fragment: Connection reset',
])
@pytest.mark.parametrize('platform', ['bilibili', 'youtube'])
def test_source_extraction_and_postprocessing_errors_do_not_switch(monkeypatch, tmp_path, message, platform):
    calls, _ = fake_downloads(monkeypatch, tmp_path, [module.yt_dlp.utils.DownloadError(message)])
    with pytest.raises(module.VideoDownloadError):
        module.YtdlpDownloader(platform, use_saved_cookies=False).download_video('https://source.example/video', 'hard')
    assert len(calls) == 1
    assert not (tmp_path / '.hard.aria2').exists()


@pytest.mark.parametrize('wrapped', [False, True])
@pytest.mark.parametrize('platform', ['bilibili', 'youtube'])
def test_cancelled_task_does_not_switch_or_become_download_failed(monkeypatch, tmp_path, wrapped, platform):
    from summary_errors import ProcessingCancelledError
    cancelled = ProcessingCancelledError('Stopped')
    error = module.yt_dlp.utils.DownloadError('Unable to download video data: timed out',
        exc_info=(type(cancelled), cancelled, None)) if wrapped else cancelled
    calls, _ = fake_downloads(monkeypatch, tmp_path, [error])
    with pytest.raises(ProcessingCancelledError):
        module.YtdlpDownloader(platform, use_saved_cookies=False).download_audio('https://source.example/video', 'stop')
    assert len(calls) == 1
    assert not (tmp_path / '.stop.aria2').exists()


def test_two_failed_transports_stop_and_report_both(monkeypatch, tmp_path):
    errors = [module.yt_dlp.utils.DownloadError('Unable to download video data: timed out'),
              module.yt_dlp.utils.DownloadError('aria2c exited with code 22')]
    calls, _ = fake_downloads(monkeypatch, tmp_path, errors)
    with pytest.raises(module.VideoDownloadError, match='Native download failed:.*aria2c fallback also failed'):
        module.YtdlpDownloader('bilibili', use_saved_cookies=False).download_video('https://source.example/video', 'both')
    assert len(calls) == 2
    assert not (tmp_path / '.both.aria2').exists()


def test_fallback_reports_real_source_access_error_instead_of_aria_exit(monkeypatch, tmp_path):
    errors = [module.yt_dlp.utils.DownloadError('aria2c exited with code 22'),
              module.yt_dlp.utils.DownloadError('HTTP Error 403: Sign in to view')]
    calls, _ = fake_downloads(monkeypatch, tmp_path, errors)
    with pytest.raises(module.VideoDownloadError) as caught:
        module.YtdlpDownloader('youtube', use_saved_cookies=False).download_video('https://source.example/video', 'restricted')
    assert caught.value.error_code == 'LOGIN_REQUIRED'
    assert len(calls) == 2


@pytest.mark.parametrize('protocol,expected', [('m3u8_native', HlsFD), ('http_dash_segments', DashSegmentsFD)])
def test_acceleration_config_keeps_fragment_protocols_native(monkeypatch, tmp_path, protocol, expected):
    calls, _ = fake_downloads(monkeypatch, tmp_path, [])
    module.YtdlpDownloader('youtube', use_saved_cookies=False).download_video('https://source.example/video', 'streams')
    assert get_suitable_downloader({'url':'https://media.example/video', 'protocol':protocol}, calls[0]) is expected
