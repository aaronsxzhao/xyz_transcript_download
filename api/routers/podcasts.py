"""Podcast management endpoints."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends

from api.schemas import PodcastResponse, PodcastCreate, EpisodeResponse
from api.auth import get_current_user, User
from config import USE_SUPABASE

router = APIRouter()


def get_db_and_user(user: Optional[User]):
    """Get the appropriate database based on config."""
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        return get_supabase_database(), user.id
    else:
        from database import get_database
        return get_database(), "local"


@router.get("", response_model=List[PodcastResponse])
async def list_podcasts(user: Optional[User] = Depends(get_current_user)):
    """List all subscribed podcasts."""
    if USE_SUPABASE:
        if not user:
            return []
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            podcasts = db.get_all_podcasts(user.id)
            result = []
            for p in podcasts:
                episodes = db.get_episodes_by_podcast(user.id, p.pid)
                result.append(PodcastResponse(
                    pid=p.pid,
                    title=p.title,
                    author=p.author,
                    description=p.description,
                    cover_url=p.cover_url,
                    episode_count=len(episodes),
                ))
            return result
    
    # Fall back to local SQLite
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
async def add_podcast(data: PodcastCreate, user: Optional[User] = Depends(get_current_user)):
    """Subscribe to a new podcast by URL."""
    from xyz_client import get_client
    
    client = get_client()
    
    # Fetch podcast info
    podcast = client.get_podcast_by_url(data.url)
    if not podcast:
        raise HTTPException(status_code=404, detail="Could not fetch podcast from URL")
    
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            # Check if already subscribed
            existing = db.get_podcast(user.id, podcast.pid)
            if existing:
                raise HTTPException(status_code=400, detail="Already subscribed to this podcast")
            
            # Save to database
            podcast_id = db.add_podcast(user.id, podcast.pid, podcast.title, podcast.author, 
                                        podcast.description, podcast.cover_url)
            
            # Fetch and save episodes
            episodes = client.get_episodes_from_page(podcast.pid, limit=50)
            for ep in episodes:
                db.add_episode(
                    user_id=user.id,
                    podcast_id=podcast_id,
                    eid=ep.eid,
                    pid=ep.pid,
                    title=ep.title,
                    description=ep.description,
                    duration=ep.duration,
                    pub_date=ep.pub_date,
                    audio_url=ep.audio_url,
                )
            
            return PodcastResponse(
                pid=podcast.pid,
                title=podcast.title,
                author=podcast.author,
                description=podcast.description,
                cover_url=podcast.cover_url,
                episode_count=len(episodes),
            )
    
    # Fall back to local SQLite
    from database import get_database
    db = get_database()
    
    # Check if already subscribed
    existing = db.get_podcast(podcast.pid)
    if existing:
        raise HTTPException(status_code=400, detail="Already subscribed to this podcast")
    
    # Save to database
    db.add_podcast(podcast.pid, podcast.title, podcast.author, podcast.description, podcast.cover_url)
    
    # Get the podcast record for the podcast_id
    podcast_record = db.get_podcast(podcast.pid)
    
    # Fetch and save episodes
    episodes = client.get_episodes_from_page(podcast.pid, limit=50)
    for ep in episodes:
        db.add_episode(
            eid=ep.eid,
            pid=ep.pid,
            podcast_id=podcast_record.id,
            title=ep.title,
            description=ep.description,
            duration=ep.duration,
            pub_date=ep.pub_date,
            audio_url=ep.audio_url,
        )
    
    return PodcastResponse(
        pid=podcast.pid,
        title=podcast.title,
        author=podcast.author,
        description=podcast.description,
        cover_url=podcast.cover_url,
        episode_count=len(episodes),
    )


@router.get("/{pid}", response_model=PodcastResponse)
async def get_podcast(pid: str, user: Optional[User] = Depends(get_current_user)):
    """Get podcast details by ID."""
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            podcast = db.get_podcast(user.id, pid)
            if not podcast:
                raise HTTPException(status_code=404, detail="Podcast not found")
            
            episodes = db.get_episodes_by_podcast(user.id, pid)
            return PodcastResponse(
                pid=podcast.pid,
                title=podcast.title,
                author=podcast.author,
                description=podcast.description,
                cover_url=podcast.cover_url,
                episode_count=len(episodes),
            )
    
    # Fall back to local SQLite
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
async def remove_podcast(pid: str, user: Optional[User] = Depends(get_current_user)):
    """Unsubscribe from a podcast."""
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            podcast = db.get_podcast(user.id, pid)
            if not podcast:
                raise HTTPException(status_code=404, detail="Podcast not found")
            
            db.delete_podcast(user.id, pid)
            return {"message": f"Unsubscribed from {podcast.title}"}
    
    # Fall back to local SQLite
    from database import get_database
    db = get_database()
    podcast = db.get_podcast(pid)
    
    if not podcast:
        # Try to force delete by pid even if not found in expected format
        # This handles edge cases where an episode was mistakenly added as a podcast
        try:
            db.force_delete_podcast_by_pid(pid)
            return {"message": f"Removed entry: {pid}"}
        except Exception:
            raise HTTPException(status_code=404, detail="Podcast not found")
    
    db.delete_podcast(pid)
    
    return {"message": f"Unsubscribed from {podcast.title}"}


@router.get("/{pid}/episodes", response_model=List[EpisodeResponse])
async def list_podcast_episodes(pid: str, limit: int = 50, user: Optional[User] = Depends(get_current_user)):
    """List episodes for a podcast."""
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            podcast = db.get_podcast(user.id, pid)
            if not podcast:
                raise HTTPException(status_code=404, detail="Podcast not found")
            
            episodes = db.get_episodes_by_podcast(user.id, pid)
            
            result = []
            for ep in episodes[:limit]:
                has_transcript = db.has_transcript(user.id, ep.eid)
                has_summary = db.has_summary(user.id, ep.eid)
                
                result.append(EpisodeResponse(
                    eid=ep.eid,
                    pid=ep.pid,
                    title=ep.title,
                    description=ep.description,
                    duration=ep.duration,
                    pub_date=ep.pub_date,
                    cover_url="",
                    audio_url=ep.audio_url,
                    status=ep.status,
                    has_transcript=has_transcript,
                    has_summary=has_summary,
                ))
            
            return result
    
    # Fall back to local SQLite
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
            cover_url=getattr(ep, 'cover_url', ''),
            audio_url=ep.audio_url,
            status=ep.status.value if hasattr(ep.status, 'value') else str(ep.status),
            has_transcript=has_transcript,
            has_summary=has_summary,
        ))
    
    return result


@router.post("/{pid}/refresh")
async def refresh_podcast_episodes(pid: str, user: Optional[User] = Depends(get_current_user)):
    """Refresh episodes for a podcast (also updates missing cover images)."""
    from xyz_client import get_client
    
    client = get_client()
    
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            podcast = db.get_podcast(user.id, pid)
            if not podcast:
                raise HTTPException(status_code=404, detail="Podcast not found")
            
            # Update cover URL if missing
            if not podcast.cover_url:
                fresh_info = client.get_podcast(pid)
                if fresh_info and fresh_info.cover_url:
                    db.update_podcast_cover(user.id, pid, fresh_info.cover_url)
            
            # Fetch latest episodes
            episodes = client.get_episodes_from_page(pid, limit=50)
            new_count = 0
            
            for ep in episodes:
                existing = db.get_episode(user.id, ep.eid)
                if not existing:
                    db.add_episode(
                        user_id=user.id,
                        podcast_id=podcast.id,
                        eid=ep.eid,
                        pid=ep.pid,
                        title=ep.title,
                        description=ep.description,
                        duration=ep.duration,
                        pub_date=ep.pub_date,
                        audio_url=ep.audio_url,
                    )
                    new_count += 1
            
            return {"message": f"Found {new_count} new episodes", "total": len(episodes)}
    
    # Fall back to local SQLite
    from database import get_database
    db = get_database()
    
    podcast = db.get_podcast(pid)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Update cover URL if missing
    if not podcast.cover_url:
        fresh_info = client.get_podcast(pid)
        if fresh_info and fresh_info.cover_url:
            db.update_podcast_cover(pid, fresh_info.cover_url)
    
    # Fetch latest episodes
    episodes = client.get_episodes_from_page(pid, limit=50)
    new_count = 0
    
    for ep in episodes:
        existing = db.get_episode(ep.eid)
        if not existing:
            db.add_episode(
                eid=ep.eid,
                pid=ep.pid,
                podcast_id=podcast.id,
                title=ep.title,
                description=ep.description,
                duration=ep.duration,
                pub_date=ep.pub_date,
                audio_url=ep.audio_url,
            )
            new_count += 1
    
    return {"message": f"Found {new_count} new episodes", "total": len(episodes)}
