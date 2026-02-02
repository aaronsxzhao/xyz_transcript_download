"""Processing endpoints with WebSocket support."""
import asyncio
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Set, Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Depends

from api.schemas import ProcessRequest, BatchProcessRequest, ProcessingStatus, ResummarizeRequest
from api.auth import get_current_user, User
from api.db import get_db, TranscriptData, SummaryData
from config import DATA_DIR, BACKGROUND_REFINEMENT_TIMEOUT, WEBSOCKET_HEARTBEAT_INTERVAL
from logger import notify_discord, get_logger

logger = get_logger("processing")

router = APIRouter()

# File-based job persistence
JOBS_FILE = DATA_DIR / "jobs.json"
JOBS_LOCK_FILE = DATA_DIR / "jobs.json.lock"

# Thread-safe lock for jobs dict and cancelled_jobs set
# Use RLock to allow recursive locking (e.g., update_job_status calling _save_jobs_to_file)
_jobs_lock = threading.RLock()

# In-memory job tracking (loaded from file on startup)
jobs: Dict[str, ProcessingStatus] = {}

# Track cancelled jobs
cancelled_jobs: Set[str] = set()

# Cache for /api/jobs responses to reduce lock contention from polling
# Now user-scoped: {"user_id_or_anonymous": {"data": ..., "time": ...}}
_jobs_cache: Dict = {}
_JOBS_CACHE_TTL = 0.5  # 500ms cache - multiple polls in same window share response


def _load_jobs_from_file():
    """Load jobs from persistent storage on startup."""
    global jobs
    with _jobs_lock:
        if JOBS_FILE.exists():
            try:
                with open(JOBS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                jobs = {
                    job_id: ProcessingStatus(**job_data)
                    for job_id, job_data in data.items()
                }
                # Mark any "in-progress" jobs as failed (they didn't complete before shutdown)
                for job_id, job in jobs.items():
                    if job.status in ("pending", "fetching", "downloading", "transcribing", "summarizing", "cancelling"):
                        job.status = "failed"
                        job.message = "Interrupted by server restart"
                _save_jobs_to_file_unlocked()
            except (json.JSONDecodeError, IOError, TypeError) as e:
                # If file is corrupted, start fresh
                jobs = {}


def _save_jobs_to_file_unlocked():
    """Persist jobs to file (caller must hold _jobs_lock)."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {job_id: job.model_dump() for job_id, job in jobs.items()}
        # Use atomic write: write to temp file then rename
        temp_file = JOBS_FILE.with_suffix('.json.tmp')
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Atomic rename (on POSIX systems)
        temp_file.replace(JOBS_FILE)
    except IOError:
        pass  # Best effort - don't fail the operation


def _save_jobs_to_file():
    """Persist jobs to file (thread-safe)."""
    with _jobs_lock:
        _save_jobs_to_file_unlocked()


def _cleanup_old_jobs(max_completed_jobs: int = 100):
    """Remove old completed/failed jobs to prevent unbounded growth."""
    global jobs
    with _jobs_lock:
        terminal_jobs = [
            (job_id, job) for job_id, job in jobs.items()
            if job.status in ("completed", "failed", "cancelled")
        ]
        if len(terminal_jobs) > max_completed_jobs:
            # Keep only the most recent jobs (by job_id which has timestamp-like ordering)
            terminal_jobs.sort(key=lambda x: x[0])
            jobs_to_remove = terminal_jobs[:-max_completed_jobs]
            for job_id, _ in jobs_to_remove:
                del jobs[job_id]
            _save_jobs_to_file_unlocked()


# Load jobs on module import
_load_jobs_from_file()

# Limit concurrent episode processing to prevent resource exhaustion
# When limit reached, jobs queue automatically and wait for a slot
# Reduced from 3 to 2 to prevent ffmpeg resource contention during concurrent processing
PROCESSING_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="episode_processor")

# Store reference to the main event loop for thread-safe broadcasting
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Set the main event loop reference for thread-safe broadcasting."""
    global _main_loop
    _main_loop = loop


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Get the main event loop for thread-safe broadcasting."""
    global _main_loop
    if _main_loop is None:
        try:
            _main_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
    return _main_loop


def is_job_cancelled(job_id: str) -> bool:
    """Check if a job has been cancelled."""
    with _jobs_lock:
        return job_id in cancelled_jobs


def mark_job_cancelled(job_id: str):
    """Mark a job as cancelled and clean up."""
    with _jobs_lock:
        cancelled_jobs.discard(job_id)


class ConnectionManager:
    """Manage WebSocket connections with user isolation (thread-safe)."""
    
    def __init__(self):
        # Store (websocket, user_id) tuples for user isolation
        self.active_connections: list[tuple[WebSocket, Optional[str]]] = []
        self._lock = threading.Lock()
    
    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None):
        await websocket.accept()
        with self._lock:
            self.active_connections.append((websocket, user_id))
            print(f"[WS] Client connected (user={user_id}). Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        with self._lock:
            self.active_connections = [(ws, uid) for ws, uid in self.active_connections if ws != websocket]
    
    async def broadcast_to_user(self, message: dict, target_user_id: Optional[str]):
        """Broadcast message only to connections belonging to the specified user."""
        # Take a snapshot of matching connections under lock
        with self._lock:
            matching_connections = [ws for ws, uid in self.active_connections if uid == target_user_id]
        
        # Send to matching connections (outside lock to avoid blocking)
        dead_connections = []
        for connection in matching_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        
        # Clean up dead connections
        if dead_connections:
            with self._lock:
                self.active_connections = [(ws, uid) for ws, uid in self.active_connections if ws not in dead_connections]
    
    async def broadcast(self, message: dict):
        """Broadcast to all connections (legacy - use broadcast_to_user for user isolation)."""
        with self._lock:
            connections = [ws for ws, uid in self.active_connections]
        
        dead_connections = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        
        if dead_connections:
            with self._lock:
                self.active_connections = [(ws, uid) for ws, uid in self.active_connections if ws not in dead_connections]


manager = ConnectionManager()


def update_job_status(job_id: str, status: str, progress: float = 0, message: str = "",
                      episode_id: str = None, episode_title: str = None):
    """Update job status, persist to file, and notify clients."""
    with _jobs_lock:
        if job_id in jobs:
            jobs[job_id].status = status
            jobs[job_id].progress = progress
            jobs[job_id].message = message
            if episode_id:
                jobs[job_id].episode_id = episode_id
            if episode_title:
                jobs[job_id].episode_title = episode_title
            
            # Persist to file on terminal states or significant progress changes
            if status in ("completed", "failed", "cancelled") or progress % 10 < 1:
                _save_jobs_to_file_unlocked()
        
        # Invalidate all user caches so next poll gets fresh data
        _jobs_cache.clear()
    
    # Broadcast update to all connected WebSocket clients (outside lock to avoid deadlock)
    # Use the cached main event loop for thread-safe broadcasting
    try:
        loop = get_main_loop()
        if loop and loop.is_running():
            # Schedule broadcast from sync context
            asyncio.run_coroutine_threadsafe(broadcast_status(job_id), loop)
        else:
            print(f"[WS] Cannot broadcast: loop={'exists' if loop else 'None'}, running={loop.is_running() if loop else 'N/A'}")
    except Exception as e:
        # Log but don't fail - status is still updated in memory
        print(f"[WS] Broadcast error: {e}")


async def broadcast_status(job_id: str):
    """Broadcast job status only to the user who owns the job."""
    with _jobs_lock:
        if job_id in jobs:
            job = jobs[job_id]
            job_data = job.model_dump()
            job_user_id = job.user_id
        else:
            return
    
    num_connections = len(manager.active_connections)
    if num_connections > 0:
        print(f"[WS] Broadcasting job {job_id} progress={job_data.get('progress', 0):.1f}% to user={job_user_id}")
    
    # Only broadcast to connections belonging to the job's owner
    await manager.broadcast_to_user({
        "type": "job_update",
        "job": job_data,
    }, job_user_id)


def _process_track(audio_path, episode_id: str, episode_title: str, 
                   transcriber, summarizer, progress_callback=None):
    """
    Process a single audio track (transcribe + summarize).
    Returns (transcript, summary) tuple or (None, None) on failure.
    """
    try:
        # Transcribe
        transcript = transcriber.transcribe(audio_path, episode_id, progress_callback=progress_callback)
        if not transcript:
            return None, None
        
        # Summarize
        summary = summarizer.summarize(transcript, episode_title=episode_title)
        return transcript, summary
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, None


def _background_refinement(audio_path, episode, fast_summary, db_interface, transcriber, summarizer, user_id):
    """
    Background task to process accurate track and silently update summary.
    Runs after job is already marked complete - user doesn't see this.
    
    Includes timeout protection to prevent indefinite processing.
    For 90-minute episodes, transcription + summarization typically takes 1-2 hours.
    Default timeout is 3 hours (configurable via BACKGROUND_REFINEMENT_TIMEOUT).
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
    from logger import get_logger
    
    logger = get_logger("background_refinement")
    start_time = time.time()
    
    def do_refinement():
        """Inner function that does the actual refinement work."""
        from summarizer import merge_summaries
        
        # Transcribe original audio
        accurate_transcript = transcriber.transcribe(audio_path, episode.eid)
        if not accurate_transcript:
            return None  # Keep fast version
        
        # Generate accurate summary
        accurate_summary = summarizer.summarize(accurate_transcript, episode_title=episode.title)
        if not accurate_summary:
            return None  # Keep fast version
        
        return accurate_transcript, accurate_summary
    
    try:
        # Run refinement with timeout using a single-worker executor
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="refinement") as executor:
            future = executor.submit(do_refinement)
            try:
                result = future.result(timeout=BACKGROUND_REFINEMENT_TIMEOUT)
            except FuturesTimeoutError:
                logger.warning(
                    f"Background refinement timed out for episode {episode.eid} "
                    f"after {BACKGROUND_REFINEMENT_TIMEOUT}s. Keeping fast version."
                )
                future.cancel()
                return
        
        if result is None:
            return  # Transcription or summarization failed, keep fast version
        
        accurate_transcript, accurate_summary = result
        
        # Save accurate transcript (better quality)
        transcript_data = TranscriptData(
            episode_id=accurate_transcript.episode_id,
            language=accurate_transcript.language,
            duration=accurate_transcript.duration,
            text=accurate_transcript.text,
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in accurate_transcript.segments],
        )
        db_interface.save_transcript(transcript_data)
        
        # Merge summaries for best of both
        from summarizer import merge_summaries
        final_summary = merge_summaries(fast_summary, accurate_summary)
        
        # Save merged summary
        summary_data = SummaryData(
            episode_id=final_summary.episode_id,
            title=final_summary.title,
            overview=final_summary.overview,
            topics=final_summary.topics,
            takeaways=final_summary.takeaways,
            key_points=[{"topic": kp.topic, "summary": kp.summary, "original_quote": kp.original_quote, "timestamp": kp.timestamp} for kp in final_summary.key_points],
        )
        db_interface.save_summary(summary_data)
        
        elapsed = time.time() - start_time
        logger.info(f"Background refinement completed for {episode.eid} in {elapsed/60:.1f} minutes")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Silently fail - keep fast version


def process_episode_sync(job_id: str, episode_url: str, transcribe_only: bool = False, force: bool = False, 
                         user_id: Optional[str] = None, whisper_model: Optional[str] = None, 
                         llm_model: Optional[str] = None, max_output_tokens: Optional[int] = None):
    """
    Synchronous episode processing with optimized dual-track processing.
    
    Uses compressed audio for fast initial results. When fast track completes,
    job is marked complete immediately. Accurate track runs silently in background
    to refine the summary - completely invisible to the user.
    
    User experience: Fast processing with seamless progress bar.
    
    Args:
        job_id: Unique job identifier
        episode_url: URL of the episode to process
        transcribe_only: If True, only transcribe (don't summarize)
        force: If True, reprocess even if already exists
        user_id: Optional user ID for database isolation
        whisper_model: Optional whisper model to use (e.g., 'whisper-large-v3-turbo')
        llm_model: Optional LLM model to use for summarization
        max_output_tokens: Optional max tokens for LLM output
    """
    import threading
    from xyz_client import get_client
    from database import get_database
    from downloader import get_downloader, compress_audio
    from transcriber import get_transcriber, Transcript, TranscriptSegment as TSeg
    from summarizer import get_summarizer
    
    client = get_client()
    db = get_database()
    downloader = get_downloader()
    transcriber = get_transcriber(model=whisper_model)  # Pass whisper model
    summarizer = get_summarizer(model=llm_model, max_output_tokens=max_output_tokens)  # Pass LLM settings
    
    # Get database interface for saving (supports both local and Supabase)
    db_interface = get_db(user_id)
    
    try:
        # Check for cancellation before starting
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 0, "Cancelled before starting")
            mark_job_cancelled(job_id)
            return
        
        # ===== PHASE 1: Fetch episode info (0-10%) =====
        update_job_status(job_id, "fetching", 5, "Fetching episode info...")
        
        episode = client.get_episode_by_share_url(episode_url)
        if not episode:
            update_job_status(job_id, "failed", 0, "Could not fetch episode")
            return
        
        update_job_status(job_id, "fetching", 10, f"Found: {episode.title}", 
                         episode.eid, episode.title)
        
        # Auto-subscribe to podcast and add episode to database
        # This ensures episodes added via URL have a podcast page to view them
        podcast_id_for_db = None
        
        # Try to get podcast ID from episode, or fetch it separately
        pid = episode.pid
        if not pid:
            # Try to get podcast ID from the episode API
            logger.info(f"Episode missing pid, trying to fetch podcast ID for {episode.eid}")
            pid = client.get_episode_podcast_id(episode.eid)
            if pid:
                episode.pid = pid
        
        if pid:
            podcast = db.get_podcast(pid)
            is_new_subscription = False
            
            if not podcast:
                # Podcast not in DB - subscribe to it
                podcast_info = client.get_podcast(pid)
                if podcast_info:
                    db.add_podcast(
                        podcast_info.pid, podcast_info.title, podcast_info.author,
                        podcast_info.description, podcast_info.cover_url
                    )
                    update_job_status(job_id, "fetching", 12, f"Subscribed to: {podcast_info.title}")
                    podcast = db.get_podcast(pid)
                    is_new_subscription = True
                    logger.info(f"Auto-subscribed to podcast: {podcast_info.title}")
            
            if podcast:
                podcast_id_for_db = podcast.id
                
                # If this is a new subscription, fetch all episodes (same as podcasts page)
                if is_new_subscription:
                    try:
                        all_episodes = client.get_episodes_from_page(pid, limit=50)
                        added_count = 0
                        for ep in all_episodes:
                            if not db.episode_exists(ep.eid):
                                db.add_episode(
                                    eid=ep.eid, pid=ep.pid, podcast_id=podcast.id,
                                    title=ep.title, description=ep.description,
                                    duration=ep.duration, pub_date=ep.pub_date,
                                    audio_url=ep.audio_url,
                                )
                                added_count += 1
                        logger.info(f"Added {added_count} episodes from podcast to database")
                    except Exception as e:
                        logger.warning(f"Failed to fetch all episodes: {e}")
                
                # ALWAYS ensure the current episode is in the database
                # (it might be older than the latest 50 episodes we just fetched)
                if not db.episode_exists(episode.eid):
                    db.add_episode(
                        eid=episode.eid, pid=pid, podcast_id=podcast.id,
                        title=episode.title, description=episode.description,
                        duration=episode.duration, pub_date=episode.pub_date,
                        audio_url=episode.audio_url,
                    )
                    logger.info(f"Added current episode to database: {episode.title}")
        else:
            logger.warning(f"Could not find podcast ID for episode {episode.eid} - episode won't appear in podcast page")
        
        # Check for existing transcript/summary
        existing_transcript = db_interface.get_transcript(episode.eid)
        existing_summary = db_interface.get_summary(episode.eid)
        
        # If user doesn't have a transcript, check for shared transcript from other users
        # Transcripts can be shared since audio content is the same for all users
        shared_transcript_used = False
        if not existing_transcript and not force:
            episode_duration = episode.duration or 0
            min_duration = episode_duration * 0.85 if episode_duration > 0 else 0
            
            shared_transcript = db_interface.copy_shared_transcript(episode.eid, min_duration)
            if shared_transcript:
                existing_transcript = shared_transcript
                shared_transcript_used = True
                logger.info(f"Using shared transcript for {episode.eid} ({shared_transcript.duration/60:.1f} min)")
                update_job_status(job_id, "fetching", 12, "Found shared transcript, reusing...")
        
        # Quick check: if both exist and transcript is not truncated, skip processing
        if existing_transcript and existing_summary and not force:
            transcript_duration = existing_transcript.duration or 0
            episode_duration = episode.duration or 0
            
            # Check if transcript is complete (>= 85% of episode duration)
            if episode_duration > 0 and transcript_duration > 0:
                coverage = transcript_duration / episode_duration
                if coverage >= 0.85:
                    update_job_status(job_id, "completed", 100, "Already processed")
                    return
                else:
                    logger.warning(f"Existing transcript is truncated ({coverage*100:.1f}%), will reprocess")
            elif transcript_duration > 0:
                # No episode duration to compare, assume valid
                update_job_status(job_id, "completed", 100, "Already processed")
                return
        
        # Check for cancellation before downloading
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 15, "Cancelled")
            mark_job_cancelled(job_id)
            return
        
        # ===== PHASE 2: Download audio (10-25%) =====
        update_job_status(job_id, "downloading", 15, "Downloading audio...")
        audio_path = downloader.download(episode)
        
        if not audio_path:
            update_job_status(job_id, "failed", 0, "Download failed")
            return
        
        update_job_status(job_id, "downloading", 25, "Download complete")
        
        # Check for cancellation before processing
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 25, "Cancelled")
            mark_job_cancelled(job_id)
            return
        
        # ===== PHASE 3: Prepare optimized audio (25-30%) =====
        # Skip compression for API mode (cloud) - Groq API is fast, compression is slow on cloud
        from config import WHISPER_MODE
        
        if WHISPER_MODE == "api":
            # Cloud mode: skip compression, use original audio directly
            update_job_status(job_id, "transcribing", 30, "Using original audio (API mode)...")
            process_path = audio_path
            use_fast_track = False  # No background refinement in API mode
        else:
            # Local mode: compress audio for faster transcription
            update_job_status(job_id, "transcribing", 28, "Preparing audio...")
            compressed_path = compress_audio(audio_path)
            
            # If compression failed, the original audio might be truncated
            # Try to re-download and compress again
            if compressed_path is None:
                update_job_status(job_id, "downloading", 20, "Re-downloading audio (compression failed)...")
                
                # Force re-download (deletes existing and downloads fresh)
                audio_path = downloader.download(episode, force=True)
                if not audio_path:
                    update_job_status(job_id, "failed", 0, "Re-download failed")
                    return
                
                # Try compression again
                update_job_status(job_id, "transcribing", 28, "Compressing audio (retry)...")
                compressed_path = compress_audio(audio_path)
            
            # Determine processing mode
            use_fast_track = compressed_path is not None and compressed_path != audio_path
            process_path = compressed_path if use_fast_track else audio_path
        
        # If we have existing transcript, check if it's complete (not truncated)
        # A transcript is considered truncated if duration < 85% of episode duration
        transcript_is_valid = False
        if existing_transcript and not force:
            transcript_duration = existing_transcript.duration or 0
            episode_duration = episode.duration or 0
            
            if episode_duration > 0 and transcript_duration > 0:
                coverage = transcript_duration / episode_duration
                if coverage >= 0.85:
                    transcript_is_valid = True
                    logger.info(f"Existing transcript is valid ({coverage*100:.1f}% coverage)")
                else:
                    logger.warning(f"Existing transcript is truncated ({coverage*100:.1f}% coverage < 85%), will re-transcribe")
            elif transcript_duration > 0:
                # No episode duration to compare, assume valid if transcript has content
                transcript_is_valid = True
                logger.info(f"Existing transcript found ({transcript_duration/60:.1f} min), episode duration unknown - assuming valid")
        
        # If we have a valid existing transcript, just summarize
        if transcript_is_valid and existing_transcript:
            status_msg = "Using shared transcript..." if shared_transcript_used else "Using existing transcript..."
            update_job_status(job_id, "summarizing", 70, status_msg)
            transcript = Transcript(
                episode_id=existing_transcript.episode_id,
                language=existing_transcript.language,
                duration=existing_transcript.duration,
                text=existing_transcript.text,
                segments=[TSeg(start=s.get("start", 0), end=s.get("end", 0), text=s.get("text", "")) 
                         for s in existing_transcript.segments],
            )
            summary = summarizer.summarize(transcript, episode_title=episode.title)
            
            if summary:
                summary_data = SummaryData(
                    episode_id=summary.episode_id, title=summary.title,
                    overview=summary.overview, topics=summary.topics,
                    takeaways=summary.takeaways,
                    key_points=[{"topic": kp.topic, "summary": kp.summary, "original_quote": kp.original_quote, "timestamp": kp.timestamp} for kp in summary.key_points],
                )
                db_interface.save_summary(summary_data)
                update_job_status(job_id, "completed", 100, "Processing complete!")
                
                # Send Discord notification
                notify_discord(
                    title="Summary Generated",
                    message=f"**{episode.title}**\n\nSummary has been generated from existing transcript.",
                    event_type="summary",
                )
            else:
                update_job_status(job_id, "failed", 0, "Summary generation failed")
            return
        
        # ===== PHASE 4: Transcribe (30-70%) =====
        update_job_status(job_id, "transcribing", 30, "Starting transcription...")
        
        # Custom exception for cancellation
        class CancelledException(Exception):
            pass
        
        last_progress = [30]
        def progress_callback(progress: float):
            # Check for cancellation on every progress update - immediate cancel
            if is_job_cancelled(job_id):
                raise CancelledException("Job cancelled")
            
            # Map 0-1 progress to 30-70% of job (40% range for transcription)
            job_progress = 30 + (progress * 40)
            # Update on every 0.5% change for smooth progress bar
            if job_progress >= last_progress[0] + 0.5:
                last_progress[0] = job_progress
                pct = int(progress * 100)
                # Show clear progress message with percentage
                update_job_status(job_id, "transcribing", job_progress, f"Transcribing audio... {pct}%")
        
        # Transcribe (using fast audio if available)
        try:
            transcript = transcriber.transcribe(process_path, episode.eid, progress_callback=progress_callback)
        except CancelledException:
            update_job_status(job_id, "cancelled", last_progress[0], "Cancelled")
            mark_job_cancelled(job_id)
            return
        
        if not transcript:
            # Check if it was cancelled during transcription
            if is_job_cancelled(job_id):
                update_job_status(job_id, "cancelled", last_progress[0], "Cancelled")
                mark_job_cancelled(job_id)
                return
            update_job_status(job_id, "failed", 0, "Transcription failed")
            return
        
        update_job_status(job_id, "transcribing", 70, "Transcription complete")
        
        # Save transcript immediately after transcription (before summarization)
        # This ensures we don't lose work if summarization fails
        transcript_data = TranscriptData(
            episode_id=transcript.episode_id, language=transcript.language,
            duration=transcript.duration, text=transcript.text,
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in transcript.segments],
        )
        db_interface.save_transcript(transcript_data)
        logger.info(f"Transcript saved for {episode.eid} ({len(transcript.segments)} segments)")
        
        if transcribe_only:
            # Transcript already saved above, just finish
            update_job_status(job_id, "completed", 100, "Transcription complete!")
            
            # Send Discord notification
            duration_str = f"{int(transcript.duration // 60)} min" if transcript.duration else "Unknown"
            notify_discord(
                title="Transcript Ready",
                message=f"**{episode.title}**\n\nTranscript has been generated.",
                event_type="transcript",
                fields=[
                    {"name": "Duration", "value": duration_str, "inline": True},
                    {"name": "Language", "value": transcript.language or "Auto", "inline": True},
                ]
            )
            return
        
        # Check for cancellation before summarizing
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 70, "Cancelled")
            mark_job_cancelled(job_id)
            return
        
        # ===== PHASE 5: Summarize (70-95%) =====
        update_job_status(job_id, "summarizing", 75, "Generating summary...")
        
        summary = summarizer.summarize(transcript, episode_title=episode.title)
        
        if not summary:
            update_job_status(job_id, "failed", 0, "Summary generation failed")
            return
        
        update_job_status(job_id, "summarizing", 95, "Saving summary...")
        
        # Transcript already saved after transcription
        # Save summary
        summary_data = SummaryData(
            episode_id=summary.episode_id, title=summary.title,
            overview=summary.overview, topics=summary.topics,
            takeaways=summary.takeaways,
            key_points=[{"topic": kp.topic, "summary": kp.summary, "original_quote": kp.original_quote, "timestamp": kp.timestamp} for kp in summary.key_points],
        )
        db_interface.save_summary(summary_data)
        
        # ===== PHASE 6: Complete! (100%) =====
        update_job_status(job_id, "completed", 100, "Processing complete!")
        
        # Send Discord notification
        duration_str = f"{int(transcript.duration // 60)} min" if transcript.duration else "Unknown"
        notify_discord(
            title="Processing Complete",
            message=f"**{episode.title}**\n\nTranscript and summary are ready!",
            event_type="success",
            fields=[
                {"name": "Duration", "value": duration_str, "inline": True},
                {"name": "Language", "value": transcript.language or "Auto", "inline": True},
            ]
        )
        
        # ===== BACKGROUND: Silently refine with original audio =====
        # Only if we used compressed audio - run accurate track in background
        if use_fast_track and not transcribe_only:
            # Start background refinement (invisible to user)
            refinement_thread = threading.Thread(
                target=_background_refinement,
                args=(audio_path, episode, summary, db_interface, transcriber, summarizer, user_id),
                daemon=True  # Won't block shutdown
            )
            refinement_thread.start()
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 0, "Cancelled")
            mark_job_cancelled(job_id)
        else:
            update_job_status(job_id, "failed", 0, f"Error: {str(e)}")


async def process_episode_async(job_id: str, episode_url: str, transcribe_only: bool = False, force: bool = False, 
                                user_id: Optional[str] = None, whisper_model: Optional[str] = None, 
                                llm_model: Optional[str] = None, max_output_tokens: Optional[int] = None):
    """Async wrapper for episode processing.
    
    Uses PROCESSING_EXECUTOR with limited workers to prevent resource exhaustion.
    When all workers are busy, jobs queue automatically and wait for a slot.
    """
    loop = asyncio.get_event_loop()
    
    # Run in limited thread pool (max 3 concurrent heavy processing jobs)
    await loop.run_in_executor(
        PROCESSING_EXECUTOR,
        lambda: process_episode_sync(job_id, episode_url, transcribe_only, force, user_id, whisper_model, llm_model, max_output_tokens)
    )
    
    # Broadcast final status
    await broadcast_status(job_id)


@router.post("/process")
async def process_episode(
    data: ProcessRequest, 
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user)
):
    """Start processing an episode."""
    if not data.episode_url:
        raise HTTPException(status_code=400, detail="episode_url is required")
    
    user_id = user.id if user else None
    
    # Try to fetch episode info for immediate display
    episode_id = None
    episode_title = None
    try:
        from xyz_client import get_client
        client = get_client()
        episode = client.get_episode_by_share_url(data.episode_url)
        if episode:
            episode_id = episode.eid
            episode_title = episode.title
    except Exception:
        pass  # Will be fetched again in background task
    
    # Create job with episode info if available
    job_id = str(uuid.uuid4())[:8]
    with _jobs_lock:
        jobs[job_id] = ProcessingStatus(
            job_id=job_id,
            user_id=user_id,  # Track job ownership for user isolation
            status="pending",
            progress=0,
            message="Starting...",
            episode_id=episode_id,
            episode_title=episode_title,
        )
    
    # Persist new job and cleanup old ones (these functions acquire their own locks)
    _cleanup_old_jobs()
    _save_jobs_to_file()
    
    # Broadcast new job to WebSocket clients immediately
    await broadcast_status(job_id)
    
    # Start background processing with user_id for Supabase support
    # Pass model settings from request
    background_tasks.add_task(
        process_episode_async,
        job_id,
        data.episode_url,
        data.transcribe_only,
        data.force,
        user_id,
        data.whisper_model,  # Pass whisper model from request
        data.llm_model,  # Pass LLM model from request
        data.max_output_tokens,  # Pass max output tokens from request
    )
    
    return {
        "job_id": job_id, 
        "message": "Processing started",
        "episode_id": episode_id,
        "episode_title": episode_title,
    }


@router.get("/jobs")
async def list_jobs(user: Optional[User] = Depends(get_current_user)):
    """List processing jobs for the current user (cached to reduce lock contention from polling)."""
    user_id = user.id if user else None
    now = time.time()
    
    # Use user-specific cache key
    cache_key = user_id or "_anonymous"
    
    # Check if we have user-specific cache
    if cache_key in _jobs_cache and _jobs_cache[cache_key].get("data") is not None:
        if (now - _jobs_cache[cache_key].get("time", 0)) < _JOBS_CACHE_TTL:
            return _jobs_cache[cache_key]["data"]
    
    # Build fresh response filtered by user_id
    with _jobs_lock:
        if user_id:
            # Return only jobs belonging to this user
            user_jobs = [job.model_dump() for job in jobs.values() if job.user_id == user_id]
        else:
            # Anonymous users only see jobs with no user_id (local mode)
            user_jobs = [job.model_dump() for job in jobs.values() if job.user_id is None]
        response = {"jobs": user_jobs}
    
    # Update user-specific cache
    if cache_key not in _jobs_cache:
        _jobs_cache[cache_key] = {}
    _jobs_cache[cache_key]["data"] = response
    _jobs_cache[cache_key]["time"] = now
    
    return response


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: Optional[User] = Depends(get_current_user)):
    """Get job status (only if user owns the job)."""
    user_id = user.id if user else None
    with _jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs[job_id]
        # Verify user ownership
        if job.user_id != user_id:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.model_dump()


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, user: Optional[User] = Depends(get_current_user)):
    """Delete a job from history (only if user owns the job)."""
    user_id = user.id if user else None
    with _jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Verify user ownership
        if jobs[job_id].user_id != user_id:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Also cancel if still running
        cancelled_jobs.add(job_id)
        del jobs[job_id]
        _save_jobs_to_file_unlocked()
    return {"message": "Job deleted"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user: Optional[User] = Depends(get_current_user)):
    """Cancel a processing job (only if user owns the job)."""
    user_id = user.id if user else None
    with _jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job = jobs[job_id]
        
        # Verify user ownership
        if job.user_id != user_id:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Check if job is still running
        if job.status in ("completed", "failed", "cancelled"):
            return {"message": "Job already finished", "status": job.status}
        
        # Request cancellation
        cancelled_jobs.add(job_id)
        
        # Give status-specific cancellation message
        cancel_msg = "Cancellation requested..."
        if job.status == "transcribing":
            cancel_msg = "Will cancel after current transcription step..."
        elif job.status == "summarizing":
            cancel_msg = "Will cancel after current LLM call..."
        elif job.status == "downloading":
            cancel_msg = "Will cancel after download completes..."
        
        job_progress = job.progress
    
    # Update status (outside lock since it acquires its own lock)
    update_job_status(job_id, "cancelling", job_progress, cancel_msg)
    
    # Broadcast update
    await broadcast_status(job_id)
    
    return {"message": "Cancellation requested", "job_id": job_id}


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user)
):
    """Retry a failed or cancelled job (only if user owns the job)."""
    user_id = user.id if user else None
    
    with _jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        old_job = jobs[job_id]
        
        # Verify user ownership
        if old_job.user_id != user_id:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Can only retry failed or cancelled jobs
        if old_job.status not in ("failed", "cancelled"):
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot retry job with status: {old_job.status}"
            )
        
        episode_id = old_job.episode_id
        if not episode_id:
            raise HTTPException(status_code=400, detail="Job has no episode_id to retry")
    
    # Construct episode URL
    episode_url = f"https://www.xiaoyuzhoufm.com/episode/{episode_id}"
    
    # Delete old cached compressed audio to force re-compression
    try:
        from downloader import get_downloader
        from xyz_client import get_client
        
        client = get_client()
        episode = client.get_episode_by_share_url(episode_url)
        if episode:
            downloader = get_downloader()
            compressed_path = downloader.get_compressed_path(episode)
            if compressed_path.exists():
                compressed_path.unlink()
    except Exception:
        pass  # Best effort - proceed with retry anyway
    
    # Create new job
    new_job_id = str(uuid.uuid4())[:8]
    with _jobs_lock:
        jobs[new_job_id] = ProcessingStatus(
            job_id=new_job_id,
            status="pending",
            progress=0,
            message="Retrying...",
            episode_id=episode_id,
            episode_title=old_job.episode_title,
        )
        
        # Remove old job
        del jobs[job_id]
    
    _save_jobs_to_file()
    
    # Broadcast new job
    await broadcast_status(new_job_id)
    
    # Start processing with force=true to bypass any caches
    background_tasks.add_task(
        process_episode_async,
        new_job_id,
        episode_url,
        False,  # transcribe_only
        True,   # force - bypass caches
        user_id,
    )
    
    return {
        "message": "Retry started",
        "old_job_id": job_id,
        "new_job_id": new_job_id,
        "episode_id": episode_id,
    }


@router.post("/episodes/{episode_id}/resummarize")
async def resummarize_episode(
    episode_id: str,
    background_tasks: BackgroundTasks,
    data: ResummarizeRequest = None,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Re-process an episode to regenerate its summary.
    
    - Uses existing audio if valid (>= 85% of episode duration), otherwise re-downloads
    - Uses existing transcript if valid (>= 85% coverage), otherwise re-transcribes
    - Always regenerates the summary
    
    Use this when you want to improve the summary without re-transcribing.
    """
    from api.db import get_db
    
    user_id = user.id if user else None
    db = get_db(user_id)
    
    # Check if episode exists
    existing_transcript = db.get_transcript(episode_id)
    if not existing_transcript:
        raise HTTPException(
            status_code=404, 
            detail="Episode transcript not found. Use normal processing instead."
        )
    
    # Delete existing summary to force regeneration
    db.delete_summary(episode_id)
    
    # Construct episode URL
    episode_url = f"https://www.xiaoyuzhoufm.com/episode/{episode_id}"
    
    # Get LLM settings from request if provided
    llm_model = data.llm_model if data else None
    max_output_tokens = data.max_output_tokens if data else None
    
    # Create new job
    job_id = str(uuid.uuid4())[:8]
    with _jobs_lock:
        jobs[job_id] = ProcessingStatus(
            job_id=job_id,
            status="pending",
            progress=0,
            message="Re-summarizing...",
            episode_id=episode_id,
            episode_title=None,  # Will be filled during processing
        )
    
    _save_jobs_to_file()
    
    # Broadcast new job
    try:
        loop = get_main_loop()
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast_status(job_id), loop)
    except Exception:
        pass
    
    # Start processing in background (will use existing transcript if valid)
    background_tasks.add_task(
        process_episode_async, job_id, episode_url, 
        transcribe_only=False, force=False, user_id=user_id,
        whisper_model=None, llm_model=llm_model, max_output_tokens=max_output_tokens
    )
    
    return {
        "message": "Re-summarization started",
        "job_id": job_id,
        "episode_id": episode_id,
    }


@router.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket, token: Optional[str] = None):
    """WebSocket endpoint for real-time progress updates with periodic heartbeat and user isolation."""
    # Extract user_id from token query parameter for user isolation
    user_id = None
    if token:
        try:
            from api.auth import verify_jwt_token
            payload = verify_jwt_token(token)
            if payload:
                user_id = payload.get("sub")
        except Exception:
            pass  # Anonymous connection if token invalid
    
    await manager.connect(websocket, user_id)
    
    # Flag to track if connection is still active
    connection_active = True
    
    async def heartbeat_loop():
        """Send periodic heartbeats to keep connection alive through proxies/load balancers."""
        while connection_active:
            try:
                await asyncio.sleep(WEBSOCKET_HEARTBEAT_INTERVAL)
                if connection_active:
                    await websocket.send_json({"type": "heartbeat"})
            except Exception:
                break
    
    # Start heartbeat task
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    
    try:
        # Send current job statuses (filtered by user_id)
        with _jobs_lock:
            if user_id:
                jobs_data = [job.model_dump() for job in jobs.values() if job.user_id == user_id]
            else:
                jobs_data = [job.model_dump() for job in jobs.values() if job.user_id is None]
        await websocket.send_json({
            "type": "init",
            "jobs": jobs_data,
        })
        
        # Keep connection alive and listen for messages
        while True:
            try:
                # Use longer timeout since heartbeat is handled separately
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
                
                # Handle ping
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
                # Handle job status request (verify user ownership)
                elif data.get("type") == "get_status":
                    job_id = data.get("job_id")
                    with _jobs_lock:
                        if job_id and job_id in jobs:
                            job = jobs[job_id]
                            # Only return if user owns the job
                            if job.user_id == user_id:
                                job_data = job.model_dump()
                            else:
                                job_data = None
                        else:
                            job_data = None
                    if job_data:
                        await websocket.send_json({
                            "type": "job_update",
                            "job": job_data,
                        })
            
            except asyncio.TimeoutError:
                # No message received, but heartbeat task handles keep-alive
                pass
    
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Clean up
        connection_active = False
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(websocket)


@router.post("/batch")
async def batch_process(
    data: BatchProcessRequest, 
    background_tasks: BackgroundTasks,
    user: Optional[User] = Depends(get_current_user)
):
    """Start batch processing for a podcast (user-scoped)."""
    from xyz_client import get_client
    
    user_id = user.id if user else None
    client = get_client()
    
    # Get podcast and episodes
    if data.podcast_url.startswith("http"):
        podcast = client.get_podcast_by_url(data.podcast_url)
        pid = client._extract_id_from_url(data.podcast_url, "podcast")
    else:
        pid = data.podcast_url
        podcast = client.get_podcast(pid)
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Could not fetch podcast")
    
    episodes = client.get_episodes_from_page(pid, limit=data.limit or 100)
    
    if not episodes:
        raise HTTPException(status_code=404, detail="No episodes found")
    
    # Create jobs for each episode (with user_id for isolation)
    job_ids = []
    with _jobs_lock:
        for ep in episodes:
            job_id = str(uuid.uuid4())[:8]
            jobs[job_id] = ProcessingStatus(
                job_id=job_id,
                user_id=user_id,  # Track job ownership
                status="pending",
                progress=0,
                message="Queued",
                episode_id=ep.eid,
                episode_title=ep.title,
            )
            job_ids.append(job_id)
    
    # Queue background tasks (outside lock to avoid holding it during task scheduling)
    for job_id, ep in zip(job_ids, episodes):
        episode_url = f"https://www.xiaoyuzhoufm.com/episode/{ep.eid}"
        background_tasks.add_task(
            process_episode_async,
            job_id,
            episode_url,
            data.transcribe_only,
            not data.skip_existing,
            user_id,  # Pass user_id for data isolation
        )
    
    # Persist all new jobs (these functions acquire their own locks)
    _cleanup_old_jobs()
    _save_jobs_to_file()
    
    return {
        "message": f"Batch processing started for {len(episodes)} episodes",
        "podcast_title": podcast.title,
        "episode_count": len(episodes),
        "job_ids": job_ids,
    }


@router.get("/truncated")
async def get_truncated_transcripts(
    threshold: float = 0.85,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Find transcripts that appear to be truncated.
    
    A transcript is considered truncated if its duration is less than
    the threshold (default 85%) of the episode's expected duration.
    
    Args:
        threshold: Minimum acceptable ratio of transcript/episode duration (0.0-1.0)
    
    Returns:
        List of truncated transcripts with episode info
    """
    from api.db import get_db
    
    db = get_db(user.id if user else None)
    truncated = db.get_truncated_transcripts(threshold)
    
    return {
        "count": len(truncated),
        "threshold_percent": round(threshold * 100, 1),
        "truncated": truncated,
    }


@router.get("/transcripts/debug")
async def debug_transcript_durations(
    user: Optional[User] = Depends(get_current_user)
):
    """
    Debug endpoint to see all transcript durations vs episode durations.
    Helps identify why truncation detection might not be working.
    """
    from api.db import get_db
    
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    db = get_db(user.id)
    
    # Get all transcripts
    all_transcripts = []
    summary_ids = db.get_summary_episode_ids()
    
    # Get all podcasts and their episodes
    podcasts = db.get_all_podcasts()
    for podcast in podcasts:
        episodes = db.get_episodes_by_podcast(podcast.pid)
        for ep in episodes:
            transcript = db.get_transcript(ep.eid)
            if transcript:
                # Calculate max segment time
                max_segment_time = 0
                if transcript.segments:
                    max_segment_time = max((s.get("end", 0) for s in transcript.segments), default=0)
                
                # Determine actual transcript duration (use max segment time if duration is 0)
                actual_duration = transcript.duration if transcript.duration > 0 else max_segment_time
                
                # Calculate percentage
                percentage = (actual_duration / ep.duration * 100) if ep.duration > 0 else 0
                
                all_transcripts.append({
                    "episode_id": ep.eid,
                    "episode_title": ep.title[:50] + "..." if len(ep.title) > 50 else ep.title,
                    "episode_duration_sec": ep.duration,
                    "episode_duration_min": round(ep.duration / 60, 1) if ep.duration else 0,
                    "transcript_duration_sec": round(transcript.duration, 1),
                    "transcript_duration_min": round(transcript.duration / 60, 1) if transcript.duration else 0,
                    "max_segment_time_sec": round(max_segment_time, 1),
                    "max_segment_time_min": round(max_segment_time / 60, 1),
                    "percentage": round(percentage, 1),
                    "has_summary": ep.eid in summary_ids,
                    "likely_truncated": percentage < 85 and percentage > 0,
                    "missing_episode_duration": ep.duration <= 0,
                })
    
    # Sort by percentage (lowest first)
    all_transcripts.sort(key=lambda x: x["percentage"])
    
    # Count issues
    truncated_count = sum(1 for t in all_transcripts if t["likely_truncated"])
    missing_duration_count = sum(1 for t in all_transcripts if t["missing_episode_duration"])
    
    return {
        "total_transcripts": len(all_transcripts),
        "truncated_count": truncated_count,
        "missing_episode_duration_count": missing_duration_count,
        "transcripts": all_transcripts,
    }


@router.delete("/truncated/{episode_id}")
async def delete_truncated_data(
    episode_id: str,
    delete_summary: bool = True,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Delete truncated transcript (and optionally summary) for an episode.
    
    This allows the episode to be reprocessed from scratch.
    
    Args:
        episode_id: The episode ID to clean up
        delete_summary: Also delete the summary (default: True, since summary is based on truncated transcript)
    """
    from api.db import get_db
    
    db = get_db(user.id if user else None)
    
    deleted_transcript = db.delete_transcript(episode_id)
    deleted_summary = False
    
    if delete_summary:
        deleted_summary = db.delete_summary(episode_id)
    
    return {
        "episode_id": episode_id,
        "deleted_transcript": deleted_transcript,
        "deleted_summary": deleted_summary,
    }


@router.post("/truncated/cleanup")
async def cleanup_truncated_data(
    threshold: float = 0.85,
    delete_summaries: bool = True,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Find and delete all truncated transcripts (and optionally summaries).
    
    This cleans up all incomplete data so episodes can be reprocessed.
    
    Args:
        threshold: Minimum acceptable ratio of transcript/episode duration (0.0-1.0)
        delete_summaries: Also delete summaries for truncated episodes (default: True)
    
    Returns:
        Summary of deleted items
    """
    from api.db import get_db
    
    db = get_db(user.id if user else None)
    truncated = db.get_truncated_transcripts(threshold)
    
    deleted = []
    for item in truncated:
        episode_id = item["episode_id"]
        deleted_transcript = db.delete_transcript(episode_id)
        deleted_summary = False
        
        if delete_summaries:
            deleted_summary = db.delete_summary(episode_id)
        
        deleted.append({
            "episode_id": episode_id,
            "episode_title": item["episode_title"],
            "percentage": item["percentage"],
            "deleted_transcript": deleted_transcript,
            "deleted_summary": deleted_summary,
        })
    
    return {
        "message": f"Cleaned up {len(deleted)} truncated transcripts",
        "threshold_percent": round(threshold * 100, 1),
        "deleted": deleted,
    }
