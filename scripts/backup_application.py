"""Private, verified application-data and generated-media backups.

Excludes credentials and auth sessions. Never uploads private data as CI artifacts.
"""
import contextlib
import io
import json
import logging
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TABLES = ('podcasts', 'episodes', 'transcripts', 'summaries', 'summary_key_points',
          'transcript_segments', 'video_tasks', 'video_task_versions', 'user_settings', 'processing_jobs')
BUCKET = 'application-backups'


def rows(client, table):
    offset = 0
    while True:
        page = client.table(table).select('*').order('user_id' if table == 'user_settings' else 'id').range(offset, offset + 499).execute().data
        if not isinstance(page, list):
            raise RuntimeError('Incomplete database snapshot')
        yield from page
        if len(page) < 500:
            break
        offset += len(page)


def backup():
    from api.supabase_client import get_supabase_admin_client
    from screenshot_extractor import _iter_bucket_objects
    client = get_supabase_admin_client()
    try:
        bucket = client.storage.get_bucket(BUCKET)
        if getattr(bucket, 'public', False):
            raise RuntimeError('Backup bucket must be private')
    except Exception:
        client.storage.create_bucket(BUCKET, options={'public': False, 'file_size_limit': 50 * 1024 * 1024})
    stream = io.BytesIO()
    counts = {}; media = 0
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for table in TABLES:
            data = list(rows(client, table))
            counts[table] = len(data)
            archive.writestr(f'database/{table}.json', json.dumps(data, ensure_ascii=False))
        for bucket in ('screenshots', 'thumbnails'):
            for item in _iter_bucket_objects(client, bucket):
                name = item.get('name', '')
                if not name or '/' in name:
                    continue
                archive.writestr(f'media/{bucket}/{name}', client.storage.from_(bucket).download(name))
                media += 1
        archive.writestr('manifest.json', json.dumps({'format': 1, 'tables': counts, 'media': media,
            'created_at': datetime.now(timezone.utc).isoformat(), 'source_revision': os.getenv('GITHUB_SHA', 'manual')}))
    content = stream.getvalue()
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + os.getenv('GITHUB_RUN_ID', 'manual') + '.zip'
    # Parts stay below the project's per-object limit even as the library grows.
    parts = []
    for offset in range(0, len(content), 20 * 1024 * 1024):
        part = name + f'.part{len(parts):04d}'
        client.storage.from_(BUCKET).upload(part, content[offset:offset + 20 * 1024 * 1024],
            file_options={'content-type': 'application/octet-stream', 'upsert': 'false'})
        parts.append(part)
    restored = b''.join(client.storage.from_(BUCKET).download(part) for part in parts)
    with zipfile.ZipFile(io.BytesIO(restored)) as check:
        if check.testzip() or json.loads(check.read('manifest.json'))['tables'] != counts or restored != content:
            raise RuntimeError('Backup verification failed')
    client.storage.from_(BUCKET).upload(name + '.manifest.json', json.dumps({'parts': parts, 'tables': counts, 'media': media}).encode(),
        file_options={'content-type': 'application/json', 'upsert': 'false'})
    return {'operation': 'backup', 'verified': 1, 'tables': len(counts), 'records': sum(counts.values()), 'media': media}


def child():
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = backup()
    except Exception:
        result = {'operation': 'backup', 'verified': 0}
    print(json.dumps(result))
    return 0 if result['verified'] else 1


if __name__ == '__main__':
    from scripts.admin_runtime import run_private_child
    sys.exit(child() if '--child' in sys.argv else run_private_child(__file__))
