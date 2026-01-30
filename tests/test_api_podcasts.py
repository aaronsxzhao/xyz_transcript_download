"""
API tests for podcasts router.
"""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestListPodcasts:
    """Tests for GET /api/podcasts"""
    
    async def test_list_podcasts_empty(self, client: AsyncClient):
        """Test listing podcasts when none exist."""
        response = await client.get("/api/podcasts")
        assert response.status_code == 200
        assert response.json() == []
    
    async def test_list_podcasts_with_data(
        self, client: AsyncClient, create_test_podcast
    ):
        """Test listing podcasts with existing data."""
        # Create test podcast
        create_test_podcast()
        
        response = await client.get("/api/podcasts")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) >= 1
        assert data[0]["pid"] == "test-podcast-123"
        assert data[0]["title"] == "Test Podcast"
    
    async def test_list_podcasts_multiple(
        self, client: AsyncClient, create_test_podcast
    ):
        """Test listing multiple podcasts."""
        create_test_podcast({"pid": "podcast-1", "title": "Podcast 1"})
        create_test_podcast({"pid": "podcast-2", "title": "Podcast 2"})
        
        response = await client.get("/api/podcasts")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) >= 2


class TestAddPodcast:
    """Tests for POST /api/podcasts"""
    
    async def test_add_podcast_valid_url(self, client: AsyncClient):
        """Test adding a podcast with valid URL."""
        with patch("api.routers.podcasts.get_client") as mock_client:
            mock_podcast = MagicMock()
            mock_podcast.pid = "new-podcast-789"
            mock_podcast.title = "New Podcast"
            mock_podcast.author = "Author"
            mock_podcast.description = "Description"
            mock_podcast.cover_url = "https://example.com/cover.jpg"
            
            mock_client.return_value.get_podcast_by_url.return_value = mock_podcast
            mock_client.return_value._extract_id_from_url.return_value = "new-podcast-789"
            
            response = await client.post(
                "/api/podcasts",
                json={"url": "https://www.xiaoyuzhoufm.com/podcast/new-podcast-789"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["pid"] == "new-podcast-789"
            assert data["title"] == "New Podcast"
    
    async def test_add_podcast_invalid_url(self, client: AsyncClient):
        """Test adding a podcast with invalid URL."""
        with patch("api.routers.podcasts.get_client") as mock_client:
            mock_client.return_value.get_podcast_by_url.return_value = None
            mock_client.return_value._extract_id_from_url.return_value = None
            mock_client.return_value.get_episode_by_share_url.return_value = None
            
            response = await client.post(
                "/api/podcasts",
                json={"url": "https://invalid-url.com/something"}
            )
            
            assert response.status_code == 404
    
    async def test_add_podcast_episode_url(self, client: AsyncClient):
        """Test adding a podcast using episode URL (should auto-subscribe to parent)."""
        with patch("api.routers.podcasts.get_client") as mock_client:
            # Mock episode
            mock_episode = MagicMock()
            mock_episode.eid = "episode-123"
            mock_episode.pid = "parent-podcast"
            mock_episode.title = "Episode Title"
            
            # Mock parent podcast
            mock_podcast = MagicMock()
            mock_podcast.pid = "parent-podcast"
            mock_podcast.title = "Parent Podcast"
            mock_podcast.author = "Author"
            mock_podcast.description = "Description"
            mock_podcast.cover_url = "https://example.com/cover.jpg"
            
            mock_client.return_value.get_podcast_by_url.return_value = None
            mock_client.return_value._extract_id_from_url.side_effect = lambda url, t: (
                "episode-123" if t == "episode" else None
            )
            mock_client.return_value.get_episode_by_share_url.return_value = mock_episode
            mock_client.return_value.get_podcast.return_value = mock_podcast
            
            response = await client.post(
                "/api/podcasts",
                json={"url": "https://www.xiaoyuzhoufm.com/episode/episode-123"}
            )
            
            assert response.status_code == 200
    
    async def test_add_podcast_missing_url(self, client: AsyncClient):
        """Test adding a podcast without URL."""
        response = await client.post("/api/podcasts", json={})
        assert response.status_code == 422  # Validation error


class TestGetPodcast:
    """Tests for GET /api/podcasts/{pid}"""
    
    async def test_get_podcast_exists(
        self, client: AsyncClient, create_test_podcast
    ):
        """Test getting an existing podcast."""
        create_test_podcast()
        
        response = await client.get("/api/podcasts/test-podcast-123")
        assert response.status_code == 200
        
        data = response.json()
        assert data["pid"] == "test-podcast-123"
        assert data["title"] == "Test Podcast"
    
    async def test_get_podcast_not_found(self, client: AsyncClient):
        """Test getting a non-existent podcast."""
        response = await client.get("/api/podcasts/nonexistent-podcast")
        assert response.status_code == 404


class TestDeletePodcast:
    """Tests for DELETE /api/podcasts/{pid}"""
    
    async def test_delete_podcast_exists(
        self, client: AsyncClient, create_test_podcast
    ):
        """Test deleting an existing podcast."""
        create_test_podcast()
        
        response = await client.delete("/api/podcasts/test-podcast-123")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()
        
        # Verify it's gone
        response = await client.get("/api/podcasts/test-podcast-123")
        assert response.status_code == 404
    
    async def test_delete_podcast_not_found(self, client: AsyncClient):
        """Test deleting a non-existent podcast."""
        response = await client.delete("/api/podcasts/nonexistent-podcast")
        assert response.status_code == 404


class TestListPodcastEpisodes:
    """Tests for GET /api/podcasts/{pid}/episodes"""
    
    async def test_list_episodes_empty(
        self, client: AsyncClient, create_test_podcast
    ):
        """Test listing episodes when none exist."""
        create_test_podcast()
        
        response = await client.get("/api/podcasts/test-podcast-123/episodes")
        assert response.status_code == 200
        assert response.json() == []
    
    async def test_list_episodes_with_data(
        self, client: AsyncClient, create_test_podcast, create_test_episode
    ):
        """Test listing episodes with existing data."""
        create_test_podcast()
        create_test_episode(podcast_id=1)
        
        response = await client.get("/api/podcasts/test-podcast-123/episodes")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) >= 1
        assert data[0]["eid"] == "test-episode-456"
    
    async def test_list_episodes_with_limit(
        self, client: AsyncClient, create_test_podcast, create_test_episode
    ):
        """Test listing episodes with limit."""
        create_test_podcast()
        for i in range(5):
            create_test_episode(podcast_id=1, override={"eid": f"episode-{i}"})
        
        response = await client.get("/api/podcasts/test-podcast-123/episodes?limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) <= 3
    
    async def test_list_episodes_podcast_not_found(self, client: AsyncClient):
        """Test listing episodes for non-existent podcast."""
        response = await client.get("/api/podcasts/nonexistent/episodes")
        assert response.status_code == 404


class TestRefreshPodcast:
    """Tests for POST /api/podcasts/{pid}/refresh"""
    
    async def test_refresh_podcast(
        self, client: AsyncClient, create_test_podcast
    ):
        """Test refreshing a podcast."""
        create_test_podcast()
        
        with patch("api.routers.podcasts.get_client") as mock_client:
            mock_client.return_value.get_episodes_from_page.return_value = []
            mock_client.return_value.get_podcast.return_value = MagicMock(
                cover_url="https://example.com/new-cover.jpg"
            )
            
            response = await client.post("/api/podcasts/test-podcast-123/refresh")
            assert response.status_code == 200
            assert "message" in response.json()
    
    async def test_refresh_podcast_not_found(self, client: AsyncClient):
        """Test refreshing a non-existent podcast."""
        response = await client.post("/api/podcasts/nonexistent/refresh")
        assert response.status_code == 404
