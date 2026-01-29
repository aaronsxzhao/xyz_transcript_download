"""Summary endpoints."""
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse

from api.schemas import SummaryResponse, SummaryListItem
from api.auth import get_current_user, User
from api.db import get_db

router = APIRouter()


async def run_sync(func, *args):
    """Run a synchronous function in executor to avoid blocking event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


@router.get("", response_model=List[SummaryListItem])
async def list_summaries(user: Optional[User] = Depends(get_current_user)):
    """List all available summaries."""
    db = get_db(user.id if user else None)
    
    summaries = await run_sync(db.get_all_summaries)
    
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
    
    summary = await run_sync(db.get_summary, eid)
    
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
    
    def generate_html():
        summary = load_summary(eid)
        if not summary:
            return None
        return export_html(summary)
    
    html_content = await run_sync(generate_html)
    
    if not html_content:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    return HTMLResponse(content=html_content)


@router.get("/{eid}/markdown")
async def get_summary_markdown(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get summary as Markdown."""
    from viewer import load_summary, export_markdown
    
    def generate_markdown():
        summary = load_summary(eid)
        if not summary:
            return None
        return export_markdown(summary)
    
    md_content = await run_sync(generate_markdown)
    
    if not md_content:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    return {"markdown": md_content}


@router.delete("/{eid}")
async def delete_summary(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Delete summary for an episode."""
    db = get_db(user.id if user else None)
    
    has_summary = await run_sync(db.has_summary, eid)
    if not has_summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    await run_sync(db.delete_summary, eid)
    
    return {"message": "Summary deleted"}
