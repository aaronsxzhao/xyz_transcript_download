"""Persistent thumbnails of public provider artwork, separate from private media."""
import asyncio
import hashlib
import io
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException
from PIL import Image, ImageOps
from config import DATA_DIR, SUPABASE_URL, SUPABASE_SERVICE_KEY, USE_SUPABASE

HOSTS = ('image.xyzcdn.net', 'bts-image.xyzcdn.net', 'jike.ruguoapp.com',
         'piccdn.igetget.com', 'mzstatic.com', 'i.ytimg.com', 'yt3.ggpht.com',
         'yt3.googleusercontent.com', 'i0.hdslb.com', 'i1.hdslb.com', 'i2.hdslb.com',
         'pbs.twimg.com', 'substackcdn.com', 'substack-post-media.s3.amazonaws.com')
MAX_SOURCE = 8 * 1024 * 1024
MAX_STORED = 32 * 1024 * 1024  # Full-resolution WebP may exceed its source JPEG.
MAX_CACHE = 64 * 1024 * 1024
VARIANTS = {'cover': 480, 'article': 1600, 'original': None}
_pending = {}
_failures = {}
_slots = asyncio.Semaphore(6)


def validate_url(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        if (len(url) > 4096 or parsed.scheme not in {'https', 'http'} or parsed.username or parsed.password
                or parsed.port not in {None, 80, 443}
                or not any(host == domain or host.endswith('.' + domain) for domain in HOSTS)):
            raise ValueError()
    except ValueError:
        raise HTTPException(403, 'Artwork domain not allowed')
    return host


def cache_key(url, variant='cover'):
    validate_url(url)
    if variant not in VARIANTS:
        raise HTTPException(422, 'Unknown image size')
    namespace = 'cover-v1:' if variant == 'cover' else f'article-v1:{variant}:'
    return hashlib.sha256((namespace + url).encode()).hexdigest()


def make_thumbnail(content, variant='cover'):
    with Image.open(io.BytesIO(content)) as source:
        if source.width * source.height > 20_000_000:
            raise ValueError('Artwork dimensions exceed limit')
        source.seek(0)
        image = ImageOps.exif_transpose(source).convert('RGB')
        size = VARIANTS[variant]
        if size:
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='WEBP', quality=74 if variant == 'cover' else 90, method=4)
        result = output.getvalue()
        if len(result) > MAX_STORED:
            raise ValueError('Converted artwork exceeds size limit')
        return result


def _paths(key):
    root = DATA_DIR / '.cover-cache'
    return root / (key + '.webp'), root / (key + '.saved')


def _write(key, content):
    target, _ = _paths(key)
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            stream.write(content); temporary = Path(stream.name)
        temporary.replace(target)
        files = sorted(target.parent.glob('*.webp'), key=lambda path: path.stat().st_mtime)
        total = sum(path.stat().st_size for path in files)
        count = len(files)
        for path in files:
            if total <= MAX_CACHE and count <= 2048: break
            if path == target: continue
            total -= path.stat().st_size; count -= 1
            path.unlink(missing_ok=True); path.with_suffix('.saved').unlink(missing_ok=True)
    except OSError:
        pass  # Storage/browser delivery does not depend on writable local disk.
    finally:
        if temporary:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass


def _cloud():
    return USE_SUPABASE and bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


async def _storage(key, content=None):
    """Service credentials stay server-side; the bucket remains private."""
    headers = {'Authorization': 'Bearer ' + SUPABASE_SERVICE_KEY, 'apikey': SUPABASE_SERVICE_KEY}
    endpoint = SUPABASE_URL.rstrip('/') + '/storage/v1/object/thumbnails/covers-v1/' + key + '.webp'
    async with httpx.AsyncClient(timeout=httpx.Timeout(5, connect=2), follow_redirects=False) as client:
        if content is None:
            response = await client.get(endpoint, headers=headers)
            if response.status_code in {400, 404}: return None
            response.raise_for_status()
            if len(response.content) > MAX_STORED or not response.content.startswith(b'RIFF'):
                raise ValueError('Invalid stored artwork')
            return response.content
        response = await client.post(endpoint, content=content, headers={**headers, 'Content-Type': 'image/webp', 'x-upsert': 'true', 'Cache-Control': '31536000'})
        response.raise_for_status()


async def _origin(url, variant='cover'):
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'image/webp,image/jpeg,image/png,image/*;q=0.8'}
    async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=3), follow_redirects=False) as client:
        for _ in range(4):
            host = validate_url(url)
            if host.endswith('hdslb.com'): headers['Referer'] = 'https://www.bilibili.com/'
            elif host.endswith('xyzcdn.net'): headers['Referer'] = 'https://www.xiaoyuzhoufm.com/'
            else: headers.pop('Referer', None)
            async with client.stream('GET', url, headers=headers) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    validate_url(url)  # Never follow redirects to a private/unknown destination.
                    continue
                if response.status_code == 404 and host == 'i.ytimg.com' and any(name in url for name in ('maxresdefault.', 'sddefault.')):
                    import re
                    url = re.sub(r'(maxresdefault|sddefault)\.[a-zA-Z]+', 'hqdefault.jpg', url)
                    continue
                response.raise_for_status()
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > MAX_SOURCE: raise ValueError('Artwork exceeds size limit')
                return await asyncio.to_thread(make_thumbnail, bytes(data), variant)
    raise ValueError('Too many artwork redirects')


async def _persist(key, content):
    if not _cloud(): return
    try:
        await _storage(key, content)
        _, marker = _paths(key)
        marker.touch()
    except Exception:
        # The background sweep retries persistence without downloading the source again.
        pass


async def _load(url, key, persist=False, variant='cover'):
    target, marker = _paths(key)
    try:
        content = await asyncio.to_thread(target.read_bytes)
        if content.startswith(b'RIFF'):
            if persist and not marker.exists(): await _persist(key, content)
            return content, 'disk'
    except OSError:
        pass
    async with _slots:
        if _cloud():
            try:
                stored = await _storage(key)
                if stored:
                    await asyncio.to_thread(_write, key, stored)
                    try: marker.touch()
                    except OSError: pass
                    return stored, 'storage'
            except Exception:
                pass  # A storage outage can still use the public provider source.
        try:
            async with asyncio.timeout(12):
                content = await _origin(url) if variant == 'cover' else await _origin(url, variant)
        except Exception as error:
            _failures[key] = time.monotonic()
            if len(_failures) > 2048: _failures.pop(next(iter(_failures)))
            headers = {'X-Artwork-Upstream-Status': str(error.response.status_code)} if isinstance(error, httpx.HTTPStatusError) else {}
            raise HTTPException(502, 'Artwork source unavailable', headers=headers) from error
        await asyncio.to_thread(_write, key, content)
        await _persist(key, content)
        return content, 'origin'


async def load_cover(url, persist=False, variant='cover'):
    key = cache_key(url, variant)
    if time.monotonic() - _failures.get(key, -1000) < 3:
        raise HTTPException(503, 'Artwork retry is temporarily delayed')
    task = _pending.get(key)
    if task is None:
        if len(_pending) >= 128: raise HTTPException(503, 'Artwork queue is busy')
        task = asyncio.create_task(_load(url, key, persist, variant))
        _pending[key] = task
        def done(completed):
            if _pending.get(key) is completed: _pending.pop(key, None)
            if not completed.cancelled(): completed.exception()
        task.add_done_callback(done)
    return await asyncio.shield(task)


async def backfill_covers():
    """Warm saved public artwork at low concurrency; never enumerate private files."""
    from api.supabase_client import get_supabase_admin_client
    while True:
        try:
            client = get_supabase_admin_client() if USE_SUPABASE else None
            if client:
                seen = set()
                for table, columns, order in [('podcasts', 'id,cover_url', 'id'), ('library_items', 'sort_key,thumbnail', 'sort_key'), ('video_tasks', 'id,thumbnail,channel_avatar', 'id')]:
                    offset = 0
                    while True:
                        def fetch():
                            query = client.table(table).select(columns)
                            if table == 'library_items': query = query.eq('status', 'completed')
                            if table == 'video_tasks': query = query.eq('status', 'success')
                            return query.order(order).range(offset, offset + 99).execute().data or []
                        rows = await asyncio.to_thread(fetch)
                        for row in rows:
                            for column in ('cover_url', 'thumbnail', 'channel_avatar'):
                                url = row.get(column)
                                if not url or url in seen: continue
                                seen.add(url)
                                try:
                                    validate_url(url)
                                    await load_cover(url, persist=True)
                                except HTTPException:
                                    pass  # Private/missing/provider failures do not block the next cover.
                                await asyncio.sleep(.05)
                        if len(rows) < 100: break
                        offset += len(rows)
        except asyncio.CancelledError:
            raise
        except Exception:
            import logging
            logging.getLogger(__name__).warning('Public artwork sweep paused; retrying later')
        await asyncio.sleep(600)
