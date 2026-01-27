"""Transcript endpoints."""
import json
from fastapi import APIRouter, HTTPException

from api.schemas import TranscriptResponse

router = APIRouter()


@router.get("/{eid}", response_model=TranscriptResponse)
async def get_transcript(eid: str):
    """Get transcript for an episode."""
    from config import DATA_DIR
    
    transcript_path = DATA_DIR / "transcripts" / f"{eid}.json"
    
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return TranscriptResponse(
        episode_id=data.get("episode_id", eid),
        language=data.get("language", "zh"),
        duration=data.get("duration", 0),
        text=data.get("text", ""),
        segments=[
            {"start": s.get("start", 0), "end": s.get("end", 0), "text": s.get("text", "")}
            for s in data.get("segments", [])
        ],
    )


@router.delete("/{eid}")
async def delete_transcript(eid: str):
    """Delete transcript for an episode."""
    from config import DATA_DIR
    
    transcript_path = DATA_DIR / "transcripts" / f"{eid}.json"
    
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    transcript_path.unlink()
    
    return {"message": "Transcript deleted"}
