"""
API tests for episodes router.
"""
import pytest
from unittest.mock import patch
from httpx import AsyncClient


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestGetEpisode:
    """Tests for GET /api/episodes/{eid}"""
    
    async def test_get_episode_exists(
        self, client: AsyncClient, create_test_podcast, create_test_episode
    ):
        """Test getting an existing episode."""
        create_test_podcast()
        create_test_episode(podcast_id=1)
        
        response = await client.get("/api/episodes/test-episode-456")
        assert response.status_code == 200
        
        data = response.json()
        assert data["eid"] == "test-episode-456"
        assert data["title"] == "Test Episode"
        assert data["pid"] == "test-podcast-123"
    
    async def test_get_episode_not_found(self, client: AsyncClient):
        """Test getting a non-existent episode."""
        response = await client.get("/api/episodes/nonexistent-episode")
        assert response.status_code == 404
    
    async def test_get_episode_has_status_fields(
        self, client: AsyncClient, create_test_podcast, create_test_episode
    ):
        """Test that episode response includes status fields."""
        create_test_podcast()
        create_test_episode(podcast_id=1)
        
        response = await client.get("/api/episodes/test-episode-456")
        assert response.status_code == 200
        
        data = response.json()
        assert "has_transcript" in data
        assert "has_summary" in data
        assert "status" in data


class TestGetEpisodeAudio:
    """Tests for GET /api/episodes/{eid}/audio"""
    
    async def test_get_episode_audio_info(
        self, client: AsyncClient, create_test_podcast, create_test_episode
    ):
        """Test getting episode audio info."""
        create_test_podcast()
        create_test_episode(podcast_id=1)
        
        response = await client.get("/api/episodes/test-episode-456/audio")
        assert response.status_code == 200
        
        data = response.json()
        assert data["eid"] == "test-episode-456"
        assert "remote_url" in data
        assert "local_path" in data
        assert "downloaded" in data
    
    async def test_get_episode_audio_not_found(self, client: AsyncClient):
        """Test getting audio for non-existent episode."""
        response = await client.get("/api/episodes/nonexistent/audio")
        assert response.status_code == 404


class TestDeleteEpisode:
    """Tests for DELETE /api/episodes/{eid}"""
    
    async def test_delete_episode_exists(
        self, client: AsyncClient, create_test_podcast, create_test_episode
    ):
        """Test deleting an existing episode."""
        create_test_podcast()
        create_test_episode(podcast_id=1)
        
        response = await client.delete("/api/episodes/test-episode-456")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()
        
        # Verify it's gone
        response = await client.get("/api/episodes/test-episode-456")
        assert response.status_code == 404
    
    async def test_delete_episode_not_found(self, client: AsyncClient):
        """Test deleting a non-existent episode."""
        response = await client.delete("/api/episodes/nonexistent")
        assert response.status_code == 404
    
    async def test_delete_episode_with_transcript(
        self, client: AsyncClient, 
        create_test_podcast, 
        create_test_episode,
        create_test_transcript
    ):
        """Test deleting an episode also removes its transcript."""
        create_test_podcast()
        create_test_episode(podcast_id=1)
        create_test_transcript()
        
        # First verify transcript exists
        response = await client.get("/api/transcripts/test-episode-456")
        assert response.status_code == 200
        
        # Delete the episode
        response = await client.delete("/api/episodes/test-episode-456")
        assert response.status_code == 200
        
        # Verify transcript is also gone
        response = await client.get("/api/transcripts/test-episode-456")
        assert response.status_code == 404
    
    async def test_delete_episode_with_summary(
        self, client: AsyncClient, 
        create_test_podcast, 
        create_test_episode,
        create_test_summary
    ):
        """Test deleting an episode also removes its summary."""
        create_test_podcast()
        create_test_episode(podcast_id=1)
        create_test_summary()
        
        # First verify summary exists
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 200
        
        # Delete the episode
        response = await client.delete("/api/episodes/test-episode-456")
        assert response.status_code == 200
        
        # Verify summary is also gone
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 404
