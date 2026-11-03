"""Private child process: account cookie arrives over stdin, never argv or logs."""
import json
import sys
import shutil
from importlib.metadata import version, PackageNotFoundError
from urllib.parse import urlparse
from api.youtube_diagnostics import SAMPLE_BYTES, failure_category, video_url


def probe(url, cookie, emit):
    from video_downloader import YtdlpDownloader, account_youtube_dl
    from yt_dlp.networking import Request
    runtime = {'node': bool(shutil.which('node')), 'deno': bool(shutil.which('deno'))}
    for package in ('yt-dlp', 'yt-dlp-ejs'):
        try: runtime[package] = version(package)
        except PackageNotFoundError: runtime[package] = 'missing'
    report = {'youtube_probe': True, 'metadata_ok': False, 'download_ok': False,
              'sample_bytes': 0, 'stage': 'metadata', 'code': 'extractor_error', 'runtime': runtime}
    messages = []

    class QuietLogger:
        def debug(self, message): pass
        def warning(self, message): messages.append(str(message))
        def error(self, message): messages.append(str(message))

    emit(report)
    if not (runtime['node'] or runtime['deno']) or runtime['yt-dlp-ejs'] == 'missing':
        report['code'] = 'runtime_missing'; emit(report); return
    try:
        opts = YtdlpDownloader('youtube', cookie, use_saved_cookies=False)._get_base_opts()
        opts.update(logger=QuietLogger(), quiet=True, no_warnings=True, cachedir=False,
                    socket_timeout=10, retries=0, extractor_retries=0, format='bestaudio/best')
        with account_youtube_dl(opts) as downloader:
            info = downloader.extract_info(video_url(url), download=False)
            report.update(metadata_ok=bool(info and info.get('id')), stage='media')
            emit(report)
            formats = [f for f in (info or {}).get('formats', []) if f.get('protocol') == 'https' and f.get('acodec') not in (None, 'none') and f.get('url')]
            if not formats:
                report['code'] = 'no_media'
            else:
                selected = min(formats, key=lambda f: f.get('abr') or f.get('tbr') or 10000)
                target = urlparse(selected['url'])
                if target.scheme != 'https' or not target.hostname or not (target.hostname == 'googlevideo.com' or target.hostname.endswith('.googlevideo.com')):
                    report['code'] = 'no_media'
                else:
                    headers = {**info.get('http_headers', {}), **selected.get('http_headers', {}), 'Range': f'bytes=0-{SAMPLE_BYTES-1}'}
                    with downloader.urlopen(Request(selected['url'], headers=headers)) as response:
                        data = response.read(SAMPLE_BYTES)
                        content_type = response.headers.get('Content-Type', '').lower()
                        valid = bool(data) and ('audio/' in content_type or 'video/' in content_type or 'application/octet-stream' in content_type) and not data.lstrip().startswith((b'<', b'{'))
                        report.update(download_ok=valid, sample_bytes=len(data), code='ok' if valid else 'invalid_media', stage='complete')
        if any(failure_category(message) == 'cookie_expired' for message in messages):
            report.update(code='cookie_expired')
    except Exception as error:
        report['code'] = failure_category('\n'.join([*messages, str(error)]))
    emit(report)


if __name__ == '__main__':
    payload = json.loads(sys.stdin.read())
    probe(payload['url'], payload['cookie'], lambda report: print(json.dumps(report), flush=True))
