"""Fill missing video publication dates from source metadata, outside page loads.

No downloads, transcription or LLM calls. Known dates and import dates are kept.
Credentials and source URLs never appear in the fixed-label numeric report.
"""
import contextlib
import io
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def source_date(task):
    from publication_dates import publication_date
    from cookie_manager import get_cookie_manager
    from video_downloader import get_downloader
    import yt_dlp
    platform = task['platform']
    hosts = {'youtube': ('youtube.com', 'youtu.be'), 'bilibili': ('bilibili.com', 'b23.tv')}
    parsed = urlsplit(task['url'])
    if parsed.scheme != 'https' or parsed.username or parsed.password or not any(
        parsed.hostname == host or (parsed.hostname or '').endswith('.' + host)
        for host in hosts.get(platform, ())
    ):
        return ''
    cookies = get_cookie_manager(task['user_id']).get_cookie(platform)
    downloader = get_downloader(platform, cookies)
    opts = {**downloader._get_base_opts(), 'skip_download': True, 'extract_flat': False,
            'socket_timeout': 10, 'retries': 0, 'extractor_retries': 0,
            'quiet': True, 'no_warnings': True}
    # Apply the same bounds to Bilibili's yt-dlp fallback too.
    downloader._get_base_opts = lambda: dict(opts)
    if platform == 'bilibili':
        # Native metadata also handles older Bilibili content without yt-dlp.
        result = downloader.get_metadata(task['url'])
        return result.published_at if result else ''
    # The watch page exposes the original date even when the player API refuses
    # media extraction on a datacenter IP. No video stream is requested here.
    try:
        import requests
        from bs4 import BeautifulSoup
        response = requests.get(task['url'], timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        tag = soup.find('meta', itemprop='datePublished') or soup.find('meta', itemprop='uploadDate')
        stamp = publication_date({'release_date': tag.get('content', '')}) if tag else ''
        if stamp:
            return stamp
    except Exception:
        pass
    with yt_dlp.YoutubeDL(opts) as extractor:
        return publication_date(extractor.extract_info(task['url'], download=False) or {})


def repair(client, fetch_date=source_date):
    report = {'operation': 'publication_dates', 'examined': 0, 'repaired': 0,
              'unavailable': 0, 'failed': 0, 'verified': 0}
    # Snapshot identifiers before mutation so filling dates cannot shift offsets.
    tasks, offset = [], 0
    while True:
        rows = (client.table('video_tasks').select('id,user_id,url,platform,published_at')
                .in_('platform', ['youtube', 'bilibili'])
                .or_('published_at.is.null,published_at.eq.').order('id')
                .range(offset, offset + 99).execute().data or [])
        tasks.extend(rows)
        if len(rows) < 100:
            break
        offset += 100
    for task in tasks:
        report['examined'] += 1
        if not task.get('user_id'):
            report['unavailable'] += 1
            continue
        try:
            stamp = fetch_date(task)
            from publication_dates import publication_date
            if not stamp or publication_date({'upload_date': stamp}) != stamp:
                report['unavailable'] += 1
                continue
            query = (client.table('video_tasks').update({'published_at': stamp})
                     .eq('id', task['id']).eq('user_id', task['user_id']))
            # Compare-and-set preserves a date recovered by a concurrent worker.
            query = query.is_('published_at', 'null') if task['published_at'] is None else query.eq('published_at', '')
            changed = query.execute().data or []
            if changed:
                report['repaired'] += 1
                verified = (client.table('video_tasks').select('published_at')
                            .eq('id', task['id']).eq('user_id', task['user_id']).limit(1).execute().data)
                if not verified or verified[0]['published_at'] != stamp:
                    raise RuntimeError('Publication date verification failed')
                report['verified'] += 1
        except Exception:
            report['failed'] += 1
    return report


def child():
    logging.disable(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from api.supabase_client import get_supabase_admin_client
        report = repair(get_supabase_admin_client())
    print(json.dumps(report), flush=True)
    return int(report['repaired'] != report['verified'])


if __name__ == '__main__':
    from scripts.admin_runtime import run_private_child
    sys.exit(child() if '--child' in sys.argv else run_private_child(__file__, timeout=1700))
