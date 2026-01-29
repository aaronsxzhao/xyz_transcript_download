"""Podcast management endpoints."""
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends

from api.schemas import PodcastResponse, PodcastCreate, EpisodeResponse
from api.auth import get_current_user, User
from api.db import get_db
from config import USE_SUPABASE

router = APIRouter()


async def run_sync(func, *args):
    """Run a synchronous function in executor to avoid blocking event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


@router.get("", response_model=List[PodcastResponse])
async def list_podcasts(user: Optional[User] = Depends(get_current_user)):
    """List all subscribed podcasts."""
    if USE_SUPABASE and not user:
        return []
    
    db = get_db(user.id if user else None)
    
    # Fetch podcasts and episode counts in parallel (2 queries instead of N+1)
    podcasts, episode_counts = await asyncio.gather(
        run_sync(db.get_all_podcasts),
        run_sync(db.get_episode_counts_by_podcast),
    )
    
    return [
        PodcastResponse(
            pid=p.pid,
            title=p.title,
            author=p.author,
            description=p.description,
            cover_url=p.cover_url,
            episode_count=episode_counts.get(p.pid, 0),
        )
        for p in podcasts
    ]


@router.post("", response_model=PodcastResponse)
async def add_podcast(data: PodcastCreate, user: Optional[User] = Depends(get_current_user)):
    """Subscribe to a new podcast by URL.
    
    If an episode URL is provided instead of a podcast URL, this will:
    1. Fetch the episode to get the parent podcast ID
    2. Subscribe to the parent podcast
    3. Include the episode in the subscription
    """
    from xyz_client import get_client
    
    client = get_client()
    db = get_db(user.id if user else None)
    
    url = data.url.strip()
    
    # Detect if this is an episode URL instead of a podcast URL
    is_episode_url = "/episode/" in url
    
    if is_episode_url:
        # User provided an episode URL - fetch episode to get parent podcast
        episode = await run_sync(client.get_episode_by_share_url, url)
        if not episode:
            raise HTTPException(status_code=404, detail="Could not fetch episode from URL")
        
        if not episode.pid:
            raise HTTPException(status_code=400, detail="Episode has no parent podcast")
        
        # Now fetch the parent podcast
        podcast = await run_sync(client.get_podcast, episode.pid)
        if not podcast:
            raise HTTPException(status_code=404, detail="Could not fetch parent podcast")
    else:
        # Normal podcast URL
        podcast = await run_sync(client.get_podcast_by_url, url)
        if not podcast:
            raise HTTPException(status_code=404, detail="Could not fetch podcast from URL")
    
    # Check if already subscribed
    existing = await run_sync(db.get_podcast, podcast.pid)
    if existing:
        raise HTTPException(status_code=400, detail="Already subscribed to this podcast")
    
    # Save to database (use lambda for multiple args)
    def save_podcast():
        return db.add_podcast(
            podcast.pid, podcast.title, podcast.author,
            podcast.description, podcast.cover_url
        )
    podcast_id = await run_sync(save_podcast)
    
    # Fetch and save episodes
    def fetch_episodes():
        return client.get_episodes_from_page(podcast.pid, limit=50)
    episodes = await run_sync(fetch_episodes)
    
    def save_episodes():
        for ep in episodes:
            db.add_episode(
                eid=ep.eid,
                pid=ep.pid,
                podcast_id=podcast_id,
                title=ep.title,
                description=ep.description,
                duration=ep.duration,
                pub_date=ep.pub_date,
                audio_url=ep.audio_url,
            )
    await run_sync(save_episodes)
    
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
    db = get_db(user.id if user else None)
    
    podcast = await run_sync(db.get_podcast, pid)
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    episodes = await run_sync(db.get_episodes_by_podcast, pid)
    
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
    db = get_db(user.id if user else None)
    
    podcast = await run_sync(db.get_podcast, pid)
    
    if not podcast:
        # Try force delete for edge cases (e.g., episode mistakenly added as podcast)
        deleted = await run_sync(db.force_delete_podcast, pid)
        if deleted:
            return {"message": f"Removed entry: {pid}"}
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    await run_sync(db.delete_podcast, pid)
    
    return {"message": f"Unsubscribed from {podcast.title}"}


@router.get("/{pid}/episodes", response_model=List[EpisodeResponse])
async def list_podcast_episodes(pid: str, limit: int = 50, user: Optional[User] = Depends(get_current_user)):
    """List episodes for a podcast."""
    db = get_db(user.id if user else None)
    
    # Fetch podcast, episodes, and transcript/summary status in parallel (3 queries instead of 2N+2)
    podcast, episodes, transcript_ids, summary_ids = await asyncio.gather(
        run_sync(db.get_podcast, pid),
        run_sync(db.get_episodes_by_podcast, pid),
        run_sync(db.get_transcript_episode_ids),
        run_sync(db.get_summary_episode_ids),
    )
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Build episode list using pre-fetched status sets
    return [
        EpisodeResponse(
            eid=ep.eid,
            pid=ep.pid,
            title=ep.title,
            description=ep.description,
            duration=ep.duration,
            pub_date=ep.pub_date,
            cover_url="",
            audio_url=ep.audio_url,
            status=ep.status,
            has_transcript=ep.eid in transcript_ids,
            has_summary=ep.eid in summary_ids,
        )
        for ep in episodes[:limit]
    ]


@router.post("/{pid}/refresh")
async def refresh_podcast_episodes(pid: str, user: Optional[User] = Depends(get_current_user)):
    """Refresh episodes for a podcast (also updates missing cover images)."""
    from xyz_client import get_client
    
    client = get_client()
    db = get_db(user.id if user else None)
    
    podcast = await run_sync(db.get_podcast, pid)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Update cover URL if missing
    if not podcast.cover_url:
        fresh_info = await run_sync(client.get_podcast, pid)
        if fresh_info and fresh_info.cover_url:
            await run_sync(db.update_podcast_cover, pid, fresh_info.cover_url)
    
    # Fetch latest episodes
    def fetch_episodes():
        return client.get_episodes_from_page(pid, limit=50)
    episodes = await run_sync(fetch_episodes)
    
    # Save new episodes
    def save_new_episodes():
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
        return new_count
    
    new_count = await run_sync(save_new_episodes)
    
    return {"message": f"Found {new_count} new episodes", "total": len(episodes)}
