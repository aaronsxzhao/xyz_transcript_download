"""
Shared pytest fixtures for all tests.
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from typing import Generator, Dict, Any
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment before imports
os.environ["USE_SUPABASE"] = "false"
os.environ["WHISPER_MODE"] = "local"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_BASE_URL"] = "https://test.api.com"
os.environ["LLM_MODEL"] = "test-model"


# ==================== Sample Data Fixtures ====================

@pytest.fixture
def sample_podcast_data() -> Dict[str, Any]:
    """Sample podcast data for testing."""
    return {
        "pid": "test-podcast-123",
        "title": "Test Podcast",
        "author": "Test Author",
        "description": "A test podcast for unit testing",
        "cover_url": "https://example.com/cover.jpg",
    }


@pytest.fixture
def sample_episode_data() -> Dict[str, Any]:
    """Sample episode data for testing."""
    return {
        "eid": "test-episode-456",
        "pid": "test-podcast-123",
        "title": "Test Episode",
        "description": "A test episode for unit testing",
        "duration": 3600,
        "pub_date": "2024-01-15",
        "audio_url": "https://example.com/audio.mp3",
        "status": "pending",
    }


@pytest.fixture
def sample_transcript_data() -> Dict[str, Any]:
    """Sample transcript data for testing."""
    return {
        "episode_id": "test-episode-456",
        "language": "zh",
        "duration": 3600.0,
        "text": "This is a test transcript with some content.",
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "This is a test"},
            {"start": 5.0, "end": 10.0, "text": "transcript with some content."},
        ],
    }


@pytest.fixture
def sample_summary_data() -> Dict[str, Any]:
    """Sample summary data for testing."""
    return {
        "episode_id": "test-episode-456",
        "title": "Test Episode Summary",
        "overview": "This is a test summary overview with key insights.",
        "topics": ["Topic 1", "Topic 2", "Topic 3"],
        "takeaways": ["Takeaway 1", "Takeaway 2"],
        "key_points": [
            {
                "topic": "Main Point",
                "summary": "This is the main point summary",
                "original_quote": "Original quote from the transcript",
                "timestamp": "00:05:30",
            },
        ],
    }


# ==================== Database Fixtures ====================

@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary data directory for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "audio").mkdir()
    (data_dir / "transcripts").mkdir()
    (data_dir / "summaries").mkdir()
    (data_dir / "logs").mkdir()
    
    # Patch the DATA_DIR in config
    with patch("config.DATA_DIR", data_dir):
        yield data_dir


@pytest.fixture
def mock_database(temp_data_dir: Path):
    """Create a mock database for testing."""
    from database import Database
    
    db_path = temp_data_dir / "test.db"
    db = Database(str(db_path))
    
    yield db
    
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def db_interface(mock_database, temp_data_dir: Path):
    """Create a DatabaseInterface for testing."""
    from api.db import DatabaseInterface
    
    with patch("api.db.DATA_DIR", temp_data_dir):
        with patch("api.db.get_database", return_value=mock_database):
            interface = DatabaseInterface(user_id=None)
            interface.db = mock_database
            yield interface


# ==================== FastAPI Test Client ====================

@pytest.fixture
def app():
    """Create FastAPI app for testing."""
    # Import here to avoid circular imports
    from api.main import app
    return app


@pytest.fixture
async def client(app, temp_data_dir: Path, mock_database) -> AsyncClient:
    """Create async test client for API testing."""
    from api.db import get_database
    
    with patch("api.db.DATA_DIR", temp_data_dir):
        with patch("api.db.get_database", return_value=mock_database):
            with patch("database.get_database", return_value=mock_database):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as ac:
                    yield ac


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Create mock auth headers for testing."""
    return {"Authorization": "Bearer test-token-123"}


# ==================== Mock Services ====================

@pytest.fixture
def mock_xyz_client():
    """Mock Xiaoyuzhou client."""
    from tests.mocks.mock_xyz_client import MockXYZClient
    return MockXYZClient()


@pytest.fixture
def mock_transcriber():
    """Mock transcriber service."""
    from tests.mocks.mock_transcriber import MockTranscriber
    return MockTranscriber()


@pytest.fixture
def mock_summarizer():
    """Mock summarizer service."""
    from tests.mocks.mock_summarizer import MockSummarizer
    return MockSummarizer()


# ==================== Utility Functions ====================

@pytest.fixture
def create_test_podcast(mock_database, sample_podcast_data):
    """Factory fixture to create test podcasts."""
    def _create(override: Dict[str, Any] = None) -> Dict[str, Any]:
        data = {**sample_podcast_data, **(override or {})}
        mock_database.add_podcast(
            pid=data["pid"],
            title=data["title"],
            author=data["author"],
            description=data["description"],
            cover_url=data["cover_url"],
        )
        return data
    return _create


@pytest.fixture
def create_test_episode(mock_database, sample_episode_data):
    """Factory fixture to create test episodes."""
    def _create(podcast_id: int = 1, override: Dict[str, Any] = None) -> Dict[str, Any]:
        data = {**sample_episode_data, **(override or {})}
        mock_database.add_episode(
            eid=data["eid"],
            pid=data["pid"],
            podcast_id=podcast_id,
            title=data["title"],
            description=data["description"],
            duration=data["duration"],
            pub_date=data["pub_date"],
            audio_url=data["audio_url"],
        )
        return data
    return _create


@pytest.fixture
def create_test_transcript(temp_data_dir: Path, sample_transcript_data):
    """Factory fixture to create test transcripts."""
    def _create(override: Dict[str, Any] = None) -> Dict[str, Any]:
        data = {**sample_transcript_data, **(override or {})}
        transcript_path = temp_data_dir / "transcripts" / f"{data['episode_id']}.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data
    return _create


@pytest.fixture
def create_test_summary(temp_data_dir: Path, sample_summary_data):
    """Factory fixture to create test summaries."""
    def _create(override: Dict[str, Any] = None) -> Dict[str, Any]:
        data = {**sample_summary_data, **(override or {})}
        summary_path = temp_data_dir / "summaries" / f"{data['episode_id']}.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data
    return _create


# ==================== Async Helpers ====================

@pytest.fixture
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
