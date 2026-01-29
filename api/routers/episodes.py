"""Episode management endpoints."""
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from api.schemas import EpisodeResponse
from api.auth import get_current_user, User
from api.db import get_db
from config import DATA_DIR

router = APIRouter()


async def run_sync(func, *args):
    """Run a synchronous function in executor to avoid blocking event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


@router.get("/{eid}", response_model=EpisodeResponse)
async def get_episode(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get episode details by ID."""
    db = get_db(user.id if user else None)
    
    episode = await run_sync(db.get_episode, eid)
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    def get_status():
        return db.has_transcript(eid), db.has_summary(eid)
    
    has_transcript, has_summary = await run_sync(get_status)
    
    return EpisodeResponse(
        eid=episode.eid,
        pid=episode.pid,
        title=episode.title,
        description=episode.description,
        duration=episode.duration,
        pub_date=episode.pub_date,
        cover_url="",
        audio_url=episode.audio_url,
        status=episode.status,
        has_transcript=has_transcript,
        has_summary=has_summary,
    )


@router.get("/{eid}/audio")
async def get_episode_audio_info(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get audio file info for an episode."""
    db = get_db(user.id if user else None)
    
    episode = await run_sync(db.get_episode, eid)
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Check if audio exists locally (file I/O in executor)
    def find_audio_path():
        audio_dir = DATA_DIR / "audio"
        if not audio_dir.exists():
            return None
        
        for ext in ['.m4a', '.mp3', '.wav']:
            # Check in podcast folder
            possible_path = audio_dir / episode.pid / f"{eid}{ext}"
            if possible_path.exists():
                return f"/data/audio/{episode.pid}/{eid}{ext}"
            # Check in unknown folder
            possible_path = audio_dir / "unknown" / f"{eid}{ext}"
            if possible_path.exists():
                return f"/data/audio/unknown/{eid}{ext}"
        return None
    
    audio_path = await run_sync(find_audio_path)
    
    return {
        "eid": eid,
        "remote_url": episode.audio_url,
        "local_path": audio_path,
        "downloaded": audio_path is not None,
    }


@router.delete("/{eid}")
async def delete_episode(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Delete an episode and its associated data (transcript, summary, audio)."""
    from api.routers.processing import cancelled_jobs, jobs
    
    db = get_db(user.id if user else None)
    
    # Cancel any in-progress job for this episode
    for job_id, job in list(jobs.items()):
        if job.episode_id == eid and job.status not in ("completed", "failed", "cancelled"):
            cancelled_jobs.add(job_id)
    
    episode = await run_sync(db.get_episode, eid)
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    episode_title = episode.title
    episode_pid = episode.pid
    
    # Delete all data in one batch (DB + files)
    def delete_all_data():
        # Delete from database
        db.delete_episode(eid)
        
        # Delete associated files (for local storage)
        db.delete_transcript(eid)
        db.delete_summary(eid)
        
        # Delete audio files
        audio_dir = DATA_DIR / "audio"
        if audio_dir.exists():
            for ext in ['.m4a', '.mp3', '.wav']:
                # Check in podcast folder
                if episode_pid:
                    audio_file = audio_dir / episode_pid / f"{eid}{ext}"
                    if audio_file.exists():
                        audio_file.unlink()
                # Check in unknown folder
                audio_file = audio_dir / "unknown" / f"{eid}{ext}"
                if audio_file.exists():
                    audio_file.unlink()
    
    await run_sync(delete_all_data)
    
    return {"message": f"Deleted episode: {episode_title}"}
