"""Transcript endpoints."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from api.schemas import TranscriptResponse
from api.auth import get_current_user, User
from api.db import get_db

router = APIRouter()


@router.get("/{eid}", response_model=TranscriptResponse)
async def get_transcript(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get transcript for an episode."""
    db = get_db(user.id if user else None)
    
    transcript = db.get_transcript(eid)
    
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    return TranscriptResponse(
        episode_id=transcript.episode_id,
        language=transcript.language,
        duration=transcript.duration,
        text=transcript.text,
        segments=[
            {"start": s.get("start", 0), "end": s.get("end", 0), "text": s.get("text", "")}
            for s in transcript.segments
        ],
    )


@router.delete("/{eid}")
async def delete_transcript(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Delete transcript for an episode."""
    db = get_db(user.id if user else None)
    
    if not db.has_transcript(eid):
        raise HTTPException(status_code=404, detail="Transcript not found")
    
    db.delete_transcript(eid)
    
    return {"message": "Transcript deleted"}
