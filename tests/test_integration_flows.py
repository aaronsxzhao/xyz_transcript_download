"""
Integration tests for complete user flows.
"""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestPodcastSubscriptionFlow:
    """Test complete podcast subscription flow."""
    
    async def test_subscribe_and_list_podcasts(self, client: AsyncClient):
        """Test subscribing to a podcast and listing it."""
        with patch("api.routers.podcasts.get_client") as mock_client:
            # Mock podcast
            mock_podcast = MagicMock()
            mock_podcast.pid = "flow-test-podcast"
            mock_podcast.title = "Flow Test Podcast"
            mock_podcast.author = "Author"
            mock_podcast.description = "Description"
            mock_podcast.cover_url = "https://example.com/cover.jpg"
            
            mock_client.return_value.get_podcast_by_url.return_value = mock_podcast
            mock_client.return_value._extract_id_from_url.return_value = "flow-test-podcast"
            
            # Step 1: Subscribe to podcast
            response = await client.post(
                "/api/podcasts",
                json={"url": "https://www.xiaoyuzhoufm.com/podcast/flow-test-podcast"}
            )
            assert response.status_code == 200
            assert response.json()["pid"] == "flow-test-podcast"
            
            # Step 2: List podcasts
            response = await client.get("/api/podcasts")
            assert response.status_code == 200
            
            podcasts = response.json()
            assert any(p["pid"] == "flow-test-podcast" for p in podcasts)
            
            # Step 3: Get podcast details
            response = await client.get("/api/podcasts/flow-test-podcast")
            assert response.status_code == 200
            assert response.json()["title"] == "Flow Test Podcast"
    
    async def test_subscribe_and_unsubscribe(self, client: AsyncClient):
        """Test subscribing and then unsubscribing from a podcast."""
        with patch("api.routers.podcasts.get_client") as mock_client:
            mock_podcast = MagicMock()
            mock_podcast.pid = "unsub-test-podcast"
            mock_podcast.title = "Unsub Test"
            mock_podcast.author = "Author"
            mock_podcast.description = "Description"
            mock_podcast.cover_url = "https://example.com/cover.jpg"
            
            mock_client.return_value.get_podcast_by_url.return_value = mock_podcast
            mock_client.return_value._extract_id_from_url.return_value = "unsub-test-podcast"
            
            # Subscribe
            response = await client.post(
                "/api/podcasts",
                json={"url": "https://www.xiaoyuzhoufm.com/podcast/unsub-test-podcast"}
            )
            assert response.status_code == 200
            
            # Verify subscription
            response = await client.get("/api/podcasts/unsub-test-podcast")
            assert response.status_code == 200
            
            # Unsubscribe
            response = await client.delete("/api/podcasts/unsub-test-podcast")
            assert response.status_code == 200
            
            # Verify unsubscription
            response = await client.get("/api/podcasts/unsub-test-podcast")
            assert response.status_code == 404


class TestEpisodeProcessingFlow:
    """Test complete episode processing flow."""
    
    async def test_start_processing_job(self, client: AsyncClient):
        """Test starting and monitoring a processing job."""
        with patch("api.routers.processing.get_client") as mock_client:
            mock_episode = MagicMock()
            mock_episode.eid = "process-test-episode"
            mock_episode.title = "Process Test Episode"
            mock_episode.pid = "test-podcast"
            
            mock_client.return_value.get_episode_by_share_url.return_value = mock_episode
            
            # Step 1: Start processing
            response = await client.post(
                "/api/process",
                json={"episode_url": "https://www.xiaoyuzhoufm.com/episode/process-test-episode"}
            )
            assert response.status_code == 200
            
            data = response.json()
            assert "job_id" in data
            job_id = data["job_id"]
            
            # Step 2: Check job status
            response = await client.get(f"/api/jobs/{job_id}")
            assert response.status_code == 200
            
            job_data = response.json()
            assert job_data["job_id"] == job_id
            assert "status" in job_data
            assert "progress" in job_data
    
    async def test_cancel_processing_job(self, client: AsyncClient):
        """Test cancelling a processing job."""
        from api.routers.processing import jobs
        from api.schemas import ProcessingStatus
        
        # Create a fake running job
        jobs["cancel-flow-job"] = ProcessingStatus(
            job_id="cancel-flow-job",
            status="transcribing",
            progress=40,
            message="Transcribing...",
        )
        
        try:
            # Cancel the job
            response = await client.post("/api/jobs/cancel-flow-job/cancel")
            assert response.status_code == 200
            
            # Verify cancellation requested
            response = await client.get("/api/jobs/cancel-flow-job")
            assert response.status_code == 200
        finally:
            jobs.pop("cancel-flow-job", None)


class TestSummaryViewingFlow:
    """Test complete summary viewing flow."""
    
    async def test_view_summary_details(
        self, client: AsyncClient, create_test_summary
    ):
        """Test viewing summary details."""
        create_test_summary()
        
        # Step 1: List summaries
        response = await client.get("/api/summaries")
        assert response.status_code == 200
        
        summaries = response.json()
        assert len(summaries) >= 1
        
        # Step 2: Get specific summary
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 200
        
        summary = response.json()
        assert "overview" in summary
        assert "key_points" in summary
        assert "topics" in summary
        assert "takeaways" in summary
    
    async def test_export_summary_html(
        self, client: AsyncClient, create_test_summary
    ):
        """Test exporting summary as HTML."""
        create_test_summary()
        
        # Export as HTML
        response = await client.get("/api/summaries/test-episode-456/html")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    async def test_export_summary_markdown(
        self, client: AsyncClient, create_test_summary
    ):
        """Test exporting summary as Markdown."""
        create_test_summary()
        
        # Export as Markdown
        response = await client.get("/api/summaries/test-episode-456/markdown")
        assert response.status_code == 200
        
        data = response.json()
        assert "markdown" in data
        assert len(data["markdown"]) > 0


class TestTranscriptViewingFlow:
    """Test complete transcript viewing flow."""
    
    async def test_view_transcript(
        self, client: AsyncClient, create_test_transcript
    ):
        """Test viewing a transcript."""
        create_test_transcript()
        
        # Get transcript
        response = await client.get("/api/transcripts/test-episode-456")
        assert response.status_code == 200
        
        transcript = response.json()
        assert "text" in transcript
        assert "segments" in transcript
        assert len(transcript["segments"]) > 0


class TestDataPersistenceFlow:
    """Test data persistence across requests."""
    
    async def test_data_persists_across_requests(
        self, client: AsyncClient, create_test_podcast, create_test_episode
    ):
        """Test that data persists between requests."""
        # Create data
        create_test_podcast()
        create_test_episode(podcast_id=1)
        
        # First request
        response = await client.get("/api/podcasts")
        assert response.status_code == 200
        initial_podcasts = response.json()
        
        # Second request - should see same data
        response = await client.get("/api/podcasts")
        assert response.status_code == 200
        second_podcasts = response.json()
        
        assert len(initial_podcasts) == len(second_podcasts)
    
    async def test_deletion_persists(
        self, client: AsyncClient, create_test_summary
    ):
        """Test that deletions persist."""
        create_test_summary()
        
        # Verify exists
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 200
        
        # Delete
        response = await client.delete("/api/summaries/test-episode-456")
        assert response.status_code == 200
        
        # Verify still deleted
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 404
        
        # Double check with another request
        response = await client.get("/api/summaries/test-episode-456")
        assert response.status_code == 404


class TestErrorHandlingFlow:
    """Test error handling in various flows."""
    
    async def test_404_errors(self, client: AsyncClient):
        """Test 404 errors for non-existent resources."""
        # Non-existent podcast
        response = await client.get("/api/podcasts/nonexistent-podcast")
        assert response.status_code == 404
        
        # Non-existent episode
        response = await client.get("/api/episodes/nonexistent-episode")
        assert response.status_code == 404
        
        # Non-existent transcript
        response = await client.get("/api/transcripts/nonexistent")
        assert response.status_code == 404
        
        # Non-existent summary
        response = await client.get("/api/summaries/nonexistent")
        assert response.status_code == 404
    
    async def test_validation_errors(self, client: AsyncClient):
        """Test validation errors for invalid input."""
        # Missing required field
        response = await client.post("/api/podcasts", json={})
        assert response.status_code == 422
        
        # Invalid request body
        response = await client.post("/api/process", json={})
        assert response.status_code == 400
    
    async def test_graceful_error_handling(self, client: AsyncClient):
        """Test that errors are handled gracefully."""
        with patch("api.routers.podcasts.get_client") as mock_client:
            # Simulate API error
            mock_client.return_value.get_podcast_by_url.side_effect = Exception("API Error")
            mock_client.return_value._extract_id_from_url.return_value = None
            mock_client.return_value.get_episode_by_share_url.side_effect = Exception("API Error")
            
            response = await client.post(
                "/api/podcasts",
                json={"url": "https://example.com/podcast"}
            )
            
            # Should return error, not crash
            assert response.status_code in [400, 404, 500]


class TestHealthAndStatsFlow:
    """Test health check and stats endpoints."""
    
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint."""
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    async def test_stats_endpoint(self, client: AsyncClient):
        """Test stats endpoint."""
        response = await client.get("/api/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_podcasts" in data
        assert "total_episodes" in data
        assert "total_transcripts" in data
        assert "total_summaries" in data
    
    async def test_settings_endpoint(self, client: AsyncClient):
        """Test settings endpoint."""
        response = await client.get("/api/settings")
        assert response.status_code == 200
        
        data = response.json()
        assert "whisper_mode" in data
        assert "llm_model" in data
