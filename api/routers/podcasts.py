"""Podcast management endpoints."""
import asyncio
import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends

from api.schemas import (
    PodcastResponse, PodcastCreate, EpisodeResponse,
    ImportSubscriptionsRequest, ImportSubscriptionsResponse
)
from api.auth import get_current_user, User
from api.db import get_db
from config import USE_SUPABASE
from logger import get_logger

logger = get_logger("podcasts")

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
    
    # Fetch podcasts, episode counts, and summarized counts in parallel (3 queries instead of N+1)
    podcasts, episode_counts, summarized_counts = await asyncio.gather(
        run_sync(db.get_all_podcasts),
        run_sync(db.get_episode_counts_by_podcast),
        run_sync(db.get_summarized_counts_by_podcast),
    )
    
    return [
        PodcastResponse(
            pid=p.pid,
            title=p.title,
            author=p.author,
            description=p.description,
            cover_url=p.cover_url,
            episode_count=episode_counts.get(p.pid, 0),
            summarized_count=summarized_counts.get(p.pid, 0),
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
        
        # Try to get podcast ID, with fallback
        pid = episode.pid
        if not pid:
            # Try to fetch podcast ID separately
            pid = await run_sync(client.get_episode_podcast_id, episode.eid)
        
        if not pid:
            raise HTTPException(status_code=400, detail="Could not find parent podcast for this episode")
        
        # Now fetch the parent podcast
        podcast = await run_sync(client.get_podcast, pid)
        if not podcast:
            raise HTTPException(status_code=404, detail="Could not fetch parent podcast")
    else:
        # Normal podcast URL
        episode = None  # Not applicable for podcast URLs
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
    
    # Track episode count for response
    episode_count = len(episodes)
    
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
    
    # If subscribed via episode URL, ensure that episode is also in the database
    # (it might be older than the latest 50 episodes we fetched)
    if is_episode_url and episode:
        episode_eids = {ep.eid for ep in episodes}
        if episode.eid not in episode_eids:
            def save_original_episode():
                db.add_episode(
                    eid=episode.eid,
                    pid=episode.pid or podcast.pid,
                    podcast_id=podcast_id,
                    title=episode.title,
                    description=episode.description,
                    duration=episode.duration,
                    pub_date=episode.pub_date,
                    audio_url=episode.audio_url,
                )
            await run_sync(save_original_episode)
            episode_count += 1
    
    return PodcastResponse(
        pid=podcast.pid,
        title=podcast.title,
        author=podcast.author,
        description=podcast.description,
        cover_url=podcast.cover_url,
        episode_count=episode_count,
        summarized_count=0,  # New podcast, no summaries yet
    )


@router.get("/{pid}", response_model=PodcastResponse)
async def get_podcast(pid: str, user: Optional[User] = Depends(get_current_user)):
    """Get podcast details by ID."""
    db = get_db(user.id if user else None)
    
    podcast = await run_sync(db.get_podcast, pid)
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Fetch episodes and summary IDs in parallel
    episodes, summary_ids = await asyncio.gather(
        run_sync(db.get_episodes_by_podcast, pid),
        run_sync(db.get_summary_episode_ids),
    )
    
    # Count episodes with summaries
    summarized_count = sum(1 for ep in episodes if ep.eid in summary_ids)
    
    return PodcastResponse(
        pid=podcast.pid,
        title=podcast.title,
        author=podcast.author,
        description=podcast.description,
        cover_url=podcast.cover_url,
        episode_count=len(episodes),
        summarized_count=summarized_count,
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
    
    # Fetch podcast, episodes, transcript/summary status, and all summaries in parallel
    podcast, episodes, transcript_ids, summary_ids, all_summaries = await asyncio.gather(
        run_sync(db.get_podcast, pid),
        run_sync(db.get_episodes_by_podcast, pid),
        run_sync(db.get_transcript_episode_ids),
        run_sync(db.get_summary_episode_ids),
        run_sync(db.get_all_summaries),
    )
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Build a map of episode_id -> (topics_count, key_points_count)
    summary_counts = {
        s.episode_id: (len(s.topics), len(s.key_points))
        for s in all_summaries
    }
    
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
            topics_count=summary_counts.get(ep.eid, (0, 0))[0],
            key_points_count=summary_counts.get(ep.eid, (0, 0))[1],
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


@router.post("/import-subscriptions", response_model=ImportSubscriptionsResponse)
async def import_user_subscriptions(
    data: ImportSubscriptionsRequest,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Import all podcasts from a Xiaoyuzhou user's subscription list.
    The target user's profile must be public.
    
    This will:
    1. Fetch the user's subscribed podcasts from their public profile
    2. Add each podcast to the database if not already subscribed
    3. Fetch up to 20 recent episodes for each new podcast
    4. Return a summary of the import results
    """
    from xyz_client import get_client
    
    if USE_SUPABASE and not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    client = get_client()
    db = get_db(user.id if user else None)
    
    username = data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    
    # Extract user ID from input (could be URL or username)
    user_id = client.extract_user_id(username)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid username or user URL")
    
    logger.info(f"Importing subscriptions for user: {user_id}")
    
    # Fetch user's subscribed podcasts
    subscribed_podcasts = await run_sync(client.get_user_subscriptions, user_id)
    
    if not subscribed_podcasts:
        raise HTTPException(
            status_code=404, 
            detail="No podcasts found. The user profile may be private or the username may be incorrect."
        )
    
    total_found = len(subscribed_podcasts)
    newly_added = 0
    already_subscribed = 0
    failed = 0
    imported_names = []
    
    logger.info(f"Found {total_found} subscribed podcasts for user {user_id}")
    
    for podcast in subscribed_podcasts:
        try:
            # Check if already subscribed
            existing = await run_sync(db.get_podcast, podcast.pid)
            if existing:
                already_subscribed += 1
                logger.debug(f"Already subscribed to: {podcast.title}")
                continue
            
            # If podcast data is incomplete, fetch full details
            if not podcast.title or podcast.title.startswith("Podcast "):
                full_podcast = await run_sync(client.get_podcast, podcast.pid)
                if full_podcast:
                    podcast = full_podcast
            
            # Save podcast to database
            def save_podcast():
                return db.add_podcast(
                    podcast.pid, podcast.title, podcast.author,
                    podcast.description, podcast.cover_url
                )
            podcast_id = await run_sync(save_podcast)
            
            # Fetch and save episodes (limit to 20 for faster import)
            def fetch_episodes():
                return client.get_episodes_from_page(podcast.pid, limit=20)
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
            
            newly_added += 1
            imported_names.append(podcast.title)
            logger.info(f"Imported podcast: {podcast.title} ({len(episodes)} episodes)")
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
            
        except Exception as e:
            failed += 1
            logger.error(f"Failed to import podcast {podcast.pid}: {e}")
    
    logger.info(f"Import complete: {newly_added} added, {already_subscribed} existing, {failed} failed")
    
    return ImportSubscriptionsResponse(
        total_found=total_found,
        newly_added=newly_added,
        already_subscribed=already_subscribed,
        failed=failed,
        podcasts=imported_names,
    )
