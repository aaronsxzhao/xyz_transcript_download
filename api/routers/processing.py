"""Processing endpoints with WebSocket support."""
import asyncio
import uuid
from typing import Dict, Set, Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks

from api.schemas import ProcessRequest, BatchProcessRequest, ProcessingStatus

router = APIRouter()

# In-memory job tracking
jobs: Dict[str, ProcessingStatus] = {}

# Track cancelled jobs
cancelled_jobs: Set[str] = set()


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


async def broadcast_status(job_id: str):
    """Broadcast job status to all connected clients."""
    if job_id in jobs:
        await manager.broadcast({
            "type": "job_update",
            "job": jobs[job_id].model_dump(),
        })


def process_episode_sync(job_id: str, episode_url: str, transcribe_only: bool = False, force: bool = False):
    """Synchronous episode processing (runs in thread)."""
    from xyz_client import get_client
    from database import get_database
    from downloader import get_downloader
    from transcriber import get_transcriber
    from summarizer import get_summarizer
    
    client = get_client()
    db = get_database()
    downloader = get_downloader()
    transcriber = get_transcriber()
    summarizer = get_summarizer()
    
    try:
        # Check for cancellation before starting
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 0, "Cancelled before starting")
            mark_job_cancelled(job_id)
            return
        
        # Get episode info
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
                    update_job_status(job_id, "fetching", 12, f"Auto-subscribed to: {podcast_info.title}")
                    podcast = db.get_podcast(episode.pid)  # Get the newly created record
            
            # Save episode to database
            if podcast:
                db.add_episode(
                    eid=episode.eid,
                    pid=episode.pid,
                    podcast_id=podcast.id,
                    title=episode.title,
                    description=episode.description,
                    duration=episode.duration,
                    pub_date=episode.pub_date,
                    audio_url=episode.audio_url,
                )
        
        # Check for cancellation before downloading
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 15, "Cancelled before download")
            mark_job_cancelled(job_id)
            return
        
        # Download
        update_job_status(job_id, "downloading", 15, "Downloading audio...")
        audio_path = downloader.download(episode)
        
        if not audio_path:
            update_job_status(job_id, "failed", 0, "Download failed")
            return
        
        update_job_status(job_id, "downloading", 30, "Download complete")
        
        # Check for cancellation before transcribing
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 30, "Cancelled before transcription")
            mark_job_cancelled(job_id)
            return
        
        # Transcribe
        if transcriber.transcript_exists(episode.eid) and not force:
            update_job_status(job_id, "transcribing", 60, "Using existing transcript")
            transcript = transcriber.load_transcript(episode.eid)
        else:
            update_job_status(job_id, "transcribing", 35, "Transcribing with Whisper...")
            transcript = transcriber.transcribe(audio_path, episode.eid)
            
            if transcript:
                transcriber.save_transcript(transcript)
                update_job_status(job_id, "transcribing", 60, "Transcription complete")
            else:
                update_job_status(job_id, "failed", 0, "Transcription failed")
                return
        
        if transcribe_only:
            update_job_status(job_id, "completed", 100, "Transcription complete (skipped summary)")
            return
        
        # Check for cancellation before summarizing
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 60, "Cancelled before summarization")
            mark_job_cancelled(job_id)
            return
        
        # Summarize
        existing_summary = summarizer.load_summary(episode.eid)
        if existing_summary and not force:
            update_job_status(job_id, "completed", 100, "Using existing summary")
            return
        
        update_job_status(job_id, "summarizing", 65, "Generating summary with LLM...")
        summary = summarizer.summarize(transcript, episode_title=episode.title)
        
        if summary:
            summarizer.save_summary(summary)
            update_job_status(job_id, "completed", 100, "Processing complete!")
        else:
            update_job_status(job_id, "failed", 0, "Summary generation failed")
    
    except Exception as e:
        # Check if cancelled during processing
        if is_job_cancelled(job_id):
            update_job_status(job_id, "cancelled", 0, "Cancelled")
            mark_job_cancelled(job_id)
        else:
            update_job_status(job_id, "failed", 0, f"Error: {str(e)}")


async def process_episode_async(job_id: str, episode_url: str, transcribe_only: bool = False, force: bool = False):
    """Async wrapper for episode processing."""
    loop = asyncio.get_event_loop()
    
    # Run in thread pool
    await loop.run_in_executor(
        None,
        process_episode_sync,
        job_id, episode_url, transcribe_only, force
    )
    
    # Broadcast final status
    await broadcast_status(job_id)


@router.post("/process")
async def process_episode(data: ProcessRequest, background_tasks: BackgroundTasks):
    """Start processing an episode."""
    if not data.episode_url:
        raise HTTPException(status_code=400, detail="episode_url is required")
    
    # Create job
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = ProcessingStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Starting...",
    )
    
    # Start background processing
    background_tasks.add_task(
        process_episode_async,
        job_id,
        data.episode_url,
        data.transcribe_only,
        data.force,
    )
    
    return {"job_id": job_id, "message": "Processing started"}


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
    
    # Update status immediately
    update_job_status(job_id, "cancelling", job.progress, "Cancellation requested...")
    
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
