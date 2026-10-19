"""Owner-scoped, additive recovery of missing historical frames. No LLM calls."""
import contextlib
import hashlib
import io
import json
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def frames(text, task_id):
    pattern = r'(?<![A-Za-z0-9_.-])' + re.escape(task_id) + r'_(\d{1,4})-(\d{2})\.jpg'
    return {m.group(0): int(m[1]) * 60 + int(m[2]) for m in re.finditer(pattern, text or '') if int(m[2]) < 60}


def recover():
    from api.supabase_client import get_supabase_admin_client
    from cookie_manager import get_cookie_manager
    from video_downloader import get_downloader
    from screenshot_extractor import _iter_bucket_objects, extract_screenshot
    import screenshot_extractor
    screenshot_extractor.USE_SUPABASE_STORAGE = False  # Recovery uploads are create-only.
    client = get_supabase_admin_client()
    owner = client.table('podcasts').select('user_id').eq('pid', '62382c1103bea1ebfffa1c00').limit(1).execute().data[0]['user_id']
    tasks = client.table('video_tasks').select('id,url,platform,markdown').eq('user_id', owner).order('id').execute().data
    existing = {o['name'] for o in _iter_bucket_objects(client, 'screenshots')}
    shard, shards = int(os.getenv('REPAIR_SHARD', '0')), int(os.getenv('REPAIR_SHARDS', '1'))
    report = {'operation': 'media_recovery', 'shard': shard, 'restored': 0, 'remaining': 0, 'source_required': 0, 'failed_sources': 0, 'notes_changed': 0}
    journal = []
    for task in tasks:
        if int(hashlib.sha256(task['id'].encode()).hexdigest(), 16) % shards != shard:
            continue
        references = frames(task['markdown'], task['id'])
        missing = {n: t for n, t in references.items() if n not in existing}
        if not missing:
            continue
        before = hashlib.sha256((task['markdown'] or '').encode()).hexdigest()
        source = urlsplit(task['url'])
        allowed = {'youtube': ('youtube.com', 'youtu.be'), 'bilibili': ('bilibili.com', 'b23.tv')}.get(task['platform'], ())
        host = source.hostname or ''
        if source.scheme != 'https' or not any(host == h or host.endswith('.' + h) for h in allowed):
            report['source_required'] += 1; report['remaining'] += len(missing)
            continue
        try:
            downloader = get_downloader(task['platform'], get_cookie_manager(owner).get_cookie(task['platform']))
            options = downloader._get_base_opts
            downloader._get_base_opts = lambda: {**options(), 'retries': 1, 'fragment_retries': 1, 'socket_timeout': 15, 'max_filesize': 500 * 1024 * 1024}
            path = downloader.download_video(task['url'], task['id'], video_quality='360')
            if not path:
                raise RuntimeError('Source unavailable')
            for name, timestamp in missing.items():
                if extract_screenshot(str(path), timestamp, task['id']) != name:
                    continue
                frame = screenshot_extractor.SCREENSHOTS_DIR / name
                try:
                    client.storage.from_('screenshots').upload(name, frame.read_bytes(),
                        file_options={'content-type': 'image/jpeg', 'upsert': 'false'})
                except Exception:
                    # Never replace an existing frame or journal another writer's file.
                    existing.add(name) if name in {o['name'] for o in _iter_bucket_objects(client, 'screenshots')} else None
                    continue
                content = client.storage.from_('screenshots').download(name)
                if content.startswith(b'\xff\xd8') and len(content) > 100:
                    existing.add(name); report['restored'] += 1
                    journal.append({'name': name, 'sha256': hashlib.sha256(content).hexdigest()})
            Path(path).unlink(missing_ok=True)
        except Exception:
            report['failed_sources'] += 1
        report['remaining'] += sum(n not in existing for n in missing)
        latest = client.table('video_tasks').select('markdown').eq('id', task['id']).eq('user_id', owner).execute().data[0]['markdown']
        report['notes_changed'] += int(hashlib.sha256((latest or '').encode()).hexdigest() != before)
    client.storage.from_('application-backups').upload(f"recovery-{os.getenv('GITHUB_RUN_ID','manual')}-{shard}.json",
        json.dumps({'created_files': journal, 'report': report}).encode(), file_options={'content-type': 'application/json', 'upsert': 'true'})
    return report


def child():
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = recover()
    except Exception:
        report = {'operation': 'media_recovery', 'fatal': 1}
    print(json.dumps(report))
    return int(bool(report.get('fatal') or report.get('notes_changed')))


if __name__ == '__main__':
    from scripts.admin_runtime import run_private_child
    sys.exit(child() if '--child' in sys.argv else run_private_child(__file__, timeout=1700))
