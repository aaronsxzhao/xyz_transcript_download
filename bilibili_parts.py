"""Explicit Bilibili part identity and resumable collection admission.

Each part remains an ordinary video task, with its own zero-based timeline.
A collection import is never represented as one 113-minute first-part summary.
"""
import math
import uuid
from urllib.parse import parse_qs, urlsplit


def selected_part(url):
    values = parse_qs(urlsplit(url).query, keep_blank_values=True).get('p')
    if values is None:
        return None
    if len(values) != 1 or not values[0].isdigit() or int(values[0]) < 1:
        raise ValueError('Invalid Bilibili part number')
    return int(values[0])


def part_manifest(data, url):
    from video_downloader import normalize_video_url
    base = normalize_video_url(url, 'bilibili').split('?')[0]
    pages = data.get('pages')
    if not isinstance(pages, list) or not pages:
        raise ValueError('Bilibili returned no part list')
    if data.get('videos') is not None and int(data['videos']) != len(pages):
        raise ValueError('Bilibili returned an incomplete part list')
    result = []
    for index, page in enumerate(pages, 1):
        duration = float(page.get('duration') or 0)
        cid = str(page.get('cid') or '')
        if page.get('page') != index or not cid.isdigit() or int(cid) <= 0 or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Bilibili returned invalid part metadata')
        result.append({'page': index, 'cid': cid, 'duration': duration,
                       'title': f"{data.get('title') or 'Bilibili'} · P{index}/{len(pages)} {page.get('part') or ''}".strip(),
                       'url': f'{base}?p={index}'})
    return result


def find_task(db, url, owner):
    task = db.get_task_by_url(url, owner)
    if task is None and selected_part(url) == 1:
        # A collection's first-part task retains the bare URL for repeat imports.
        task = db.get_task_by_url(url.split('?')[0], owner)
    return task


def prepare_parts(db, task, parts, url, options, submit, check_cancel=lambda: None):
    """Idempotently admit children before processing P1; retry unaccepted work.

    The queue, not task status, deduplicates queued/running admissions. This also
    repairs a crash between saving a child row and handing it to the queue.
    """
    page = selected_part(url)
    if page is not None and page > len(parts):
        raise ValueError(f'Bilibili has {len(parts)} parts; P{page} does not exist')
    current = parts[(page or 1)-1]
    owner = task.get('user_id')
    links, pending = [], []
    for part in parts:
        check_cancel()
        if part['page'] == current['page']:
            child_id = task['id']
        else:
            child = find_task(db, part['url'], owner)
            child_id = child['id'] if child else None
            if page is None:
                if child is None:
                    # Stable identity survives a retry after an uncertain insert.
                    child_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(owner) + ':' + part['url']))[:12]
                    try:
                        db.create_task({**options, 'id':child_id, 'user_id':owner,
                                        'url':part['url'], 'platform':'bilibili',
                                        'title':part['title'], 'duration':part['duration'],
                                        'channel':task.get('channel',''), 'thumbnail':task.get('thumbnail','')})
                    except Exception:
                        child = db.get_task(child_id, owner)
                        if not child or child.get('url') != part['url']:
                            raise
                transcript = (child or {}).get('transcript') or {}
                if (not child or child.get('status') != 'success' or not child.get('markdown')
                        or transcript.get('bilibili_part') != part):
                    pending.append((child_id, part['url']))
        links.append({**part, 'task_id':child_id})
    metadata = {'type':'video', 'bilibili_part':current,
                'bilibili_parts':links, 'collection_requested':page is None}
    db.update_task(task['id'], {'source_metadata':metadata, 'duration':current['duration'], 'title':current['title']})
    for child_id, child_url in pending:
        check_cancel()
        submit(child_id, child_url)
    return current
