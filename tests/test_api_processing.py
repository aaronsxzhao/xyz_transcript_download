"""
API tests for processing router.
"""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient


pytestmark = [pytest.mark.api, pytest.mark.asyncio]


class TestProcessEpisode:
    """Tests for POST /api/process"""
    
    async def test_process_episode_start(self, client: AsyncClient):
        """Test starting episode processing."""
        with patch("api.routers.processing.get_client") as mock_client:
            mock_episode = MagicMock()
            mock_episode.eid = "test-episode"
            mock_episode.title = "Test Episode"
            mock_client.return_value.get_episode_by_share_url.return_value = mock_episode
            
            response = await client.post(
                "/api/process",
                json={"episode_url": "https://www.xiaoyuzhoufm.com/episode/test-episode"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["message"] == "Processing started"
    
    async def test_process_episode_missing_url(self, client: AsyncClient):
        """Test processing without episode URL."""
        response = await client.post("/api/process", json={})
        assert response.status_code == 400
    
    async def test_process_episode_transcribe_only(self, client: AsyncClient):
        """Test processing with transcribe_only flag."""
        with patch("api.routers.processing.get_client") as mock_client:
            mock_episode = MagicMock()
            mock_episode.eid = "test-episode"
            mock_episode.title = "Test Episode"
            mock_client.return_value.get_episode_by_share_url.return_value = mock_episode
            
            response = await client.post(
                "/api/process",
                json={
                    "episode_url": "https://www.xiaoyuzhoufm.com/episode/test-episode",
                    "transcribe_only": True
                }
            )
            
            assert response.status_code == 200
    
    async def test_process_episode_force(self, client: AsyncClient):
        """Test processing with force flag."""
        with patch("api.routers.processing.get_client") as mock_client:
            mock_episode = MagicMock()
            mock_episode.eid = "test-episode"
            mock_episode.title = "Test Episode"
            mock_client.return_value.get_episode_by_share_url.return_value = mock_episode
            
            response = await client.post(
                "/api/process",
                json={
                    "episode_url": "https://www.xiaoyuzhoufm.com/episode/test-episode",
                    "force": True
                }
            )
            
            assert response.status_code == 200


class TestListJobs:
    """Tests for GET /api/jobs"""
    
    async def test_list_jobs_empty(self, client: AsyncClient):
        """Test listing jobs when none exist."""
        # Clear any existing jobs
        with patch("api.routers.processing.jobs", {}):
            response = await client.get("/api/jobs")
            assert response.status_code == 200
            assert "jobs" in response.json()
    
    async def test_list_jobs_with_active(self, client: AsyncClient):
        """Test listing jobs with active jobs."""
        from api.routers.processing import jobs, ProcessingStatus
        from api.schemas import ProcessingStatus as PS
        
        # Add a test job
        jobs["test-job-1"] = PS(
            job_id="test-job-1",
            status="processing",
            progress=50,
            message="Transcribing...",
            episode_id="test-episode",
            episode_title="Test Episode",
        )
        
        try:
            response = await client.get("/api/jobs")
            assert response.status_code == 200
            
            data = response.json()
            assert len(data["jobs"]) >= 1
        finally:
            # Cleanup
            jobs.pop("test-job-1", None)


class TestGetJob:
    """Tests for GET /api/jobs/{job_id}"""
    
    async def test_get_job_exists(self, client: AsyncClient):
        """Test getting an existing job."""
        from api.routers.processing import jobs
        from api.schemas import ProcessingStatus
        
        jobs["test-job-2"] = ProcessingStatus(
            job_id="test-job-2",
            status="transcribing",
            progress=30,
            message="Transcribing audio...",
        )
        
        try:
            response = await client.get("/api/jobs/test-job-2")
            assert response.status_code == 200
            
            data = response.json()
            assert data["job_id"] == "test-job-2"
            assert data["status"] == "transcribing"
            assert data["progress"] == 30
        finally:
            jobs.pop("test-job-2", None)
    
    async def test_get_job_not_found(self, client: AsyncClient):
        """Test getting a non-existent job."""
        response = await client.get("/api/jobs/nonexistent-job")
        assert response.status_code == 404


class TestCancelJob:
    """Tests for POST /api/jobs/{job_id}/cancel"""
    
    async def test_cancel_job_active(self, client: AsyncClient):
        """Test cancelling an active job."""
        from api.routers.processing import jobs
        from api.schemas import ProcessingStatus
        
        jobs["test-job-3"] = ProcessingStatus(
            job_id="test-job-3",
            status="transcribing",
            progress=40,
            message="Transcribing...",
        )
        
        try:
            response = await client.post("/api/jobs/test-job-3/cancel")
            assert response.status_code == 200
            assert "cancel" in response.json()["message"].lower()
        finally:
            jobs.pop("test-job-3", None)
    
    async def test_cancel_job_not_found(self, client: AsyncClient):
        """Test cancelling a non-existent job."""
        response = await client.post("/api/jobs/nonexistent/cancel")
        assert response.status_code == 404
    
    async def test_cancel_job_already_completed(self, client: AsyncClient):
        """Test cancelling an already completed job."""
        from api.routers.processing import jobs
        from api.schemas import ProcessingStatus
        
        jobs["test-job-4"] = ProcessingStatus(
            job_id="test-job-4",
            status="completed",
            progress=100,
            message="Done",
        )
        
        try:
            response = await client.post("/api/jobs/test-job-4/cancel")
            assert response.status_code == 200
            assert "already" in response.json()["message"].lower()
        finally:
            jobs.pop("test-job-4", None)


class TestDeleteJob:
    """Tests for DELETE /api/jobs/{job_id}"""
    
    async def test_delete_job_exists(self, client: AsyncClient):
        """Test deleting an existing job."""
        from api.routers.processing import jobs
        from api.schemas import ProcessingStatus
        
        jobs["test-job-5"] = ProcessingStatus(
            job_id="test-job-5",
            status="completed",
            progress=100,
            message="Done",
        )
        
        response = await client.delete("/api/jobs/test-job-5")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()
        
        # Verify it's gone
        response = await client.get("/api/jobs/test-job-5")
        assert response.status_code == 404
    
    async def test_delete_job_not_found(self, client: AsyncClient):
        """Test deleting a non-existent job."""
        response = await client.delete("/api/jobs/nonexistent")
        assert response.status_code == 404


class TestBatchProcess:
    """Tests for POST /api/batch"""
    
    async def test_batch_process_podcast(self, client: AsyncClient):
        """Test batch processing a podcast."""
        with patch("api.routers.processing.get_client") as mock_client:
            mock_podcast = MagicMock()
            mock_podcast.title = "Test Podcast"
            
            mock_episode = MagicMock()
            mock_episode.eid = "episode-1"
            mock_episode.title = "Episode 1"
            
            mock_client.return_value.get_podcast_by_url.return_value = mock_podcast
            mock_client.return_value.get_podcast.return_value = mock_podcast
            mock_client.return_value._extract_id_from_url.return_value = "test-podcast"
            mock_client.return_value.get_episodes_from_page.return_value = [mock_episode]
            
            response = await client.post(
                "/api/batch",
                json={"podcast_url": "https://www.xiaoyuzhoufm.com/podcast/test-podcast"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "job_ids" in data
            assert data["episode_count"] >= 1
    
    async def test_batch_process_with_limit(self, client: AsyncClient):
        """Test batch processing with limit."""
        with patch("api.routers.processing.get_client") as mock_client:
            mock_podcast = MagicMock()
            mock_podcast.title = "Test Podcast"
            
            episodes = [
                MagicMock(eid=f"ep-{i}", title=f"Episode {i}")
                for i in range(10)
            ]
            
            mock_client.return_value.get_podcast_by_url.return_value = mock_podcast
            mock_client.return_value.get_podcast.return_value = mock_podcast
            mock_client.return_value._extract_id_from_url.return_value = "test-podcast"
            mock_client.return_value.get_episodes_from_page.return_value = episodes[:5]
            
            response = await client.post(
                "/api/batch",
                json={
                    "podcast_url": "https://www.xiaoyuzhoufm.com/podcast/test-podcast",
                    "limit": 5
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["episode_count"] <= 5
    
    async def test_batch_process_podcast_not_found(self, client: AsyncClient):
        """Test batch processing non-existent podcast."""
        with patch("api.routers.processing.get_client") as mock_client:
            mock_client.return_value.get_podcast_by_url.return_value = None
            mock_client.return_value.get_podcast.return_value = None
            mock_client.return_value._extract_id_from_url.return_value = "nonexistent"
            
            response = await client.post(
                "/api/batch",
                json={"podcast_url": "https://www.xiaoyuzhoufm.com/podcast/nonexistent"}
            )
            
            assert response.status_code == 404
