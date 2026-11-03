"""Bounded YouTube verification in the normal account/runtime trust boundary."""
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

DEFAULT_VIDEO = 'https://www.youtube.com/watch?v=BaW_jenozKc'
MAX_SECONDS = 40
SAMPLE_BYTES = 65536

MESSAGES = {
    'ok': 'Video information and a media sample were downloaded successfully from this server.',
    'missing_cookie': 'No YouTube cookie is saved. Import a fresh cookies.txt file, then verify again.',
    'invalid_cookie': 'The saved cookie file could not be loaded. Export a fresh Netscape cookies.txt file and import it again.',
    'cookie_expired': 'YouTube rejected the saved session. Export fresh cookies from a logged-in browser and import them again.',
    'sign_in_or_bot_challenge': 'YouTube requires sign-in or a bot check from this server. Refresh the cookies; if it persists, the server network may be restricted.',
    'rate_limited': 'YouTube is rate-limiting this server. Wait before trying again.',
    'forbidden': 'YouTube refused this request. Refresh cookies and retry; the server IP or media access token may also be restricted.',
    'unavailable': 'This video is unavailable to the saved session. Try another video to distinguish a video restriction from a connection problem.',
    'runtime_missing': 'The server is missing a supported JavaScript runtime or YouTube challenge solver.',
    'timeout': 'Verification exceeded its time limit. Check the server connection and retry later.',
    'network_error': 'The server could not connect to YouTube. Check DNS, TLS and outbound connectivity.',
    'no_media': 'Video information was read, but no direct downloadable audio/video format was available.',
    'invalid_media': 'The media server returned an empty response or an error page instead of media.',
    'storage_unavailable': 'Saved account credentials could not be read. Retry after account storage recovers.',
    'extractor_error': 'YouTube extraction failed. Share the diagnostic reference to inspect the server runtime.',
}


def video_url(value):
    value = (value or DEFAULT_VIDEO).strip()
    try:
        parsed = urlparse(value)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port:
            raise ValueError()
        if parsed.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'}:
            ident = parse_qs(parsed.query).get('v', [''])[0] if parsed.path == '/watch' else parsed.path.split('/')[2] if re.fullmatch(r'/(?:shorts|live|embed)/[^/]+/?', parsed.path) else ''
        elif parsed.hostname == 'youtu.be':
            ident = parsed.path.strip('/')
        else:
            raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', ident): raise ValueError()
        return 'https://www.youtube.com/watch?v=' + ident
    except (ValueError, IndexError):
        raise ValueError('Enter a valid HTTPS YouTube video URL (not a channel or playlist).') from None


def failure_category(message):
    value = message.lower()
    for phrases, category in [
        (('failed to load cookies', 'cookies file must be netscape'), 'invalid_cookie'),
        (('cookies are no longer valid', 'cookies have expired', 'cookie has expired'), 'cookie_expired'),
        (('sign in to confirm', 'sign in to verify', 'not a bot'), 'sign_in_or_bot_challenge'),
        (('429', 'too many requests'), 'rate_limited'),
        (('403', 'forbidden'), 'forbidden'),
        (('video unavailable', 'private video', 'members-only', 'not available in your country'), 'unavailable'),
        (('no supported javascript', 'challenge solver', 'js runtime'), 'runtime_missing'),
        (('timed out', 'timeout'), 'timeout'),
        (('connection', 'name resolution', 'certificate', 'network is unreachable'), 'network_error'),
    ]:
        if any(phrase in value for phrase in phrases): return category
    return 'extractor_error'


def verify_saved_cookie(owner, url):
    """Read only this account's saved cookie; never return or log its value."""
    from cookie_manager import get_cookie_manager
    started = time.monotonic()
    report = {'reference': str(uuid.uuid4()), 'checked_at': datetime.now(timezone.utc).isoformat(),
              'revision': os.environ.get('APP_REVISION', 'unknown'), 'cookie_present': False,
              'metadata_ok': False, 'download_ok': False, 'sample_bytes': 0,
              'stage': 'cookie', 'code': 'extractor_error', 'runtime': {}}
    try:
        cookie = get_cookie_manager(owner).get_cookie('youtube', strict=True)
    except Exception:
        cookie = None
        report['code'] = 'storage_unavailable'
    if cookie is not None:
        report['cookie_present'] = bool(cookie)
        if not cookie:
            report['code'] = 'missing_cookie'
        else:
            try:
                report.update(run_probe(url, cookie, timeout=max(1, min(MAX_SECONDS, 45 - (time.monotonic() - started)))))
            except Exception:
                report.update(code='extractor_error', stage='startup')
    report['elapsed_seconds'] = round(time.monotonic() - started, 2)
    report['message'] = MESSAGES.get(report['code'], MESSAGES['extractor_error'])
    # Whitelisted summary only: no user URL, title, cookie, exception, or media URL.
    from logger import get_logger
    get_logger('youtube_diagnostics').info('YouTube verification %s', json.dumps(report))
    return report


def run_probe(url, cookie, *, timeout=MAX_SECONDS):
    """Kill the probe process group at the deadline, including any JS children."""
    with tempfile.TemporaryDirectory(prefix='youtube-verify-') as directory:
        process = subprocess.Popen([sys.executable, '-m', 'api.youtube_diagnostic_worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, start_new_session=True, env={**os.environ, 'TMPDIR': directory})
        try:
            stdout, _ = process.communicate(json.dumps({'url': url, 'cookie': cookie}), timeout=timeout)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            stdout, _ = process.communicate()
            result = _last_result(stdout)
            result.update(code='timeout', download_ok=False)
            return result
        result = _last_result(stdout)
        if process.returncode: result.update(code='extractor_error', download_ok=False)
        return result


def _last_result(output):
    result = {'stage': 'startup', 'code': 'extractor_error'}
    for line in output.splitlines():
        try: row = json.loads(line)
        except ValueError: continue
        if isinstance(row, dict) and row.get('youtube_probe') is True:
            result = {key: row[key] for key in ('stage', 'code', 'metadata_ok', 'download_ok', 'sample_bytes', 'runtime') if key in row}
    return result
