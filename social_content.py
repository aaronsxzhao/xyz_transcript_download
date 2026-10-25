"""Public social sources: preserve text verbatim; send only media through AI."""
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup, NavigableString, Comment


class SocialSourceError(ValueError):
    pass


TWITTER_HOSTS = {'x.com', 'www.x.com', 'mobile.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com'}


def social_platform(url: str) -> str:
    try:
        p = urlsplit(url.strip())
        if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
            return ''
        host = p.hostname.lower()
        if host in TWITTER_HOSTS or host == 't.co':
            return 'twitter'
        if host == 'substack.com' or host.endswith('.substack.com') or re.match(r'^/(?:embed/)?p/[^/]+/?$', p.path):
            return 'substack'
    except ValueError:
        pass
    return ''


def normalize_social_url(url: str) -> str:
    p = urlsplit(url.strip())
    platform = social_platform(url)
    if not platform:
        raise SocialSourceError('Use an X post/article or a Substack post/Note link, rather than a profile or home page.')
    if platform == 'twitter' and p.hostname != 't.co':
        match = re.fullmatch(r'/(?:[^/]+/status|statuses|i/(?:status|web/status|article))/(\d+)(?:/(?:photo|video)/\d+)?/?', p.path)
        if not match:
            raise SocialSourceError('Use a specific X post or Article link. Profile, search and live Space links are not supported.')
        path = '/i/article/' + match[1] if '/article/' in p.path else '/i/status/' + match[1]
        return 'https://x.com' + path
    query = '' if re.fullmatch(r'/(?:embed/)?p/[^/]+/?',p.path) else urlencode([(key,value) for key,value in parse_qsl(p.query) if not key.startswith('utm_') and key not in ('fbclid','si')])
    return urlunsplit(('https', p.netloc.lower(), p.path.rstrip('/'), query, ''))


def _validate_public_url(url: str):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise SocialSourceError('The source returned an unsupported destination.')
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise OSError('Not public')
    except OSError:
        raise SocialSourceError('The source is not reachable at a public address. Check the link and retry.') from None


def _read(url: str, deadline: float) -> tuple[bytes, str]:
    for _ in range(6):
        host = (urlsplit(url).hostname or '').lower()
        if not any(host == domain or host.endswith('.' + domain) for domain in ('substack.com','fxtwitter.com','x.com','twitter.com','t.co')):
            from public_content_fetch import fetch_public
            response = fetch_public(url, deadline=deadline)
            return response.content, response.url
        _validate_public_url(url)
        if time.monotonic() >= deadline:
            raise SocialSourceError('Social source lookup timed out. Please retry later.')
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 ContentReader/1.0', 'Accept': 'application/json,text/html'},
                                    timeout=(4, min(12, max(1, deadline - time.monotonic()))), stream=True, allow_redirects=False)
        except requests.RequestException:
            raise SocialSourceError('Cannot connect to the social source. Please retry later.') from None
        try:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('Location')
                if not location:
                    raise SocialSourceError('The source returned an invalid redirect.')
                url = urljoin(url, location)
                continue
            if response.status_code in (401, 402, 403):
                raise SocialSourceError('Source access is restricted or requires a subscription/sign-in. Open the original link; a preview will not be imported as a complete article.')
            if response.status_code == 429:
                raise SocialSourceError('The source is rate limited. Wait before retrying.')
            if response.status_code >= 400:
                raise SocialSourceError(f'The source could not be read (HTTP {response.status_code}). It may have been removed or be temporarily unavailable.')
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 8 * 1024 * 1024 or time.monotonic() >= deadline:
                    raise SocialSourceError('The source is too large or slow to read completely. Nothing was silently truncated.')
                chunks.append(chunk)
            return b''.join(chunks), url
        except requests.RequestException:
            raise SocialSourceError('The source connection was interrupted. Retry to read its full content.') from None
        finally:
            response.close()
    raise SocialSourceError('The source redirected too many times.')


def _json(url: str, deadline: float):
    raw, _ = _read(url, deadline)
    try:
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError('Expected source object')
        return data
    except (ValueError, UnicodeError):
        raise SocialSourceError('The public source returned an unreadable response. It may require sign-in or have changed its page format.') from None


def public_media_target(url: str) -> str:
    """Check media redirects without buffering/downloading the recording twice."""
    for _ in range(6):
        _validate_public_url(url)
        try:
            response=requests.get(url,headers={'User-Agent':'Mozilla/5.0 ContentReader/1.0','Range':'bytes=0-0'},timeout=(4,10),stream=True,allow_redirects=False)
        except requests.RequestException:
            raise SocialSourceError('The media source could not be reached. Retry later.') from None
        try:
            if response.status_code in (301,302,303,307,308):
                destination=response.headers.get('Location')
                if not destination:raise SocialSourceError('The media source returned an invalid redirect.')
                url=urljoin(url,destination)
                continue
            if response.status_code>=400:raise SocialSourceError(f'The media source is unavailable or restricted (HTTP {response.status_code}).')
            return url
        finally:response.close()
    raise SocialSourceError('The media source redirected too many times.')


def _escape(text) -> str:
    return re.sub(r'([\\`*{}\[\]<>])', r'\\\1', str(text or ''))


def _link(url: str, base: str) -> str:
    if not str(url or '').strip():
        return ''
    url = urljoin(base, str(url).strip())
    try:
        return url.replace(' ', '%20').replace('(', '%28').replace(')', '%29') if urlsplit(url).scheme in ('http', 'https') else ''
    except ValueError:
        return ''


def html_markdown(html: str, base: str) -> str:
    """Render source structure, not nav/chrome or executable HTML."""
    def render(node):
        if isinstance(node,Comment):return ''
        if isinstance(node, NavigableString):
            return _escape(node)
        name = node.name
        if name in ('script', 'style', 'noscript', 'button', 'form'):
            return ''
        if name == 'pre':
            text = node.get_text()
            fence = '`' * max(3, max((len(m[0]) for m in re.finditer(r'`+', text)), default=0) + 1)
            return f'\n\n{fence}\n{text}\n{fence}\n\n'
        if name == 'code':
            text=node.get_text()
            fence='`'*max(1,max((len(m[0]) for m in re.finditer(r'`+',text)),default=0)+1)
            return fence+' '+text+' '+fence
        if name == 'table':
            rows = [[ ''.join(render(child) for child in cell.children).strip().replace('|', '\\|').replace('\n',' ') for cell in row.find_all(['td','th'],recursive=False)] for row in node.find_all('tr')]
            rows = [row for row in rows if row]
            if not rows: return ''
            width=max(map(len,rows))
            lines=['| '+' | '.join(row+['']*(width-len(row)))+' |' for row in rows]
            lines.insert(1,'| '+' | '.join(['---']*width)+' |')
            return '\n\n'+'\n'.join(lines)+'\n\n'
        if name == 'ol':
            try: start=int(node.get('start',1))
            except ValueError: start=1
            return '\n\n'+'\n'.join(f'{start+i}. '+''.join(render(child) for child in item.children).strip().replace('\n','\n   ') for i,item in enumerate(node.find_all('li',recursive=False)))+'\n\n'
        children = ''.join(render(child) for child in node.children)
        if re.fullmatch('h[1-6]', name or ''):
            return '\n\n' + '#' * int(name[1]) + ' ' + children.strip() + '\n\n'
        if name == 'br':
            return '  \n'
        if name == 'a':
            url = _link(node.get('href'), base)
            label = children.strip()
            if not url: return children
            if '\n\n' in label:
                # Markdown links cannot contain block paragraphs. Keep the
                # complete content and offer its destination separately.
                return children + f'\n\n[Open linked source]({url})\n\n'
            return f'[{label}]({url})'
        if name == 'img':
            url = next((target for attr in ('data-src','data-original','data-lazy-src','src')
                        if (target := _link(node.get(attr), base))), '')
            return f'\n\n![{_escape(node.get("alt", ""))}]({url})\n\n' if url else ''
        if name in ('strong', 'b', 'em', 'i'):
            marker = '**' if name in ('strong', 'b') else '*'
            return marker + children + marker
        if name == 'li':
            return '\n- ' + children.strip().replace('\n', '\n  ') + '\n'
        if name == 'blockquote':
            return '\n\n' + '\n'.join('> ' + line for line in children.strip().splitlines()) + '\n\n'
        if name in ('video', 'audio', 'iframe'):
            source = node.find('source') if name in ('video', 'audio') else None
            url = _link(node.get('src'), base) or _link(source.get('src') if source else '', base)
            return f'\n\n[Embedded media]({url})\n\n' if url else children
        if name in ('p', 'div', 'section', 'article', 'ul', 'ol', 'tr', 'table', 'figure', 'figcaption'):
            return '\n\n' + children.strip() + '\n\n'
        if name in ('td', 'th'):
            return children.strip() + ' | '
        return children
    soup = BeautifulSoup(html or '', 'html.parser')
    return ''.join(render(node) for node in soup.children).strip()


def _body_json(node) -> str:
    if isinstance(node,str):
        try: node=json.loads(node)
        except ValueError: return _escape(node)
    if not isinstance(node, dict):
        return ''
    text = _escape(node.get('text', ''))
    for mark in node.get('marks', []):
        kind = mark.get('type')
        if kind in ('bold', 'strong', 'italic', 'em', 'code'):
            symbol = '**' if kind in ('bold', 'strong') else '`' if kind == 'code' else '*'
            text = symbol + text + symbol
        if kind == 'link':
            url = _link(mark.get('attrs', {}).get('href'), 'https://substack.com')
            if url: text = f'[{text}]({url})'
    children = text + ''.join(_body_json(child) for child in node.get('content', []))
    kind = node.get('type')
    if kind in ('bullet_list','ordered_list'):
        start=node.get('attrs',{}).get('order',1)
        return '\n\n'+'\n'.join((str(start+i)+'. ' if kind=='ordered_list' else '- ')+''.join(_body_json(part) for part in child.get('content',[])).strip().replace('\n','\n  ') for i,child in enumerate(node.get('content',[])))+'\n\n'
    if kind == 'blockquote': return '\n\n'+'\n'.join('> '+line for line in children.strip().splitlines())+'\n\n'
    if kind == 'hard_break': return '  \n'
    if kind == 'heading': return '\n\n' + '#' * min(6, max(1, int(node.get('attrs', {}).get('level', 2)))) + ' ' + children + '\n\n'
    if kind == 'image':
        attrs = node.get('attrs', {}); url = _link(attrs.get('src'), 'https://substack.com')
        return f'\n\n![{_escape(attrs.get("alt"))}]({url})\n\n' if url else ''
    return children + ('\n\n' if kind in ('paragraph', 'blockquote', 'list_item') else '')


@dataclass
class SocialContent:
    platform: str
    url: str
    title: str
    body: str
    author: str = ''
    published: str = ''
    thumbnail: str = ''
    media: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.published:
            try:
                if not isinstance(self.published,str):raise ValueError('Unsupported date')
                try: parsed=datetime.fromisoformat(self.published.replace('Z','+00:00'))
                except ValueError: parsed=parsedate_to_datetime(self.published)
                self.published=parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).isoformat()
            except (ValueError,TypeError): self.published=''

    def markdown(self) -> str:
        return '\n\n'.join(part for part in [f'# {_escape(self.title)}',
            f'Author: {_escape(self.author)}' if self.author else '',
            f'Published: {_escape(self.published)}' if self.published else '',
            f'[Original source]({_link(self.url, self.url)})', self.body] if part)


def _media_url(url: str, platform: str, source: str = '') -> str:
    """Only known media hosts; arbitrary author-controlled download URLs are excluded."""
    p = urlsplit(str(url or ''))
    host = (p.hostname or '').lower()
    domains = ('twimg.com',) if platform == 'twitter' else ('substack.com', 'substackcdn.com', 'substack-video.com', 'cloudfront.net')
    own_video = platform == 'substack' and host == urlsplit(source).hostname and re.fullmatch(r'/api/v1/video/upload/[\w-]+/src', p.path)
    if p.scheme == 'https' and not p.username and not p.password and p.port in (None,443) and (own_video or any(host == domain or host.endswith('.' + domain) for domain in domains)):
        return url
    raise SocialSourceError('The post contains media on an unsupported host. Open the original media link directly; no attachment was silently skipped.')


def _twitter_article_image(media, base):
    return _link(((media or {}).get('media_info') or {}).get('original_img_url'), base)


def _twitter_article_body(article, base):
    """Restore Draft.js media at their referenced positions, not in a footer.

    Draft.js offsets count UTF-16 code units, including surrogate pairs. Preserve
    unrecognised entities as text; only replace a placeholder we can render.
    """
    content = article.get('content') or article.get('content_state') or {}
    blocks = content.get('blocks') or []
    if not blocks:
        raise SocialSourceError('X returned an Article preview without the full body. The preview was not imported as complete content.')
    entries = content.get('entityMap') or []
    entities = entries if isinstance(entries, dict) else {str(item['key']): item.get('value', {}) for item in entries if 'key' in item}
    media = {str(item.get('media_id')): item for item in article.get('media_entities', [])}
    cover = _twitter_article_image(article.get('cover_media') or article.get('cover_media_results'), base)
    parts = [f'![Article cover]({cover})'] if cover else []
    placed = {cover} if cover else set()
    for block in blocks:
        raw = block.get('text') or ''
        if block.get('type') == 'code-block':
            # A source may itself contain backtick fences.
            fence = '`' * max(3, max((len(m[0]) + 1 for m in re.finditer(r'`+', raw)), default=3))
            parts.append(f'{fence}\n{raw}\n{fence}')
            continue
        encoded = raw.encode('utf-16-le')
        spans = []
        for ref in block.get('entityRanges', []):
            entity = entities.get(str(ref.get('key')), {})
            payload = entity.get('data') or {}
            replacement, images = [], []
            if entity.get('type') == 'MEDIA':
                for item in payload.get('mediaItems') or []:
                    target = _twitter_article_image(media.get(str(item.get('mediaId'))), base)
                    if target:
                        replacement.append(f'![Article image]({target})')
                        images.append(target)
            elif entity.get('type') == 'MARKDOWN' and payload.get('markdown'):
                replacement.append(payload['markdown'])
            elif entity.get('type') == 'TWEET' and re.fullmatch(r'\d+', str(payload.get('tweetId', ''))):
                replacement.append(f'[Embedded X post](https://x.com/i/status/{payload["tweetId"]})')
            start, length = ref.get('offset'), ref.get('length')
            if replacement and isinstance(start, int) and isinstance(length, int) and start >= 0 and length >= 0 and (start + length) * 2 <= len(encoded):
                spans.append((start * 2, (start + length) * 2, '\n\n'.join(replacement), images))
        pieces, cursor = [], 0
        for start, end, replacement, images in sorted(spans):
            if start < cursor:
                continue
            try:
                preceding = encoded[cursor:start].decode('utf-16-le')
                encoded[end:].decode('utf-16-le')
            except UnicodeDecodeError:
                continue
            pieces.extend([_escape(preceding), replacement])
            placed.update(images)
            cursor = end
        pieces.append(_escape(encoded[cursor:].decode('utf-16-le')))
        prefix = {'header-one':'## ', 'header-two':'### ', 'header-three':'#### ', 'unordered-list-item':'- ', 'ordered-list-item':'1. ', 'blockquote':'> '}.get(block.get('type'), '')
        parts.append(prefix + ''.join(pieces))
    for item in media.values():
        target = _twitter_article_image(item, base)
        if target and target not in placed:
            parts.append(f'![Article image]({target})')
            placed.add(target)
    return '\n\n'.join(parts), cover


def _twitter(url: str, deadline: float) -> SocialContent:
    if '/i/article/' in url:
        raw, final = _read(url, deadline)
        soup = BeautifulSoup(raw, 'html.parser')
        for script in soup.find_all('script', type='application/ld+json'):
            try: data = json.loads(script.string or script.get_text())
            except ValueError: continue
            for article in data if isinstance(data, list) else [data]:
                if isinstance(article, dict) and article.get('articleBody'):
                    images = article.get('image') or []
                    if not isinstance(images, list): images = [images]
                    images = [_link(image.get('url') or image.get('contentUrl'), final) if isinstance(image, dict) else _link(image, final) for image in images]
                    images = list(dict.fromkeys(image for image in images if image))
                    body = '\n\n'.join([*(f'![Article image]({image})' for image in images), _escape(article['articleBody'])])
                    return SocialContent('twitter', final, article.get('headline') or 'X Article', body,
                                         published=article.get('datePublished') or '', thumbnail=images[0] if images else '')
        raise SocialSourceError('X did not expose this Article body publicly. Use the post linking to the Article or open it on X. A title/preview was not saved as a full Article.')
    ident = url.rsplit('/',1)[-1]
    # Public FxEmbed API v2 returns complete long-post text and Draft.js articles.
    data = _json('https://api.fxtwitter.com/2/status/' + ident, deadline)
    post = data.get('status') or data.get('tweet')
    if data.get('code') != 200 or not isinstance(post, dict) or post.get('type') == 'tombstone':
        raise SocialSourceError('X post unavailable, private, deleted or rate limited. Check the original link and retry later.')
    author = post.get('author') or {}
    raw_text=(post.get('raw_text') or {}).get('text') or ''
    text = _escape(max([post.get('text') or '',raw_text],key=len))
    article = post.get('article') or {}
    if article:
        body, _ = _twitter_article_body(article, url)
        text += '\n\n' + body
    media = post.get('media') or {}; attachments = []
    for photo in media.get('photos', []):
        target = _link(photo.get('url'), url)
        if target: text += f'\n\n![{_escape(photo.get("altText", ""))}]({target})'
    for video in media.get('videos', []):
        if video.get('type') == 'gif':
            text += f'\n\n[Animation]({_link(video.get("url"), url)})'
        else:
            attachments.append({'url':_media_url(video.get('url'), 'twitter'), 'kind':'video', 'duration':video.get('duration') or 0})
    for entry in article.get('media_entities', []):
        info = entry.get('media_info') or {}
        variants = info.get('variants') or (info.get('video_info') or {}).get('variants') or []
        variants = [row for row in variants if row.get('content_type', 'video/mp4') == 'video/mp4' and '.m3u8' not in row.get('url', '')]
        if variants:
            variant=max(variants,key=lambda row:row.get('bitrate') or row.get('bit_rate') or 0)
            attachments.append({'url':_media_url(variant.get('url'),'twitter'),'kind':'video','duration':((info.get('video_info') or info).get('duration_millis') or 0)/1000})
    quote = post.get('quote') or {}
    if quote.get('text'):
        text += '\n\n## Quoted post\n\n' + _escape(quote['text'])
        if quote.get('url'): text += f'\n\n[Quoted source]({_link(quote["url"],url)})'
    attachments = list({item['url']:item for item in attachments}.values())
    if not text.strip() and not attachments:
        raise SocialSourceError('X returned no readable text or media. Check source access and retry.')
    title = article.get('title') or (post.get('text') or 'X post').splitlines()[0][:120]
    return SocialContent('twitter', url, title, text.strip(), author.get('name') or author.get('display_name') or author.get('screen_name') or '', post.get('created_at') or '',
                         _twitter_article_image(article.get('cover_media') or article.get('cover_media_results'), url) or (media.get('photos') or [{}])[0].get('url', '') or ((media.get('videos') or [{}])[0].get('thumbnail_url') or ''), attachments)


def _substack(url: str, deadline: float) -> SocialContent:
    p = urlsplit(url)
    note = re.search(r'/(?:note/)?c-(\d+)(?:/|$)', p.path)
    if note:
        data = _json('https://substack.com/api/v1/reader/comment/' + note[1], deadline)
        item = (data.get('item') or {}).get('comment') or data.get('comment') or data
        if item.get('isTruncated') or item.get('body_is_truncated'):
            raise SocialSourceError('Substack returned an incomplete Note. Open the original link; a preview was not imported as a complete Note.')
        body = html_markdown(item.get('body_html', ''), url) or _body_json(item.get('body_json') or {}) or _escape(item.get('body', ''))
        if not body.strip(): raise SocialSourceError('Substack did not return this Note body. It may be private or removed.')
        author = item.get('user') or (data.get('item') or {}).get('user') or data.get('user') or {}; name = author.get('name') or item.get('name') or ''
        media=[]
        for attachment in item.get('attachments') or item.get('media_attachments') or []:
            upload=attachment.get('mediaUpload') or attachment.get('videoUpload') or attachment
            target=upload.get('url') or upload.get('src') or attachment.get('imageUrl')
            kind=attachment.get('type') or upload.get('type') or ''
            if kind in ('video','audio'):
                if not target and upload.get('id'):
                    target=f'https://substack.com/api/v1/{kind}/upload/{upload["id"]}/src'+('?type=mp4' if kind=='video' else '')
                media.append({'url':_media_url(target,'substack',url),'kind':kind,'duration':upload.get('duration') or 0})
            elif kind in ('image','photo') and target:
                body+=f'\n\n![Note image]({_link(target,url)})'
            elif kind in ('post','link'):
                metadata=attachment.get('linkMetadata') or attachment.get('post') or {}
                target=_link(metadata.get('url') or metadata.get('canonical_url'),url)
                if target: body+=f'\n\n[{_escape(metadata.get("title") or "Attached source")}]({target})'
        return SocialContent('substack', url, (item.get('body') or 'Substack Note').splitlines()[0][:120], body.strip(), name, item.get('date') or item.get('created_at') or '',media=media)
    match = re.fullmatch(r'/(?:embed/)?p/([^/]+)', p.path)
    if not match:
        raw, final = _read(url, deadline)
        final_parts = urlsplit(final)
        if final != url and social_platform(final) == 'substack' and re.fullmatch(r'/p/[^/]+', final_parts.path):
            return _substack(final, deadline)
        soup = BeautifulSoup(raw, 'html.parser')
        canonical = soup.find('link', rel='canonical')
        target = urljoin(final, canonical.get('href', '')) if canonical else ''
        if target and target != url and social_platform(target) == 'substack' and re.fullmatch(r'/p/[^/]+', urlsplit(target).path):
            return _substack(target, deadline)
        raise SocialSourceError('Use a specific Substack /p/ article or /note/c- Note link. This page did not expose a readable post.')
    data = _json(f'{p.scheme}://{p.netloc}/api/v1/posts/{match[1]}', deadline)
    post = data.get('post') or data
    if post.get('audience') in ('only_paid', 'paid', 'founding') or post.get('is_paywalled') or post.get('requires_subscription'):
        raise SocialSourceError('This Substack post requires a subscription. Its public preview will not be saved as the complete article. Open the original post with your subscription.')
    if not post.get('title') or not isinstance(post.get('body_html'), str):
        raise SocialSourceError('The link did not return a readable Substack post. Custom domains must serve the public Substack post API.')
    body = html_markdown(post['body_html'], url)
    attachments = []; video = post.get('videoUpload') or post.get('video_upload') or {}
    if video:
        target = video.get('url') or video.get('src')
        if not target and re.fullmatch(r'[\w-]+', str(video.get('id') or '')):
            target = f'{p.scheme}://{p.netloc}/api/v1/video/upload/{video["id"]}/src?type=mp4'
        if target: attachments.append({'url':_media_url(target, 'substack',url), 'kind':'video','duration':video.get('duration') or 0})
    elif post.get('podcast_url'):
        attachments.append({'url':_media_url(post['podcast_url'], 'substack'), 'kind':'audio','duration':post.get('podcast_duration') or 0})
    if not body.strip() and not attachments: raise SocialSourceError('Substack returned an empty article. Check access to the original post.')
    authors = post.get('publishedBylines') or []
    return SocialContent('substack', url, post['title'], body, ', '.join(str(a.get('name','')) for a in authors), post.get('post_date') or '', post.get('cover_image') or '', attachments)


def resolve_social_content(url: str) -> SocialContent:
    url = normalize_social_url(url)
    deadline = time.monotonic() + 45
    if urlsplit(url).hostname == 't.co':
        _, url = _read(url, deadline)
        url = normalize_social_url(url)
    return _twitter(url, deadline) if social_platform(url) == 'twitter' else _substack(url, deadline)
