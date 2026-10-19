"""Recreate the reported note's missing frames without changing saved notes.

The runner reads existing server credentials in memory. Output is restricted to
fixed result labels and counts; no source URLs, cookies, notes, or credentials.
"""
import contextlib
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TASK_ID = 'bc2c988b-2b4'
PODCAST_ID = '62382c1103bea1ebfffa1c00'


def frame_references(markdown: str) -> dict[str, int]:
    pattern = r'(?<![A-Za-z0-9_.-])' + re.escape(TASK_ID) + r'_(\d{1,4})-(\d{2})\.jpg'
    return {match.group(0): int(match.group(1)) * 60 + int(match.group(2))
            for match in re.finditer(pattern, markdown) if int(match.group(2)) < 60}


def repair() -> dict:
    from api.supabase_client import get_supabase_admin_client
    from cookie_manager import get_cookie_manager
    from video_downloader import get_downloader
    from screenshot_extractor import extract_screenshot
    database = get_supabase_admin_client()
    owner = database.table('podcasts').select('user_id').eq('pid', PODCAST_ID).limit(1).execute().data[0]['user_id']

    def read_note():
        return database.table('video_tasks').select('id,url,platform,markdown').eq('id', TASK_ID).eq('user_id', owner).execute().data[0]

    def versions_digest():
        rows = database.table('video_task_versions').select('id,content').eq('task_id', TASK_ID).order('id').execute().data
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

    note = read_note()
    original = note['markdown']
    versions_before = versions_digest()
    references = frame_references(original)
    if not references or len(references) > 40:
        raise ValueError('Unexpected screenshot inventory')

    def present(name):
        try:
            content = database.storage.from_('screenshots').download(name)
            return content.startswith(b'\xff\xd8') and len(content) > 100
        except Exception:
            return False

    missing = {name: timestamp for name, timestamp in references.items() if not present(name)}
    if missing:
        source = urlsplit(note['url'])
        if note['platform'] != 'youtube' or source.scheme != 'https' or source.hostname not in {'www.youtube.com', 'youtube.com', 'youtu.be', 'm.youtube.com'}:
            raise ValueError('Unexpected source platform')
        downloader = get_downloader('youtube', get_cookie_manager(owner).get_cookie('youtube'))
        base_options = downloader._get_base_opts
        downloader._get_base_opts = lambda: {**base_options(), 'retries': 1, 'fragment_retries': 1,
                                           'socket_timeout': 15, 'max_filesize': 250 * 1024 * 1024}
        path = downloader.download_video(note['url'], TASK_ID, video_quality='360')
        if not path:
            raise RuntimeError('Source unavailable')
        for name, timestamp in missing.items():
            if extract_screenshot(str(path), timestamp, TASK_ID) != name:
                raise RuntimeError('Frame extraction failed')
    verified = sum(present(name) for name in references)
    report = {'repair': 'reported_screenshots', 'expected': len(references), 'restored': len(missing),
              'verified': verified, 'note_unchanged': int(read_note()['markdown'] == original),
              'versions_unchanged': int(versions_digest() == versions_before)}
    report['passed'] = int(verified == len(references) and report['note_unchanged'] and report['versions_unchanged'])
    return report


def run_child():
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = repair()
    except Exception as error:
        code = getattr(error, 'error_code', '')
        result = {'repair': 'reported_screenshots', 'passed': 0,
                  'source_auth_required': int(code in {'AUTH_REQUIRED', 'LOGIN_REQUIRED', 'COOKIE_EXPIRED', 'AGE_RESTRICTED', 'BOT_DETECTED'}),
                  'download_failed': int(type(error).__name__ == 'VideoDownloadError')}
        if type(error).__name__ in {'ImportError', 'ModuleNotFoundError', 'IndexError', 'ValueError', 'RuntimeError', 'APIError', 'StorageApiError', 'VideoDownloadError'}:
            result['error_type'] = type(error).__name__
    print(json.dumps(result))
    return 0 if result.get('passed') else 1


def run():
    from scripts.diagnose_deployment import oci_json
    instance = oci_json(['container-instances', 'container-instance', 'get', '--container-instance-id', os.environ['CONTAINER_INSTANCE_ID']],
                        'data.containers[*]."container-id"')
    if not instance:
        raise RuntimeError('Deployment unavailable')
    settings = oci_json(['container-instances', 'container', 'get', '--container-id', instance[0]], 'data."environment-variables"')
    bindings = {key: value for key, value in settings.items() if key.startswith('SUPABASE_')}
    with tempfile.TemporaryDirectory() as directory:
        environment = {**os.environ, 'PYTHONPATH': '.', **bindings,
                       'XYZ_DATA_DIR': directory, 'SUPABASE_STORAGE_ENABLED': 'true', 'WHISPER_MODE': 'api'}
        try:
            result = subprocess.run([sys.executable, __file__, '--child'], env=environment,
                                    capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            print(json.dumps({'repair': 'reported_screenshots', 'passed': 0, 'source_timeout': 1}))
            return 1
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('repair') != 'reported_screenshots':
            continue
        safe = {'repair': 'reported_screenshots'}
        safe.update({key: row[key] for key in ('expected', 'restored', 'verified', 'note_unchanged', 'versions_unchanged', 'passed', 'source_auth_required', 'download_failed')
                     if type(row.get(key)) is int and 0 <= row[key] <= 100})
        if row.get('error_type') in {'ImportError', 'ModuleNotFoundError', 'IndexError', 'ValueError', 'RuntimeError', 'APIError', 'StorageApiError', 'VideoDownloadError'}:
            safe['error_type'] = row['error_type']
        print(json.dumps(safe))
        return 0 if safe.get('passed') == 1 else 1
    print(json.dumps({'repair': 'reported_screenshots', 'passed': 0}))
    return 1


if __name__ == '__main__':
    sys.exit(run_child() if '--child' in sys.argv else run())
