"""
Supabase database operations.
Provides user-scoped CRUD operations for podcasts, episodes, transcripts, and summaries.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from config import USE_SUPABASE
from api.supabase_client import get_supabase_admin_client


@dataclass
class PodcastRecord:
    id: int
    user_id: str
    pid: str
    title: str
    author: str
    description: str
    cover_url: str
    last_checked: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class EpisodeRecord:
    id: int
    podcast_id: int
    user_id: str
    eid: str
    pid: str
    title: str
    description: str
    duration: int
    pub_date: str
    audio_url: str
    status: str
    error_message: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class TranscriptRecord:
    id: int
    user_id: str
    episode_id: str
    language: str
    duration: float
    text: str
    segments: List[Dict[str, Any]]
    created_at: Optional[str] = None


@dataclass
class SummaryRecord:
    id: int
    user_id: str
    episode_id: str
    title: str
    overview: str
    topics: List[str]
    takeaways: List[str]
    key_points: List[Dict[str, Any]]
    created_at: Optional[str] = None


class SupabaseDatabase:
    """Database operations using Supabase."""
    
    def __init__(self):
        self.client = get_supabase_admin_client()
    
    # ==================== Podcasts ====================
    
    def get_all_podcasts(self, user_id: str) -> List[PodcastRecord]:
        """Get all podcasts for a user."""
        if not self.client:
            return []
        
        result = self.client.table("podcasts").select("*").eq("user_id", user_id).execute()
        return [PodcastRecord(**row) for row in result.data]
    
    def get_podcast(self, user_id: str, pid: str) -> Optional[PodcastRecord]:
        """Get a podcast by pid for a user."""
        if not self.client:
            return None
        
        result = self.client.table("podcasts").select("*").eq("user_id", user_id).eq("pid", pid).execute()
        if result.data:
            return PodcastRecord(**result.data[0])
        return None
    
    def get_podcast_by_id(self, podcast_id: int) -> Optional[PodcastRecord]:
        """Get a podcast by database ID."""
        if not self.client:
            return None
        
        result = self.client.table("podcasts").select("*").eq("id", podcast_id).execute()
        if result.data:
            return PodcastRecord(**result.data[0])
        return None
    
    def add_podcast(self, user_id: str, pid: str, title: str, author: str = "",
                    description: str = "", cover_url: str = "") -> Optional[int]:
        """Add a new podcast for a user."""
        if not self.client:
            return None
        
        result = self.client.table("podcasts").insert({
            "user_id": user_id,
            "pid": pid,
            "title": title,
            "author": author,
            "description": description,
            "cover_url": cover_url
        }).execute()
        
        if result.data:
            return result.data[0]["id"]
        return None
    
    def delete_podcast(self, user_id: str, pid: str) -> bool:
        """Delete a podcast and all its episodes."""
        if not self.client:
            return False
        
        self.client.table("podcasts").delete().eq("user_id", user_id).eq("pid", pid).execute()
        return True
    
    # ==================== Episodes ====================
    
    def get_episodes_by_podcast(self, user_id: str, pid: str) -> List[EpisodeRecord]:
        """Get all episodes for a podcast."""
        if not self.client:
            return []
        
        result = self.client.table("episodes").select("*").eq("user_id", user_id).eq("pid", pid).order("pub_date", desc=True).execute()
        return [EpisodeRecord(**row) for row in result.data]
    
    def get_episode(self, user_id: str, eid: str) -> Optional[EpisodeRecord]:
        """Get an episode by eid."""
        if not self.client:
            return None
        
        result = self.client.table("episodes").select("*").eq("user_id", user_id).eq("eid", eid).execute()
        if result.data:
            return EpisodeRecord(**result.data[0])
        return None
    
    def add_episode(self, user_id: str, podcast_id: int, eid: str, pid: str, title: str,
                    description: str = "", duration: int = 0, pub_date: str = "",
                    audio_url: str = "", status: str = "pending") -> Optional[int]:
        """Add a new episode."""
        if not self.client:
            return None
        
        result = self.client.table("episodes").insert({
            "user_id": user_id,
            "podcast_id": podcast_id,
            "eid": eid,
            "pid": pid,
            "title": title,
            "description": description,
            "duration": duration,
            "pub_date": pub_date,
            "audio_url": audio_url,
            "status": status
        }).execute()
        
        if result.data:
            return result.data[0]["id"]
        return None
    
    def update_episode_status(self, user_id: str, eid: str, status: str,
                               error_message: str = "") -> bool:
        """Update episode status."""
        if not self.client:
            return False
        
        self.client.table("episodes").update({
            "status": status,
            "error_message": error_message,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("user_id", user_id).eq("eid", eid).execute()
        return True
    
    def delete_episode(self, user_id: str, eid: str) -> bool:
        """Delete an episode."""
        if not self.client:
            return False
        
        self.client.table("episodes").delete().eq("user_id", user_id).eq("eid", eid).execute()
        return True
    
    # ==================== Transcripts ====================
    
    def get_transcript(self, user_id: str, episode_id: str) -> Optional[TranscriptRecord]:
        """Get a transcript by episode ID."""
        if not self.client:
            return None
        
        result = self.client.table("transcripts").select("*").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        if not result.data:
            return None
        
        transcript = result.data[0]
        
        # Get segments
        segments_result = self.client.table("transcript_segments").select("*").eq("transcript_id", transcript["id"]).order("start_time").execute()
        segments = [{"start": s["start_time"], "end": s["end_time"], "text": s["text"]} for s in segments_result.data]
        
        return TranscriptRecord(
            id=transcript["id"],
            user_id=transcript["user_id"],
            episode_id=transcript["episode_id"],
            language=transcript["language"],
            duration=transcript["duration"],
            text=transcript["text"],
            segments=segments
        )
    
    def save_transcript(self, user_id: str, episode_id: str, language: str,
                        duration: float, text: str, segments: List[Dict[str, Any]]) -> bool:
        """Save a transcript with segments."""
        if not self.client:
            return False
        
        # Upsert transcript
        result = self.client.table("transcripts").upsert({
            "user_id": user_id,
            "episode_id": episode_id,
            "language": language,
            "duration": duration,
            "text": text
        }, on_conflict="user_id,episode_id").execute()
        
        if not result.data:
            return False
        
        transcript_id = result.data[0]["id"]
        
        # Delete old segments
        self.client.table("transcript_segments").delete().eq("transcript_id", transcript_id).execute()
        
        # Insert new segments
        if segments:
            segment_rows = [
                {
                    "transcript_id": transcript_id,
                    "start_time": seg.get("start", 0),
                    "end_time": seg.get("end", 0),
                    "text": seg.get("text", "")
                }
                for seg in segments
            ]
            self.client.table("transcript_segments").insert(segment_rows).execute()
        
        return True
    
    def has_transcript(self, user_id: str, episode_id: str) -> bool:
        """Check if a transcript exists."""
        if not self.client:
            return False
        
        result = self.client.table("transcripts").select("id").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        return len(result.data) > 0
    
    # ==================== Summaries ====================
    
    def get_summary(self, user_id: str, episode_id: str) -> Optional[SummaryRecord]:
        """Get a summary by episode ID."""
        if not self.client:
            return None
        
        result = self.client.table("summaries").select("*").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        if not result.data:
            return None
        
        summary = result.data[0]
        
        # Get key points
        kp_result = self.client.table("summary_key_points").select("*").eq("summary_id", summary["id"]).execute()
        key_points = [
            {
                "topic": kp["topic"],
                "summary": kp["summary"],
                "original_quote": kp["original_quote"],
                "timestamp": kp["timestamp"]
            }
            for kp in kp_result.data
        ]
        
        return SummaryRecord(
            id=summary["id"],
            user_id=summary["user_id"],
            episode_id=summary["episode_id"],
            title=summary["title"],
            overview=summary["overview"],
            topics=summary.get("topics", []),
            takeaways=summary.get("takeaways", []),
            key_points=key_points
        )
    
    def get_all_summaries(self, user_id: str) -> List[SummaryRecord]:
        """Get all summaries for a user."""
        if not self.client:
            return []
        
        result = self.client.table("summaries").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        
        summaries = []
        for summary in result.data:
            # Get key points for each summary
            kp_result = self.client.table("summary_key_points").select("*").eq("summary_id", summary["id"]).execute()
            key_points = [
                {
                    "topic": kp["topic"],
                    "summary": kp["summary"],
                    "original_quote": kp["original_quote"],
                    "timestamp": kp["timestamp"]
                }
                for kp in kp_result.data
            ]
            
            summaries.append(SummaryRecord(
                id=summary["id"],
                user_id=summary["user_id"],
                episode_id=summary["episode_id"],
                title=summary["title"],
                overview=summary["overview"],
                topics=summary.get("topics", []),
                takeaways=summary.get("takeaways", []),
                key_points=key_points
            ))
        
        return summaries
    
    def save_summary(self, user_id: str, episode_id: str, title: str, overview: str,
                     topics: List[str], takeaways: List[str],
                     key_points: List[Dict[str, Any]]) -> bool:
        """Save a summary with key points."""
        if not self.client:
            return False
        
        # Upsert summary
        result = self.client.table("summaries").upsert({
            "user_id": user_id,
            "episode_id": episode_id,
            "title": title,
            "overview": overview,
            "topics": topics,
            "takeaways": takeaways
        }, on_conflict="user_id,episode_id").execute()
        
        if not result.data:
            return False
        
        summary_id = result.data[0]["id"]
        
        # Delete old key points
        self.client.table("summary_key_points").delete().eq("summary_id", summary_id).execute()
        
        # Insert new key points
        if key_points:
            kp_rows = [
                {
                    "summary_id": summary_id,
                    "topic": kp.get("topic", ""),
                    "summary": kp.get("summary", ""),
                    "original_quote": kp.get("original_quote", ""),
                    "timestamp": kp.get("timestamp", "")
                }
                for kp in key_points
            ]
            self.client.table("summary_key_points").insert(kp_rows).execute()
        
        return True
    
    def has_summary(self, user_id: str, episode_id: str) -> bool:
        """Check if a summary exists."""
        if not self.client:
            return False
        
        result = self.client.table("summaries").select("id").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        return len(result.data) > 0
    
    # ==================== Stats ====================
    
    def get_stats(self, user_id: str) -> Dict[str, int]:
        """Get statistics for a user."""
        if not self.client:
            return {"podcasts": 0, "episodes": 0, "transcripts": 0, "summaries": 0}
        
        podcasts = self.client.table("podcasts").select("id", count="exact").eq("user_id", user_id).execute()
        episodes = self.client.table("episodes").select("id", count="exact").eq("user_id", user_id).execute()
        transcripts = self.client.table("transcripts").select("id", count="exact").eq("user_id", user_id).execute()
        summaries = self.client.table("summaries").select("id", count="exact").eq("user_id", user_id).execute()
        
        return {
            "podcasts": podcasts.count or 0,
            "episodes": episodes.count or 0,
            "transcripts": transcripts.count or 0,
            "summaries": summaries.count or 0
        }


# Singleton instance
_supabase_db: Optional[SupabaseDatabase] = None


def get_supabase_database() -> Optional[SupabaseDatabase]:
    """Get the Supabase database instance."""
    global _supabase_db
    if not USE_SUPABASE:
        return None
    if _supabase_db is None:
        _supabase_db = SupabaseDatabase()
    return _supabase_db
