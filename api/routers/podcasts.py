"""Podcast management endpoints."""
import asyncio
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form

from api.schemas import (
    PodcastResponse, PodcastCreate, EpisodeResponse, LocalAudioUploadResponse,
    ImportSubscriptionsRequest, ImportSubscriptionsResponse
)
from api.auth import get_current_user, User
from api.db import get_db
from api.local_media import (
    LOCAL_AUDIO_DIR,
    LOCAL_AUDIO_EXTENSIONS,
    LOCAL_PODCAST_AUTHOR,
    LOCAL_PODCAST_DESCRIPTION,
    LOCAL_PODCAST_PID,
    LOCAL_PODCAST_TITLE,
    get_local_audio_dir,
    make_local_episode_id,
)
from config import USE_SUPABASE
from logger import get_logger

logger = get_logger("podcasts")

router = APIRouter()
LOCAL_AUDIO_CHUNK_DIR = LOCAL_AUDIO_DIR / "_chunks"
LOCAL_AUDIO_CHUNK_DIR.mkdir(parents=True, exist_ok=True)


async def run_sync(func, *args):
    """Run a synchronous function in executor to avoid blocking event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


def _get_media_duration_seconds(file_path: Path) -> int:
    """Read media duration with ffprobe. Returns 0 if unavailable."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return max(0, int(float((result.stdout or "0").strip() or 0)))
    except Exception:
        return 0


def _audio_upload_session_dir(upload_id: str) -> Path:
    return LOCAL_AUDIO_CHUNK_DIR / upload_id


def _audio_upload_meta_path(upload_id: str) -> Path:
    return _audio_upload_session_dir(upload_id) / "meta.json"


def _audio_upload_chunk_path(upload_id: str, index: int) -> Path:
    return _audio_upload_session_dir(upload_id) / f"{index:06d}.part"


def _cleanup_audio_upload_session(upload_id: str) -> None:
    shutil.rmtree(_audio_upload_session_dir(upload_id), ignore_errors=True)


def _get_audio_upload_meta(upload_id: str) -> dict:
    meta_path = _audio_upload_meta_path(upload_id)
    if not meta_path.exists():
        raise FileNotFoundError(upload_id)
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _write_audio_upload_meta(upload_id: str, meta: dict) -> dict:
    _audio_upload_meta_path(upload_id).write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _update_audio_upload_meta(upload_id: str, updater) -> dict:
    meta = _get_audio_upload_meta(upload_id)
    return _write_audio_upload_meta(upload_id, updater(meta))


def _maybe_cleanup_stale_audio_uploads(max_age_seconds: int = 12 * 60 * 60) -> None:
    now = time.time()
    for session_dir in LOCAL_AUDIO_CHUNK_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        try:
            meta_path = session_dir / "meta.json"
            last_updated = meta_path.stat().st_mtime if meta_path.exists() else session_dir.stat().st_mtime
            if now - last_updated > max_age_seconds:
                shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            continue


def _podcast_response_from_record(db, podcast) -> PodcastResponse:
    episodes = db.get_episodes_by_podcast(podcast.pid)
    summary_ids = db.get_summary_episode_ids()
    summarized_count = sum(1 for ep in episodes if ep.eid in summary_ids)
    return PodcastResponse(
        pid=podcast.pid,
        title=podcast.title,
        author=podcast.author,
        description=podcast.description,
        cover_url=podcast.cover_url,
        episode_count=len(episodes),
        summarized_count=summarized_count,
        platform=getattr(podcast, "platform", "xiaoyuzhou") or "xiaoyuzhou",
        feed_url=getattr(podcast, "feed_url", "") or "",
    )


def _episode_response_from_record(db, episode) -> EpisodeResponse:
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
        has_transcript=db.has_transcript(episode.eid),
        has_summary=db.has_summary(episode.eid),
        topics_count=0,
        key_points_count=0,
        created_at=episode.created_at,
    )


def _ensure_local_podcast(db):
    podcast = db.get_podcast(LOCAL_PODCAST_PID)
    if podcast:
        return podcast
    podcast_id = db.add_podcast(
        LOCAL_PODCAST_PID,
        LOCAL_PODCAST_TITLE,
        LOCAL_PODCAST_AUTHOR,
        LOCAL_PODCAST_DESCRIPTION,
        "",
        platform="local",
    )
    if not podcast_id:
        raise RuntimeError("Failed to create local podcast")
    podcast = db.get_podcast(LOCAL_PODCAST_PID)
    if not podcast:
        raise RuntimeError("Local podcast created but could not be loaded")
    return podcast


@router.get("", response_model=List[PodcastResponse])
async def list_podcasts(user: Optional[User] = Depends(get_current_user)):
    """List all subscribed podcasts."""
    if USE_SUPABASE and not user:
        return []
    
    db = get_db(user.id if user else None)
    
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
            platform=getattr(p, 'platform', 'xiaoyuzhou') or 'xiaoyuzhou',
            feed_url=getattr(p, 'feed_url', '') or '',
        )
        for p in podcasts
    ]


@router.post("", response_model=PodcastResponse)
async def add_podcast(data: PodcastCreate, user: Optional[User] = Depends(get_current_user)):
    """Subscribe to a new podcast by URL.
    
    Supports Xiaoyuzhou and Apple Podcasts URLs.
    If an episode URL is provided (Xiaoyuzhou), it resolves to the parent podcast.
    """
    from apple_podcasts_client import detect_platform as detect_podcast_platform
    
    db = get_db(user.id if user else None)
    url = data.url.strip()
    platform = detect_podcast_platform(url) or "xiaoyuzhou"
    
    if platform == "apple":
        return await _add_apple_podcast(url, db)
    else:
        return await _add_xyz_podcast(url, db)


@router.post("/upload-audio", response_model=LocalAudioUploadResponse)
async def upload_local_audio(
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
    user: Optional[User] = Depends(get_current_user),
):
    """Upload a local audio file into the user's local podcast."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    original_name = Path(file.filename).name
    ext = Path(original_name).suffix.lower()
    if ext not in LOCAL_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {ext or 'unknown'}")

    user_id = user.id if user else None
    db = get_db(user_id)
    podcast = await run_sync(_ensure_local_podcast, db)

    eid = make_local_episode_id()
    save_dir = get_local_audio_dir(user_id)
    save_path = save_dir / f"{eid}{ext}"
    file_size = 0

    try:
        with open(save_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                file_size += len(chunk)
    finally:
        await file.close()

    if file_size <= 0:
        try:
            save_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    duration = await run_sync(_get_media_duration_seconds, save_path)
    episode_title = title.strip() or Path(original_name).stem
    episode_description = description.strip()
    pub_date = datetime.now(timezone.utc).isoformat()

    def save_episode():
        return db.add_episode(
            eid=eid,
            pid=podcast.pid,
            podcast_id=podcast.id,
            title=episode_title,
            description=episode_description,
            duration=duration,
            pub_date=pub_date,
            audio_url=str(save_path),
        )

    await run_sync(save_episode)
    episode = await run_sync(db.get_episode, eid)
    if not episode:
        raise HTTPException(status_code=500, detail="Failed to load uploaded episode")

    podcast_response, episode_response = await asyncio.gather(
        run_sync(_podcast_response_from_record, db, podcast),
        run_sync(_episode_response_from_record, db, episode),
    )
    return LocalAudioUploadResponse(podcast=podcast_response, episode=episode_response)


@router.post("/upload-audio/init")
async def init_chunked_audio_upload(
    filename: str = Form(...),
    size: int = Form(...),
    user: Optional[User] = Depends(get_current_user),
):
    """Initialize a chunked local audio upload session."""
    _maybe_cleanup_stale_audio_uploads()

    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    ext = Path(filename).suffix.lower()
    if ext not in LOCAL_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {ext or 'unknown'}")

    upload_id = str(uuid.uuid4())[:16]
    session_dir = _audio_upload_session_dir(upload_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    chunk_size = 5 * 1024 * 1024
    total_size = max(0, int(size or 0))
    total_chunks = max(1, (total_size + chunk_size - 1) // chunk_size)
    _write_audio_upload_meta(upload_id, {
        "filename": Path(filename).name,
        "size": total_size,
        "ext": ext,
        "user_id": user.id if user else None,
        "received_chunks": [],
        "received_bytes": 0,
        "total_chunks": total_chunks,
        "created_at": time.time(),
    })
    return {
        "upload_id": upload_id,
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
    }


@router.post("/upload-audio/chunk")
async def upload_local_audio_chunk(
    upload_id: str = Form(...),
    index: int = Form(...),
    chunk: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user),
):
    """Upload one chunk of a local audio file."""
    try:
        meta = _get_audio_upload_meta(upload_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload session not found")

    if meta.get("user_id") != (user.id if user else None):
        raise HTTPException(status_code=403, detail="Upload session does not belong to this user")
    if index < 0:
        raise HTTPException(status_code=400, detail="Chunk index must be >= 0")

    total_chunks = int(meta.get("total_chunks") or 0)
    if total_chunks and index >= total_chunks:
        raise HTTPException(status_code=400, detail=f"Chunk index {index} is out of range")

    part_path = _audio_upload_chunk_path(upload_id, index)
    previous_size = part_path.stat().st_size if part_path.exists() else 0
    chunk_size = 0
    try:
        with open(part_path, "wb") as out:
            while True:
                data = await chunk.read(1024 * 1024)
                if not data:
                    break
                out.write(data)
                chunk_size += len(data)
    finally:
        await chunk.close()

    if chunk_size <= 0:
        part_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded chunk is empty")

    _update_audio_upload_meta(upload_id, lambda current: {
        **current,
        "received_bytes": max(0, int(current.get("received_bytes") or 0) - previous_size + chunk_size),
        "received_chunks": sorted({
            *[int(i) for i in current.get("received_chunks", [])],
            index,
        }),
    })
    return {"upload_id": upload_id, "index": index, "size": chunk_size}


@router.post("/upload-audio/complete", response_model=LocalAudioUploadResponse)
async def complete_chunked_audio_upload(
    upload_id: str = Form(...),
    title: str = Form(""),
    description: str = Form(""),
    user: Optional[User] = Depends(get_current_user),
):
    """Assemble a chunked local audio upload and create the episode."""
    try:
        meta = _get_audio_upload_meta(upload_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload session not found")

    user_id = user.id if user else None
    if meta.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Upload session does not belong to this user")

    session_dir = _audio_upload_session_dir(upload_id)
    part_paths = sorted(session_dir.glob("*.part"))
    if not part_paths:
        raise HTTPException(status_code=400, detail="No uploaded chunks found")

    original_name = meta.get("filename", "")
    ext = Path(original_name).suffix.lower() or meta.get("ext", "")
    if ext not in LOCAL_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {ext or 'unknown'}")

    db = get_db(user_id)
    podcast = await run_sync(_ensure_local_podcast, db)
    eid = make_local_episode_id()
    save_dir = get_local_audio_dir(user_id)
    save_path = save_dir / f"{eid}{ext}"

    bytes_written = 0
    try:
        with open(save_path, "wb") as out:
            for part_path in part_paths:
                with open(part_path, "rb") as src:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                bytes_written += part_path.stat().st_size
    except Exception:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to assemble uploaded audio")
    finally:
        _cleanup_audio_upload_session(upload_id)

    expected_size = int(meta.get("size") or 0)
    if bytes_written <= 0:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if expected_size > 0 and bytes_written != expected_size:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Upload incomplete: expected {expected_size} bytes, received {bytes_written} bytes",
        )

    duration = await run_sync(_get_media_duration_seconds, save_path)
    episode_title = title.strip() or Path(original_name).stem
    episode_description = description.strip()
    pub_date = datetime.now(timezone.utc).isoformat()

    def save_episode():
        return db.add_episode(
            eid=eid,
            pid=podcast.pid,
            podcast_id=podcast.id,
            title=episode_title,
            description=episode_description,
            duration=duration,
            pub_date=pub_date,
            audio_url=str(save_path),
        )

    await run_sync(save_episode)
    episode = await run_sync(db.get_episode, eid)
    if not episode:
        raise HTTPException(status_code=500, detail="Failed to load uploaded episode")

    podcast_response, episode_response = await asyncio.gather(
        run_sync(_podcast_response_from_record, db, podcast),
        run_sync(_episode_response_from_record, db, episode),
    )
    return LocalAudioUploadResponse(podcast=podcast_response, episode=episode_response)


async def _add_apple_podcast(url: str, db) -> PodcastResponse:
    """Add a podcast from Apple Podcasts."""
    from apple_podcasts_client import get_podcast_by_url, get_episodes_from_feed
    
    podcast = await run_sync(get_podcast_by_url, url)
    if not podcast:
        raise HTTPException(
            status_code=404,
            detail="Could not fetch podcast. This may be an Apple-exclusive podcast without a public RSS feed."
        )
    
    existing = await run_sync(db.get_podcast, podcast.pid)
    if existing:
        raise HTTPException(status_code=400, detail="Already subscribed to this podcast")
    
    def save_podcast():
        return db.add_podcast(
            podcast.pid, podcast.title, podcast.author,
            podcast.description, podcast.cover_url,
            platform="apple", feed_url=podcast.feed_url,
        )
    podcast_id = await run_sync(save_podcast)
    
    def fetch_episodes():
        return get_episodes_from_feed(podcast.feed_url, podcast.pid, limit=50)
    episodes = await run_sync(fetch_episodes)
    
    def save_episodes():
        for ep in episodes:
            db.add_episode(
                eid=ep.eid, pid=ep.pid, podcast_id=podcast_id,
                title=ep.title, description=ep.description,
                duration=ep.duration, pub_date=ep.pub_date,
                audio_url=ep.audio_url,
            )
    await run_sync(save_episodes)
    
    return PodcastResponse(
        pid=podcast.pid, title=podcast.title, author=podcast.author,
        description=podcast.description, cover_url=podcast.cover_url,
        episode_count=len(episodes), summarized_count=0,
        platform="apple", feed_url=podcast.feed_url,
    )


async def _add_xyz_podcast(url: str, db) -> PodcastResponse:
    """Add a podcast from Xiaoyuzhou."""
    from xyz_client import get_client
    
    client = get_client()
    is_episode_url = "/episode/" in url
    
    if is_episode_url:
        episode = await run_sync(client.get_episode_by_share_url, url)
        if not episode:
            raise HTTPException(status_code=404, detail="Could not fetch episode from URL")
        pid = episode.pid
        if not pid:
            pid = await run_sync(client.get_episode_podcast_id, episode.eid)
        if not pid:
            raise HTTPException(status_code=400, detail="Could not find parent podcast for this episode")
        podcast = await run_sync(client.get_podcast, pid)
        if not podcast:
            raise HTTPException(status_code=404, detail="Could not fetch parent podcast")
    else:
        episode = None
        podcast = await run_sync(client.get_podcast_by_url, url)
        if not podcast:
            raise HTTPException(status_code=404, detail="Could not fetch podcast from URL")
    
    existing = await run_sync(db.get_podcast, podcast.pid)
    if existing:
        raise HTTPException(status_code=400, detail="Already subscribed to this podcast")
    
    def save_podcast():
        return db.add_podcast(
            podcast.pid, podcast.title, podcast.author,
            podcast.description, podcast.cover_url,
            platform="xiaoyuzhou",
        )
    podcast_id = await run_sync(save_podcast)
    
    def fetch_episodes():
        return client.get_episodes_from_page(podcast.pid, limit=50)
    episodes = await run_sync(fetch_episodes)
    episode_count = len(episodes)
    
    def save_episodes():
        for ep in episodes:
            db.add_episode(
                eid=ep.eid, pid=ep.pid, podcast_id=podcast_id,
                title=ep.title, description=ep.description,
                duration=ep.duration, pub_date=ep.pub_date,
                audio_url=ep.audio_url,
            )
    await run_sync(save_episodes)
    
    if is_episode_url and episode:
        episode_eids = {ep.eid for ep in episodes}
        if episode.eid not in episode_eids:
            def save_original_episode():
                db.add_episode(
                    eid=episode.eid, pid=episode.pid or podcast.pid,
                    podcast_id=podcast_id, title=episode.title,
                    description=episode.description, duration=episode.duration,
                    pub_date=episode.pub_date, audio_url=episode.audio_url,
                )
            await run_sync(save_original_episode)
            episode_count += 1
    
    return PodcastResponse(
        pid=podcast.pid, title=podcast.title, author=podcast.author,
        description=podcast.description, cover_url=podcast.cover_url,
        episode_count=episode_count, summarized_count=0,
        platform="xiaoyuzhou",
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
        platform=getattr(podcast, 'platform', 'xiaoyuzhou') or 'xiaoyuzhou',
        feed_url=getattr(podcast, 'feed_url', '') or '',
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
            created_at=ep.created_at,
        )
        for ep in episodes[:limit]
    ]


@router.post("/{pid}/refresh")
async def refresh_podcast_episodes(pid: str, user: Optional[User] = Depends(get_current_user)):
    """Refresh episodes for a podcast (also updates missing cover images)."""
    db = get_db(user.id if user else None)
    
    podcast = await run_sync(db.get_podcast, pid)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    platform = getattr(podcast, 'platform', 'xiaoyuzhou') or 'xiaoyuzhou'
    feed_url = getattr(podcast, 'feed_url', '') or ''
    
    if platform == "apple" and feed_url:
        from apple_podcasts_client import get_episodes_from_feed
        def fetch_episodes():
            return get_episodes_from_feed(feed_url, pid, limit=50)
        episodes = await run_sync(fetch_episodes)
    else:
        from xyz_client import get_client
        client = get_client()
        if not podcast.cover_url:
            fresh_info = await run_sync(client.get_podcast, pid)
            if fresh_info and fresh_info.cover_url:
                await run_sync(db.update_podcast_cover, pid, fresh_info.cover_url)
        def fetch_episodes():
            return client.get_episodes_from_page(pid, limit=50)
        episodes = await run_sync(fetch_episodes)
    
    def save_new_episodes():
        new_count = 0
        for ep in episodes:
            existing = db.get_episode(ep.eid)
            if not existing:
                db.add_episode(
                    eid=ep.eid,
                    pid=ep.pid or pid,
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
    try:
        subscribed_podcasts = await run_sync(client.get_user_subscriptions, user_id)
    except Exception as e:
        err_msg = str(e)
        if "500" in err_msg or "error responses" in err_msg.lower():
            raise HTTPException(
                status_code=502,
                detail="Xiaoyuzhou servers are currently unavailable (HTTP 500). Please try again later."
            )
        raise HTTPException(status_code=502, detail=f"Failed to reach Xiaoyuzhou: {err_msg}")
    
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
