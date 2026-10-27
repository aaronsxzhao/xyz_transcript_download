"""Exercise yt-dlp transport selection and actual HTTP downloads without a CDN."""
import threading
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
def test_installed_aria2_does_not_change_source_transport(monkeypatch, platform, protocol, expected):
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/synthetic/bin/' + name)
    opts = module.YtdlpDownloader(platform, use_saved_cookies=False)._get_base_opts()
    info = {'url': 'https://media.example.test/file', 'protocol': protocol}
    assert get_suitable_downloader(info, opts) is expected
    assert opts['concurrent_fragment_downloads'] == 8


def test_native_download_transfers_bytes_and_reports_progress_even_with_broken_aria2(monkeypatch, tmp_path):
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
    real_which = module.shutil.which
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/synthetic/broken/aria2c' if name == 'aria2c' else real_which(name))
    # An old segmented download can contain holes despite its apparent size.
    (tmp_path / 'native.mp4.part').write_bytes(b'broken segmented bytes')
    (tmp_path / 'native.mp4.part.aria2').write_bytes(b'control')
    progress = []
    try:
        downloader = module.YtdlpDownloader('bilibili', use_saved_cookies=False)
        path = downloader.download_video(f'http://127.0.0.1:{server.server_port}/source.mp4', 'native',
                                         progress_callback=lambda pct, message: progress.append((pct, message)))
        assert path == tmp_path / 'native.mp4'
        assert path.read_bytes() == content
        assert not (tmp_path / 'native.mp4.part.aria2').exists()
        assert requests and all(path == '/source.mp4' for path in requests)
        assert progress and progress[-1][0] == 1
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
