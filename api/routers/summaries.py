"""Summary endpoints."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse

from api.schemas import SummaryResponse, SummaryListItem
from api.auth import get_current_user, User
from api.db import get_db

router = APIRouter()


@router.get("", response_model=List[SummaryListItem])
async def list_summaries(user: Optional[User] = Depends(get_current_user)):
    """List all available summaries."""
    db = get_db(user.id if user else None)
    
    summaries = db.get_all_summaries()
    
    return [
        SummaryListItem(
            episode_id=s.episode_id,
            title=s.title,
            topics_count=len(s.topics),
            key_points_count=len(s.key_points),
        )
        for s in summaries
    ]


@router.get("/{eid}", response_model=SummaryResponse)
async def get_summary(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get summary for an episode."""
    db = get_db(user.id if user else None)
    
    summary = db.get_summary(eid)
    
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    return SummaryResponse(
        episode_id=summary.episode_id,
        title=summary.title,
        overview=summary.overview,
        key_points=summary.key_points,
        topics=summary.topics,
        takeaways=summary.takeaways,
    )


@router.get("/{eid}/html", response_class=HTMLResponse)
async def get_summary_html(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get summary as HTML page."""
    from viewer import load_summary, export_html
    
    summary = load_summary(eid)
    
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    html_content = export_html(summary)
    
    return HTMLResponse(content=html_content)


@router.get("/{eid}/markdown")
async def get_summary_markdown(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get summary as Markdown."""
    from viewer import load_summary, export_markdown
    
    summary = load_summary(eid)
    
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    md_content = export_markdown(summary)
    
    return {"markdown": md_content}


@router.delete("/{eid}")
async def delete_summary(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Delete summary for an episode."""
    db = get_db(user.id if user else None)
    
    if not db.has_summary(eid):
        raise HTTPException(status_code=404, detail="Summary not found")
    
    db.delete_summary(eid)
    
    return {"message": "Summary deleted"}
