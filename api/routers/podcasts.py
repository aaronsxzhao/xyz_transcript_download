"""Podcast management endpoints."""
from typing import List
from fastapi import APIRouter, HTTPException

from api.schemas import PodcastResponse, PodcastCreate, EpisodeResponse

router = APIRouter()


@router.get("", response_model=List[PodcastResponse])
async def list_podcasts():
    """List all subscribed podcasts."""
    from database import get_database
    
    db = get_database()
    podcasts = db.get_all_podcasts()
    
    result = []
    for p in podcasts:
        episodes = db.get_episodes_by_podcast(p.pid)
        result.append(PodcastResponse(
            pid=p.pid,
            title=p.title,
            author=p.author,
            description=p.description,
            cover_url=p.cover_url,
            episode_count=len(episodes),
        ))
    
    return result


@router.post("", response_model=PodcastResponse)
async def add_podcast(data: PodcastCreate):
    """Subscribe to a new podcast by URL."""
    from xyz_client import get_client
    from database import get_database
    
    client = get_client()
    db = get_database()
    
    # Fetch podcast info
    podcast = client.get_podcast_by_url(data.url)
    if not podcast:
        raise HTTPException(status_code=404, detail="Could not fetch podcast from URL")
    
    # Check if already subscribed
    existing = db.get_podcast(podcast.pid)
    if existing:
        raise HTTPException(status_code=400, detail="Already subscribed to this podcast")
    
    # Save to database
    db.save_podcast(podcast)
    
    # Fetch and save episodes
    episodes = client.get_episodes_from_page(podcast.pid, limit=50)
    for ep in episodes:
        db.save_episode(ep)
    
    return PodcastResponse(
        pid=podcast.pid,
        title=podcast.title,
        author=podcast.author,
        description=podcast.description,
        cover_url=podcast.cover_url,
        episode_count=len(episodes),
    )


@router.get("/{pid}", response_model=PodcastResponse)
async def get_podcast(pid: str):
    """Get podcast details by ID."""
    from database import get_database
    
    db = get_database()
    podcast = db.get_podcast(pid)
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    episodes = db.get_episodes_by_podcast(pid)
    
    return PodcastResponse(
        pid=podcast.pid,
        title=podcast.title,
        author=podcast.author,
        description=podcast.description,
        cover_url=podcast.cover_url,
        episode_count=len(episodes),
    )


@router.delete("/{pid}")
async def remove_podcast(pid: str):
    """Unsubscribe from a podcast."""
    from database import get_database
    
    db = get_database()
    podcast = db.get_podcast(pid)
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    db.remove_podcast(pid)
    
    return {"message": f"Unsubscribed from {podcast.title}"}


@router.get("/{pid}/episodes", response_model=List[EpisodeResponse])
async def list_podcast_episodes(pid: str, limit: int = 50):
    """List episodes for a podcast."""
    from database import get_database
    from config import DATA_DIR
    
    db = get_database()
    podcast = db.get_podcast(pid)
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    episodes = db.get_episodes_by_podcast(pid)
    
    # Check for transcripts and summaries
    transcripts_dir = DATA_DIR / "transcripts"
    summaries_dir = DATA_DIR / "summaries"
    
    result = []
    for ep in episodes[:limit]:
        has_transcript = (transcripts_dir / f"{ep.eid}.json").exists() if transcripts_dir.exists() else False
        has_summary = (summaries_dir / f"{ep.eid}.json").exists() if summaries_dir.exists() else False
        
        result.append(EpisodeResponse(
            eid=ep.eid,
            pid=ep.pid,
            title=ep.title,
            description=ep.description,
            duration=ep.duration,
            pub_date=ep.pub_date,
            cover_url=getattr(ep, 'cover_url', ''),  # EpisodeRecord may not have cover_url
            audio_url=ep.audio_url,
            status=ep.status.value if hasattr(ep.status, 'value') else str(ep.status),
            has_transcript=has_transcript,
            has_summary=has_summary,
        ))
    
    return result


@router.post("/{pid}/refresh")
async def refresh_podcast_episodes(pid: str):
    """Refresh episodes for a podcast."""
    from xyz_client import get_client
    from database import get_database
    
    client = get_client()
    db = get_database()
    
    podcast = db.get_podcast(pid)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Fetch latest episodes
    episodes = client.get_episodes_from_page(pid, limit=50)
    new_count = 0
    
    for ep in episodes:
        existing = db.get_episode(ep.eid)
        if not existing:
            db.save_episode(ep)
            new_count += 1
    
    return {"message": f"Found {new_count} new episodes", "total": len(episodes)}
