"""Private, verified application-data and generated-media backups.

Never uploads private data as CI artifacts. The isolated child emits numeric
verification diagnostics only; archive data stays in the private storage bucket.
"""
import contextlib
import io
import json
import logging
import os
import sys
import zipfile
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TABLES = ('podcasts', 'episodes', 'transcripts', 'summaries', 'summary_key_points',
          'transcript_segments', 'video_tasks', 'video_task_versions', 'user_settings', 'processing_jobs',
          'content_updates', 'episode_source_access')
BUCKET = 'application-backups'
_PHASE = 0


def rows(client, table):
    offset = 0
    while True:
        query = client.table(table).select('*')
        keys = {'user_settings':('user_id',),'content_updates':('user_id','item_key'),'episode_source_access':('user_id','eid')}.get(table,('id',))
        for key in keys: query = query.order(key)
        page = query.range(offset, offset + 99).execute().data
        if not isinstance(page, list):
            raise RuntimeError('Incomplete database snapshot')
        yield from page
        if len(page) < 100:
            break
        offset += len(page)


def backup():
    from api.supabase_client import get_supabase_admin_client
    from screenshot_extractor import _iter_bucket_objects
    client = get_supabase_admin_client()
    global _PHASE
    _PHASE = 1
    bucket = client.storage.get_bucket(BUCKET)
    if (bucket.get('public',False) if isinstance(bucket,dict) else getattr(bucket,'public',False)):
        raise RuntimeError('Backup bucket must be private')
    counts = {}; media = 0
    with tempfile.TemporaryDirectory() as directory:
        archive_path = Path(directory)/'backup.zip'
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for table in TABLES:
                count = 0
                with archive.open(f'database/{table}.json','w') as output:
                    output.write(b'[')
                    for row in rows(client, table):
                        if count: output.write(b',')
                        output.write(json.dumps(row,ensure_ascii=False).encode())
                        count += 1
                    output.write(b']')
                counts[table] = count
            _PHASE = 2
            for source_bucket in ('screenshots', 'thumbnails'):
                for item in _iter_bucket_objects(client, source_bucket):
                    name = item.get('name', '')
                    if not name or '/' in name: continue
                    archive.writestr(f'media/{source_bucket}/{name}', client.storage.from_(source_bucket).download(name))
                    media += 1
            archive.writestr('manifest.json',json.dumps({'format':2,'tables':counts,'media':media,
                'created_at':datetime.now(timezone.utc).isoformat(),'source_revision':os.getenv('GITHUB_SHA','manual')}))
        _PHASE = 3
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.getenv('GITHUB_RUN_ID','manual')+'.zip'
        parts = []; checksums = []
        # Keep archive creation, upload and verification bounded in memory.
        with archive_path.open('rb') as source:
            while chunk := source.read(8*1024*1024):
                part = name+f'.part{len(parts):04d}'
                client.storage.from_(BUCKET).upload(part,chunk,file_options={'content-type':'application/octet-stream','upsert':'false'})
                parts.append(part); checksums.append(hashlib.sha256(chunk).hexdigest())
        _PHASE = 4
        restored_path = Path(directory)/'restored.zip'
        with restored_path.open('wb') as restored:
            for part, expected in zip(parts,checksums):
                chunk = client.storage.from_(BUCKET).download(part)
                if hashlib.sha256(chunk).hexdigest()!=expected: raise RuntimeError('Part verification failed')
                restored.write(chunk)
        with zipfile.ZipFile(restored_path) as check:
            if check.testzip() or json.loads(check.read('manifest.json'))['tables']!=counts:
                raise RuntimeError('Archive verification failed')
            for table,count in counts.items():
                if len(json.loads(check.read(f'database/{table}.json')))!=count:
                    raise RuntimeError('Record count verification failed')
        client.storage.from_(BUCKET).upload(name+'.manifest.json',json.dumps({'format':2,'parts':parts,'sha256':checksums,'tables':counts,'media':media}).encode(),file_options={'content-type':'application/json','upsert':'false'})
    return {'operation':'backup','verified':1,'tables':len(counts),'records':sum(counts.values()),'media':media}


def child():
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = backup()
    except Exception as error:
        result = {'operation': 'backup', 'verified': 0, 'phase':_PHASE,'error_kind':{'ReadTimeout':1,'APIError':2,'StorageApiError':3,'RuntimeError':4}.get(type(error).__name__,9),'error_code': int(getattr(error,'status_code',0) or 0)}
    print(json.dumps(result))
    return 0 if result['verified'] else 1


if __name__ == '__main__':
    from scripts.admin_runtime import run_private_child
    sys.exit(child() if '--child' in sys.argv else run_private_child(__file__))
