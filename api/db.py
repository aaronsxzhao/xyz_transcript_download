"""
Database abstraction layer.

Provides a unified interface for database operations that works with both
SQLite (local) and Supabase (cloud) backends.
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from config import USE_SUPABASE, DATA_DIR
import json


@dataclass
class PodcastData:
    """Unified podcast data structure."""
    id: int
    pid: str
    title: str
    author: str = ""
    description: str = ""
    cover_url: str = ""
    user_id: Optional[str] = None


@dataclass
class EpisodeData:
    """Unified episode data structure."""
    id: int
    eid: str
    pid: str
    podcast_id: int
    title: str
    description: str = ""
    duration: int = 0
    pub_date: str = ""
    audio_url: str = ""
    status: str = "pending"
    user_id: Optional[str] = None


@dataclass
class TranscriptData:
    """Unified transcript data structure."""
    episode_id: str
    language: str
    duration: float
    text: str
    segments: List[Dict[str, Any]]


@dataclass
class SummaryData:
    """Unified summary data structure."""
    episode_id: str
    title: str
    overview: str
    topics: List[str]
    takeaways: List[str]
    key_points: List[Dict[str, Any]]


class DatabaseInterface:
    """
    Unified database interface that routes to the appropriate backend.
    
    Usage:
        db = get_db(user_id)  # user_id is optional
        podcasts = db.get_all_podcasts()
    """
    
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.use_supabase = USE_SUPABASE and user_id is not None
        self._db = None
    
    @property
    def db(self):
        """Lazy load the appropriate database backend."""
        if self._db is None:
            if self.use_supabase:
                from api.supabase_db import get_supabase_database
                self._db = get_supabase_database()
            else:
                from database import get_database
                self._db = get_database()
        return self._db
    
    # ==================== Podcasts ====================
    
    def get_all_podcasts(self) -> List[PodcastData]:
        """Get all podcasts."""
        if self.use_supabase:
            records = self.db.get_all_podcasts(self.user_id)
        else:
            records = self.db.get_all_podcasts()
        
        return [
            PodcastData(
                id=r.id,
                pid=r.pid,
                title=r.title,
                author=getattr(r, 'author', ''),
                description=getattr(r, 'description', ''),
                cover_url=getattr(r, 'cover_url', ''),
                user_id=self.user_id,
            )
            for r in records
        ]
    
    def get_podcast(self, pid: str) -> Optional[PodcastData]:
        """Get a podcast by pid."""
        if self.use_supabase:
            r = self.db.get_podcast(self.user_id, pid)
        else:
            r = self.db.get_podcast(pid)
        
        if not r:
            return None
        
        return PodcastData(
            id=r.id,
            pid=r.pid,
            title=r.title,
            author=getattr(r, 'author', ''),
            description=getattr(r, 'description', ''),
            cover_url=getattr(r, 'cover_url', ''),
            user_id=self.user_id,
        )
    
    def add_podcast(self, pid: str, title: str, author: str = "", 
                    description: str = "", cover_url: str = "") -> Optional[int]:
        """Add a new podcast."""
        if self.use_supabase:
            return self.db.add_podcast(self.user_id, pid, title, author, description, cover_url)
        else:
            return self.db.add_podcast(pid, title, author, description, cover_url)
    
    def delete_podcast(self, pid: str) -> bool:
        """Delete a podcast."""
        if self.use_supabase:
            return self.db.delete_podcast(self.user_id, pid)
        else:
            return self.db.delete_podcast(pid)
    
    def update_podcast_cover(self, pid: str, cover_url: str) -> bool:
        """Update podcast cover URL."""
        if self.use_supabase:
            return self.db.update_podcast_cover(self.user_id, pid, cover_url)
        else:
            return self.db.update_podcast_cover(pid, cover_url)
    
    def force_delete_podcast(self, pid: str) -> bool:
        """Force delete a podcast by pid."""
        if self.use_supabase:
            return self.db.delete_podcast(self.user_id, pid)
        else:
            return self.db.force_delete_podcast_by_pid(pid)
    
    # ==================== Episodes ====================
    
    def get_episodes_by_podcast(self, pid: str) -> List[EpisodeData]:
        """Get all episodes for a podcast."""
        if self.use_supabase:
            records = self.db.get_episodes_by_podcast(self.user_id, pid)
        else:
            records = self.db.get_episodes_by_podcast(pid)
        
        return [
            EpisodeData(
                id=r.id,
                eid=r.eid,
                pid=r.pid,
                podcast_id=getattr(r, 'podcast_id', 0),
                title=r.title,
                description=getattr(r, 'description', ''),
                duration=getattr(r, 'duration', 0),
                pub_date=getattr(r, 'pub_date', ''),
                audio_url=getattr(r, 'audio_url', ''),
                status=str(getattr(r, 'status', 'pending')),
                user_id=self.user_id,
            )
            for r in records
        ]
    
    def get_episode(self, eid: str) -> Optional[EpisodeData]:
        """Get an episode by eid."""
        if self.use_supabase:
            r = self.db.get_episode(self.user_id, eid)
        else:
            r = self.db.get_episode(eid)
        
        if not r:
            return None
        
        return EpisodeData(
            id=r.id,
            eid=r.eid,
            pid=r.pid,
            podcast_id=getattr(r, 'podcast_id', 0),
            title=r.title,
            description=getattr(r, 'description', ''),
            duration=getattr(r, 'duration', 0),
            pub_date=getattr(r, 'pub_date', ''),
            audio_url=getattr(r, 'audio_url', ''),
            status=str(getattr(r, 'status', 'pending')),
            user_id=self.user_id,
        )
    
    def episode_exists(self, eid: str) -> bool:
        """Check if an episode exists in the database."""
        if self.use_supabase:
            return self.db.episode_exists(self.user_id, eid)
        else:
            return self.db.episode_exists(eid)
    
    def add_episode(self, eid: str, pid: str, podcast_id: int, title: str,
                    description: str = "", duration: int = 0, pub_date: str = "",
                    audio_url: str = "") -> Optional[int]:
        """Add a new episode."""
        if self.use_supabase:
            return self.db.add_episode(
                self.user_id, podcast_id, eid, pid, title,
                description, duration, pub_date, audio_url
            )
        else:
            return self.db.add_episode(
                eid, pid, podcast_id, title,
                description, duration, pub_date, audio_url
            )
    
    def delete_episode(self, eid: str) -> bool:
        """Delete an episode."""
        if self.use_supabase:
            return self.db.delete_episode(self.user_id, eid)
        else:
            return self.db.delete_episode(eid)
    
    # ==================== Transcripts ====================
    
    def get_transcript(self, episode_id: str) -> Optional[TranscriptData]:
        """Get transcript for an episode."""
        if self.use_supabase:
            r = self.db.get_transcript(self.user_id, episode_id)
            if r:
                return TranscriptData(
                    episode_id=r.episode_id,
                    language=r.language,
                    duration=r.duration,
                    text=r.text,
                    segments=r.segments,
                )
        else:
            # Load from file
            transcript_path = DATA_DIR / "transcripts" / f"{episode_id}.json"
            if transcript_path.exists():
                with open(transcript_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return TranscriptData(
                    episode_id=data.get("episode_id", episode_id),
                    language=data.get("language", "zh"),
                    duration=data.get("duration", 0),
                    text=data.get("text", ""),
                    segments=data.get("segments", []),
                )
        return None
    
    def has_transcript(self, episode_id: str) -> bool:
        """Check if episode has a transcript."""
        if self.use_supabase:
            return self.db.has_transcript(self.user_id, episode_id)
        else:
            transcript_path = DATA_DIR / "transcripts" / f"{episode_id}.json"
            return transcript_path.exists()
    
    def save_transcript(self, transcript_data: TranscriptData) -> bool:
        """Save a transcript."""
        if self.use_supabase:
            return self.db.save_transcript(
                self.user_id,
                transcript_data.episode_id,
                transcript_data.language,
                transcript_data.duration,
                transcript_data.text,
                transcript_data.segments,
            )
        else:
            # Save to file
            transcripts_dir = DATA_DIR / "transcripts"
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            transcript_path = transcripts_dir / f"{transcript_data.episode_id}.json"
            data = {
                "episode_id": transcript_data.episode_id,
                "language": transcript_data.language,
                "duration": transcript_data.duration,
                "text": transcript_data.text,
                "segments": transcript_data.segments,
            }
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
    
    def delete_transcript(self, episode_id: str) -> bool:
        """Delete transcript for an episode."""
        if self.use_supabase:
            return self.db.delete_transcript(self.user_id, episode_id)
        else:
            transcript_path = DATA_DIR / "transcripts" / f"{episode_id}.json"
            if transcript_path.exists():
                transcript_path.unlink()
                return True
            return False
    
    # ==================== Summaries ====================
    
    def get_summary(self, episode_id: str) -> Optional[SummaryData]:
        """Get summary for an episode."""
        if self.use_supabase:
            r = self.db.get_summary(self.user_id, episode_id)
            if r:
                return SummaryData(
                    episode_id=r.episode_id,
                    title=r.title,
                    overview=r.overview,
                    topics=r.topics,
                    takeaways=r.takeaways,
                    key_points=r.key_points,
                )
        else:
            # Load from file
            summary_path = DATA_DIR / "summaries" / f"{episode_id}.json"
            if summary_path.exists():
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SummaryData(
                    episode_id=data.get("episode_id", episode_id),
                    title=data.get("title", ""),
                    overview=data.get("overview", ""),
                    topics=data.get("topics", []),
                    takeaways=data.get("takeaways", []),
                    key_points=data.get("key_points", []),
                )
        return None
    
    def get_all_summaries(self) -> List[SummaryData]:
        """Get all summaries."""
        if self.use_supabase:
            records = self.db.get_all_summaries(self.user_id)
            return [
                SummaryData(
                    episode_id=r.episode_id,
                    title=r.title,
                    overview=r.overview,
                    topics=r.topics,
                    takeaways=r.takeaways,
                    key_points=r.key_points,
                )
                for r in records
            ]
        else:
            # Load from files
            summaries_dir = DATA_DIR / "summaries"
            results = []
            if summaries_dir.exists():
                for path in summaries_dir.glob("*.json"):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        results.append(SummaryData(
                            episode_id=data.get("episode_id", path.stem),
                            title=data.get("title", ""),
                            overview=data.get("overview", ""),
                            topics=data.get("topics", []),
                            takeaways=data.get("takeaways", []),
                            key_points=data.get("key_points", []),
                        ))
                    except (json.JSONDecodeError, IOError):
                        continue
            return results
    
    def has_summary(self, episode_id: str) -> bool:
        """Check if episode has a summary."""
        if self.use_supabase:
            return self.db.has_summary(self.user_id, episode_id)
        else:
            summary_path = DATA_DIR / "summaries" / f"{episode_id}.json"
            return summary_path.exists()
    
    def save_summary(self, summary_data: SummaryData) -> bool:
        """Save a summary."""
        if self.use_supabase:
            return self.db.save_summary(
                self.user_id,
                summary_data.episode_id,
                summary_data.title,
                summary_data.overview,
                summary_data.topics,
                summary_data.takeaways,
                summary_data.key_points,
            )
        else:
            # Save to file
            summaries_dir = DATA_DIR / "summaries"
            summaries_dir.mkdir(parents=True, exist_ok=True)
            summary_path = summaries_dir / f"{summary_data.episode_id}.json"
            data = {
                "episode_id": summary_data.episode_id,
                "title": summary_data.title,
                "overview": summary_data.overview,
                "topics": summary_data.topics,
                "takeaways": summary_data.takeaways,
                "key_points": summary_data.key_points,
            }
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
    
    def delete_summary(self, episode_id: str) -> bool:
        """Delete summary for an episode."""
        if self.use_supabase:
            return self.db.delete_summary(self.user_id, episode_id)
        else:
            summary_path = DATA_DIR / "summaries" / f"{episode_id}.json"
            if summary_path.exists():
                summary_path.unlink()
                return True
            return False
    
    # ==================== Stats ====================
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics."""
        if self.use_supabase:
            return self.db.get_stats(self.user_id)
        else:
            podcasts = self.db.get_all_podcasts()
            total_episodes = sum(
                len(self.db.get_episodes_by_podcast(p.pid)) for p in podcasts
            )
            
            transcripts_dir = DATA_DIR / "transcripts"
            summaries_dir = DATA_DIR / "summaries"
            
            return {
                "podcasts": len(podcasts),
                "episodes": total_episodes,
                "transcripts": len(list(transcripts_dir.glob("*.json"))) if transcripts_dir.exists() else 0,
                "summaries": len(list(summaries_dir.glob("*.json"))) if summaries_dir.exists() else 0,
            }
    
    # ==================== Batch Operations (Performance) ====================
    
    def get_episode_counts_by_podcast(self) -> Dict[str, int]:
        """Get episode counts for all podcasts in one query."""
        if self.use_supabase:
            return self.db.get_all_episode_counts_by_podcast(self.user_id)
        else:
            # Local: count from database
            podcasts = self.db.get_all_podcasts()
            return {
                p.pid: len(self.db.get_episodes_by_podcast(p.pid))
                for p in podcasts
            }
    
    def get_transcript_episode_ids(self) -> set:
        """Get set of episode IDs that have transcripts."""
        if self.use_supabase:
            return self.db.get_transcript_episode_ids(self.user_id)
        else:
            # Local: check filesystem
            transcripts_dir = DATA_DIR / "transcripts"
            if not transcripts_dir.exists():
                return set()
            return {f.stem for f in transcripts_dir.glob("*.json")}
    
    def get_summary_episode_ids(self) -> set:
        """Get set of episode IDs that have summaries."""
        if self.use_supabase:
            return self.db.get_summary_episode_ids(self.user_id)
        else:
            # Local: check filesystem
            summaries_dir = DATA_DIR / "summaries"
            if not summaries_dir.exists():
                return set()
            return {f.stem for f in summaries_dir.glob("*.json") if not f.stem.startswith(".")}
    
    def get_summarized_counts_by_podcast(self) -> Dict[str, int]:
        """Get counts of episodes with summaries for all podcasts."""
        if self.use_supabase:
            return self.db.get_summarized_counts_by_podcast(self.user_id)
        else:
            # Local: count summaries per podcast
            summary_ids = self.get_summary_episode_ids()
            podcasts = self.db.get_all_podcasts()
            counts: Dict[str, int] = {}
            for p in podcasts:
                episodes = self.db.get_episodes_by_podcast(p.pid)
                count = sum(1 for ep in episodes if ep.eid in summary_ids)
                if count > 0:
                    counts[p.pid] = count
            return counts
    
    def get_truncated_transcripts(self, threshold: float = 0.85) -> List[Dict[str, Any]]:
        """
        Find transcripts that appear to be truncated.
        
        A transcript is considered truncated if its duration is less than
        threshold (default 85%) of the episode's expected duration.
        
        Returns list of dicts with episode_id, episode_title, episode_duration, 
        transcript_duration, and percentage.
        """
        if self.use_supabase:
            return self.db.get_truncated_transcripts(self.user_id, threshold)
        else:
            # Local: check transcript files against episode durations
            truncated = []
            podcasts = self.db.get_all_podcasts()
            transcripts_dir = DATA_DIR / "transcripts"
            
            if not transcripts_dir.exists():
                return []
            
            for p in podcasts:
                episodes = self.db.get_episodes_by_podcast(p.pid)
                for ep in episodes:
                    if ep.duration <= 0:
                        continue
                    
                    transcript_path = transcripts_dir / f"{ep.eid}.json"
                    if not transcript_path.exists():
                        continue
                    
                    try:
                        with open(transcript_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        transcript_duration = data.get("duration", 0)
                        
                        if transcript_duration <= 0:
                            continue
                        
                        percentage = transcript_duration / ep.duration
                        if percentage < threshold:
                            truncated.append({
                                "episode_id": ep.eid,
                                "pid": ep.pid,
                                "episode_title": ep.title,
                                "episode_duration": ep.duration,
                                "transcript_duration": transcript_duration,
                                "percentage": round(percentage * 100, 1),
                            })
                    except (json.JSONDecodeError, IOError):
                        continue
            
            return truncated


def get_db(user_id: Optional[str] = None) -> DatabaseInterface:
    """
    Get a database interface instance.
    
    Args:
        user_id: Optional user ID for multi-user support (Supabase).
                 If None and USE_SUPABASE is True, operations may fail.
                 If None and USE_SUPABASE is False, uses local SQLite.
    
    Returns:
        DatabaseInterface instance configured for the appropriate backend.
    """
    return DatabaseInterface(user_id)
