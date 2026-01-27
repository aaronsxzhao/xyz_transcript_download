"""
Xiaoyuzhou (小宇宙) API client.
Handles podcast and episode fetching with retry logic.
Tries public access first, falls back to authenticated access if needed.
"""

import re
import json
from dataclasses import dataclass
from typing import Optional, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import XYZ_API_BASE, DEFAULT_HEADERS
from auth import get_session_manager
from retry_utils import RetryableSession, get_request_timeout
from logger import get_logger

logger = get_logger("client")


@dataclass
class Podcast:
    """Represents a podcast."""
    pid: str
    title: str
    author: str
    description: str
    cover_url: str
    episode_count: int


@dataclass
class Episode:
    """Represents a podcast episode."""
    eid: str
    pid: str
    title: str
    description: str
    duration: int  # in seconds
    pub_date: str
    audio_url: str
    cover_url: str
    shownotes: str


class XyzClient:
    """Client for interacting with Xiaoyuzhou with retry logic."""

    def __init__(self):
        self.session_manager = get_session_manager()
        self.session = RetryableSession(headers=DEFAULT_HEADERS)

    def get_podcast_by_url(self, url: str) -> Optional[Podcast]:
        """
        Get podcast details by scraping the share page.
        
        Args:
            url: Podcast URL like https://www.xiaoyuzhoufm.com/podcast/xxx
            
        Returns:
            Podcast object or None
        """
        try:
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract from meta tags
            title_tag = soup.find('meta', {'property': 'og:title'})
            description_tag = soup.find('meta', {'property': 'og:description'})
            image_tag = soup.find('meta', {'property': 'og:image'})

            # Extract podcast ID from URL
            pid = self._extract_id_from_url(url, "podcast")

            # Try to get author from page content
            author = ""
            author_elem = soup.find('div', class_='author') or soup.find('span', class_='author')
            if author_elem:
                author = author_elem.get_text(strip=True)

            return Podcast(
                pid=pid or "",
                title=title_tag['content'] if title_tag else "",
                author=author,
                description=description_tag['content'] if description_tag else "",
                cover_url=image_tag['content'] if image_tag else "",
                episode_count=0,
            )

        except Exception as e:
            logger.error(f"Failed to get podcast: {e}")
            return None

    def search_podcast(self, keyword: str) -> List[Podcast]:
        """
        Search for podcasts by keyword using web search.
        Note: Limited functionality without API access.
        """
        # For now, suggest using URL directly
        logger.warning("Search not available. Please provide the podcast URL directly.")
        logger.info("Example: https://www.xiaoyuzhoufm.com/podcast/xxx")
        return []

    def get_podcast(self, pid: str) -> Optional[Podcast]:
        """Get podcast details by ID."""
        url = f"https://www.xiaoyuzhoufm.com/podcast/{pid}"
        return self.get_podcast_by_url(url)

    def get_episodes_from_page(self, pid: str, limit: int = 20) -> List[Episode]:
        """
        Get episodes by scraping the podcast page.
        
        Args:
            pid: Podcast ID
            limit: Maximum number of episodes
            
        Returns:
            List of episodes
        """
        url = f"https://www.xiaoyuzhoufm.com/podcast/{pid}"
        episodes = []

        try:
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find episode links
            episode_links = soup.find_all('a', href=re.compile(r'/episode/'))
            seen_eids = set()

            for link in episode_links[:limit * 2]:  # Get extra in case of duplicates
                href = link.get('href', '')
                eid = self._extract_id_from_url(href, "episode")
                
                if eid and eid not in seen_eids:
                    seen_eids.add(eid)
                    # Get episode details
                    episode = self.get_episode_by_share_url(
                        f"https://www.xiaoyuzhoufm.com/episode/{eid}"
                    )
                    if episode:
                        episode.pid = pid
                        episodes.append(episode)
                    
                    if len(episodes) >= limit:
                        break

        except Exception as e:
            logger.error(f"Failed to get episodes: {e}")

        return episodes

    def get_episodes(self, pid: str, limit: int = 20) -> List[Episode]:
        """Get episodes for a podcast."""
        return self.get_episodes_from_page(pid, limit)

    def get_episode(self, eid: str) -> Optional[Episode]:
        """Get a single episode by ID."""
        url = f"https://www.xiaoyuzhoufm.com/episode/{eid}"
        return self.get_episode_by_share_url(url)

    def get_episode_podcast_id(self, eid: str) -> Optional[str]:
        """
        Get the podcast ID for an episode.
        Useful for orphaned episodes that need to be categorized.
        
        Args:
            eid: Episode ID
            
        Returns:
            Podcast ID or None
        """
        episode = self.get_episode(eid)
        if episode and episode.pid:
            return episode.pid
        return None

    def get_episode_transcript(self, url: str) -> Optional[str]:
        """
        Check if Xiaoyuzhou already has a transcript/shownotes for the episode.
        
        Args:
            url: Episode URL
            
        Returns:
            Transcript text if available, None otherwise
        """
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for shownotes/transcript content
            # Try different possible selectors
            transcript = None
            
            # Look for shownotes section
            shownotes_div = soup.find('div', class_='shownotes') or \
                           soup.find('div', class_='episode-shownotes') or \
                           soup.find('div', class_='content') or \
                           soup.find('article')
            
            if shownotes_div:
                # Get text content
                text = shownotes_div.get_text(separator='\n', strip=True)
                # Check if it's substantial (not just timestamps)
                if len(text) > 500:  # Meaningful content
                    transcript = text
            
            # Also check for script tags with JSON data
            scripts = soup.find_all('script', type='application/json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    # Look for transcript in the data
                    if isinstance(data, dict):
                        if 'shownotes' in data and len(data.get('shownotes', '')) > 500:
                            transcript = data['shownotes']
                            break
                        # Check nested structures
                        for key, value in data.items():
                            if isinstance(value, dict) and 'shownotes' in value:
                                if len(value.get('shownotes', '')) > 500:
                                    transcript = value['shownotes']
                                    break
                except (json.JSONDecodeError, TypeError):
                    continue

            return transcript

        except Exception as e:
            return None

    def get_episode_by_share_url(self, url: str) -> Optional[Episode]:
        """
        Get episode from a share URL by scraping the page.
        Tries public access first, prompts for login if content is private.
        
        Args:
            url: Share URL like https://www.xiaoyuzhoufm.com/episode/xxx
            
        Returns:
            Episode object or None
        """
        # First try public access
        try:
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract metadata from og tags
            title_tag = soup.find('meta', {'property': 'og:title'})
            audio_tag = soup.find('meta', {'property': 'og:audio'})
            description_tag = soup.find('meta', {'property': 'og:description'})
            image_tag = soup.find('meta', {'property': 'og:image'})

            # Check if content is available
            if audio_tag and audio_tag.get('content'):
                # Public content - success!
                eid = self._extract_id_from_url(url, "episode")
                
                # Try to extract podcast ID from JSON data in the page
                pid = ""
                duration = 0
                pub_date = ""
                
                scripts = soup.find_all('script', type='application/json')
                for script in scripts:
                    try:
                        if not script.string:
                            continue
                        data = json.loads(script.string)
                        if isinstance(data, dict):
                            # Look for podcast info in various structures
                            podcast_data = data.get('podcast') or data.get('props', {}).get('pageProps', {}).get('podcast')
                            if podcast_data and isinstance(podcast_data, dict):
                                pid = podcast_data.get('id') or podcast_data.get('pid') or ""
                            
                            # Also check for episode data with podcast reference
                            episode_data = data.get('episode') or data.get('props', {}).get('pageProps', {}).get('episode')
                            if episode_data and isinstance(episode_data, dict):
                                if not pid:
                                    pid = episode_data.get('pid') or episode_data.get('podcastId') or ""
                                duration = episode_data.get('duration') or 0
                                pub_date = episode_data.get('pubDate') or episode_data.get('publishTime') or ""
                            
                            # Check for nested data
                            for key, value in data.items():
                                if isinstance(value, dict):
                                    if 'podcast' in value and isinstance(value['podcast'], dict):
                                        if not pid:
                                            pid = value['podcast'].get('id') or value['podcast'].get('pid') or ""
                                    if 'pid' in value and not pid:
                                        pid = value['pid']
                            
                            if pid:
                                break
                    except (json.JSONDecodeError, TypeError, KeyError):
                        continue
                
                return Episode(
                    eid=eid or "",
                    pid=pid,
                    title=title_tag['content'] if title_tag else "",
                    description=description_tag['content'] if description_tag else "",
                    duration=duration,
                    pub_date=pub_date,
                    audio_url=audio_tag['content'],
                    cover_url=image_tag['content'] if image_tag else "",
                    shownotes="",
                )

            # No audio URL - might be private content
            # Check for login prompt or paywall indicators
            page_text = soup.get_text().lower()
            if "登录" in page_text or "会员" in page_text or not title_tag:
                logger.warning("This episode may require login to access.")
                return self._get_episode_with_auth(url)

            # Has title but no audio - still try auth
            if title_tag and not audio_tag:
                logger.warning("Audio not found in public page. Trying authenticated access...")
                return self._get_episode_with_auth(url)

            logger.error("Could not find audio URL in share page")
            return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [401, 403]:
                logger.warning("This content requires login.")
                return self._get_episode_with_auth(url)
            logger.error(f"HTTP error: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse share URL: {e}")
            return None

    def _get_episode_with_auth(self, url: str) -> Optional[Episode]:
        """Try to get episode using authenticated session."""
        if not self.session_manager.ensure_authenticated():
            logger.error("Authentication required but not available")
            return None

        eid = self._extract_id_from_url(url, "episode")
        if not eid:
            return None

        # Try API endpoint with auth
        try:
            auth_session = self.session_manager.get_session()
            api_url = f"{XYZ_API_BASE}/v1/episode/get"
            response = auth_session.post(
                api_url, 
                json={"eid": eid},
                timeout=get_request_timeout(),
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            return self._parse_episode(data)
        except Exception as e:
            logger.error(f"Authenticated request failed: {e}")
            return None

    def _parse_episode(self, data: dict) -> Optional[Episode]:
        """Parse episode data from API response."""
        if not data:
            return None

        # Get audio URL - might be in different locations
        audio_url = ""
        media_key = data.get("mediaKey", "")
        if media_key:
            audio_url = data.get("media", {}).get("source", {}).get("url", "")
            if not audio_url:
                audio_url = data.get("enclosure", {}).get("url", "")

        return Episode(
            eid=data.get("eid", ""),
            pid=data.get("pid", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            duration=data.get("duration", 0),
            pub_date=data.get("pubDate", ""),
            audio_url=audio_url,
            cover_url=data.get("image", {}).get("picUrl", ""),
            shownotes=data.get("shownotes", ""),
        )

    def _extract_id_from_url(self, url: str, id_type: str) -> Optional[str]:
        """Extract podcast or episode ID from URL."""
        patterns = {
            "podcast": r"/podcast/([a-zA-Z0-9]+)",
            "episode": r"/episode/([a-zA-Z0-9]+)",
        }

        pattern = patterns.get(id_type)
        if pattern:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def extract_podcast_id(self, input_str: str) -> Optional[str]:
        """
        Extract podcast ID from various input formats.
        
        Args:
            input_str: Could be a URL or ID
            
        Returns:
            Podcast ID or None
        """
        # If it looks like a URL
        if "xiaoyuzhoufm.com" in input_str:
            return self._extract_id_from_url(input_str, "podcast")

        # If it's already an ID (alphanumeric)
        if re.match(r'^[a-zA-Z0-9]+$', input_str) and len(input_str) > 10:
            return input_str

        # Can't search without API, return None
        logger.warning("Please provide a podcast URL instead of name.")
        logger.info("Example: https://www.xiaoyuzhoufm.com/podcast/xxx")
        return None

    def extract_episode_id(self, input_str: str) -> Optional[str]:
        """
        Extract episode ID from various input formats.
        
        Args:
            input_str: Could be a URL or ID
            
        Returns:
            Episode ID or None
        """
        if "xiaoyuzhoufm.com" in input_str:
            return self._extract_id_from_url(input_str, "episode")

        if re.match(r'^[a-zA-Z0-9]+$', input_str) and len(input_str) > 10:
            return input_str

        return None


# Global client instance
_client: Optional[XyzClient] = None


def get_client() -> XyzClient:
    """Get or create the global XyzClient instance."""
    global _client
    if _client is None:
        _client = XyzClient()
    return _client
