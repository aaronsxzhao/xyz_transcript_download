"""Publication labels from explicit source metadata, independent of authors."""
import json


def clean_publication(value):
    if not isinstance(value, str):
        return ''
    value = ' '.join(value.split())
    return value if 0 < len(value) <= 200 and value.casefold() != 'substack' else ''


def substack_publication_data(soup):
    node = soup.find('script', id='preloads-json')
    try:
        data = json.loads(node.string or '') if node else {}
        return data.get('pub', {}) if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def publication_name(soup, article=None):
    """No domain/title guessing: absent evidence leaves the existing fallback."""
    for meta in soup.find_all('meta', attrs={'property':'og:site_name'}):
        name = clean_publication(meta.get('content'))
        if name:
            return name
    pub = substack_publication_data(soup)
    name = clean_publication(pub.get('name')) if isinstance(pub, dict) else ''
    if name:
        return name
    for key in ('isPartOf', 'publisher'):
        value = (article or {}).get(key)
        for item in value if isinstance(value, list) else [value]:
            name = clean_publication(item.get('name') if isinstance(item, dict) else item)
            if name:
                return name
    return ''


def substack_publication(data, post, url, deadline):
    """Use the API envelope first; optional HTML must match its publication ID."""
    from bs4 import BeautifulSoup
    from social_content import _read, SocialSourceError
    import time
    for container in (data, post):
        for key in ('publication', 'pub'):
            pub = container.get(key)
            if isinstance(pub, dict):
                name = clean_publication(pub.get('name'))
                if name and (not post.get('publication_id') or not pub.get('id') or str(pub['id']) == str(post['publication_id'])):
                    return name
    if not post.get('publication_id'):
        return ''
    try:
        raw, _ = _read(url, min(deadline, time.monotonic() + 8))
        pub = substack_publication_data(BeautifulSoup(raw, 'html.parser'))
        if isinstance(pub, dict) and str(pub.get('id')) == str(post['publication_id']):
            return clean_publication(pub.get('name'))
    except SocialSourceError:
        pass  # An unavailable optional label must not lose a complete article.
    return ''
