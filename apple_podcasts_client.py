"""
Apple Podcasts client.
Fetches podcast metadata via iTunes Lookup API and episodes via RSS feeds.
"""

import hashlib
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import List, Optional
from xml.etree import ElementTree

import requests

from logger import get_logger

logger = get_logger("apple_podcasts")


@dataclass
class Podcast:
    pid: str
    title: str
    author: str
    description: str
    cover_url: str
    episode_count: int
    feed_url: str


@dataclass
class Episode:
    eid: str
    pid: str
    title: str
    description: str
    duration: int
    pub_date: str
    audio_url: str
    cover_url: str
    shownotes: str


def detect_platform(url: str) -> str:
    """Detect podcast platform from URL."""
    u = url.lower()
    if "xiaoyuzhoufm.com" in u:
        return "xiaoyuzhou"
    if "podcasts.apple.com" in u or "itunes.apple.com" in u:
        return "apple"
    return ""


def extract_apple_id(url: str) -> Optional[str]:
    """Extract numeric podcast ID from an Apple Podcasts URL."""
    m = re.search(r"/id(\d+)", url)
    return m.group(1) if m else None


def _parse_duration(text: str) -> int:
    """Parse duration string like '01:23:45' or '3600' to seconds."""
    if not text:
        return 0
    if ":" in text:
        parts = text.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _stable_eid(guid: str, title: str, audio_url: str) -> str:
    """Generate a stable episode ID from available metadata."""
    source = guid or audio_url or title
    return hashlib.sha256(source.encode()).hexdigest()[:24]


def get_podcast_by_url(url: str) -> Optional[Podcast]:
    """Fetch podcast metadata from an Apple Podcasts URL via iTunes Lookup API."""
    apple_id = extract_apple_id(url)
    if not apple_id:
        logger.warning(f"Could not extract Apple ID from URL: {url}")
        return None

    try:
        resp = requests.get(
            f"https://itunes.apple.com/lookup?id={apple_id}&entity=podcast",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            logger.warning(f"No results from iTunes Lookup for ID {apple_id}")
            return None

        r = results[0]
        feed_url = r.get("feedUrl", "")
        if not feed_url:
            name = r.get("collectionName") or r.get("trackName") or apple_id
            logger.warning(f"No feedUrl in iTunes Lookup for '{name}' (ID {apple_id}) - likely an Apple-exclusive podcast")
            return None

        return Podcast(
            pid=f"apple_{apple_id}",
            title=r.get("collectionName") or r.get("trackName") or "",
            author=r.get("artistName", ""),
            description=r.get("description", "") or r.get("collectionName", ""),
            cover_url=r.get("artworkUrl600") or r.get("artworkUrl100", ""),
            episode_count=r.get("trackCount", 0),
            feed_url=feed_url,
        )
    except Exception as e:
        logger.error(f"iTunes Lookup failed for {url}: {e}")
        return None


def get_episodes_from_feed(feed_url: str, pid: str = "", limit: int = 50) -> List[Episode]:
    """Fetch episodes from an RSS feed URL."""
    try:
        resp = requests.get(
            feed_url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch RSS feed {feed_url}: {e}")
        return []

    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as e:
        logger.error(f"Failed to parse RSS feed: {e}")
        return []

    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    channel = root.find("channel")
    if channel is None:
        return []

    episodes: List[Episode] = []
    for item in channel.findall("item"):
        if len(episodes) >= limit:
            break

        title_el = item.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        desc_el = item.find("description")
        description = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

        enclosure = item.find("enclosure")
        audio_url = ""
        if enclosure is not None:
            audio_url = enclosure.get("url", "")

        if not audio_url:
            continue

        guid_el = item.find("guid")
        guid = guid_el.text.strip() if guid_el is not None and guid_el.text else ""

        pub_el = item.find("pubDate")
        pub_date_raw = pub_el.text.strip() if pub_el is not None and pub_el.text else ""
        pub_date = ""
        if pub_date_raw:
            try:
                pub_date = parsedate_to_datetime(pub_date_raw).isoformat()
            except Exception:
                pub_date = pub_date_raw

        dur_el = item.find("itunes:duration", ns)
        duration_text = dur_el.text.strip() if dur_el is not None and dur_el.text else ""

        img_el = item.find("itunes:image", ns)
        cover_url = img_el.get("href", "") if img_el is not None else ""

        episodes.append(Episode(
            eid=_stable_eid(guid, title, audio_url),
            pid=pid,
            title=title,
            description=description[:500] if description else "",
            duration=_parse_duration(duration_text),
            pub_date=pub_date,
            audio_url=audio_url,
            cover_url=cover_url,
            shownotes="",
        ))

    logger.info(f"Parsed {len(episodes)} episodes from RSS feed")
    return episodes
