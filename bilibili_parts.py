"""Explicit Bilibili part identity and resumable collection admission.

Each part remains an ordinary video task, with its own zero-based timeline.
A collection import is never represented as one 113-minute first-part summary.
"""
import math
import uuid
import re
from urllib.parse import parse_qs, urlsplit


def public_collection_metadata(url):
    """Read a complete legacy directory without cookies, media or DB writes."""
    import requests
    from video_downloader import BilibiliDownloader
    parsed = urlsplit(url)
    if parsed.hostname in ('b23.tv', 'www.b23.tv'):
        url = BilibiliDownloader._resolve_short_url(url)
        parsed = urlsplit(url)
    identity = re.fullmatch(r'/video/(BV\w+|av\d+)/?', parsed.path)
    if (parsed.scheme not in ('http', 'https') or parsed.username or parsed.password
            or parsed.port not in (None, 80, 443)
            or parsed.hostname not in ('bilibili.com', 'www.bilibili.com', 'm.bilibili.com')
            or not identity):
        raise ValueError('No canonical Bilibili source identity')
    video_id = identity.group(1)
    params = {'bvid': video_id} if video_id.startswith('BV') else {'aid': video_id[2:]}
    # The public page-list endpoint returns the complete collection directly.
    # A directory does not need the separate video overview (which may reject
    # an anonymous read even while the public page list remains available).
    with requests.get('https://api.bilibili.com/x/player/pagelist', params=params,
                      headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'},
                      timeout=15, allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError(f'Public part metadata unavailable (HTTP {response.status_code})')
        data = response.json()
    if not isinstance(data, dict) or data.get('code') != 0:
        raise ValueError('Public part metadata was rejected')
    pages = data.get('data')
    if not isinstance(pages, list) or not all(isinstance(page, dict) for page in pages):
        raise ValueError('Public part metadata is invalid')
    try:
        # Do not invent an overview title or a source-reported total. Keep each
        # public part label; the saved collection heading remains unchanged.
        parts = part_manifest({'title': 'Bilibili', 'pages': pages}, url)
    except TypeError as error:
        raise ValueError('Public part metadata is invalid') from error
    page = selected_part(url) or 1
    if page > len(parts):
        raise ValueError('Saved part is absent from the public directory')
    return {'bilibili_parts': parts, 'bilibili_part': parts[page - 1]}


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
        title = data.get('title') or page.get('part') or 'Bilibili'
        if len(pages) > 1:
            title = f"{title} · P{index}/{len(pages)} {page.get('part') or ''}".strip()
        result.append({'page': index, 'cid': cid, 'duration': duration,
                       'title': title,
                       'url': f'{base}?p={index}'})
    return result


def find_task(db, url, owner):
    task = db.get_task_by_url(url, owner)
    if task is None and selected_part(url) == 1:
        # A collection's first-part task retains the bare URL for repeat imports.
        task = db.get_task_by_url(url.split('?')[0], owner)
    return task


def same_part_source(saved, current):
    """A presentation-only title correction does not invalidate saved audio text."""
    if not isinstance(saved, dict) or not isinstance(current, dict):
        return False
    if not saved.get('cid') or not current.get('cid'):
        return False
    return {k:v for k,v in saved.items() if k != 'title'} == {k:v for k,v in current.items() if k != 'title'}


def ensure_part_task(db, parent, part, options):
    owner = parent.get('user_id')
    child = find_task(db, part['url'], owner)
    if child:
        return child
    child_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(owner) + ':' + part['url']))[:12]
    try:
        db.create_task({**options, 'id':child_id, 'user_id':owner,
                        'url':part['url'], 'platform':'bilibili',
                        'title':part['title'], 'duration':part['duration'],
                        'channel':parent.get('channel',''), 'thumbnail':parent.get('thumbnail','')})
    except Exception:
        child = db.get_task(child_id, owner)
        if not child or child.get('url') != part['url']:
            raise
        return child
    return db.get_task(child_id, owner)


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
                    child = ensure_part_task(db, task, part, options)
                    child_id = child['id']
                transcript = (child or {}).get('transcript') or {}
                if (not child or child.get('status') != 'success' or not child.get('markdown')
                        or not same_part_source(transcript.get('bilibili_part'), part)):
                    pending.append((child_id, part['url']))
        links.append({**part, 'task_id':child_id})
    metadata = {'type':'video', 'bilibili_part':current,
                'bilibili_parts':links, 'collection_requested':page is None}
    db.update_task(task['id'], {'source_metadata':metadata, 'duration':current['duration'], 'title':current['title']})
    for child_id, child_url in pending:
        check_cancel()
        submit(child_id, child_url)
    return current
