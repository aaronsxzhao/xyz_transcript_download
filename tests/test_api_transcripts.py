"""
API tests for transcripts router.
"""
import pytest
from httpx import AsyncClient


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestGetTranscript:
    """Tests for GET /api/transcripts/{eid}"""
    
    async def test_get_transcript_exists(
        self, client: AsyncClient, create_test_transcript
    ):
        """Test getting an existing transcript."""
        create_test_transcript()
        
        response = await client.get("/api/transcripts/test-episode-456")
        assert response.status_code == 200
        
        data = response.json()
        assert data["episode_id"] == "test-episode-456"
        assert "text" in data
        assert "segments" in data
        assert "language" in data
        assert "duration" in data
    
    async def test_get_transcript_not_found(self, client: AsyncClient):
        """Test getting a non-existent transcript."""
        response = await client.get("/api/transcripts/nonexistent")
        assert response.status_code == 404
    
    async def test_get_transcript_has_segments(
        self, client: AsyncClient, create_test_transcript
    ):
        """Test that transcript includes segments with timestamps."""
        create_test_transcript()
        
        response = await client.get("/api/transcripts/test-episode-456")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["segments"]) > 0
        
        segment = data["segments"][0]
        assert "start" in segment
        assert "end" in segment
        assert "text" in segment
    
    async def test_get_transcript_chinese_content(
        self, client: AsyncClient, create_test_transcript
    ):
        """Test that transcript handles Chinese content correctly."""
        create_test_transcript()
        
        response = await client.get("/api/transcripts/test-episode-456")
        assert response.status_code == 200
        
        data = response.json()
        assert data["language"] == "zh"
        # Should contain Chinese characters
        assert any('\u4e00' <= c <= '\u9fff' for c in data["text"])


class TestDeleteTranscript:
    """Tests for DELETE /api/transcripts/{eid}"""
    
    async def test_delete_transcript_exists(
        self, client: AsyncClient, create_test_transcript
    ):
        """Test deleting an existing transcript."""
        create_test_transcript()
        
        response = await client.delete("/api/transcripts/test-episode-456")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()
        
        # Verify it's gone
        response = await client.get("/api/transcripts/test-episode-456")
        assert response.status_code == 404
    
    async def test_delete_transcript_not_found(self, client: AsyncClient):
        """Test deleting a non-existent transcript."""
        response = await client.delete("/api/transcripts/nonexistent")
        assert response.status_code == 404
    
    async def test_delete_transcript_keeps_summary(
        self, client: AsyncClient, create_test_transcript, create_test_summary
    ):
        """Test that deleting transcript doesn't affect summary."""
        create_test_transcript()
        create_test_summary()
        
        # Delete transcript
        response = await client.delete("/api/transcripts/test-episode-456")
        assert response.status_code == 200
        
        # Summary should still exist
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 200
