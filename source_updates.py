"""Discover public author updates without downloading media or invoking models."""
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urljoin
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from public_content_fetch import fetch_public
from social_content import SocialSourceError, normalize_social_url, _json


def author_url(platform, url):
    """Canonicalize a saved author/publication URL, retaining legacy post links."""
    p = urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise SocialSourceError('This source has no usable public author URL. Reimport an original post link.')
    host = (p.hostname or '').lower()
    if platform == 'twitter':
        if host not in ('x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com', 'mobile.x.com'):
            raise SocialSourceError('The saved X author URL is not supported.')
        handle = p.path.strip('/').split('/')[0]
        if re.fullmatch(r'[A-Za-z0-9_]{1,15}', handle) and handle.lower() not in ('i', 'statuses', 'home', 'search'):
            return 'https://x.com/' + handle
        return normalize_social_url(url)
    if platform == 'substack':
        if host == 'substack.com':
            handle = re.match(r'^/(@[A-Za-z0-9_-]+)(?:/|$)', p.path)
            if handle: return 'https://substack.com/' + handle[1]
            raise SocialSourceError('This Substack link has no public publication or author update page.')
        if not (host.endswith('.substack.com') or p.path in ('','/') or re.match(r'^/(?:p/|feed/?$)', p.path)):
            raise SocialSourceError('This source has no saved public Substack publication feed.')
        return 'https://' + host
    raise SocialSourceError('This platform has no public author update scanner.')


def _stamp(value):
    try:
        try: date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError: date = parsedate_to_datetime(value)
        return date.replace(tzinfo=date.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, AttributeError): return ''


def _substack(source, deadline, limit):
    p = urlsplit(source)
    if p.hostname == 'substack.com':
        response = fetch_public(source, deadline=deadline, max_bytes=4*1024*1024)
        soup = BeautifulSoup(response.content, 'html.parser')
        links = {}
        prefix = p.path + '/note/c-'
        for anchor in soup.select('a[href]'):
            target = urljoin(source, anchor['href'])
            path = urlsplit(target)
            if path.hostname == 'substack.com' and path.path.startswith(prefix) and re.fullmatch(re.escape(prefix)+r'\d+/?',path.path):
                canonical = normalize_social_url(target)
                links[canonical] = {'url':canonical,'title':anchor.get_text(' ',strip=True)[:200] or 'Substack Note'}
        if not links:
            raise SocialSourceError('Substack did not expose a readable public Notes list. Open the author page to check access; no successful empty scan was assumed.')
        return sorted(links.values(),key=lambda row:int(row['url'].rsplit('c-',1)[-1]),reverse=True)[:limit]
    response = fetch_public(source + '/feed', deadline=deadline, max_bytes=4*1024*1024)
    try: root = ET.fromstring(response.content)
    except ET.ParseError:
        raise SocialSourceError('The publication did not return a readable public RSS feed.') from None
    if root.tag not in ('rss', '{http://www.w3.org/2005/Atom}feed'):
        raise SocialSourceError('The publication returned a page instead of a public feed.')
    if root.tag == 'rss' and root.find('channel') is None:
        raise SocialSourceError('The publication returned an incomplete RSS feed.')
    rows = []
    entries = root.findall('./channel/item') + root.findall('{http://www.w3.org/2005/Atom}entry')
    for item in entries:
        target = item.findtext('link') or ''
        if not target:
            link = item.find('{http://www.w3.org/2005/Atom}link')
            target = link.get('href','') if link is not None else ''
        target = urljoin(response.url, target)
        parsed = urlsplit(target)
        # A publication feed must not import arbitrary off-site destinations.
        allowed = {p.hostname, urlsplit(response.url).hostname}
        if parsed.hostname not in allowed or parsed.scheme != 'https' or parsed.username or parsed.password:
            continue
        if not re.fullmatch(r'/p/[^/]+/?', parsed.path): continue
        rows.append({'url':normalize_social_url(target),
            'title':item.findtext('title') or item.findtext('{http://www.w3.org/2005/Atom}title') or 'Substack post',
            'published_at':_stamp(item.findtext('pubDate') or item.findtext('{http://www.w3.org/2005/Atom}published') or '')})
    if entries and not rows:
        raise SocialSourceError('The feed returned no verifiable post links for this publication.')
    # Feed order is publisher-defined; pinned posts must not hide newer entries.
    rows.sort(key=lambda row:row['published_at'],reverse=True)
    return list({row['url']:row for row in rows}.values())[:limit]


def _twitter(source, deadline, limit):
    if '/status/' in source or '/article/' in source:
        ident = source.rstrip('/').split('/')[-1]
        data = _json('https://api.fxtwitter.com/2/status/' + ident, deadline)
        post = data.get('tweet') or {}
        handle = (post.get('author') or {}).get('screen_name') or ''
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', handle):
            raise SocialSourceError('X did not return the original author. Reimport an original post link.')
        source = 'https://x.com/' + handle
    handle = source.rsplit('/',1)[-1]
    response = fetch_public('https://syndication.twitter.com/srv/timeline-profile/screen-name/' + handle,
                            deadline=deadline,max_bytes=4*1024*1024)
    soup = BeautifulSoup(response.content,'html.parser')
    script = soup.find('script',id='__NEXT_DATA__')
    try:
        data = json.loads(script.string or script.get_text()) if script else {}
        entries = data['props']['pageProps']['timeline']['entries']
        if not isinstance(entries,list): raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise SocialSourceError('X did not expose its public author timeline. It may require sign-in or restrict automated access. Open the original profile; this was not counted as an empty successful check.') from None
    rows = []
    for entry in entries:
        tweet = (entry.get('content') or {}).get('tweet') or {}
        author = tweet.get('user') or {}
        ident = str(tweet.get('id_str') or tweet.get('id') or '')
        # Skip recommendations/reposts by other authors, not just matching names.
        if author.get('screen_name','').lower() != handle.lower() or not ident.isdigit(): continue
        rows.append({'url':'https://x.com/i/status/'+ident,
            'title':(tweet.get('full_text') or tweet.get('text') or 'X post').splitlines()[0][:200],
            'channel_url':source,
            'published_at':_stamp(tweet.get('created_at') or '')})
    if entries and not rows:
        raise SocialSourceError('X returned no verifiable posts for this author. Check the original profile.')
    rows.sort(key=lambda row:int(row['url'].rsplit('/',1)[-1]),reverse=True)
    return list({row['url']:row for row in rows}.values())[:limit]


def list_author_updates(url, platform, limit=15):
    source = author_url(platform,url)
    deadline = time.monotonic()+15
    rows = _twitter(source,deadline,limit) if platform=='twitter' else _substack(source,deadline,limit)
    if platform == 'substack':
        for row in rows: row['channel_url'] = source
    return rows
