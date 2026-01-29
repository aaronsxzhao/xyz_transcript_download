"""FastAPI application for Podcast Transcript Tool."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routers import podcasts, episodes, transcripts, summaries, processing
from api.routers import auth_router
from api.auth import get_current_user, User

# Create FastAPI app
app = FastAPI(
    title="Podcast Transcript API",
    description="API for managing podcast transcripts and summaries",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    """Capture the main event loop on startup for thread-safe broadcasting."""
    loop = asyncio.get_running_loop()
    processing.set_main_loop(loop)


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    # Shutdown the processing thread pool executor
    processing.PROCESSING_EXECUTOR.shutdown(wait=False, cancel_futures=True)

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

# Mount static files for data
data_dir = Path(__file__).parent.parent / "data"
if data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")

# Check for pre-built frontend
frontend_dist = Path(__file__).parent.parent / "web" / "dist"
if frontend_dist.exists():
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


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
        WHISPER_MODE, WHISPER_LOCAL_MODEL, WHISPER_BACKEND,
        WHISPER_DEVICE, LLM_MODEL, CHECK_INTERVAL
    )
    
    return {
        "whisper_mode": WHISPER_MODE,
        "whisper_model": WHISPER_LOCAL_MODEL,
        "whisper_backend": WHISPER_BACKEND,
        "whisper_device": WHISPER_DEVICE,
        "llm_model": LLM_MODEL,
        "check_interval": CHECK_INTERVAL,
    }


# Serve React frontend for all non-API routes (must be last)
@app.get("/{path:path}")
async def serve_frontend(path: str):
    """Serve React frontend for client-side routing."""
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
