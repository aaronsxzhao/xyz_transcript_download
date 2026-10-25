"""Extensible source resolution: platform adapters first, public documents next."""
import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, urljoin

from bs4 import BeautifulSoup

from public_content_fetch import fetch_public, normalize_public_url
from social_content import SocialContent, SocialSourceError, html_markdown, _escape, _link, _image_url, social_platform, resolve_social_content

DOCUMENT_PLATFORMS = ('twitter', 'substack', 'web')
EXTRACTION_VERSION = 'public-article-v1'


@dataclass
class ContentDocument(SocialContent):
    content_type: str = 'article'
    canonical_url: str = ''
    attachments: list[dict] = field(default_factory=list)

    def markdown(self):
        markdown = super().markdown()
        # A domain is a source/channel fallback, not a discovered author name.
        if self.author == urlsplit(self.url).hostname:
            prefix = f'# {_escape(self.title)}\n\nAuthor: {_escape(self.author)}\n\n'
            if markdown.startswith(prefix):
                markdown = markdown.replace(prefix, prefix.replace('\n\nAuthor:', '\n\nSource:'), 1)
        return markdown

    def metadata(self):
        result = {'type': self.content_type, 'canonical_url': self.canonical_url or self.url,
                'attachments': self.attachments, 'access': 'complete', 'extractor': EXTRACTION_VERSION}
        if self.media:
            result.update(media=self.media, source_body=self.body)
        return result


def saved_web_media(task):
    """Regenerate saved media transcripts without refetching an expired source.

    Article refreshes still resolve the live page. Older direct-media imports
    have a canonical URL but no snapshot; their original body was just a link.
    Actual downloads continue through the public URL/DNS validation boundary.
    """
    if not task or task.get('platform') != 'web':
        return None
    transcript = task.get('transcript') or {}
    text = transcript.get('text')
    meta = task.get('source_metadata') or {}
    if not isinstance(text, str) or len(text) <= 50 or meta.get('type') not in ('audio', 'video'):
        return None
    try:
        url = normalize_public_url(task['url'])
        media = meta.get('media') or [{'url': meta.get('canonical_url') or url,
                                      'kind': meta['type'], 'duration': task.get('duration') or 0}]
        if not isinstance(media, list) or not media or any(item.get('kind') not in ('audio', 'video') for item in media):
            return None
        media = [dict(item, url=normalize_public_url(item['url'])) for item in media]
        return ContentDocument('web', url, task.get('title') or urlsplit(url).hostname,
            meta.get('source_body') or f'[Original media]({_link(media[0]["url"], url)})',
            author=task.get('channel') or '', published=task.get('published_at') or '',
            thumbnail=task.get('thumbnail') or '', media=media, content_type=meta['type'],
            canonical_url=meta.get('canonical_url') or url)
    except (SocialSourceError, KeyError, TypeError, AttributeError):
        return None


def normalize_document_url(url):
    p = urlsplit(normalize_public_url(url))
    query = urlencode([(key, value) for key, value in parse_qsl(p.query, keep_blank_values=True)
                       if not key.lower().startswith('utm_') and key.lower() not in ('fbclid', 'gclid')])
    return urlunsplit((p.scheme, p.netloc, p.path, query, ''))


def _articles(soup):
    def objects(value):
        if isinstance(value, list):
            for item in value: yield from objects(item)
        elif isinstance(value, dict):
            yield value
            yield from objects(value.get('@graph'))
    for script in soup.find_all('script', type='application/ld+json'):
        try: data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError): continue
        for item in objects(data):
            types = item.get('@type', [])
            if isinstance(types, str): types = [types]
            if any(kind in ('Article', 'BlogPosting', 'NewsArticle', 'TechArticle', 'ScholarlyArticle') for kind in types):
                yield item


def extract_public_article(raw, url, content_type='text/html'):
    """Preserve source structure without an LLM, fixed word target or truncation."""
    url = normalize_document_url(url)
    host = urlsplit(url).hostname
    if content_type == 'text/plain':
        text = raw.decode('utf-8-sig', errors='strict')
        if not text.strip() or '\x00' in text: raise SocialSourceError('This link did not return readable original text.')
        return ContentDocument('web', url, urlsplit(url).path.rsplit('/', 1)[-1] or host, _escape(text), author=host)
    if content_type not in ('text/html', 'application/xhtml+xml', ''):
        raise SocialSourceError('This file type is not supported yet. Use a public article page or a direct audio/video link.')
    soup = BeautifulSoup(raw, 'html.parser')
    base_tag = soup.find('base', href=True)
    base = (_link(base_tag['href'], url) if base_tag else '') or url
    records = list(_articles(soup))
    data = records[0] if records else {}
    if any(item.get('isAccessibleForFree') in (False, 'False', 'false') for item in records):
        raise SocialSourceError('This article requires purchase or a subscription. Its preview was not imported as the complete article. Open the original link to check access.')
    def meta(*names):
        for name in names:
            tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'): return tag['content'].strip()
        return ''
    title = data.get('headline') or meta('og:title', 'twitter:title') or (soup.title.get_text(' ', strip=True) if soup.title else '')
    published = data.get('datePublished') or meta('article:published_time', 'date', 'datePublished')
    if not published:
        timestamp = soup.find('time', datetime=True)
        if timestamp: published = timestamp['datetime']
    author = data.get('author') or meta('author')
    if not isinstance(author, list): author = [author]
    author = ', '.join(str(item.get('name') or '') if isinstance(item, dict) else str(item or '') for item in author).strip(', ')
    canonical = soup.find('link', rel='canonical')
    canonical = _link(canonical.get('href'), base) if canonical else url
    cover = data.get('image') or meta('og:image', 'twitter:image')
    if isinstance(cover, list): cover = cover[0] if cover else ''
    if isinstance(cover, dict): cover = cover.get('url') or cover.get('contentUrl')
    cover = _link(cover, base)
    # Remove site chrome, not substantive headers/captions inside the article.
    for node in soup.select('script,style,noscript,nav,aside,form,button,dialog,[hidden],[aria-hidden="true"],.cookie-banner,.cookie-consent,.comments,#comments'):
        node.decompose()
    candidates = (soup.select('.post-body, .entry-content, .post-content, .article-body, .article-content')
                  or soup.select('article') or soup.select('main, [role="main"]'))
    if candidates:
        # Prefer the complete readable container; never extract only a preview
        # paragraph or the first matching descendant of a multi-part article.
        root = max(candidates, key=lambda node: len(node.get_text(' ', strip=True)))
    else:
        root = soup.body or soup
        for node in root.select('header,footer'): node.decompose()
    text = root.get_text(' ', strip=True)
    if not text or (len(text) < 200 and not root.find(['h1', 'h2', 'p'])):
        raise SocialSourceError('No complete article text was exposed. This page may require JavaScript, sign-in or a subscription. Open the original link; a preview was not saved as a complete article.')
    gate = root.select_one('[data-paywall],.paywall,.paywall-content,.subscriber-only,.members-only-content')
    if gate:
        raise SocialSourceError('The page contains restricted or preview-only content. Sign-in or purchase may be required; the preview was not saved as a complete article.')
    if not candidates:
        linked = sum(len(a.get_text(' ', strip=True)) for a in root.find_all('a'))
        if linked > len(text) * .6:
            raise SocialSourceError('This looks like an index or link directory. Use the individual article link.')
    title = str(title or (root.h1.get_text(' ', strip=True) if root.h1 else host))
    # The reading wrapper supplies the title once. Keep distinct source headings.
    if root.h1 and root.h1.get_text(' ', strip=True) == title:
        root.h1.decompose()
    # Numbered standalone bold source headings are common on older blogs.
    # Promote their existing structure without inventing chapter names.
    for paragraph in root.find_all('p'):
        bold = paragraph.find(['strong', 'b'], recursive=False)
        value = paragraph.get_text(' ', strip=True)
        if bold and value == bold.get_text(' ',strip=True) and len(value) <= 180 and re.match(r'^\d+[.)]\s+\S',value):
            paragraph.name = 'h2'
    if not cover:
        first_image = root.find('img')
        if first_image: cover = _image_url(first_image, base)
    attachments, seen = [], set()
    for node in root.find_all(['audio', 'video', 'iframe']):
        source = node.find('source')
        target = _link(node.get('src') or (source.get('src') if source else ''), base)
        if target and target not in seen:
            seen.add(target)
            attachments.append({'url': target, 'kind': node.name if node.name != 'iframe' else 'embedded', 'title': node.get('title') or 'Embedded media'})
    body = html_markdown(str(root), base)
    if cover and cover not in body:
        body = f'![Article cover]({cover})\n\n' + body
    if not body.strip(): raise SocialSourceError('The website did not expose readable original content.')
    return ContentDocument('web', url, title, body, author or host, published, cover,
                           canonical_url=canonical, attachments=attachments)


def resolve_content(url):
    if social_platform(url):
        try:
            return resolve_social_content(url)
        except SocialSourceError as error:
            host = urlsplit(url).hostname or ''
            # /p/ is a discovery hint for custom Substack domains, not proof
            # that every blog using that path belongs to Substack. Never fall
            # back after an explicit subscription/access restriction.
            if social_platform(url) != 'substack' or host == 'substack.com' or host.endswith('.substack.com') or not ('HTTP 404' in str(error) or 'Custom domains must serve' in str(error)):
                raise
    url = normalize_document_url(url)
    response = fetch_public(url, media_headers_only=True)
    if response.content_type.startswith(('audio/', 'video/')):
        kind = response.content_type.split('/')[0]
        title = urlsplit(response.url).path.rsplit('/', 1)[-1] or 'Original media'
        return ContentDocument('web', url, title, f'[Original {kind}]({_link(response.url, url)})',
            author=urlsplit(response.url).hostname, media=[{'url':response.url, 'kind':kind, 'duration':0}], content_type=kind,
            canonical_url=response.url)
    return extract_public_article(response.content, response.url, response.content_type)
