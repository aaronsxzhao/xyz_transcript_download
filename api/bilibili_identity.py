"""Read-time identity for previously resolved multipart short links."""

def video_source_url(task):
    """Use an already resolved Bilibili identity for legacy short-link imports."""
    from urllib.parse import urlparse
    import re
    original = task.get('url') or ''
    try:
        if urlparse(original).hostname not in ('b23.tv', 'www.b23.tv'):
            return original
        metadata = task.get('source_metadata') or {}
        part = task.get('bilibili_part') or metadata.get('bilibili_part') or {}
        resolved = part.get('url') or ''
        parsed = urlparse(resolved)
        if parsed.scheme in ('http', 'https') and parsed.hostname in ('bilibili.com', 'www.bilibili.com', 'm.bilibili.com') and re.fullmatch(r'/video/(?:BV[\w]+|av\d+)/?', parsed.path):
            return resolved
    except (ValueError, AttributeError, TypeError):
        pass
    return original

