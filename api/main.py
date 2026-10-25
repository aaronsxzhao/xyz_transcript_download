"""FastAPI application for Podcast Transcript Tool."""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.responses import JSONResponse
import httpx
from api.request_timing import RequestTimingMiddleware

from api.routers import podcasts, episodes, transcripts, summaries, processing
from api.routers import auth_router, video_notes, cookies, notion
from api.routers import performance, maintenance, library, bilibili_favorites
from api.auth import get_current_user, require_debug_access, User
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
_generated_media_cleanup_task: Optional[asyncio.Task] = None
# User-scoped cache: {user_id: {"episodes": [...], "last_check": ...}}
_new_episodes_cache: dict = {}
_NEW_EPISODES_CACHE_MAX_KEYS = 128


def _prune_new_episodes_cache() -> None:
    """Drop oldest entries when the in-memory cache grows too large."""
    global _new_episodes_cache
    if len(_new_episodes_cache) <= _NEW_EPISODES_CACHE_MAX_KEYS:
        return
    ranked = sorted(
        _new_episodes_cache.items(),
        key=lambda kv: kv[1].get("last_check") or "",
    )
    overflow = len(_new_episodes_cache) - _NEW_EPISODES_CACHE_MAX_KEYS + 1
    for key, _ in ranked[:overflow]:
        del _new_episodes_cache[key]


def _store_new_episodes_cache(user_id: str, episodes: list) -> None:
    _new_episodes_cache[user_id] = {
        "episodes": episodes[:20],
        "last_check": datetime.now().isoformat(),
    }
    _prune_new_episodes_cache()


async def _scan_podcasts_for_new_episodes(db, inter_podcast_delay: Optional[float] = None) -> tuple[int, list]:
    """
    Fetch latest episodes for all podcasts in db, persist new ones, return counts and list for UI cache.
    """
    from xyz_client import get_client

    all_podcasts = await asyncio.to_thread(db.get_all_podcasts)
    if not all_podcasts:
        return 0, []

    total_new = 0
    new_episodes_list = []

    for podcast in all_podcasts:
        try:
            platform = getattr(podcast, "platform", "xiaoyuzhou")
            if platform == "local":
                continue
            if platform in ("apple", "spotify"):
                from apple_podcasts_client import get_episodes_from_feed
                if not podcast.feed_url:
                    continue
                episodes = await asyncio.to_thread(get_episodes_from_feed, podcast.feed_url, podcast.pid, 50)
            elif platform == 'xiaoyuzhou':
                episodes = await asyncio.to_thread(get_client().get_episodes_from_page, podcast.pid, limit=50)
            else:
                continue

            new_count = 0
            for ep in episodes:
                if not await asyncio.to_thread(db.episode_exists, ep.eid):
                    await asyncio.to_thread(db.add_episode,
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

            await asyncio.to_thread(db.update_podcast_checked, podcast.pid)

        except Exception as e:
            logger.warning(f"[PodcastChecker] Error checking '{podcast.title}': {e}")

        if inter_podcast_delay is not None:
            await asyncio.sleep(inter_podcast_delay)

    return total_new, new_episodes_list


async def check_podcasts_for_updates():
    """Background task that periodically checks podcasts for new episodes."""
    from config import CHECK_INTERVAL
    from api.db import get_db

    check_interval = max(CHECK_INTERVAL, 600)  # At least 10 minutes

    logger.info(f"[PodcastChecker] Started background podcast checker (interval: {check_interval}s)")

    while True:
        try:
            await asyncio.sleep(check_interval)

            logger.info("[PodcastChecker] Checking podcasts for updates...")

            await check_subscription_owners()

        except asyncio.CancelledError:
            logger.info("[PodcastChecker] Background checker stopped")
            break
        except Exception as e:
            logger.error(f"[PodcastChecker] Error in background checker: {e}")
            await asyncio.sleep(60)  # Wait before retry on error


async def check_subscription_owners():
    from config import USE_SUPABASE
    from api.db import get_db
    if USE_SUPABASE:
        from api.supabase_db import get_supabase_database
        owners = await asyncio.to_thread(get_supabase_database().get_subscription_user_ids)
    else:
        owners = ["local"]
    for owner in owners:
        try:
            _, episodes = await _scan_podcasts_for_new_episodes(get_db(owner), inter_podcast_delay=2.0)
            _store_new_episodes_cache(owner, episodes)
        except Exception:
            logger.exception("[PodcastChecker] Could not update subscriptions for an account")


async def cleanup_generated_media_loop():
    """Background task that periodically deletes expired screenshots/thumbnails."""
    from config import GENERATED_MEDIA_CLEANUP_INTERVAL_HOURS, GENERATED_MEDIA_RETENTION_DAYS
    from screenshot_extractor import cleanup_expired_assets

    if GENERATED_MEDIA_RETENTION_DAYS <= 0:
        logger.info("[MediaCleanup] Disabled (GENERATED_MEDIA_RETENTION_DAYS <= 0)")
        return

    interval_seconds = max(GENERATED_MEDIA_CLEANUP_INTERVAL_HOURS, 1) * 3600
    logger.info(
        "[MediaCleanup] Started generated media cleanup "
        f"(retention={GENERATED_MEDIA_RETENTION_DAYS}d, interval={GENERATED_MEDIA_CLEANUP_INTERVAL_HOURS}h)"
    )

    while True:
        try:
            stats = await asyncio.to_thread(cleanup_expired_assets, GENERATED_MEDIA_RETENTION_DAYS)
            deleted_total = int(stats.get("local_deleted", 0)) + int(stats.get("remote_deleted", 0))
            if deleted_total or stats.get("remote_skipped_unknown_age"):
                logger.info(
                    "[MediaCleanup] Completed cleanup: "
                    f"local_deleted={stats.get('local_deleted', 0)}, "
                    f"remote_deleted={stats.get('remote_deleted', 0)}, "
                    f"remote_skipped_unknown_age={stats.get('remote_skipped_unknown_age', 0)}"
                )
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[MediaCleanup] Background cleanup stopped")
            break
        except Exception as e:
            logger.error(f"[MediaCleanup] Error during cleanup: {e}")
            await asyncio.sleep(300)


@app.on_event("startup")
async def startup_event():
    """Capture the main event loop on startup for thread-safe broadcasting."""
    global _podcast_check_task, _generated_media_cleanup_task
    from config import USE_SUPABASE, SUPABASE_JWT_SECRET
    
    loop = asyncio.get_running_loop()
    processing.set_main_loop(loop)
    from api.job_persistence import restore_jobs, reconcile_video_jobs, save_job
    from api.schemas import ProcessingStatus
    for saved in await asyncio.to_thread(restore_jobs):
        job = ProcessingStatus(**saved)
        if job.status not in {'completed', 'failed', 'cancelled'}:
            job.status = 'failed'
            job.advance_revision()
            job.message = 'Interrupted by server restart. Retry to continue from saved data.'
            await asyncio.to_thread(save_job, job)
        processing.jobs[job.job_id] = job
    await asyncio.to_thread(reconcile_video_jobs)
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
        jwks = await asyncio.to_thread(_get_cached_jwks)
        if jwks:
            logger.info(f"[Auth] JWKS keys cached ({len(jwks.get('keys', []))} keys)")
        else:
            logger.warning("[Auth] Failed to pre-fetch JWKS - will retry on first auth request")
    else:
        logger.info("[Auth] Local mode: No authentication required")
    
    # Start background podcast checker
    _podcast_check_task = asyncio.create_task(check_podcasts_for_updates())
    _generated_media_cleanup_task = asyncio.create_task(cleanup_generated_media_loop())
    from api.media import backfill_previews
    app.state.preview_task = asyncio.create_task(backfill_previews())
    from api.covers import backfill_covers
    app.state.cover_task = asyncio.create_task(backfill_covers())
    
    # Send Discord notification on startup
    from logger import notify_discord
    import os
    
    # RENDER is set by Render.com when deployed; unset means local/other host
    env_name = "Render (Production)" if os.environ.get("RENDER") else "Local Development"
    
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
    global _podcast_check_task, _generated_media_cleanup_task
    
    # Cancel background podcast checker
    if _podcast_check_task:
        _podcast_check_task.cancel()
        try:
            await _podcast_check_task
        except asyncio.CancelledError:
            pass

    if _generated_media_cleanup_task:
        _generated_media_cleanup_task.cancel()
        try:
            await _generated_media_cleanup_task
        except asyncio.CancelledError:
            pass
    
    preview_task = getattr(app.state, 'preview_task', None)
    if preview_task:
        preview_task.cancel()
        try:
            await preview_task
        except asyncio.CancelledError:
            pass

    cover_task = getattr(app.state, 'cover_task', None)
    if cover_task:
        cover_task.cancel()
        try: await cover_task
        except asyncio.CancelledError: pass

    # Shutdown the processing thread pool executors
    processing.PROCESSING_EXECUTOR.shutdown(wait=False, cancel_futures=True)
    video_notes.VIDEO_EXECUTOR.shutdown(wait=False, cancel_futures=True)

# CORS: explicit origins required when credentials are allowed (see CORS_ALLOWED_ORIGINS in config)
from config import CORS_ALLOWED_ORIGINS as _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(RequestTimingMiddleware)


@app.exception_handler(httpx.TransportError)
async def upstream_connection_error(request, error):
    logger.warning('Upstream connection unavailable (%s)', type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "The server connection was interrupted. Please retry."},
                        headers={"Retry-After": "1"})

# Include routers
from api.content_updates import router as content_updates_router
app.include_router(content_updates_router, prefix="/api/content-updates", tags=["Content updates"])
app.include_router(auth_router.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(podcasts.router, prefix="/api/podcasts", tags=["Podcasts"])
app.include_router(episodes.router, prefix="/api/episodes", tags=["Episodes"])
app.include_router(transcripts.router, prefix="/api/transcripts", tags=["Transcripts"])
app.include_router(summaries.router, prefix="/api/summaries", tags=["Summaries"])
app.include_router(processing.router, prefix="/api", tags=["Processing"])
app.include_router(video_notes.router, prefix="/api/video-notes", tags=["Video Notes"])
app.include_router(bilibili_favorites.router, prefix="/api/bilibili-favorites", tags=["Bilibili favorites"])
app.include_router(cookies.router, prefix="/api/cookies", tags=["Cookies"])
app.include_router(notion.router, prefix="/api/notion", tags=["Notion"])
app.include_router(library.router, prefix="/api/library", tags=["Library"])
app.include_router(performance.router, prefix="/api/performance", tags=["Performance"])
app.include_router(maintenance.router, prefix="/api/maintenance", tags=["Data recovery"])

# Private data is never exposed by a StaticFiles mount.
from config import DATA_DIR as _data_dir
_data_dir.mkdir(parents=True, exist_ok=True)
(_data_dir / "screenshots").mkdir(parents=True, exist_ok=True)
(_data_dir / "thumbnails").mkdir(parents=True, exist_ok=True)
(_data_dir / "uploads").mkdir(parents=True, exist_ok=True)


@app.get("/data/{folder}/{filename}")
async def generated_media(folder: str, filename: str, expires: int = Query(0), signature: str = Query(""), preview: bool = Query(False)):
    from config import USE_SUPABASE
    from api.media import media_file, verify_media_signature, load_cloud_media, load_preview
    path = media_file(folder, filename)
    if USE_SUPABASE and not verify_media_signature(f"/data/{folder}/{filename}", expires, signature):
        raise HTTPException(status_code=403, detail="Media link is invalid or expired")
    headers = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"}
    if path.is_file():
        if preview:
            return Response(await load_preview(folder, filename), media_type='image/webp', headers=headers)
        return FileResponse(path, headers=headers)
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        client = get_supabase_admin_client()
        if client:
            try:
                if preview:
                    return Response(await load_preview(folder, filename, client.storage.from_(folder)), media_type='image/webp', headers=headers)
                content = await load_cloud_media(folder, filename, client.storage.from_(folder).download)
                media_type = "image/jpeg" if path.suffix in {".jpg", ".jpeg"} else f"image/{path.suffix[1:]}"
                return Response(content, media_type=media_type, headers=headers)
            except Exception as error:
                missing = str(getattr(error, 'status', '')) == '404' or getattr(error, 'code', '') in {'NoSuchKey', 'NotFound', 'not_found'}
                if not missing:
                    raise HTTPException(status_code=503, detail="Image storage temporarily unavailable", headers={"Cache-Control":"private, no-store"})
        else:
            raise HTTPException(status_code=503, detail="Image storage temporarily unavailable", headers={"Cache-Control":"private, no-store"})
    raise HTTPException(status_code=404, detail="File not found", headers={"Cache-Control": "private, no-store"})

# Check for pre-built frontend
frontend_dist = Path(__file__).parent.parent / "web" / "dist"
if frontend_dist.exists():
    # Mount static assets
    from api.static_assets import VersionedStaticFiles

    app.mount("/assets", VersionedStaticFiles(directory=str(frontend_dist / "assets")), name="assets")


@app.get("/api/health")
@app.head("/api/health")
async def health_check(response: Response):
    """Health check endpoint."""
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok", "revision": os.getenv("APP_REVISION", "unknown")}


@app.get("/api/debug/screenshots")
def debug_screenshots(_: None = Depends(require_debug_access)):
    """Debug: list screenshot directory contents and config."""
    import os
    screenshots_dir = _data_dir / "screenshots"
    files = []
    if screenshots_dir.exists():
        for f in sorted(screenshots_dir.iterdir()):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
    return {
        "data_dir": str(_data_dir),
        "screenshots_dir": str(screenshots_dir),
        "screenshots_dir_exists": screenshots_dir.exists(),
        "file_count": len(files),
        "files": files[:50],
        "cwd": os.getcwd(),
        "data_dir_contents": [p.name for p in _data_dir.iterdir()] if _data_dir.exists() else [],
    }


@app.get("/api/debug/youtube-test")
def debug_youtube_test(_: None = Depends(require_debug_access)):
    """Debug: test YouTube download capability (JS challenge solver + node)."""
    import shutil
    import subprocess
    result: dict = {}

    node_path = shutil.which("node")
    result["node_available"] = node_path is not None
    result["node_path"] = node_path
    if node_path:
        try:
            ver = subprocess.run([node_path, "--version"], capture_output=True, text=True, timeout=5)
            result["node_version"] = ver.stdout.strip()
        except Exception as e:
            result["node_version_error"] = str(e)

    try:
        import yt_dlp
        result["ytdlp_version"] = yt_dlp.version.__version__
    except Exception as e:
        result["ytdlp_error"] = str(e)

    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    try:
        import yt_dlp
        opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": False,
            "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
            "remote_components": {"ejs:github"},
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
        if info:
            result["test_status"] = "SUCCESS"
            result["test_title"] = info.get("title", "")
            result["test_duration"] = info.get("duration", 0)
        else:
            result["test_status"] = "FAILED"
            result["test_detail"] = "extract_info returned None"
    except Exception as e:
        result["test_status"] = "ERROR"
        result["test_detail"] = f"{type(e).__name__}: {str(e)[:500]}"

    from cookie_manager import get_cookie_manager
    mgr = get_cookie_manager()
    yt_cookie = mgr.get_cookie("youtube")
    result["youtube_cookie_saved"] = bool(yt_cookie)
    result["youtube_cookie_length"] = len(yt_cookie) if yt_cookie else 0
    if yt_cookie:
        lines = yt_cookie.strip().split("\n")
        cookie_names = [l.split("\t")[-2] for l in lines if "\t" in l and not l.startswith("#")]
        result["youtube_cookie_keys"] = cookie_names[:20]
        critical_keys = {"SID", "SSID", "HSID", "APISID", "SAPISID", "LOGIN_INFO"}
        result["has_critical_auth_cookies"] = bool(critical_keys & set(cookie_names))

    return result


@app.get("/api/debug/logs")
def debug_logs(
    _: None = Depends(require_debug_access),
    lines: int = 200,
    level: str = "",
):
    """Return recent application log lines for remote debugging."""
    from config import DATA_DIR
    logs_dir = DATA_DIR / "logs"
    if not logs_dir.exists():
        return {"error": "No logs directory", "lines": []}

    log_files = sorted(logs_dir.glob("xyz_*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not log_files:
        return {"error": "No log files found", "files": [f.name for f in logs_dir.iterdir()], "lines": []}

    latest = log_files[0]
    try:
        all_lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return {"error": str(e), "lines": []}

    if level:
        level_upper = level.upper()
        all_lines = [l for l in all_lines if level_upper in l]

    tail = all_lines[-lines:]
    return {
        "file": latest.name,
        "total_lines": len(all_lines),
        "showing": len(tail),
        "lines": tail,
    }


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
    from api.db import get_db

    db = get_db(user.id if user else None)
    all_podcasts = await asyncio.to_thread(db.get_all_podcasts)

    if not all_podcasts:
        return {"message": "No podcasts subscribed", "new_episodes": 0}

    total_new, new_episodes_list = await _scan_podcasts_for_new_episodes(db, inter_podcast_delay=None)

    user_id = user.id if user else "_anonymous"
    _store_new_episodes_cache(user_id, new_episodes_list)
    
    return {
        "message": f"Found {total_new} new episode(s)",
        "new_episodes": total_new,
        "episodes": new_episodes_list[:10],
    }


@app.get("/api/image-proxy")
async def image_proxy(request: Request, url: str):
    """Serve a persistent WebP cover, with a browser cache validator."""
    from api.covers import load_cover
    from fastapi.responses import Response
    import hashlib
    try:
        content, source = await load_cover(url)
    except HTTPException as error:
        return Response(status_code=error.status_code, headers={'Cache-Control':'no-store', 'Retry-After':'3', **(error.headers or {})})
    etag = '"' + hashlib.sha256(content).hexdigest()[:24] + '"'
    headers = {'Cache-Control':'public, max-age=604800, stale-while-revalidate=2592000',
               'ETag':etag, 'X-Artwork-Cache':source, 'X-Content-Type-Options':'nosniff'}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=content, media_type='image/webp', headers=headers)


@app.get("/api/stats")
def get_stats(user: Optional["User"] = Depends(get_current_user)):
    """Get dashboard statistics."""
    from api.db import get_db
    from video_task_db import get_video_task_db
    from concurrent.futures import ThreadPoolExecutor

    db = get_db(user.id if user else None)
    video_db = get_video_task_db()
    user_id = user.id if user else None
    with ThreadPoolExecutor(max_workers=3) as pool:
        stats_job = pool.submit(db.get_stats)
        videos_job = pool.submit(video_db.count_tasks, user_id)
        channels_job = pool.submit(video_db.count_distinct_channels, user_id)
        stats, vcounts, channel_count = stats_job.result(), videos_job.result(), channels_job.result()

    return {
        "total_podcasts": stats["podcasts"],
        "total_episodes": stats["episodes"],
        "total_transcripts": stats["transcripts"],
        "total_summaries": stats["summaries"],
        "processing_queue": 0,
        "total_videos": vcounts["total"],
        "completed_videos": vcounts["completed"],
        "total_video_channels": channel_count,
    }


@app.get("/api/settings")
async def get_settings(user: User = Depends(get_current_user)):
    """Get current settings."""
    from api.user_settings import get_user_settings
    try:
        runtime = await asyncio.to_thread(get_user_settings, user.id)
    except Exception:
        raise HTTPException(status_code=503, detail="Account settings unavailable. Check the user settings database migration.")
    
    return _public_settings(runtime)


def _public_settings(runtime: dict) -> dict:
    from config import WHISPER_MODE, WHISPER_BACKEND, WHISPER_DEVICE, WHISPER_API_PROVIDER, CHECK_INTERVAL
    from api.llm_settings import provider_status
    return {
        **provider_status(runtime),
        "whisper_mode": WHISPER_MODE,
        "whisper_model": runtime.get("whisper_model", "whisper-large-v3-turbo"),
        "whisper_backend": WHISPER_BACKEND,
        "whisper_device": WHISPER_DEVICE,
        "whisper_provider": WHISPER_API_PROVIDER,
        "llm_model": runtime.get("llm_model", "openrouter/openai/gpt-4o"),
        "transcription_provider": runtime.get("transcription_provider", "server"),
        "llm_base_url": runtime.get("llm_base_url", ""),
        "whisper_base_url": runtime.get("whisper_base_url", ""),
        "llm_key_saved": bool(runtime.get("llm_api_key")),
        "whisper_key_saved": bool(runtime.get("whisper_api_key")),
        "llm_key_error": runtime.get("llm_api_key_error", ""),
        "whisper_key_error": runtime.get("whisper_api_key_error", ""),
        "check_interval": CHECK_INTERVAL,
    }


@app.post("/api/settings")
async def update_settings(settings: dict, user: User = Depends(get_current_user)):
    """Update this account's model preferences."""
    from api.model_settings import update_user_settings
    from api.custom_models import ModelConfigurationError
    try:
        persisted = await asyncio.to_thread(update_user_settings, user.id, settings)
    except ModelConfigurationError as error:
        raise HTTPException(422, detail=str(error))
    except Exception:
        raise HTTPException(status_code=503, detail="Could not save account settings. Check the user settings database migration.")
    
    return {"message": "Settings updated successfully", "settings": _public_settings(persisted)}


@app.post("/api/settings/test-llm")
def test_llm_connection(settings: dict, user: User = Depends(get_current_user)):
    """Verify the selected summary provider without processing private content."""
    from api.llm_settings import test_summary_connection, safe_provider_error
    from api.user_settings import get_user_settings
    from api.model_settings import prepared_settings
    from api.custom_models import ModelConfigurationError, public_model_error
    try:
        preferences, _ = prepared_settings(user.id, settings)
        return test_summary_connection(preferences)
    except ModelConfigurationError as error:
        raise HTTPException(422, detail=str(error))
    except Exception as error:
        detail = public_model_error(error, "summary JSON output") if settings.get("llm_provider") == "custom" else safe_provider_error(error)
        raise HTTPException(status_code=502, detail=detail)


from api.model_settings import router as model_settings_router
app.include_router(model_settings_router, prefix="/api/settings", tags=["settings"])


# Serve React frontend for all non-API routes (must be last)
@app.get("/{path:path}")
def serve_frontend(path: str, request: Request):
    """Serve React frontend for client-side routing."""
    if path.split("/", 1)[0] in {"api", "data"}:
        raise HTTPException(status_code=404, detail="Not found")
    frontend_dist = (Path(__file__).parent.parent / "web" / "dist").resolve()
    
    if not frontend_dist.exists():
        return {"error": "Frontend not built. Run 'cd web && npm run build'"}
    
    # Check if requesting a static file
    file_path = (frontend_dist / path).resolve()
    if not file_path.is_relative_to(frontend_dist):
        raise HTTPException(status_code=404, detail="Not found")
    if path != "index.html" and file_path.exists() and file_path.is_file():
        cache_control = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-store" if path == 'sw.js' else "no-cache"
        return FileResponse(file_path, headers={"Cache-Control": cache_control})
    
    # Otherwise serve index.html for client-side routing
    index_path = frontend_dist / "index.html"
    if index_path.exists():
        from api.frontend import frontend_html
        from config import USE_SUPABASE, SUPABASE_URL
        import hashlib
        html = frontend_html(frontend_dist, path, USE_SUPABASE, SUPABASE_URL)
        etag = '"' + hashlib.sha256(html.encode()).hexdigest()[:24] + '"'
        headers = {"Cache-Control": "no-cache", "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(html, media_type="text/html", headers=headers)
    
    return {"error": "Frontend not found"}
