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
    return await run_sync(_build_summary_list_items, db, summaries)


def _build_summary_list_items(db, summaries) -> List[SummaryListItem]:
    """Convert summary records into lightweight list items with podcast metadata."""
    metadata = db.get_summary_podcast_metadata([s.episode_id for s in summaries])

    results = []
    for s in summaries:
        from api.summary_quality import needs_review
        if not s.topics and not s.key_points:
            episode = db.get_episode(s.episode_id)
            if episode and needs_review(episode.duration,s.topics,s.key_points):
                continue
        pt, pc = metadata.get(s.episode_id, ("", ""))
        results.append(SummaryListItem(
            episode_id=s.episode_id,
            title=s.title,
            topics_count=len(s.topics),
            key_points_count=len(s.key_points),
            podcast_title=pt,
            podcast_cover=pc,
            created_at=s.created_at,
        ))
    return results


@router.get("/recent", response_model=List[SummaryListItem])
async def list_recent_summaries(
    limit: int = Query(6, ge=1, le=20),
    user: Optional[User] = Depends(get_current_user),
):
    """List recent summaries for the dashboard."""
    db = get_db(user.id if user else None)
    if db.use_supabase:
        def recent():
            rows = db.db.client.table('library_items').select('id,title,topics_count,key_points_count,source,thumbnail,date').eq('user_id',user.id).eq('kind','podcast').eq('status','completed').order('sort_key',desc=True).limit(limit).execute().data or []
            return [SummaryListItem(episode_id=r['id'],title=r['title'],topics_count=r['topics_count'],key_points_count=r['key_points_count'],podcast_title=r['source'],podcast_cover=r['thumbnail'],created_at=r['date']) for r in rows]
        return await run_sync(recent)
    summaries = await run_sync(db.get_recent_summaries, limit)
    return await run_sync(_build_summary_list_items, db, summaries)


@router.get("/{eid}", response_model=SummaryResponse)
async def get_summary(eid: str, user: Optional[User] = Depends(get_current_user)):
    """Get summary for an episode."""
    db = get_db(user.id if user else None)
    
    summary = await run_sync(db.get_summary, eid)
    
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    warning = ''
    access_status = 'unknown'
    access_message = ''
    # Normal summaries keep the existing fast path. Empty results need an
    # integrity check so historic recognition failures aren't shown as valid.
    if not summary.key_points and not summary.topics:
        episode, transcript = await asyncio.gather(run_sync(db.get_episode,eid),run_sync(db.get_transcript,eid))
        if episode:
            from source_access import source_message
            access_status = episode.source_status
            access_message = source_message(access_status)
        if transcript:
            from transcript_quality import validate_transcript, IncompleteTranscriptError
            try:
                validate_transcript(transcript, episode.duration if episode else 0)
            except IncompleteTranscriptError:
                warning = 'This summary is based on an incomplete transcript and does not represent the full episode. Restore access to the full audio before regenerating.'
        elif episode:
            warning = 'The original transcript is missing. This empty summary cannot be verified.'
        from api.summary_quality import needs_review, EMPTY_LONG_MESSAGE
        if not warning and episode and needs_review(episode.duration,summary.topics,summary.key_points):
            warning = EMPTY_LONG_MESSAGE

    return SummaryResponse(
        quality_warning=warning, source_status=access_status, source_message=access_message,
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
    
    if not summary_data.key_points and not summary_data.topics:
        checked = await get_summary(eid,user)
        if checked.quality_warning:
            raise HTTPException(status_code=409,detail=(checked.source_message+' '+checked.quality_warning).strip())
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
    
    return HTMLResponse(content=html_content, headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff",
    })


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
    
    if not summary_data.key_points and not summary_data.topics:
        checked = await get_summary(eid,user)
        if checked.quality_warning:
            raise HTTPException(status_code=409,detail=(checked.source_message+' '+checked.quality_warning).strip())
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
