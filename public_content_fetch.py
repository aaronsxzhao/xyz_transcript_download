"""Bounded public-document requests with DNS pinning and redirect validation.

Only the chosen public address is contacted; Host/SNI still use the source
hostname. Proxy and CA configuration are honoured. No source cookies, API keys
or Authorization headers are forwarded to websites or across redirects.
"""
import ipaddress
import os
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit, urljoin, quote

import requests
import urllib3
from urllib3.util import Timeout, make_headers, parse_url

from social_content import SocialSourceError


def normalize_public_url(raw):
    try:
        if len(raw) > 4096 or any(ord(c) < 32 or c == '\\' for c in raw):
            raise ValueError()
        p = urlsplit(raw.strip())
        if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
            raise ValueError()
        host = p.hostname.encode('idna').decode('ascii').lower()
        try:
            if not ipaddress.ip_address(host).is_global: raise ValueError()
        except ValueError:
            if ':' in host or host.replace('.', '').isdigit(): raise ValueError()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        authority = '[' + host + ']' if ':' in host else host
        if p.port and p.port != (443 if p.scheme == 'https' else 80): authority += ':' + str(p.port)
        return urlunsplit((p.scheme, authority, quote(p.path or '/', safe="/%:@!$&'()*+,;=-._~"),
                           quote(p.query, safe="%:@!$&'()*+,;=/?-._~"), ''))
    except (ValueError, UnicodeError, AttributeError):
        raise SocialSourceError('Use a public HTTP or HTTPS article or media link. Private addresses, credentials and unusual ports are not supported.') from None


def public_addresses(host, port):
    try:
        addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise OSError()
        return addresses
    except (OSError, ValueError):
        raise SocialSourceError('The website does not resolve to a reachable public address. Check the link and retry.') from None


def _open(url, deadline):
    p = urlsplit(url)
    port = p.port or (443 if p.scheme == 'https' else 80)
    addresses = public_addresses(p.hostname, port)
    ca = os.getenv('REQUESTS_CA_BUNDLE') or os.getenv('CURL_CA_BUNDLE') or os.getenv('SSL_CERT_FILE') or requests.certs.where()
    options = {'cert_reqs': 'CERT_REQUIRED', 'ca_certs': ca}
    proxy = requests.utils.select_proxy(url, requests.utils.get_environ_proxies(url))
    if proxy:
        parsed = parse_url(proxy)
        headers = make_headers(proxy_basic_auth=parsed.auth) if parsed.auth else None
        manager = urllib3.ProxyManager(proxy, proxy_headers=headers, **options)
    else:
        manager = urllib3.PoolManager(**options)
    try:
        # Resolve once, validate every answer, then use only those pinned IPs.
        # An unreachable IPv6/CDN address must not hide a working alternative.
        for index, address in enumerate(addresses):
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError()
            authority = '[' + address + ']' if ':' in address else address
            pinned = urlunsplit((p.scheme, authority + ':' + str(port), p.path or '/', p.query, ''))
            kwargs = {'assert_hostname': p.hostname, 'server_hostname': p.hostname} if p.scheme == 'https' else {}
            pool = manager.connection_from_url(pinned, pool_kwargs=kwargs)
            target = pinned if proxy and p.scheme == 'http' else urlunsplit(('', '', p.path or '/', p.query, ''))
            try:
                response = pool.urlopen('GET', target, headers={'Host': p.netloc, 'User-Agent': 'Mozilla/5.0 ContentReader/1.0',
                    'Accept': 'text/html,text/plain,audio/*,video/*,image/*;q=0.8', 'Accept-Encoding': 'gzip,deflate'},
                    redirect=False, retries=False, preload_content=False, assert_same_host=False,
                    timeout=Timeout(connect=min(4, remaining), read=min(12, remaining), total=remaining))
                return response, manager
            except urllib3.exceptions.ConnectTimeoutError:
                if index == len(addresses) - 1: raise
    except Exception:
        manager.clear()
        raise


@dataclass
class PublicResponse:
    url: str
    content_type: str
    content: bytes
    headers: dict


def fetch_public(url, *, deadline=None, max_bytes=8*1024*1024, media_headers_only=False, sink=None, progress_callback=None):
    deadline = deadline or time.monotonic() + 30
    url = normalize_public_url(url)
    try:
        for _ in range(6):
            if time.monotonic() >= deadline: raise TimeoutError()
            response, manager = _open(url, deadline)
            try:
                if response.status in (301, 302, 303, 307, 308):
                    target = response.headers.get('Location')
                    if not target: raise SocialSourceError('The website returned a redirect without a destination.')
                    url = normalize_public_url(urljoin(url, target))
                    continue
                if response.status in (401, 402, 403):
                    raise SocialSourceError('This source requires sign-in, purchase or permission. Its preview was not imported as a complete article. Open the original link to check access.')
                if response.status == 429:
                    raise SocialSourceError('The website is rate limited. Please retry later.')
                if response.status >= 400:
                    raise SocialSourceError(f'The website could not be read (HTTP {response.status}). Check the original link and retry.')
                kind = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
                if media_headers_only and kind.startswith(('audio/', 'video/')):
                    return PublicResponse(url, kind, b'', dict(response.headers))
                chunks, size = [], 0
                try: total = int(response.headers.get('Content-Length', 0))
                except (ValueError, TypeError): total = 0
                for chunk in response.stream(65536, decode_content=True):
                    size += len(chunk)
                    if size > max_bytes:
                        raise SocialSourceError('The source is too large to read completely. Nothing was silently truncated.')
                    if time.monotonic() >= deadline: raise TimeoutError()
                    if progress_callback: progress_callback(size, total)
                    if sink: sink.write(chunk)
                    else: chunks.append(chunk)
                return PublicResponse(url, kind, b''.join(chunks), dict(response.headers))
            finally:
                response.close()
                response.release_conn()
                manager.clear()
        raise SocialSourceError('The website redirected too many times.')
    except SocialSourceError:
        raise
    except (urllib3.exceptions.HTTPError, OSError, TimeoutError, ValueError):
        raise SocialSourceError('The website connection failed or timed out. Please retry; no incomplete content was saved as complete.') from None
