"""
Database operation tests for both SQLite and Supabase modes.
"""
import pytest
import json
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.db]


# ==================== Podcast Operations ====================

class TestPodcastOperations:
    """Tests for podcast database operations."""
    
    def test_add_podcast(self, mock_database, sample_podcast_data):
        """Test adding a new podcast."""
        data = sample_podcast_data
        mock_database.add_podcast(
            pid=data["pid"],
            title=data["title"],
            author=data["author"],
            description=data["description"],
            cover_url=data["cover_url"],
        )
        
        podcast = mock_database.get_podcast(data["pid"])
        assert podcast is not None
        assert podcast.pid == data["pid"]
        assert podcast.title == data["title"]
    
    def test_add_podcast_duplicate(self, mock_database, sample_podcast_data):
        """Test adding duplicate podcast (should handle gracefully)."""
        data = sample_podcast_data
        
        # Add first time
        mock_database.add_podcast(
            pid=data["pid"],
            title=data["title"],
            author=data["author"],
            description=data["description"],
            cover_url=data["cover_url"],
        )
        
        # Add again - should not raise error
        mock_database.add_podcast(
            pid=data["pid"],
            title="Updated Title",
            author=data["author"],
            description=data["description"],
            cover_url=data["cover_url"],
        )
        
        podcasts = mock_database.get_all_podcasts()
        # Should only have one podcast (or updated)
        assert len([p for p in podcasts if p.pid == data["pid"]]) >= 1
    
    def test_get_podcast_exists(self, mock_database, sample_podcast_data):
        """Test getting an existing podcast."""
        data = sample_podcast_data
        mock_database.add_podcast(
            pid=data["pid"],
            title=data["title"],
            author=data["author"],
            description=data["description"],
            cover_url=data["cover_url"],
        )
        
        podcast = mock_database.get_podcast(data["pid"])
        assert podcast is not None
        assert podcast.pid == data["pid"]
    
    def test_get_podcast_not_found(self, mock_database):
        """Test getting a non-existent podcast."""
        podcast = mock_database.get_podcast("nonexistent")
        assert podcast is None
    
    def test_get_all_podcasts_empty(self, mock_database):
        """Test getting podcasts when none exist."""
        podcasts = mock_database.get_all_podcasts()
        assert podcasts == []
    
    def test_get_all_podcasts_multiple(self, mock_database):
        """Test getting multiple podcasts."""
        for i in range(3):
            mock_database.add_podcast(
                pid=f"podcast-{i}",
                title=f"Podcast {i}",
                author="Author",
                description="Description",
                cover_url="https://example.com/cover.jpg",
            )
        
        podcasts = mock_database.get_all_podcasts()
        assert len(podcasts) == 3
    
    def test_delete_podcast(self, mock_database, sample_podcast_data):
        """Test deleting a podcast."""
        data = sample_podcast_data
        mock_database.add_podcast(
            pid=data["pid"],
            title=data["title"],
            author=data["author"],
            description=data["description"],
            cover_url=data["cover_url"],
        )
        
        # Verify it exists
        assert mock_database.get_podcast(data["pid"]) is not None
        
        # Delete
        mock_database.delete_podcast(data["pid"])
        
        # Verify it's gone
        assert mock_database.get_podcast(data["pid"]) is None
    
    def test_update_podcast_cover(self, mock_database, sample_podcast_data):
        """Test updating podcast cover URL."""
        data = sample_podcast_data
        mock_database.add_podcast(
            pid=data["pid"],
            title=data["title"],
            author=data["author"],
            description=data["description"],
            cover_url=data["cover_url"],
        )
        
        new_cover = "https://example.com/new-cover.jpg"
        mock_database.update_podcast_cover(data["pid"], new_cover)
        
        podcast = mock_database.get_podcast(data["pid"])
        assert podcast.cover_url == new_cover


# ==================== Episode Operations ====================

class TestEpisodeOperations:
    """Tests for episode database operations."""
    
    def test_add_episode(self, mock_database, sample_podcast_data, sample_episode_data):
        """Test adding a new episode."""
        # First add podcast
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        podcast = mock_database.get_podcast(pd["pid"])
        
        # Add episode
        ed = sample_episode_data
        mock_database.add_episode(
            eid=ed["eid"], pid=ed["pid"], podcast_id=podcast.id,
            title=ed["title"], description=ed["description"],
            duration=ed["duration"], pub_date=ed["pub_date"],
            audio_url=ed["audio_url"],
        )
        
        episode = mock_database.get_episode(ed["eid"])
        assert episode is not None
        assert episode.eid == ed["eid"]
        assert episode.title == ed["title"]
    
    def test_get_episode_exists(self, mock_database, sample_podcast_data, sample_episode_data):
        """Test getting an existing episode."""
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        podcast = mock_database.get_podcast(pd["pid"])
        
        ed = sample_episode_data
        mock_database.add_episode(
            eid=ed["eid"], pid=ed["pid"], podcast_id=podcast.id,
            title=ed["title"], description=ed["description"],
            duration=ed["duration"], pub_date=ed["pub_date"],
            audio_url=ed["audio_url"],
        )
        
        episode = mock_database.get_episode(ed["eid"])
        assert episode is not None
    
    def test_get_episode_not_found(self, mock_database):
        """Test getting a non-existent episode."""
        episode = mock_database.get_episode("nonexistent")
        assert episode is None
    
    def test_get_episodes_by_podcast(self, mock_database, sample_podcast_data):
        """Test getting episodes for a podcast."""
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        podcast = mock_database.get_podcast(pd["pid"])
        
        # Add multiple episodes
        for i in range(3):
            mock_database.add_episode(
                eid=f"episode-{i}", pid=pd["pid"], podcast_id=podcast.id,
                title=f"Episode {i}", description="Description",
                duration=3600, pub_date="2024-01-15",
                audio_url=f"https://example.com/audio-{i}.mp3",
            )
        
        episodes = mock_database.get_episodes_by_podcast(pd["pid"])
        assert len(episodes) == 3
    
    def test_get_episodes_empty_podcast(self, mock_database, sample_podcast_data):
        """Test getting episodes for a podcast with no episodes."""
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        
        episodes = mock_database.get_episodes_by_podcast(pd["pid"])
        assert episodes == []
    
    def test_update_episode_status(self, mock_database, sample_podcast_data, sample_episode_data):
        """Test updating episode status."""
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        podcast = mock_database.get_podcast(pd["pid"])
        
        ed = sample_episode_data
        mock_database.add_episode(
            eid=ed["eid"], pid=ed["pid"], podcast_id=podcast.id,
            title=ed["title"], description=ed["description"],
            duration=ed["duration"], pub_date=ed["pub_date"],
            audio_url=ed["audio_url"],
        )
        
        mock_database.update_episode_status(ed["eid"], "completed")
        
        episode = mock_database.get_episode(ed["eid"])
        assert episode.status == "completed"
    
    def test_delete_episode(self, mock_database, sample_podcast_data, sample_episode_data):
        """Test deleting an episode."""
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        podcast = mock_database.get_podcast(pd["pid"])
        
        ed = sample_episode_data
        mock_database.add_episode(
            eid=ed["eid"], pid=ed["pid"], podcast_id=podcast.id,
            title=ed["title"], description=ed["description"],
            duration=ed["duration"], pub_date=ed["pub_date"],
            audio_url=ed["audio_url"],
        )
        
        # Delete
        mock_database.delete_episode(ed["eid"])
        
        # Verify it's gone
        assert mock_database.get_episode(ed["eid"]) is None
    
    def test_cascade_delete_episodes(self, mock_database, sample_podcast_data, sample_episode_data):
        """Test that deleting a podcast also deletes its episodes."""
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        podcast = mock_database.get_podcast(pd["pid"])
        
        ed = sample_episode_data
        mock_database.add_episode(
            eid=ed["eid"], pid=ed["pid"], podcast_id=podcast.id,
            title=ed["title"], description=ed["description"],
            duration=ed["duration"], pub_date=ed["pub_date"],
            audio_url=ed["audio_url"],
        )
        
        # Delete podcast
        mock_database.delete_podcast(pd["pid"])
        
        # Episodes should also be gone
        episodes = mock_database.get_episodes_by_podcast(pd["pid"])
        assert episodes == []


# ==================== Database Interface Tests ====================

class TestDatabaseInterface:
    """Tests for the unified DatabaseInterface."""
    
    def test_get_stats_empty(self, db_interface):
        """Test getting stats from empty database."""
        stats = db_interface.get_stats()
        
        assert "podcasts" in stats
        assert "episodes" in stats
        assert "transcripts" in stats
        assert "summaries" in stats
        assert stats["podcasts"] == 0
    
    def test_get_stats_with_data(self, db_interface, mock_database, sample_podcast_data):
        """Test getting stats with data."""
        pd = sample_podcast_data
        mock_database.add_podcast(
            pid=pd["pid"], title=pd["title"], author=pd["author"],
            description=pd["description"], cover_url=pd["cover_url"],
        )
        
        stats = db_interface.get_stats()
        assert stats["podcasts"] >= 1
    
    def test_transcript_operations(self, db_interface, temp_data_dir: Path, sample_transcript_data):
        """Test transcript save and load via interface."""
        from api.db import TranscriptData
        
        td = sample_transcript_data
        transcript = TranscriptData(
            episode_id=td["episode_id"],
            language=td["language"],
            duration=td["duration"],
            text=td["text"],
            segments=td["segments"],
        )
        
        # Save
        db_interface.save_transcript(transcript)
        
        # Load
        loaded = db_interface.get_transcript(td["episode_id"])
        assert loaded is not None
        assert loaded.episode_id == td["episode_id"]
        assert loaded.text == td["text"]
    
    def test_summary_operations(self, db_interface, temp_data_dir: Path, sample_summary_data):
        """Test summary save and load via interface."""
        from api.db import SummaryData
        
        sd = sample_summary_data
        summary = SummaryData(
            episode_id=sd["episode_id"],
            title=sd["title"],
            overview=sd["overview"],
            topics=sd["topics"],
            takeaways=sd["takeaways"],
            key_points=sd["key_points"],
        )
        
        # Save
        db_interface.save_summary(summary)
        
        # Load
        loaded = db_interface.get_summary(sd["episode_id"])
        assert loaded is not None
        assert loaded.episode_id == sd["episode_id"]
        assert loaded.title == sd["title"]
    
    def test_has_transcript(self, db_interface, temp_data_dir: Path, sample_transcript_data):
        """Test checking if transcript exists."""
        from api.db import TranscriptData
        
        assert db_interface.has_transcript("nonexistent") == False
        
        td = sample_transcript_data
        transcript = TranscriptData(
            episode_id=td["episode_id"],
            language=td["language"],
            duration=td["duration"],
            text=td["text"],
            segments=td["segments"],
        )
        db_interface.save_transcript(transcript)
        
        assert db_interface.has_transcript(td["episode_id"]) == True
    
    def test_has_summary(self, db_interface, temp_data_dir: Path, sample_summary_data):
        """Test checking if summary exists."""
        from api.db import SummaryData
        
        assert db_interface.has_summary("nonexistent") == False
        
        sd = sample_summary_data
        summary = SummaryData(
            episode_id=sd["episode_id"],
            title=sd["title"],
            overview=sd["overview"],
            topics=sd["topics"],
            takeaways=sd["takeaways"],
            key_points=sd["key_points"],
        )
        db_interface.save_summary(summary)
        
        assert db_interface.has_summary(sd["episode_id"]) == True
    
    def test_delete_transcript(self, db_interface, temp_data_dir: Path, sample_transcript_data):
        """Test deleting a transcript."""
        from api.db import TranscriptData
        
        td = sample_transcript_data
        transcript = TranscriptData(
            episode_id=td["episode_id"],
            language=td["language"],
            duration=td["duration"],
            text=td["text"],
            segments=td["segments"],
        )
        db_interface.save_transcript(transcript)
        
        assert db_interface.has_transcript(td["episode_id"]) == True
        
        db_interface.delete_transcript(td["episode_id"])
        
        assert db_interface.has_transcript(td["episode_id"]) == False
    
    def test_delete_summary(self, db_interface, temp_data_dir: Path, sample_summary_data):
        """Test deleting a summary."""
        from api.db import SummaryData
        
        sd = sample_summary_data
        summary = SummaryData(
            episode_id=sd["episode_id"],
            title=sd["title"],
            overview=sd["overview"],
            topics=sd["topics"],
            takeaways=sd["takeaways"],
            key_points=sd["key_points"],
        )
        db_interface.save_summary(summary)
        
        assert db_interface.has_summary(sd["episode_id"]) == True
        
        db_interface.delete_summary(sd["episode_id"])
        
        assert db_interface.has_summary(sd["episode_id"]) == False
    
    def test_get_all_summaries(self, db_interface, temp_data_dir: Path, sample_summary_data):
        """Test getting all summaries."""
        from api.db import SummaryData
        
        # Initially empty
        summaries = db_interface.get_all_summaries()
        initial_count = len(summaries)
        
        # Add summaries
        for i in range(3):
            sd = {**sample_summary_data, "episode_id": f"episode-{i}"}
            summary = SummaryData(
                episode_id=sd["episode_id"],
                title=sd["title"],
                overview=sd["overview"],
                topics=sd["topics"],
                takeaways=sd["takeaways"],
                key_points=sd["key_points"],
            )
            db_interface.save_summary(summary)
        
        summaries = db_interface.get_all_summaries()
        assert len(summaries) == initial_count + 3


# ==================== Edge Cases ====================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_strings(self, mock_database):
        """Test handling of empty strings."""
        mock_database.add_podcast(
            pid="empty-test",
            title="",
            author="",
            description="",
            cover_url="",
        )
        
        podcast = mock_database.get_podcast("empty-test")
        assert podcast is not None
        assert podcast.title == ""
    
    def test_special_characters(self, mock_database):
        """Test handling of special characters."""
        special_title = "Test <script>alert('xss')</script> & \"quotes\" 'apostrophe'"
        
        mock_database.add_podcast(
            pid="special-test",
            title=special_title,
            author="Author",
            description="Description",
            cover_url="https://example.com/cover.jpg",
        )
        
        podcast = mock_database.get_podcast("special-test")
        assert podcast is not None
        assert podcast.title == special_title
    
    def test_unicode_content(self, mock_database):
        """Test handling of Unicode content."""
        unicode_title = "测试播客 🎙️ Тест ポッドキャスト"
        
        mock_database.add_podcast(
            pid="unicode-test",
            title=unicode_title,
            author="作者",
            description="描述",
            cover_url="https://example.com/cover.jpg",
        )
        
        podcast = mock_database.get_podcast("unicode-test")
        assert podcast is not None
        assert podcast.title == unicode_title
    
    def test_long_content(self, mock_database):
        """Test handling of very long content."""
        long_description = "A" * 10000
        
        mock_database.add_podcast(
            pid="long-test",
            title="Long Test",
            author="Author",
            description=long_description,
            cover_url="https://example.com/cover.jpg",
        )
        
        podcast = mock_database.get_podcast("long-test")
        assert podcast is not None
        assert len(podcast.description) == 10000
    
    def test_concurrent_operations(self, mock_database):
        """Test basic concurrent-like operations."""
        # Simulate rapid operations
        for i in range(10):
            mock_database.add_podcast(
                pid=f"concurrent-{i}",
                title=f"Podcast {i}",
                author="Author",
                description="Description",
                cover_url="https://example.com/cover.jpg",
            )
        
        podcasts = mock_database.get_all_podcasts()
        assert len([p for p in podcasts if p.pid.startswith("concurrent-")]) == 10
