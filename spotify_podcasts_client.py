"""Resolve Spotify episode shares to independently published podcast RSS audio."""
import ipaddress
import json
import re
import socket
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urljoin, urlsplit
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup
from apple_podcasts_client import Podcast, Episode, _stable_eid, _parse_duration


class SpotifySourceError(ValueError):
    """An actionable public-source failure, not a Spotify login requirement."""


def spotify_episode_id(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        match = re.fullmatch(r'/(?:intl-[a-zA-Z-]+/)?(?:embed/)?episode/([A-Za-z0-9]{22})/?', parsed.path)
        if parsed.scheme == 'https' and parsed.hostname == 'open.spotify.com' and not parsed.username and not parsed.password and parsed.port in (None, 443) and match:
            return match[1]
    except ValueError:
        pass
    return ''


def is_spotify_url(url: str) -> bool:
    try:
        return urlsplit(url.strip()).hostname == 'open.spotify.com'
    except ValueError:
        return False


def _validate_public_url(url: str):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise SpotifySourceError('The public podcast source returned an unsupported URL. Use its Apple Podcasts link or upload complete audio.')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise OSError('Not a public destination')
    except OSError:
        raise SpotifySourceError('The public podcast source is not reachable. Retry, use its Apple Podcasts link, or upload complete audio.') from None


def _open_public(url: str, deadline: float, headers=None):
    for _ in range(7):
        if time.monotonic() >= deadline:
            raise SpotifySourceError('Public podcast lookup timed out. Please retry.')
        _validate_public_url(url)
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 PodcastReader/1.0', **(headers or {})},
                                timeout=(4, min(12, max(1, deadline - time.monotonic()))), stream=True, allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            destination = response.headers.get('Location')
            response.close()
            if not destination:
                break
            url = urljoin(url, destination)
            continue
        if response.status_code >= 400:
            response.close()
            raise SpotifySourceError('The public podcast source is temporarily unavailable or restricted. Retry, use its Apple Podcasts link, or upload complete audio.')
        return response
    raise SpotifySourceError('The public podcast source redirected too many times. Use its Apple Podcasts link or upload complete audio.')


def _get_bytes(url: str, deadline: float, limit=32 * 1024 * 1024) -> bytes:
    response = _open_public(url, deadline)
    try:
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > limit or time.monotonic() >= deadline:
                raise SpotifySourceError('The public podcast feed is too large or slow to read. Use its Apple Podcasts link or upload complete audio.')
            chunks.append(chunk)
        return b''.join(chunks)
    finally:
        response.close()


def _probe_audio(url: str, deadline: float):
    response = _open_public(url, deadline, {'Range': 'bytes=0-0'})
    try:
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type or 'application/json' in content_type:
            raise SpotifySourceError('The publisher returned a web page instead of public audio. Use its Apple Podcasts link or upload complete audio.')
    finally:
        response.close()


@dataclass
class SpotifyMetadata:
    title: str
    show: str
    duration: int = 0
    published: str = ''


@dataclass
class SpotifyResolution:
    podcast: Podcast
    episode: Episode


def _metadata(html: bytes, episode_id: str) -> SpotifyMetadata:
    soup = BeautifulSoup(html, 'html.parser')
    script = soup.find('script', id='__NEXT_DATA__')
    try:
        entity = json.loads(script.get_text())['props']['pageProps']['state']['data']['entity']
        if entity.get('type') != 'episode' or entity.get('id', episode_id) != episode_id or entity.get('uri', 'spotify:episode:' + episode_id) != 'spotify:episode:' + episode_id:
            raise ValueError('Wrong Spotify entity')
        title, show = (entity.get('title') or entity.get('name') or '').strip(), (entity.get('subtitle') or '').strip()
        if not title or not show:
            raise ValueError('Missing episode/show title')
        release = entity.get('releaseDate') or {}
        published = release.get('isoString', '') if isinstance(release, dict) else str(release)
        return SpotifyMetadata(title, show, max(0, int(float(entity.get('duration') or 0) / 1000)), published)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SpotifySourceError('Cannot read this Spotify episode and show title. Spotify may be unavailable or its page format may have changed. Retry or use the Apple Podcasts link.') from None


def _name(value: str) -> str:
    return ''.join(character for character in unicodedata.normalize('NFKC', value).casefold() if character.isalnum())


def _date(value: str):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except ValueError:
        try:
            return parsedate_to_datetime(value).date()
        except (ValueError, TypeError):
            return None


def _matching_episodes(xml: bytes, pid: str, reference: SpotifyMetadata):
    try:
        channel = ElementTree.fromstring(xml).find('channel')
    except ElementTree.ParseError:
        return []
    if channel is None or _name(channel.findtext('title', '')) != _name(reference.show):
        return []
    matches = []
    ns = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}
    for item in channel.findall('item'):
        title = item.findtext('title', '').strip()
        if _name(title) != _name(reference.title):
            continue
        enclosure = item.find('enclosure')
        if enclosure is None or not enclosure.get('url'):
            continue
        media_type = enclosure.get('type', '').lower()
        if media_type and not media_type.startswith(('audio/', 'video/', 'application/octet-stream')):
            continue
        duration = _parse_duration(item.findtext('itunes:duration', '', ns))
        if duration and reference.duration and not .8 <= duration / reference.duration <= 1.25:
            continue  # Never substitute a short preview or a different recording.
        pub_date = item.findtext('pubDate', '')
        expected_date, actual_date = _date(reference.published), _date(pub_date)
        if expected_date and actual_date and abs((expected_date - actual_date).days) > 3:
            continue
        audio_url = enclosure.get('url')
        try:
            pub_date = parsedate_to_datetime(pub_date).isoformat()
        except (ValueError, TypeError):
            pass
        matches.append(Episode(eid=_stable_eid(item.findtext('guid', ''), title, audio_url), pid=pid,
                               title=title, description=item.findtext('description', ''), duration=max(duration, reference.duration),
                               pub_date=pub_date,
                               audio_url=audio_url, cover_url='', shownotes=''))
    return matches


def resolve_spotify_episode(url: str) -> SpotifyResolution:
    episode_id = spotify_episode_id(url)
    if not episode_id:
        raise SpotifySourceError('Paste a Spotify episode link (https://open.spotify.com/episode/...). Show, music and shortened links are not supported; copy the episode share link.')
    deadline = time.monotonic() + 45
    try:
        metadata = _metadata(_get_bytes('https://open.spotify.com/embed/episode/' + episode_id, deadline, 4 * 1024 * 1024), episode_id)
        search = json.loads(_get_bytes('https://itunes.apple.com/search?' + urlencode({'term': metadata.show, 'entity': 'podcast', 'limit': 12}), deadline, 2 * 1024 * 1024))
        candidates = [row for row in search.get('results', []) if row.get('feedUrl') and row.get('collectionId') and _name(row.get('collectionName', '')) == _name(metadata.show)]
        results, feeds, failures = {}, set(), 0
        for row in candidates[:4]:
            if row['feedUrl'] in feeds:
                continue
            feeds.add(row['feedUrl'])
            pid = 'apple_' + str(row['collectionId'])
            try:
                matches = _matching_episodes(_get_bytes(row['feedUrl'], deadline), pid, metadata)
            except (requests.RequestException, SpotifySourceError):
                failures += 1
                continue
            for episode in matches:
                podcast = Podcast(pid, row['collectionName'], row.get('artistName', ''), '', row.get('artworkUrl600') or row.get('artworkUrl100', ''), 1, row['feedUrl'])
                results[(episode.eid, episode.audio_url)] = SpotifyResolution(podcast, episode)
        if len(results) > 1:
            raise SpotifySourceError('Several public recordings match this Spotify episode. Use its Apple Podcasts episode link to choose the correct one, or upload complete audio.')
        if not results:
            if failures:
                raise SpotifySourceError('The matching public RSS feed could not be read. Please retry or use its Apple Podcasts link.')
            raise SpotifySourceError('No matching full episode was found in a public RSS feed. It may be Spotify-only, paid, a preview, or absent from the current feed. Use its Apple Podcasts link or upload complete audio.')
        result = next(iter(results.values()))
        _probe_audio(result.episode.audio_url, deadline)
        return result
    except SpotifySourceError:
        raise
    except (requests.RequestException, ValueError, TypeError):
        raise SpotifySourceError('Could not look up the public podcast source. Please retry or use its Apple Podcasts link.') from None
