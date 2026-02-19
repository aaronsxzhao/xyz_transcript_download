"""FastAPI application for Podcast Transcript Tool."""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routers import podcasts, episodes, transcripts, summaries, processing
from api.routers import auth_router, video_notes, cookies
from api.auth import get_current_user, User
from logger import get_logger

logger = get_logger("api.main")


# Create FastAPI app
app = FastAPI(
    title="Podcast Transcript API",
    description="API for managing podcast transcripts and summaries",
    version="1.0.0",
)


# Background task for checking podcast updates
_podcast_check_task: Optional[asyncio.Task] = None
# User-scoped cache: {user_id: {"episodes": [...], "last_check": ...}}
_new_episodes_cache: dict = {}


async def check_podcasts_for_updates():
    """Background task that periodically checks podcasts for new episodes."""
    from config import CHECK_INTERVAL
    from xyz_client import get_client
    from api.db import get_db
    
    check_interval = max(CHECK_INTERVAL, 600)  # At least 10 minutes
    
    logger.info(f"[PodcastChecker] Started background podcast checker (interval: {check_interval}s)")
    
    while True:
        try:
            await asyncio.sleep(check_interval)
            
            logger.info("[PodcastChecker] Checking podcasts for updates...")
            
            # Get all podcasts (for local mode, no user_id)
            db = get_db(None)
            all_podcasts = db.get_all_podcasts()
            
            if not all_podcasts:
                logger.debug("[PodcastChecker] No podcasts to check")
                continue
            
            client = get_client()
            total_new = 0
            new_episodes_list = []
            
            for podcast in all_podcasts:
                try:
                    # Fetch latest episodes from web
                    episodes = client.get_episodes_from_page(podcast.pid, limit=10)
                    
                    new_count = 0
                    for ep in episodes:
                        if not db.episode_exists(ep.eid):
                            # Add new episode
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
                            new_episodes_list.append({
                                "eid": ep.eid,
                                "title": ep.title,
                                "podcast_title": podcast.title,
                                "podcast_pid": podcast.pid,
                            })
                    
                    if new_count > 0:
                        logger.info(f"[PodcastChecker] Found {new_count} new episode(s) for '{podcast.title}'")
                        total_new += new_count
                    
                    # Update last checked timestamp
                    db.update_podcast_checked(podcast.pid)
                    
                except Exception as e:
                    logger.warning(f"[PodcastChecker] Error checking '{podcast.title}': {e}")
                
                # Small delay between podcasts to avoid rate limiting
                await asyncio.sleep(2)
            
            # Update cache with new episodes (for local/anonymous mode)
            if new_episodes_list:
                _new_episodes_cache["_anonymous"] = {
                    "episodes": new_episodes_list[:20],  # Keep last 20
                    "last_check": datetime.now().isoformat(),
                }
                logger.info(f"[PodcastChecker] Total: {total_new} new episodes found")
            
        except asyncio.CancelledError:
            logger.info("[PodcastChecker] Background checker stopped")
            break
        except Exception as e:
            logger.error(f"[PodcastChecker] Error in background checker: {e}")
            await asyncio.sleep(60)  # Wait before retry on error


@app.on_event("startup")
async def startup_event():
    """Capture the main event loop on startup for thread-safe broadcasting."""
    global _podcast_check_task
    from config import USE_SUPABASE, SUPABASE_JWT_SECRET
    
    loop = asyncio.get_running_loop()
    processing.set_main_loop(loop)
    print(f"[WS] Main event loop captured: {loop}")
    
    # Log auth configuration
    if USE_SUPABASE:
        from api.auth import _get_jwks_url, _get_cached_jwks
        jwks_url = _get_jwks_url()
        logger.info(f"[Auth] Supabase mode enabled")
        logger.info(f"[Auth] JWKS URL: {jwks_url}")
        if SUPABASE_JWT_SECRET:
            logger.info(f"[Auth] Legacy JWT secret: configured (length={len(SUPABASE_JWT_SECRET)})")
        else:
            logger.info("[Auth] Legacy JWT secret: not configured")
        # Pre-fetch JWKS for faster first request
        logger.info("[Auth] Pre-fetching JWKS keys...")
        jwks = _get_cached_jwks()
        if jwks:
            logger.info(f"[Auth] JWKS keys cached ({len(jwks.get('keys', []))} keys)")
        else:
            logger.warning("[Auth] Failed to pre-fetch JWKS - will retry on first auth request")
    else:
        logger.info("[Auth] Local mode: No authentication required")
    
    # Start background podcast checker
    _podcast_check_task = asyncio.create_task(check_podcasts_for_updates())
    
    # Send Discord notification on startup
    from logger import notify_discord
    import os
    
    # Get environment info
    env = os.environ.get("RENDER", "local")
    if env:
        env_name = "Render (Production)"
    else:
        env_name = "Local Development"
    
    notify_discord(
        title="API Started",
        message=f"Podcast Transcript API is now running",
        event_type="startup",
        fields=[
            {"name": "Environment", "value": env_name, "inline": True},
            {"name": "Version", "value": "1.0.0", "inline": True},
        ]
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    global _podcast_check_task
    
    # Cancel background podcast checker
    if _podcast_check_task:
        _podcast_check_task.cancel()
        try:
            await _podcast_check_task
        except asyncio.CancelledError:
            pass
    
    # Shutdown the processing thread pool executors
    processing.PROCESSING_EXECUTOR.shutdown(wait=False, cancel_futures=True)
    video_notes.VIDEO_EXECUTOR.shutdown(wait=False, cancel_futures=True)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(podcasts.router, prefix="/api/podcasts", tags=["Podcasts"])
app.include_router(episodes.router, prefix="/api/episodes", tags=["Episodes"])
app.include_router(transcripts.router, prefix="/api/transcripts", tags=["Transcripts"])
app.include_router(summaries.router, prefix="/api/summaries", tags=["Summaries"])
app.include_router(processing.router, prefix="/api", tags=["Processing"])
app.include_router(video_notes.router, prefix="/api/video-notes", tags=["Video Notes"])
app.include_router(cookies.router, prefix="/api/cookies", tags=["Cookies"])

# Mount static files for data — use the same DATA_DIR that the rest of the app uses
from config import DATA_DIR as _data_dir
_data_dir.mkdir(parents=True, exist_ok=True)
(_data_dir / "screenshots").mkdir(parents=True, exist_ok=True)
(_data_dir / "uploads").mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(_data_dir)), name="data")

# Check for pre-built frontend
frontend_dist = Path(__file__).parent.parent / "web" / "dist"
if frontend_dist.exists():
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")


@app.get("/api/health")
@app.head("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.head("/")
@app.head("/{path:path}")
async def head_request(path: str = ""):
    """Handle HEAD requests for health checks and load balancers."""
    from fastapi.responses import Response
    return Response(status_code=200)


@app.get("/api/new-episodes")
async def get_new_episodes(user: Optional[User] = Depends(get_current_user)):
    """Get recently discovered new episodes from subscribed podcasts (user-scoped)."""
    user_id = user.id if user else "_anonymous"
    user_cache = _new_episodes_cache.get(user_id, {})
    return {
        "episodes": user_cache.get("episodes", []),
        "last_check": user_cache.get("last_check"),
    }


@app.post("/api/check-podcasts")
async def trigger_podcast_check(user: Optional[User] = Depends(get_current_user)):
    """Manually trigger a podcast update check."""
    from xyz_client import get_client
    from api.db import get_db
    
    db = get_db(user.id if user else None)
    all_podcasts = db.get_all_podcasts()
    
    if not all_podcasts:
        return {"message": "No podcasts subscribed", "new_episodes": 0}
    
    client = get_client()
    total_new = 0
    new_episodes_list = []
    
    for podcast in all_podcasts:
        try:
            episodes = client.get_episodes_from_page(podcast.pid, limit=10)
            
            for ep in episodes:
                if not db.episode_exists(ep.eid):
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
                    total_new += 1
                    new_episodes_list.append({
                        "eid": ep.eid,
                        "title": ep.title,
                        "podcast_title": podcast.title,
                        "podcast_pid": podcast.pid,
                    })
            
            db.update_podcast_checked(podcast.pid)
            
        except Exception as e:
            logger.warning(f"Error checking '{podcast.title}': {e}")
    
    # Update user-specific cache
    user_id = user.id if user else "_anonymous"
    if new_episodes_list:
        _new_episodes_cache[user_id] = {
            "episodes": new_episodes_list[:20],
            "last_check": datetime.now().isoformat(),
        }
    
    return {
        "message": f"Found {total_new} new episode(s)",
        "new_episodes": total_new,
        "episodes": new_episodes_list[:10],
    }


@app.get("/api/image-proxy")
async def image_proxy(url: str):
    """Proxy images to avoid CORS issues."""
    import httpx
    from fastapi.responses import Response
    
    # Validate URL is an image from known domains
    allowed_domains = [
        "image.xyzcdn.net",
        "jike.ruguoapp.com",
        "piccdn.igetget.com",
    ]
    
    from urllib.parse import urlparse
    parsed = urlparse(url)
    
    if not any(domain in parsed.netloc for domain in allowed_domains):
        return Response(status_code=403, content="Domain not allowed")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "image/jpeg")
                return Response(
                    content=resp.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"}  # Cache for 1 day
                )
            return Response(status_code=resp.status_code)
    except Exception:
        return Response(status_code=502)


@app.get("/api/stats")
async def get_stats(user: Optional["User"] = Depends(get_current_user)):
    """Get dashboard statistics."""
    from api.db import get_db
    
    db = get_db(user.id if user else None)
    stats = db.get_stats()
    
    return {
        "total_podcasts": stats["podcasts"],
        "total_episodes": stats["episodes"],
        "total_transcripts": stats["transcripts"],
        "total_summaries": stats["summaries"],
        "processing_queue": 0,
    }


@app.get("/api/settings")
async def get_settings():
    """Get current settings."""
    from config import (
        WHISPER_MODE, WHISPER_BACKEND,
        WHISPER_DEVICE, CHECK_INTERVAL, get_runtime_settings
    )
    
    runtime = get_runtime_settings()
    
    return {
        "whisper_mode": WHISPER_MODE,
        "whisper_model": runtime.get("whisper_model", "whisper-large-v3-turbo"),
        "whisper_backend": WHISPER_BACKEND,
        "whisper_device": WHISPER_DEVICE,
        "llm_model": runtime.get("llm_model", "openrouter/openai/gpt-4o"),
        "check_interval": CHECK_INTERVAL,
    }


@app.post("/api/settings")
async def update_settings(settings: dict):
    """Update runtime settings."""
    from config import set_runtime_settings
    
    allowed_keys = {"whisper_model", "llm_model"}
    filtered = {k: v for k, v in settings.items() if k in allowed_keys}
    
    set_runtime_settings(filtered)
    
    return {"message": "Settings updated successfully"}


# Serve React frontend for all non-API routes (must be last)
@app.get("/{path:path}")
async def serve_frontend(path: str):
    """Serve React frontend for client-side routing."""
    # Serve files from the data directory (screenshots, uploads, etc.)
    if path.startswith("data/"):
        data_file = _data_dir / path[len("data/"):]
        if data_file.exists() and data_file.is_file():
            return FileResponse(data_file)

    frontend_dist = Path(__file__).parent.parent / "web" / "dist"
    
    if not frontend_dist.exists():
        return {"error": "Frontend not built. Run 'cd web && npm run build'"}
    
    # Check if requesting a static file
    file_path = frontend_dist / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    
    # Otherwise serve index.html for client-side routing
    index_path = frontend_dist / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return {"error": "Frontend not found"}
