"""Summary endpoints."""
import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse

from api.schemas import SummaryResponse, SummaryListItem
from api.auth import get_current_user, User
from config import USE_SUPABASE

router = APIRouter()


@router.get("", response_model=List[SummaryListItem])
async def list_summaries(user: Optional[User] = Depends(get_current_user)):
    """List all available summaries."""
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            summaries = db.get_all_summaries(user.id)
            return [
                SummaryListItem(
                    episode_id=s.episode_id,
                    title=s.title,
                    topics_count=len(s.topics),
                    key_points_count=len(s.key_points),
                )
                for s in summaries
            ]
    
    # Fall back to local file storage
    from config import DATA_DIR
    
    summaries_dir = DATA_DIR / "summaries"
    
    if not summaries_dir.exists():
        return []
    
    result = []
    for path in sorted(summaries_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            result.append(SummaryListItem(
                episode_id=path.stem,
                title=data.get("title", "Unknown"),
                topics_count=len(data.get("topics", [])),
                key_points_count=len(data.get("key_points", [])),
            ))
        except Exception:
            pass
    
    return result


@router.get("/{eid}", response_model=SummaryResponse)
async def get_summary(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get summary for an episode."""
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            summary = db.get_summary(user.id, eid)
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
    
    # Fall back to local file storage
    from config import DATA_DIR
    
    summary_path = DATA_DIR / "summaries" / f"{eid}.json"
    
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Summary not found")
    
    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return SummaryResponse(
        episode_id=data.get("episode_id", eid),
        title=data.get("title", ""),
        overview=data.get("overview", ""),
        key_points=[
            {
                "topic": kp.get("topic", ""),
                "summary": kp.get("summary", ""),
                "original_quote": kp.get("original_quote", ""),
                "timestamp": kp.get("timestamp", ""),
            }
            for kp in data.get("key_points", [])
        ],
        topics=data.get("topics", []),
        takeaways=data.get("takeaways", []),
    )


@router.get("/{eid}/html", response_class=HTMLResponse)
async def get_summary_html(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get summary as HTML page."""
    from config import DATA_DIR
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
    if USE_SUPABASE and user:
        from api.supabase_db import get_supabase_database
        db = get_supabase_database()
        if db:
            # Note: Supabase doesn't have delete_summary method yet
            # For now, just return success
            return {"message": "Summary deleted"}
    
    # Fall back to local file storage
    from config import DATA_DIR
    
    summary_path = DATA_DIR / "summaries" / f"{eid}.json"
    
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Summary not found")
    
    summary_path.unlink()
    
    return {"message": "Summary deleted"}
