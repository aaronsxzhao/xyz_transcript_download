"""
Mock Xiaoyuzhou client for testing.
"""
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class MockPodcast:
    """Mock podcast data."""
    pid: str
    title: str
    author: str
    description: str
    cover_url: str


@dataclass
class MockEpisode:
    """Mock episode data."""
    eid: str
    pid: str
    title: str
    description: str
    duration: int
    pub_date: str
    audio_url: str


class MockXYZClient:
    """Mock Xiaoyuzhou API client for testing."""
    
    def __init__(self):
        self.podcasts = {}
        self.episodes = {}
        self._setup_default_data()
    
    def _setup_default_data(self):
        """Setup default test data."""
        # Default test podcast
        self.podcasts["test-podcast-123"] = MockPodcast(
            pid="test-podcast-123",
            title="Test Podcast",
            author="Test Author",
            description="A test podcast for unit testing",
            cover_url="https://example.com/cover.jpg",
        )
        
        # Default test episode
        self.episodes["test-episode-456"] = MockEpisode(
            eid="test-episode-456",
            pid="test-podcast-123",
            title="Test Episode",
            description="A test episode",
            duration=3600,
            pub_date="2024-01-15",
            audio_url="https://example.com/audio.mp3",
        )
    
    def get_podcast(self, pid: str) -> Optional[MockPodcast]:
        """Get podcast by ID."""
        return self.podcasts.get(pid)
    
    def get_podcast_by_url(self, url: str) -> Optional[MockPodcast]:
        """Get podcast by URL."""
        # Extract pid from URL
        if "podcast/" in url:
            pid = url.split("podcast/")[-1].split("?")[0]
            return self.podcasts.get(pid)
        return None
    
    def get_episode(self, eid: str) -> Optional[MockEpisode]:
        """Get episode by ID."""
        return self.episodes.get(eid)
    
    def get_episode_by_share_url(self, url: str) -> Optional[MockEpisode]:
        """Get episode by share URL."""
        # Extract eid from URL
        if "episode/" in url:
            eid = url.split("episode/")[-1].split("?")[0]
            return self.episodes.get(eid)
        return None
    
    def get_episodes_from_page(self, pid: str, limit: int = 50) -> List[MockEpisode]:
        """Get episodes for a podcast."""
        return [ep for ep in self.episodes.values() if ep.pid == pid][:limit]
    
    def _extract_id_from_url(self, url: str, type_: str) -> Optional[str]:
        """Extract ID from URL."""
        if f"{type_}/" in url:
            return url.split(f"{type_}/")[-1].split("?")[0]
        return None
    
    def add_test_podcast(self, pid: str, title: str = "Test", **kwargs) -> MockPodcast:
        """Add a test podcast."""
        podcast = MockPodcast(
            pid=pid,
            title=title,
            author=kwargs.get("author", "Author"),
            description=kwargs.get("description", "Description"),
            cover_url=kwargs.get("cover_url", "https://example.com/cover.jpg"),
        )
        self.podcasts[pid] = podcast
        return podcast
    
    def add_test_episode(self, eid: str, pid: str, title: str = "Test", **kwargs) -> MockEpisode:
        """Add a test episode."""
        episode = MockEpisode(
            eid=eid,
            pid=pid,
            title=title,
            description=kwargs.get("description", "Description"),
            duration=kwargs.get("duration", 3600),
            pub_date=kwargs.get("pub_date", "2024-01-15"),
            audio_url=kwargs.get("audio_url", "https://example.com/audio.mp3"),
        )
        self.episodes[eid] = episode
        return episode
