"""Summary endpoints."""
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse

from api.schemas import SummaryResponse, SummaryListItem
from api.auth import get_current_user, get_user_from_token_param, User
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
    
    # Debug logging
    for s in summaries[:3]:  # Log first 3
        print(f"[DEBUG] Summary {s.episode_id}: topics={len(s.topics)}, key_points={len(s.key_points)}")
        if s.key_points:
            print(f"[DEBUG]   First key point: {s.key_points[0].get('topic', 'N/A')[:50]}")
    
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
async def get_summary_html(
    eid: str,
    token: Optional[str] = Query(None, description="Auth token for browser access"),
    user: Optional[User] = Depends(get_user_from_token_param)
):
    """Get summary as HTML page. Accepts token via query param for browser tabs."""
    from viewer import Summary, KeyPoint, export_html
    
    db = get_db(user.id if user else None)
    summary_data = await run_sync(db.get_summary, eid)
    
    if not summary_data:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    # Convert database format to viewer format
    key_points = [
        KeyPoint(
            topic=kp.get("topic", ""),
            summary=kp.get("summary", ""),
            original_quote=kp.get("original_quote", ""),
            timestamp=kp.get("timestamp", ""),
        )
        for kp in summary_data.key_points
    ]
    
    summary = Summary(
        episode_id=summary_data.episode_id,
        title=summary_data.title,
        overview=summary_data.overview,
        key_points=key_points,
        topics=summary_data.topics,
        takeaways=summary_data.takeaways,
    )
    
    html_content = await run_sync(export_html, summary)
    
    return HTMLResponse(content=html_content)


@router.get("/{eid}/markdown")
async def get_summary_markdown(
    eid: str,
    token: Optional[str] = Query(None, description="Auth token for browser access"),
    user: Optional[User] = Depends(get_user_from_token_param)
):
    """Get summary as Markdown. Accepts token via query param for browser tabs."""
    from viewer import Summary, KeyPoint, export_markdown
    
    db = get_db(user.id if user else None)
    summary_data = await run_sync(db.get_summary, eid)
    
    if not summary_data:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    # Convert database format to viewer format
    key_points = [
        KeyPoint(
            topic=kp.get("topic", ""),
            summary=kp.get("summary", ""),
            original_quote=kp.get("original_quote", ""),
            timestamp=kp.get("timestamp", ""),
        )
        for kp in summary_data.key_points
    ]
    
    summary = Summary(
        episode_id=summary_data.episode_id,
        title=summary_data.title,
        overview=summary_data.overview,
        key_points=key_points,
        topics=summary_data.topics,
        takeaways=summary_data.takeaways,
    )
    
    md_content = await run_sync(export_markdown, summary)
    
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


@router.get("/debug/raw")
async def debug_raw_summaries(user: Optional[User] = Depends(get_current_user)):
    """Debug endpoint to see raw summary data with key point counts."""
    db = get_db(user.id if user else None)
    
    summaries = await run_sync(db.get_all_summaries)
    
    return {
        "count": len(summaries),
        "summaries": [
            {
                "episode_id": s.episode_id,
                "title": s.title[:50] if s.title else "",
                "topics_count": len(s.topics),
                "topics": s.topics[:3] if s.topics else [],
                "key_points_count": len(s.key_points),
                "key_points_sample": [
                    {"topic": kp.get("topic", "")[:30]} 
                    for kp in (s.key_points[:3] if s.key_points else [])
                ],
            }
            for s in summaries[:10]  # Limit to first 10
        ]
    }
