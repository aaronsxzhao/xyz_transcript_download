"""Processing endpoints with WebSocket support."""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Set, Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Depends

from api.schemas import ProcessRequest, BatchProcessRequest, ProcessingStatus
from api.auth import get_current_user, User
from api.db import get_db, TranscriptData, SummaryData

router = APIRouter()

# In-memory job tracking
jobs: Dict[str, ProcessingStatus] = {}

# Track cancelled jobs
cancelled_jobs: Set[str] = set()

# Limit concurrent episode processing to prevent resource exhaustion
# When limit reached, jobs queue automatically and wait for a slot
PROCESSING_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="episode_processor")

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
    return job_id in cancelled_jobs


def mark_job_cancelled(job_id: str):
    """Mark a job as cancelled and clean up."""
    if job_id in cancelled_jobs:
        cancelled_jobs.discard(job_id)


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


def update_job_status(job_id: str, status: str, progress: float = 0, message: str = "",
                      episode_id: str = None, episode_title: str = None):
    """Update job status and notify clients."""
    if job_id in jobs:
        jobs[job_id].status = status
        jobs[job_id].progress = progress
        jobs[job_id].message = message
        if episode_id:
            jobs[job_id].episode_id = episode_id
        if episode_title:
            jobs[job_id].episode_title = episode_title
        
        # Broadcast update to all connected WebSocket clients
        # Use the cached main event loop for thread-safe broadcasting
        try:
            loop = get_main_loop()
            if loop and loop.is_running():
                # Schedule broadcast from sync context
                asyncio.run_coroutine_threadsafe(broadcast_status(job_id), loop)
        except Exception as e:
            # Log but don't fail - status is still updated in memory
            import traceback
            traceback.print_exc()


async def broadcast_status(job_id: str):
    """Broadcast job status to all connected clients."""
    if job_id in jobs:
        await manager.broadcast({
            "type": "job_update",
            "job": jobs[job_id].model_dump(),
        })


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
    """
    try:
        from summarizer import merge_summaries
        
        # Transcribe original audio
        accurate_transcript = transcriber.transcribe(audio_path, episode.eid)
        if not accurate_transcript:
            return  # Keep fast version
        
        # Generate accurate summary
        accurate_summary = summarizer.summarize(accurate_transcript, episode_title=episode.title)
        if not accurate_summary:
            return  # Keep fast version
        
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
        final_summary = merge_summaries(fast_summary, accurate_summary)
        
        # Save merged summary
        summary_data = SummaryData(
            episode_id=final_summary.episode_id,
            title=final_summary.title,
            overview=final_summary.overview,
            topics=final_summary.topics,
            takeaways=final_summary.takeaways,
            key_points=[{"topic": kp.topic, "points": kp.points} for kp in final_summary.key_points],
        )
        db_interface.save_summary(summary_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Silently fail - keep fast version


def process_episode_sync(job_id: str, episode_url: str, transcribe_only: bool = False, force: bool = False, user_id: Optional[str] = None):
    """
    Synchronous episode processing with optimized dual-track processing.
    
    Uses compressed audio for fast initial results. When fast track completes,
    job is marked complete immediately. Accurate track runs silently in background
    to refine the summary - completely invisible to the user.
    
    User experience: Fast processing with seamless progress bar.
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
    transcriber = get_transcriber()
    summarizer = get_summarizer()
    
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
        
        # Auto-subscribe to podcast if episode has a podcast ID
        if episode.pid:
            podcast = db.get_podcast(episode.pid)
            if not podcast:
                podcast_info = client.get_podcast(episode.pid)
                if podcast_info:
                    db.add_podcast(podcast_info.pid, podcast_info.title, podcast_info.author, podcast_info.description, podcast_info.cover_url)
                    update_job_status(job_id, "fetching", 12, f"Subscribed to: {podcast_info.title}")
                    podcast = db.get_podcast(episode.pid)
            
            if podcast:
                db.add_episode(
                    eid=episode.eid, pid=episode.pid, podcast_id=podcast.id,
                    title=episode.title, description=episode.description,
                    duration=episode.duration, pub_date=episode.pub_date,
                    audio_url=episode.audio_url,
                )
        
        # Check for existing transcript/summary
        existing_transcript = db_interface.get_transcript(episode.eid)
        existing_summary = db_interface.get_summary(episode.eid)
        
        if existing_transcript and existing_summary and not force:
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
        update_job_status(job_id, "transcribing", 28, "Preparing audio...")
        compressed_path = compress_audio(audio_path)
        
        # Determine processing mode
        use_fast_track = compressed_path is not None and compressed_path != audio_path
        process_path = compressed_path if use_fast_track else audio_path
        
        # If we have existing transcript, just summarize
        if existing_transcript and not force:
            update_job_status(job_id, "summarizing", 70, "Generating summary...")
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
                    key_points=[{"topic": kp.topic, "points": kp.points} for kp in summary.key_points],
                )
                db_interface.save_summary(summary_data)
                update_job_status(job_id, "completed", 100, "Processing complete!")
            else:
                update_job_status(job_id, "failed", 0, "Summary generation failed")
            return
        
        # ===== PHASE 4: Transcribe (30-70%) =====
        update_job_status(job_id, "transcribing", 30, "Transcribing audio...")
        
        last_progress = [30]
        def progress_callback(progress: float):
            # Map 0-1 progress to 30-70% of job
            job_progress = 30 + (progress * 40)
            if job_progress >= last_progress[0] + 1:
                last_progress[0] = job_progress
                pct = int(progress * 100)
                update_job_status(job_id, "transcribing", job_progress, f"Transcribing... {pct}%")
        
        # Transcribe (using fast audio if available)
        transcript = transcriber.transcribe(process_path, episode.eid, progress_callback=progress_callback)
        
        if not transcript:
            update_job_status(job_id, "failed", 0, "Transcription failed")
            return
        
        update_job_status(job_id, "transcribing", 70, "Transcription complete")
        
        if transcribe_only:
            # Save and finish
            transcript_data = TranscriptData(
                episode_id=transcript.episode_id, language=transcript.language,
                duration=transcript.duration, text=transcript.text,
                segments=[{"start": s.start, "end": s.end, "text": s.text} for s in transcript.segments],
            )
            db_interface.save_transcript(transcript_data)
            update_job_status(job_id, "completed", 100, "Transcription complete!")
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
        
        update_job_status(job_id, "summarizing", 95, "Saving results...")
        
        # Save transcript
        transcript_data = TranscriptData(
            episode_id=transcript.episode_id, language=transcript.language,
            duration=transcript.duration, text=transcript.text,
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in transcript.segments],
        )
        db_interface.save_transcript(transcript_data)
        
        # Save summary
        summary_data = SummaryData(
            episode_id=summary.episode_id, title=summary.title,
            overview=summary.overview, topics=summary.topics,
            takeaways=summary.takeaways,
            key_points=[{"topic": kp.topic, "points": kp.points} for kp in summary.key_points],
        )
        db_interface.save_summary(summary_data)
        
        # ===== PHASE 6: Complete! (100%) =====
        update_job_status(job_id, "completed", 100, "Processing complete!")
        
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


async def process_episode_async(job_id: str, episode_url: str, transcribe_only: bool = False, force: bool = False, user_id: Optional[str] = None):
    """Async wrapper for episode processing.
    
    Uses PROCESSING_EXECUTOR with limited workers to prevent resource exhaustion.
    When all workers are busy, jobs queue automatically and wait for a slot.
    """
    loop = asyncio.get_event_loop()
    
    # Run in limited thread pool (max 3 concurrent heavy processing jobs)
    await loop.run_in_executor(
        PROCESSING_EXECUTOR,
        lambda: process_episode_sync(job_id, episode_url, transcribe_only, force, user_id)
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
    jobs[job_id] = ProcessingStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Starting...",
        episode_id=episode_id,
        episode_title=episode_title,
    )
    
    # Broadcast new job to WebSocket clients immediately
    await broadcast_status(job_id)
    
    # Start background processing with user_id for Supabase support
    background_tasks.add_task(
        process_episode_async,
        job_id,
        data.episode_url,
        data.transcribe_only,
        data.force,
        user_id,
    )
    
    return {
        "job_id": job_id, 
        "message": "Processing started",
        "episode_id": episode_id,
        "episode_title": episode_title,
    }


@router.get("/jobs")
async def list_jobs():
    """List all processing jobs."""
    return {"jobs": [job.model_dump() for job in jobs.values()]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job status."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id]


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job from history."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Also cancel if still running
    cancelled_jobs.add(job_id)
    del jobs[job_id]
    return {"message": "Job deleted"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a processing job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
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
    
    # Update status immediately
    update_job_status(job_id, "cancelling", job.progress, cancel_msg)
    
    # Broadcast update
    await broadcast_status(job_id)
    
    return {"message": "Cancellation requested", "job_id": job_id}


@router.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket endpoint for real-time progress updates."""
    await manager.connect(websocket)
    
    try:
        # Send current job statuses
        await websocket.send_json({
            "type": "init",
            "jobs": [job.model_dump() for job in jobs.values()],
        })
        
        # Keep connection alive and listen for messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                
                # Handle ping
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
                # Handle job status request
                elif data.get("type") == "get_status":
                    job_id = data.get("job_id")
                    if job_id and job_id in jobs:
                        await websocket.send_json({
                            "type": "job_update",
                            "job": jobs[job_id].model_dump(),
                        })
            
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@router.post("/batch")
async def batch_process(data: BatchProcessRequest, background_tasks: BackgroundTasks):
    """Start batch processing for a podcast."""
    from xyz_client import get_client
    
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
    
    # Create jobs for each episode
    job_ids = []
    for ep in episodes:
        job_id = str(uuid.uuid4())[:8]
        jobs[job_id] = ProcessingStatus(
            job_id=job_id,
            status="pending",
            progress=0,
            message="Queued",
            episode_id=ep.eid,
            episode_title=ep.title,
        )
        job_ids.append(job_id)
        
        # Queue background task
        episode_url = f"https://www.xiaoyuzhoufm.com/episode/{ep.eid}"
        background_tasks.add_task(
            process_episode_async,
            job_id,
            episode_url,
            data.transcribe_only,
            not data.skip_existing,
        )
    
    return {
        "message": f"Batch processing started for {len(episodes)} episodes",
        "podcast_title": podcast.title,
        "episode_count": len(episodes),
        "job_ids": job_ids,
    }
