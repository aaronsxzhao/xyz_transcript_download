"""Signed public-article images; arbitrary callers cannot use an open proxy."""
import asyncio
import hashlib
import re
import time
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from api.media import _signature, verify_media_signature
from api.covers import _cached_image, make_thumbnail, VARIANTS
from public_content_fetch import fetch_public, normalize_public_url
from social_content import SocialSourceError

router = APIRouter()


def signed_article_image(raw, size='article'):
    try: url = normalize_public_url(raw)
    except SocialSourceError: return ''
    expires = (int(time.time()) // 86400 + 7) * 86400
    return '/api/article-image?' + urlencode({'url':url, 'expires':expires,
        'signature':_signature('article-image:' + url, expires), 'size':size})


def sign_article_markdown(markdown):
    # Leave source links, code examples and stored Markdown untouched. Only
    # image tokens from the authenticated read response receive capabilities.
    from markdown_it import MarkdownIt
    parser = MarkdownIt()
    lines = markdown.splitlines(keepends=True)
    for token in reversed(parser.parse(markdown)):
        if token.type != 'inline' or not token.map: continue
        images = []
        def walk(children):
            for child in children or []:
                if child.type == 'image': images.append(child.attrGet('src'))
                walk(child.children)
        walk(token.children)
        if not images: continue
        start,end = token.map
        block = ''.join(lines[start:end])
        for url in images:
            if not url or not url.startswith(('http://','https://')): continue
            pattern = r'(!\[(?:\\.|[^\]\\\n])*\]\()' + re.escape(url) + r'(\))'
            block = re.sub(pattern, lambda match:match[1] + signed_article_image(url) + match[2], block)
        lines[start:end] = [block] + [''] * (end-start-1)
    return ''.join(lines)


def sign_web_task(task):
    from article_markdown import repair_web_attribution
    result = dict(task)
    if result.get('thumbnail', '').startswith(('https://','http://')):
        result['thumbnail'] = signed_article_image(result['thumbnail'], 'cover')
    if result.get('style') == 'original':
        if result.get('markdown'): result['markdown'] = sign_article_markdown(repair_web_attribution(result['markdown'], result.get('url') or ''))
        if result.get('versions'):
            result['versions'] = [{**v,'content':sign_article_markdown(repair_web_attribution(v['content'], result.get('url') or ''))}
                                 if v.get('style') == 'original' and v.get('content') else v for v in result['versions']]
    return result


@router.get('/api/article-image')
async def article_image(request: Request, url: str, expires: int, signature: str, size: str = 'article'):
    if size not in VARIANTS:
        raise HTTPException(422, 'Unknown image size', headers={'Cache-Control':'no-store'})
    if not verify_media_signature('article-image:' + url, expires, signature):
        raise HTTPException(403, 'Image link expired. Refresh the article to renew it.', headers={'Cache-Control':'no-store'})
    try:
        url = normalize_public_url(url)
        async def origin():
            def fetch():
                response = fetch_public(url)
                if response.content_type and not response.content_type.startswith('image/'):
                    raise ValueError('Source is not an image')
                return make_thumbnail(response.content, size)
            return await asyncio.to_thread(fetch)
        key = hashlib.sha256(('web-image-v1:' + size + ':' + url).encode()).hexdigest()
        content, source = await _cached_image(url, key, variant=size, fetcher=origin)
    except (HTTPException, SocialSourceError) as error:
        return Response(status_code=error.status_code if isinstance(error,HTTPException) else 502,
                        headers={'Cache-Control':'no-store','Retry-After':'3'})
    etag = '"' + hashlib.sha256(content).hexdigest()[:24] + '"'
    headers = {'Cache-Control':'private, max-age=86400','ETag':etag,'X-Artwork-Cache':source,'X-Content-Type-Options':'nosniff'}
    return Response(status_code=304, headers=headers) if request.headers.get('if-none-match') == etag else Response(content,media_type='image/webp',headers=headers)
