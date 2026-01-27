"""Episode management endpoints."""
from fastapi import APIRouter, HTTPException

from api.schemas import EpisodeResponse

router = APIRouter()


@router.get("/{eid}", response_model=EpisodeResponse)
async def get_episode(eid: str):
    """Get episode details by ID."""
    from database import get_database
    from config import DATA_DIR
    
    db = get_database()
    episode = db.get_episode(eid)
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Check for transcripts and summaries
    transcripts_dir = DATA_DIR / "transcripts"
    summaries_dir = DATA_DIR / "summaries"
    
    has_transcript = (transcripts_dir / f"{eid}.json").exists() if transcripts_dir.exists() else False
    has_summary = (summaries_dir / f"{eid}.json").exists() if summaries_dir.exists() else False
    
    return EpisodeResponse(
        eid=episode.eid,
        pid=episode.pid,
        title=episode.title,
        description=episode.description,
        duration=episode.duration,
        pub_date=episode.pub_date,
        cover_url=getattr(episode, 'cover_url', ''),  # EpisodeRecord may not have cover_url
        audio_url=episode.audio_url,
        status=episode.status.value if hasattr(episode.status, 'value') else str(episode.status),
        has_transcript=has_transcript,
        has_summary=has_summary,
    )


@router.get("/{eid}/audio")
async def get_episode_audio_info(eid: str):
    """Get audio file info for an episode."""
    from config import DATA_DIR
    from database import get_database
    
    db = get_database()
    episode = db.get_episode(eid)
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Check if audio exists locally
    audio_dir = DATA_DIR / "audio"
    audio_path = None
    
    if audio_dir.exists():
        # Check in podcast folder
        for ext in ['.m4a', '.mp3', '.wav']:
            possible_path = audio_dir / episode.pid / f"{eid}{ext}"
            if possible_path.exists():
                audio_path = f"/data/audio/{episode.pid}/{eid}{ext}"
                break
            # Also check unknown folder
            possible_path = audio_dir / "unknown" / f"{eid}{ext}"
            if possible_path.exists():
                audio_path = f"/data/audio/unknown/{eid}{ext}"
                break
    
    return {
        "eid": eid,
        "remote_url": episode.audio_url,
        "local_path": audio_path,
        "downloaded": audio_path is not None,
    }
