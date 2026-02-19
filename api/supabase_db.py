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
    
    def get_podcast_by_id(self, user_id: str, podcast_id: int) -> Optional[PodcastRecord]:
        """Get a podcast by database ID, filtered by user_id for security."""
        if not self.client:
            return None
        
        result = self.client.table("podcasts").select("*").eq("user_id", user_id).eq("id", podcast_id).execute()
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
    
    def update_podcast_cover(self, user_id: str, pid: str, cover_url: str) -> bool:
        """Update the cover URL for a podcast."""
        if not self.client:
            return False
        
        self.client.table("podcasts").update({
            "cover_url": cover_url
        }).eq("user_id", user_id).eq("pid", pid).execute()
        return True
    
    def update_podcast_checked(self, user_id: str, pid: str) -> bool:
        """Update the last checked timestamp for a podcast."""
        if not self.client:
            return False
        
        from datetime import datetime
        self.client.table("podcasts").update({
            "last_checked": datetime.now().isoformat()
        }).eq("user_id", user_id).eq("pid", pid).execute()
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
    
    def episode_exists(self, user_id: str, eid: str) -> bool:
        """Check if an episode exists in the database."""
        if not self.client:
            return False
        
        result = self.client.table("episodes").select("eid").eq("user_id", user_id).eq("eid", eid).limit(1).execute()
        return len(result.data) > 0
    
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
        
        # Get ALL segments (Supabase default limit is 1000, so we paginate)
        all_segments = []
        offset = 0
        page_size = 1000
        
        while True:
            segments_result = self.client.table("transcript_segments").select("*").eq(
                "transcript_id", transcript["id"]
            ).order("start_time").range(offset, offset + page_size - 1).execute()
            
            if not segments_result.data:
                break
                
            all_segments.extend(segments_result.data)
            
            if len(segments_result.data) < page_size:
                break  # Last page
                
            offset += page_size
        
        segments = [{"start": s["start_time"], "end": s["end_time"], "text": s["text"]} for s in all_segments]
        
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
    
    def find_shared_transcript(self, episode_id: str, min_duration: float = 0) -> Optional[TranscriptRecord]:
        """
        Find any valid transcript for an episode from any user (shared pool).
        
        This allows reusing transcripts across users since transcript content
        is the same regardless of who requested it.
        
        Args:
            episode_id: The episode ID to find a transcript for
            min_duration: Minimum transcript duration to consider valid (optional)
            
        Returns:
            TranscriptRecord if a valid shared transcript exists, None otherwise
        """
        if not self.client:
            return None
        
        # Find any transcript for this episode, ordered by duration (prefer longest/most complete)
        query = self.client.table("transcripts").select("*").eq("episode_id", episode_id)
        if min_duration > 0:
            query = query.gte("duration", min_duration)
        result = query.order("duration", desc=True).limit(1).execute()
        
        if not result.data:
            return None
        
        transcript = result.data[0]
        
        # Get segments
        segments_result = self.client.table("transcript_segments").select("*").eq("transcript_id", transcript["id"]).order("start_time").execute()
        segments = [
            {
                "start": seg["start_time"],
                "end": seg["end_time"],
                "text": seg["text"]
            }
            for seg in segments_result.data
        ] if segments_result.data else []
        
        return TranscriptRecord(
            id=transcript["id"],
            user_id=transcript["user_id"],
            episode_id=transcript["episode_id"],
            language=transcript["language"],
            duration=transcript["duration"],
            text=transcript.get("text", ""),
            segments=segments
        )
    
    def copy_transcript_to_user(self, source_transcript: TranscriptRecord, target_user_id: str) -> bool:
        """
        Copy a transcript from one user to another (for sharing).
        
        Args:
            source_transcript: The transcript to copy
            target_user_id: The user ID to copy the transcript to
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False
        
        # Check if target user already has this transcript
        existing = self.client.table("transcripts").select("id").eq("user_id", target_user_id).eq("episode_id", source_transcript.episode_id).execute()
        if existing.data:
            return True  # Already exists
        
        # Copy the transcript
        return self.save_transcript(
            target_user_id,
            source_transcript.episode_id,
            source_transcript.language,
            source_transcript.duration,
            source_transcript.text,
            source_transcript.segments
        )
    
    # ==================== Summaries ====================
    
    def get_summary(self, user_id: str, episode_id: str) -> Optional[SummaryRecord]:
        """Get a summary by episode ID."""
        if not self.client:
            return None
        
        result = self.client.table("summaries").select("*").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        if not result.data:
            return None
        
        summary = result.data[0]
        
        # Get key points from summary_key_points table
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
        
        # Check if key_points stored directly in summaries table (old format)
        # Use whichever source has more key_points
        old_key_points = summary.get("key_points", []) or []
        if isinstance(old_key_points, list) and len(old_key_points) > len(key_points):
            key_points = old_key_points
        
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
        
        if not result.data:
            return []
        
        # Get all summary IDs
        summary_ids = [s["id"] for s in result.data]
        
        print(f"[DEBUG] get_all_summaries: Found {len(summary_ids)} summaries, fetching key points...")
        
        # Fetch ALL key points in ONE query instead of N queries
        kp_by_summary: Dict[int, List[Dict[str, Any]]] = {}
        
        if summary_ids:
            try:
                kp_result = self.client.table("summary_key_points").select("*").in_("summary_id", summary_ids).execute()
                print(f"[DEBUG] get_all_summaries: Fetched {len(kp_result.data) if kp_result.data else 0} key points total")
                
                # Group key points by summary_id
                for kp in (kp_result.data or []):
                    sid = kp["summary_id"]
                    if sid not in kp_by_summary:
                        kp_by_summary[sid] = []
                    kp_by_summary[sid].append({
                        "topic": kp["topic"],
                        "summary": kp["summary"],
                        "original_quote": kp["original_quote"],
                        "timestamp": kp["timestamp"]
                    })
            except Exception as e:
                print(f"[DEBUG] get_all_summaries: Error fetching key points: {e}")
        
        summaries = []
        for summary in result.data:
            # Get key_points from summary_key_points table first
            kp_list = kp_by_summary.get(summary["id"], [])
            
            # Check if key_points stored directly in summaries table (old format)
            # Use whichever source has more key_points
            old_kp_list = summary.get("key_points", []) or []
            if isinstance(old_kp_list, list) and len(old_kp_list) > len(kp_list):
                kp_list = old_kp_list
            
            summaries.append(SummaryRecord(
                id=summary["id"],
                user_id=summary["user_id"],
                episode_id=summary["episode_id"],
                title=summary["title"],
                overview=summary["overview"],
                topics=summary.get("topics", []),
                takeaways=summary.get("takeaways", []),
                key_points=kp_list
            ))
        
        return summaries
    
    def save_summary(self, user_id: str, episode_id: str, title: str, overview: str,
                     topics: List[str], takeaways: List[str],
                     key_points: List[Dict[str, Any]]) -> bool:
        """Save a summary with key points."""
        if not self.client:
            return False
        
        print(f"[DEBUG] save_summary: episode_id={episode_id}, topics={len(topics)}, key_points={len(key_points)}")
        
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
            print(f"[DEBUG] save_summary: Failed to upsert summary")
            return False
        
        summary_id = result.data[0]["id"]
        print(f"[DEBUG] save_summary: summary_id={summary_id}")
        
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
            try:
                insert_result = self.client.table("summary_key_points").insert(kp_rows).execute()
                print(f"[DEBUG] save_summary: Inserted {len(insert_result.data) if insert_result.data else 0} key points")
            except Exception as e:
                print(f"[DEBUG] save_summary: Failed to insert key points: {e}")
        else:
            print(f"[DEBUG] save_summary: No key points to insert")
        
        return True
    
    def has_summary(self, user_id: str, episode_id: str) -> bool:
        """Check if a summary exists."""
        if not self.client:
            return False
        
        result = self.client.table("summaries").select("id").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        return len(result.data) > 0
    
    def delete_transcript(self, user_id: str, episode_id: str) -> bool:
        """Delete a transcript and its segments."""
        if not self.client:
            return False
        
        # Get transcript ID first
        result = self.client.table("transcripts").select("id").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        if not result.data:
            return False
        
        transcript_id = result.data[0]["id"]
        
        # Delete segments first (foreign key constraint)
        self.client.table("transcript_segments").delete().eq("transcript_id", transcript_id).execute()
        
        # Delete transcript
        self.client.table("transcripts").delete().eq("id", transcript_id).execute()
        return True
    
    def delete_summary(self, user_id: str, episode_id: str) -> bool:
        """Delete a summary and its key points."""
        if not self.client:
            return False
        
        # Get summary ID first
        result = self.client.table("summaries").select("id").eq("user_id", user_id).eq("episode_id", episode_id).execute()
        if not result.data:
            return False
        
        summary_id = result.data[0]["id"]
        
        # Delete key points first (foreign key constraint)
        self.client.table("summary_key_points").delete().eq("summary_id", summary_id).execute()
        
        # Delete summary
        self.client.table("summaries").delete().eq("id", summary_id).execute()
        return True
    
    # ==================== Stats ====================
    
    def get_stats(self, user_id: str) -> Dict[str, int]:
        """Get statistics for a user."""
        if not self.client:
            return {"podcasts": 0, "episodes": 0, "transcripts": 0, "summaries": 0}
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        def count_table(table: str) -> int:
            # Retry logic for transient connection errors
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = self.client.table(table).select("id", count="exact").eq("user_id", user_id).execute()
                    return result.count or 0
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    # Log but don't crash - return 0 for this table
                    print(f"[Stats] Failed to count {table} after {max_retries} attempts: {e}")
                    return 0
        
        # Execute all count queries in parallel
        tables = ["podcasts", "episodes", "transcripts", "summaries"]
        results = {}
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(count_table, table): table for table in tables}
            for future in as_completed(futures):
                table = futures[future]
                results[table] = future.result()
        
        return results
    
    # ==================== Batch Operations ====================
    
    def get_transcript_episode_ids(self, user_id: str) -> set:
        """Get set of episode IDs that have transcripts."""
        if not self.client:
            return set()
        result = self.client.table("transcripts").select("episode_id").eq("user_id", user_id).execute()
        return {r["episode_id"] for r in result.data}
    
    def get_summary_episode_ids(self, user_id: str) -> set:
        """Get set of episode IDs that have summaries."""
        if not self.client:
            return set()
        result = self.client.table("summaries").select("episode_id").eq("user_id", user_id).execute()
        return {r["episode_id"] for r in result.data}
    
    def get_all_episode_counts_by_podcast(self, user_id: str) -> Dict[str, int]:
        """Get episode counts for all podcasts in one query."""
        if not self.client:
            return {}
        result = self.client.table("episodes").select("pid").eq("user_id", user_id).execute()
        counts: Dict[str, int] = {}
        for r in result.data:
            pid = r["pid"]
            counts[pid] = counts.get(pid, 0) + 1
        return counts
    
    def get_summarized_counts_by_podcast(self, user_id: str) -> Dict[str, int]:
        """Get counts of episodes with summaries for all podcasts."""
        if not self.client:
            return {}
        
        # Get all episode_ids that have summaries
        summary_result = self.client.table("summaries").select("episode_id").eq("user_id", user_id).execute()
        summary_episode_ids = {r["episode_id"] for r in summary_result.data}
        
        if not summary_episode_ids:
            return {}
        
        # Get pid for each episode that has a summary
        episodes_result = self.client.table("episodes").select("eid, pid").eq("user_id", user_id).execute()
        
        counts: Dict[str, int] = {}
        for ep in episodes_result.data:
            if ep["eid"] in summary_episode_ids:
                pid = ep["pid"]
                counts[pid] = counts.get(pid, 0) + 1
        
        return counts
    
    # ==================== Video Tasks ====================

    def create_video_task(self, user_id: str, task_id: str, task_data: dict) -> str:
        """Create a new video task."""
        if not self.client:
            return task_id

        row = {
            "id": task_id,
            "user_id": user_id,
            "url": task_data.get("url", ""),
            "platform": task_data.get("platform", ""),
            "title": task_data.get("title", ""),
            "status": "pending",
            "style": task_data.get("style", "detailed"),
            "model": task_data.get("model", ""),
            "formats": task_data.get("formats", []),
            "quality": task_data.get("quality", "medium"),
            "video_quality": task_data.get("video_quality", "720"),
            "extras": task_data.get("extras", ""),
            "video_understanding": bool(task_data.get("video_understanding")),
            "video_interval": task_data.get("video_interval", 4),
            "grid_cols": task_data.get("grid_cols", 3),
            "grid_rows": task_data.get("grid_rows", 3),
        }
        self.client.table("video_tasks").insert(row).execute()
        return task_id

    def update_video_task(self, task_id: str, updates: dict):
        """Update video task fields."""
        if not self.client:
            return

        allowed = {
            "status", "progress", "message", "markdown", "transcript_json",
            "title", "thumbnail", "duration", "error", "model",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = datetime.utcnow().isoformat()
        self.client.table("video_tasks").update(fields).eq("id", task_id).execute()

    def get_video_task(self, task_id: str, user_id: str = None) -> Optional[dict]:
        """Get a video task by ID."""
        if not self.client:
            return None

        query = self.client.table("video_tasks").select("*").eq("id", task_id)
        if user_id:
            query = query.eq("user_id", user_id)
        result = query.execute()
        if not result.data:
            return None
        return self._video_task_to_dict(result.data[0])

    def list_video_tasks(self, user_id: str, limit: int = 100) -> List[dict]:
        """List all video tasks for a user."""
        if not self.client:
            return []

        result = (
            self.client.table("video_tasks")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [self._video_task_to_dict(r) for r in result.data]

    def delete_video_task(self, task_id: str, user_id: str = None) -> bool:
        """Delete a video task and its versions."""
        if not self.client:
            return False

        # Versions are CASCADE deleted via FK
        query = self.client.table("video_tasks").delete().eq("id", task_id)
        if user_id:
            query = query.eq("user_id", user_id)
        result = query.execute()
        return bool(result.data)

    def add_video_task_version(self, task_id: str, version_id: str,
                               content: str, style: str = "", model_name: str = "") -> str:
        """Add a version to a video task."""
        if not self.client:
            return version_id

        self.client.table("video_task_versions").insert({
            "id": version_id,
            "task_id": task_id,
            "content": content,
            "style": style,
            "model_name": model_name,
        }).execute()
        return version_id

    def get_video_task_versions(self, task_id: str) -> List[dict]:
        """Get all versions for a video task."""
        if not self.client:
            return []

        result = (
            self.client.table("video_task_versions")
            .select("*")
            .eq("task_id", task_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [dict(r) for r in result.data]

    @staticmethod
    def _video_task_to_dict(row: dict) -> dict:
        """Convert a Supabase video_tasks row to the dict format expected by the app."""
        d = dict(row)
        # formats is already JSONB in Supabase, comes back as list
        if isinstance(d.get("formats"), str):
            import json as _json
            try:
                d["formats"] = _json.loads(d["formats"])
            except (ValueError, TypeError):
                d["formats"] = []
        # Parse transcript_json
        transcript_json = d.get("transcript_json", "")
        if transcript_json:
            import json as _json
            try:
                d["transcript"] = _json.loads(transcript_json)
            except (ValueError, TypeError):
                d["transcript"] = None
        else:
            d["transcript"] = None
        d.pop("transcript_json", None)
        # Ensure boolean
        d["video_understanding"] = bool(d.get("video_understanding"))
        return d

    def get_truncated_transcripts(self, user_id: str, threshold: float = 0.95) -> List[Dict[str, Any]]:
        """
        Find transcripts that appear to be truncated.
        
        A transcript is considered truncated if its duration is less than
        threshold (default 95%) of the episode's expected duration.
        
        Returns list of dicts with episode_id, episode_title, episode_duration, 
        transcript_duration, and percentage.
        """
        if not self.client:
            return []
        
        # Get all transcripts with duration and ID
        transcripts_result = self.client.table("transcripts").select(
            "id, episode_id, duration"
        ).eq("user_id", user_id).execute()
        
        if not transcripts_result.data:
            return []
        
        transcript_info = {
            r["episode_id"]: {"id": r["id"], "duration": r["duration"]} 
            for r in transcripts_result.data
        }
        
        # Get max segment end_time for each transcript to verify actual duration
        # This is more reliable than the duration field
        segment_max_times = {}
        for episode_id, info in transcript_info.items():
            transcript_id = info["id"]
            segments_result = self.client.table("transcript_segments").select(
                "end_time"
            ).eq("transcript_id", transcript_id).order("end_time", desc=True).limit(1).execute()
            
            if segments_result.data:
                segment_max_times[episode_id] = segments_result.data[0]["end_time"]
        
        # Get all episodes with duration
        episodes_result = self.client.table("episodes").select(
            "eid, pid, title, duration"
        ).eq("user_id", user_id).execute()
        
        truncated = []
        for ep in episodes_result.data:
            episode_duration = ep["duration"]
            
            # Skip episodes without transcripts
            if ep["eid"] not in transcript_info:
                continue
            
            # Get transcript duration - prefer segment max time, fallback to duration field
            transcript_duration = segment_max_times.get(ep["eid"]) or transcript_info[ep["eid"]]["duration"] or 0
            
            if transcript_duration <= 0:
                continue
            
            # If episode duration is 0 or very small, try to detect based on transcript being too short
            # (less than 10 minutes for a transcript with content suggests truncation if episode should be longer)
            if episode_duration <= 0:
                # Can't compare without episode duration, skip
                continue
            
            percentage = transcript_duration / episode_duration
            if percentage < threshold:
                truncated.append({
                    "episode_id": ep["eid"],
                    "pid": ep["pid"],
                    "episode_title": ep["title"],
                    "episode_duration": episode_duration,
                    "transcript_duration": round(transcript_duration, 1),
                    "percentage": round(percentage * 100, 1),
                })
        
        return truncated


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
