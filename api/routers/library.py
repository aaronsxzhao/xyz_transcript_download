"""Bounded saved-note discovery. No full note/transcript payloads."""
from typing import Literal
from fastapi import APIRouter, Depends, Query
from api.auth import User, get_current_user
from api.db import get_db

router = APIRouter()


def page_rows(rows, limit):
    more = len(rows) > limit
    items = rows[:limit]
    return {'items': [{k: v for k, v in row.items() if k not in ('user_id', 'search_text', 'sort_key')} for row in items],
            'next_cursor': items[-1]['sort_key'] if more else None}


@router.get('')
def library(q: str = Query('', max_length=200), kind: Literal['', 'podcast', 'video'] = '',
            status: str = Query('', max_length=32), source: str = Query('', max_length=200),
            sort: Literal['newest', 'oldest'] = 'newest', cursor: str = Query('', max_length=400),
            limit: int = Query(40, ge=1, le=60), user: User = Depends(get_current_user)):
    db = get_db(user.id)
    if db.use_supabase:
        query = db.db.client.table('library_items').select('id,kind,title,source,date,status,sort_key').eq('user_id', user.id)
        if kind: query = query.eq('kind', kind)
        if status: query = query.eq('status', status)
        if source: query = query.ilike('source', '%' + source.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        if q: query = query.ilike('search_text', '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        if cursor: query = query.lt('sort_key', cursor) if sort == 'newest' else query.gt('sort_key', cursor)
        rows = query.order('sort_key', desc=sort == 'newest').limit(limit + 1).execute().data or []
        return page_rows(rows, limit)
    # Local summaries live as JSON files; cloud queries never take this path.
    summaries = db.get_all_summaries()
    metadata = db.get_summary_podcast_metadata([s.episode_id for s in summaries])
    rows = [dict(id=s.episode_id, kind='podcast', title=s.title, source=metadata.get(s.episode_id, ('Podcast', ''))[0] or 'Podcast', date=s.created_at, status='completed') for s in summaries]
    from video_task_db import get_video_task_db
    videos = get_video_task_db().list_tasks(user.id, limit=1000000)
    rows += [dict(id=t['id'], kind='video', title=t.get('title') or 'Untitled video', source=t.get('channel') or t.get('platform') or 'Video', date=t.get('updated_at') or t.get('created_at') or '', status='completed' if t['status'] == 'success' else t['status']) for t in videos if t['status'] != 'discovered']
    from datetime import datetime, timezone
    for row in rows:
        try: date = datetime.fromisoformat(row['date'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc).strftime('%Y%m%d%H%M%S%f')
        except (ValueError, TypeError): date = '00000000000000000000'
        row['sort_key'] = date + ':' + row['kind'] + ':' + row['id']
    rows = [r for r in rows if (not kind or r['kind'] == kind) and (not status or r['status'] == status) and source.casefold() in r['source'].casefold() and q.casefold() in (r['title'] + ' ' + r['source']).casefold() and (not cursor or (r['sort_key'] < cursor if sort == 'newest' else r['sort_key'] > cursor))]
    rows.sort(key=lambda r: r['sort_key'], reverse=sort == 'newest')
    return page_rows(rows, limit)
