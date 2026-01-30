"""
API tests for summaries router.
"""
import pytest
from httpx import AsyncClient


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestListSummaries:
    """Tests for GET /api/summaries"""
    
    async def test_list_summaries_empty(self, client: AsyncClient):
        """Test listing summaries when none exist."""
        response = await client.get("/api/summaries")
        assert response.status_code == 200
        assert response.json() == []
    
    async def test_list_summaries_with_data(
        self, client: AsyncClient, create_test_summary
    ):
        """Test listing summaries with existing data."""
        create_test_summary()
        
        response = await client.get("/api/summaries")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) >= 1
        assert data[0]["episode_id"] == "test-episode-456"
    
    async def test_list_summaries_multiple(
        self, client: AsyncClient, create_test_summary
    ):
        """Test listing multiple summaries."""
        create_test_summary({"episode_id": "episode-1"})
        create_test_summary({"episode_id": "episode-2"})
        
        response = await client.get("/api/summaries")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) >= 2


class TestGetSummary:
    """Tests for GET /api/summaries/{eid}"""
    
    async def test_get_summary_exists(
        self, client: AsyncClient, create_test_summary
    ):
        """Test getting an existing summary."""
        create_test_summary()
        
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 200
        
        data = response.json()
        assert data["episode_id"] == "test-episode-456"
        assert "overview" in data
        assert "key_points" in data
        assert "topics" in data
        assert "takeaways" in data
    
    async def test_get_summary_not_found(self, client: AsyncClient):
        """Test getting a non-existent summary."""
        response = await client.get("/api/summaries/nonexistent")
        assert response.status_code == 404
    
    async def test_get_summary_has_key_points(
        self, client: AsyncClient, create_test_summary
    ):
        """Test that summary includes key points with all fields."""
        create_test_summary()
        
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["key_points"]) > 0
        
        kp = data["key_points"][0]
        assert "topic" in kp
        assert "summary" in kp
        assert "original_quote" in kp
        assert "timestamp" in kp


class TestGetSummaryHtml:
    """Tests for GET /api/summaries/{eid}/html"""
    
    async def test_get_summary_html_exists(
        self, client: AsyncClient, create_test_summary
    ):
        """Test getting summary as HTML."""
        create_test_summary()
        
        response = await client.get("/api/summaries/test-episode-456/html")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        
        # Should contain HTML structure
        content = response.text
        assert "<html" in content.lower() or "<!doctype" in content.lower()
    
    async def test_get_summary_html_not_found(self, client: AsyncClient):
        """Test getting HTML for non-existent summary."""
        response = await client.get("/api/summaries/nonexistent/html")
        assert response.status_code == 404
    
    async def test_get_summary_html_with_token(
        self, client: AsyncClient, create_test_summary
    ):
        """Test getting HTML with token parameter."""
        create_test_summary()
        
        response = await client.get("/api/summaries/test-episode-456/html?token=test-token")
        # Should work even with invalid token in local mode
        assert response.status_code in [200, 401]


class TestGetSummaryMarkdown:
    """Tests for GET /api/summaries/{eid}/markdown"""
    
    async def test_get_summary_markdown_exists(
        self, client: AsyncClient, create_test_summary
    ):
        """Test getting summary as Markdown."""
        create_test_summary()
        
        response = await client.get("/api/summaries/test-episode-456/markdown")
        assert response.status_code == 200
        
        data = response.json()
        assert "markdown" in data
        assert len(data["markdown"]) > 0
    
    async def test_get_summary_markdown_not_found(self, client: AsyncClient):
        """Test getting Markdown for non-existent summary."""
        response = await client.get("/api/summaries/nonexistent/markdown")
        assert response.status_code == 404


class TestDeleteSummary:
    """Tests for DELETE /api/summaries/{eid}"""
    
    async def test_delete_summary_exists(
        self, client: AsyncClient, create_test_summary
    ):
        """Test deleting an existing summary."""
        create_test_summary()
        
        response = await client.delete("/api/summaries/test-episode-456")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()
        
        # Verify it's gone
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 404
    
    async def test_delete_summary_not_found(self, client: AsyncClient):
        """Test deleting a non-existent summary."""
        response = await client.delete("/api/summaries/nonexistent")
        assert response.status_code == 404
