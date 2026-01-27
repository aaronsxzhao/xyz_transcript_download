"""FastAPI application for Podcast Transcript Tool."""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import podcasts, episodes, transcripts, summaries, processing

# Create FastAPI app
app = FastAPI(
    title="Podcast Transcript API",
    description="API for managing podcast transcripts and summaries",
    version="1.0.0",
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(podcasts.router, prefix="/api/podcasts", tags=["Podcasts"])
app.include_router(episodes.router, prefix="/api/episodes", tags=["Episodes"])
app.include_router(transcripts.router, prefix="/api/transcripts", tags=["Transcripts"])
app.include_router(summaries.router, prefix="/api/summaries", tags=["Summaries"])
app.include_router(processing.router, prefix="/api", tags=["Processing"])

# Mount static files for audio
data_dir = Path(__file__).parent.parent / "data"
if data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics."""
    from database import get_database
    from config import DATA_DIR
    
    db = get_database()
    
    # Count podcasts and episodes
    podcasts = db.get_all_podcasts()
    total_episodes = sum(
        len(db.get_episodes_by_podcast(p.pid)) for p in podcasts
    )
    
    # Count transcripts and summaries
    transcripts_dir = DATA_DIR / "transcripts"
    summaries_dir = DATA_DIR / "summaries"
    
    total_transcripts = len(list(transcripts_dir.glob("*.json"))) if transcripts_dir.exists() else 0
    total_summaries = len(list(summaries_dir.glob("*.json"))) if summaries_dir.exists() else 0
    
    return {
        "total_podcasts": len(podcasts),
        "total_episodes": total_episodes,
        "total_transcripts": total_transcripts,
        "total_summaries": total_summaries,
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
