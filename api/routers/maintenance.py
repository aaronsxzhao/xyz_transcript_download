"""Account-owned integrity checks, portable exports and save/media recovery."""
import hashlib
import json
import re
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse
from fastapi.responses import StreamingResponse
from api.auth import User, get_current_user
from config import USE_SUPABASE

router = APIRouter()
_running = set()
_reports = {}
_lock = threading.Lock()


def references(markdown, task_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', task_id):
        return {}
    pattern = r'(?<![A-Za-z0-9_.-])' + re.escape(task_id) + r'_(\d{1,4})-(\d{2})\.jpg'
    return {m.group(0): int(m[1]) * 60 + int(m[2]) for m in re.finditer(pattern, markdown or '') if int(m[2]) < 60}


def _client():
    from api.supabase_client import get_supabase_admin_client
    return get_supabase_admin_client()


def _tasks(owner):
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    if USE_SUPABASE:
        tasks = []
        offset = 0
        while True:
            page = _client().table('video_tasks').select('id,title,platform,markdown,url,status').eq('user_id', owner).order('id').range(offset, offset + 499).execute().data
            tasks.extend(page)
            if len(page) < 500:
                return tasks
            offset += 500
    return [db.get_task(t['id'], owner, include_transcript=False) for t in db.list_tasks(owner, limit=2000)]


def _existing():
    from screenshot_extractor import SCREENSHOTS_DIR, _iter_bucket_objects
    if USE_SUPABASE:
        return {o['name'] for o in _iter_bucket_objects(_client(), 'screenshots')}
    return {p.name for p in SCREENSHOTS_DIR.glob('*.jpg')}


def _frames(task, owner):
    from video_task_db import get_video_task_db
    found = references(task.get('markdown'), task['id'])
    for version in get_video_task_db().get_versions(task['id']):
        found.update(references(version.get('content'), task['id']))
    return found


@router.get('/media-integrity')
def media_integrity(user: User = Depends(get_current_user)):
    existing = _existing()
    items = []
    total = 0
    tasks = _tasks(user.id)
    versions = {}
    if USE_SUPABASE:
        ids = [t['id'] for t in tasks]
        for start in range(0, len(ids), 100):
            offset = 0
            while True:
                page = _client().table('video_task_versions').select('id,task_id,content').in_('task_id', ids[start:start + 100]).order('id').range(offset, offset + 499).execute().data
                for v in page:
                    versions.setdefault(v['task_id'], {}).update(references(v['content'], v['task_id']))
                if len(page) < 500:
                    break
                offset += 500
    for task in tasks:
        if not task:
            continue
        frames = references(task.get('markdown'), task['id'])
        frames.update(versions.get(task['id'], {}) if USE_SUPABASE else _frames(task, user.id))
        total += len(frames)
        missing = len(set(frames) - existing)
        if missing:
            items.append({'id': task['id'], 'title': task.get('title') or 'Untitled note',
                          'platform': task.get('platform'), 'missing': missing,
                          'source_required': task.get('platform') == 'local'})
    return {'referenced': total, 'missing': sum(t['missing'] for t in items), 'notes': items}


def _image(name):
    from screenshot_extractor import SCREENSHOTS_DIR
    path = SCREENSHOTS_DIR / name
    if path.is_file():
        return path.read_bytes()
    if USE_SUPABASE:
        return _client().storage.from_('screenshots').download(name)
    raise FileNotFoundError(name)


def _zip_response(stream, name, missing=0):
    stream.seek(0)
    def chunks():
        try:
            while data := stream.read(256 * 1024):
                yield data
        finally:
            stream.close()
    return StreamingResponse(chunks(), media_type='application/zip', headers={
        'Content-Disposition': f'attachment; filename="{name}"', 'Cache-Control': 'private, no-store',
        'X-Missing-Images': str(missing), 'X-Content-Type-Options': 'nosniff'})


@router.get('/notes/{task_id}/bundle')
def portable_note(task_id: str, version: str = '', user: User = Depends(get_current_user)):
    from video_task_db import get_video_task_db
    db = get_video_task_db()
    task = db.get_task(task_id, user.id, include_transcript=False)
    if not task:
        raise HTTPException(status_code=404, detail='Note not found')
    markdown = task.get('markdown') or ''
    if version:
        saved = db.get_version(task_id, version)
        if not saved:
            raise HTTPException(status_code=404, detail='Version not found')
        markdown = saved['content']
    stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    manifest = {'format': 1, 'title': task.get('title'), 'images': [], 'missing_images': []}
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in references(markdown, task_id):
            try:
                content = _image(name)
                archive.writestr('images/' + name, content)
                manifest['images'].append({'file': name, 'sha256': hashlib.sha256(content).hexdigest()})
            except Exception:
                manifest['missing_images'].append(name)
            # Replace only this task's generated-image URLs, including signed
            # query parameters. Arbitrary external URLs are never fetched.
            markdown = re.sub(r'(?:https?://[^\s()]+)?/(?:storage/v1/object/(?:public|sign)/)?(?:data/)?screenshots/' + re.escape(name) + r'(?:\?[^\s)]*)?', 'images/' + name, markdown)
        archive.writestr('note.md', markdown)
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr('README.txt', 'Open note.md beside the images folder. manifest.json lists any unavailable historical screenshots.\n')
    return _zip_response(stream, 'note-' + re.sub(r'[^A-Za-z0-9_-]', '', task_id) + '.zip', len(manifest['missing_images']))


def _save_report(key, report):
    with _lock:
        _reports[key] = report.copy()
        if len(_reports) > 500:
            for old in list(_reports):
                if old not in _running:
                    del _reports[old]
                    break
    if USE_SUPABASE:
        _client().storage.from_('application-backups').upload(key, json.dumps(report).encode(), file_options={'content-type': 'application/json', 'upsert': 'true'})


def _repair(task, owner, key):
    from screenshot_extractor import extract_screenshots_batch
    from cookie_manager import get_cookie_manager
    from video_downloader import get_downloader
    from social_content import social_platform, SocialSourceError
    report = {'status': 'running', 'missing': 0, 'message': 'Restoring screenshots…', 'started_at': datetime.now(timezone.utc).isoformat()}
    downloader = None
    try:
        _save_report(key, report)
        missing = {n: t for n, t in _frames(task, owner).items() if n not in _existing()}
        if missing:
            if task.get('platform') == 'local':
                from api.local_media import get_local_video_dir
                source = Path(task['url']).resolve()
                if not source.is_relative_to(get_local_video_dir(owner).resolve()) or not source.is_file():
                    raise SocialSourceError('The original uploaded video is needed. Upload it again to recover these frames.')
            else:
                host = (urlparse(task['url']).hostname or '').lower()
                domains = {'youtube': ('youtube.com', 'youtu.be'), 'bilibili': ('bilibili.com', 'b23.tv'), 'douyin': ('douyin.com', 'tiktok.com'), 'kuaishou': ('kuaishou.com', 'kwai.com')}
                social = task.get('platform') in {'twitter','substack'} and social_platform(task['url']) == task['platform']
                if task.get('platform') == 'web':
                    from public_content_fetch import normalize_public_url
                    normalize_public_url(task['url'])
                    social = True
                if urlparse(task['url']).scheme != 'https' or not (social or any(host == d or host.endswith('.' + d) for d in domains.get(task.get('platform'), ()))):
                    raise ValueError('Unsupported source URL')
                downloader = get_downloader(task['platform'], get_cookie_manager(owner).get_cookie(task['platform']))
                source = downloader.download_video(task['url'], task['id'], video_quality='360')
            if not source:
                raise ValueError('Original video is unavailable. Check your platform connection.')
            extract_screenshots_batch(str(source), list(missing.values()), task['id'])
        remaining = len(set(_frames(task, owner)) - _existing())
        if not remaining:
            from video_task_db import get_video_task_db
            db = get_video_task_db()
            current = db.get_task(task['id'], owner, include_transcript=False)
            if current and current.get('status') == 'success' and current.get('error'):
                db.update_task(task['id'], {'error': '', 'message': 'Notes saved'})
                db.flush_task(task['id'], strict=True)
        report.update(status='completed' if not remaining else 'failed', missing=remaining,
                      message='Screenshots restored' if not remaining else 'Some screenshots are unavailable. Check your platform connection or original file.')
    except SocialSourceError as error:
        report.update(status='failed', message=str(error))
    except Exception:
        report.update(status='failed', message='Cannot restore these frames. Reconnect the platform account, or provide the original uploaded file.')
    finally:
        if task.get('platform') == 'web' and downloader is not None:
            try: downloader.cleanup()
            except OSError: pass
        with _lock:
            _running.discard(key)
        try:
            _save_report(key, report)
        except Exception:
            pass


class RepairRequest(BaseModel):
    source_path: str = ''


@router.post('/notes/{task_id}/repair-media')
def repair_media(task_id: str, background: BackgroundTasks, data: RepairRequest = None, user: User = Depends(get_current_user)):
    from video_task_db import get_video_task_db
    task = get_video_task_db().get_task(task_id, user.id)
    if not task:
        raise HTTPException(status_code=404, detail='Note not found')
    if task.get('status') not in {'success', 'failed', 'cancelled'}:
        raise HTTPException(status_code=409, detail='Wait until note processing finishes before repairing screenshots.')
    if data and data.source_path:
        from api.local_media import get_local_video_dir
        source = Path(data.source_path).resolve()
        if task.get('platform') != 'local' or not source.is_relative_to(get_local_video_dir(user.id).resolve()) or not source.is_file():
            raise HTTPException(status_code=400, detail='Upload the original video using your own account first.')
        task = {**task, 'url': str(source)}
    key = f'media-repair/{user.id}/{task_id}.json'
    with _lock:
        if key in _running:
            return {'status': 'running'}
        # A small per-process limit protects the media tools; this is unrelated
        # to the account's paid Groq plan and never changes provider settings.
        if len(_running) >= 2:
            raise HTTPException(status_code=409, detail='Two screenshot repairs are already running. Please wait.')
        _running.add(key)
    background.add_task(_repair, task, user.id, key)
    return {'status': 'running'}


@router.get('/notes/{task_id}/repair-media')
def repair_status(task_id: str, user: User = Depends(get_current_user)):
    from video_task_db import get_video_task_db
    if not get_video_task_db().get_task(task_id, user.id, include_transcript=False):
        raise HTTPException(status_code=404, detail='Note not found')
    key = f'media-repair/{user.id}/{task_id}.json'
    with _lock:
        if key in _running:
            return {'status': 'running'}
        if key in _reports:
            return _reports[key]
    if USE_SUPABASE:
        try:
            report = json.loads(_client().storage.from_('application-backups').download(key))
            if report.get('status') == 'running':
                report.update(status='failed', message='The server restarted. Retry screenshot repair.')
            return report
        except Exception:
            pass
    return {'status': 'idle'}


@router.post('/notes/{task_id}/retry-save')
def retry_save(task_id: str, user: User = Depends(get_current_user)):
    from video_task_db import get_video_task_db
    from api.save_outbox import pending
    db = get_video_task_db()
    task = db.get_task(task_id, user.id)
    if not task:
        raise HTTPException(status_code=404, detail='Note not found')
    if task.get('status') not in {'failed', 'cancelled', 'success'}:
        raise HTTPException(status_code=409, detail='Wait until processing finishes before recovering a saved copy.')
    try:
        payload = pending(user.id, task_id)
    except Exception:
        raise HTTPException(status_code=404, detail='There is no pending saved copy for this note.')
    if task.get('status') == 'success' and task.get('markdown') != payload['content']:
        raise HTTPException(status_code=409, detail='A completed note already exists. Its content has been preserved.')
    db.complete_task(**payload)
    from api.routers.video_notes import _invalidate_list_cache
    _invalidate_list_cache(user.id)
    return {'saved': True}


def _owned_backup(owner):
    """Owner predicates apply before using the privileged database client."""
    if not USE_SUPABASE:
        from dataclasses import asdict, is_dataclass
        from api.db import get_db
        def value(item):
            return asdict(item) if is_dataclass(item) else item.model_dump() if hasattr(item, 'model_dump') else item
        db = get_db(owner)
        podcasts = db.get_all_podcasts()
        episodes = [e for p in podcasts for e in db.get_episodes_by_podcast(p.pid)]
        return {'podcasts': [value(p) for p in podcasts], 'episodes': [value(e) for e in episodes],
                'summaries': [value(s) for s in db.get_all_summaries()],
                'transcripts': [value(t) for e in episodes if (t := db.get_transcript(e.eid))]}
    client = _client()
    data = {}
    def read(table, column, values):
        rows = []
        for start in range(0, len(values), 100):
            ids = values[start:start + 100]
            offset = 0
            while True:
                query = client.table(table).select('*')
                query = query.eq(column, ids[0]) if len(ids) == 1 else query.in_(column, ids)
                page = query.order('id').range(offset, offset + 499).execute().data
                rows.extend(page)
                if len(page) < 500:
                    break
                offset += 500
        return rows
    for table in ('podcasts', 'episodes', 'transcripts', 'summaries', 'video_tasks'):
        data[table] = read(table, 'user_id', [owner])
    for table, parent, fk in [('video_task_versions', 'video_tasks', 'task_id'),
                              ('transcript_segments', 'transcripts', 'transcript_id'),
                              ('summary_key_points', 'summaries', 'summary_id')]:
        data[table] = read(table, fk, [r['id'] for r in data[parent]])
    return data


@router.get('/backup')
def account_backup(user: User = Depends(get_current_user)):
    """Portable account data and generated media, excluding credentials/sessions."""
    from concurrent.futures import ThreadPoolExecutor
    from video_task_db import get_video_task_db
    data = _owned_backup(user.id)
    if 'video_tasks' not in data:
        data['video_tasks'] = _tasks(user.id)
        data['video_task_versions'] = [v for t in data['video_tasks'] for v in get_video_task_db().get_versions(t['id'])]
    names = set()
    for task in data['video_tasks']:
        names.update(references(task.get('markdown'), task['id']))
    for version in data['video_task_versions']:
        names.update(references(version.get('content'), version['task_id']))
    stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    missing = []
    def download(name):
        try:
            return name, _image(name)
        except Exception:
            return name, None
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for table, rows in data.items():
            archive.writestr(f'database/{table}.json', json.dumps(rows, ensure_ascii=False, default=str))
        with ThreadPoolExecutor(max_workers=6) as pool:
            for name, content in pool.map(download, sorted(names)):
                if content is None:
                    missing.append(name)
                else:
                    archive.writestr('images/' + name, content)
        archive.writestr('manifest.json', json.dumps({'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'tables': {t: len(rows) for t, rows in data.items()}, 'missing_images': missing}, indent=2))
        archive.writestr('README.txt', 'Your account data and generated screenshots. Credentials and authentication sessions are excluded. Original audio/video files must be backed up separately. See manifest.json for unavailable images.\n')
    return _zip_response(stream, 'library-backup.zip', len(missing))
