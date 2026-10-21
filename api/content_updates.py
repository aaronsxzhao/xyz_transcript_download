"""Durable, account-scoped notifications independent of provider scans."""
from datetime import datetime, timezone
import sqlite3
from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, Field
from api.auth import get_current_user, User
from typing import Optional
from starlette.concurrency import run_in_threadpool

router = APIRouter()


def install_sqlite_updates(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS content_updates (
        user_id TEXT NOT NULL, item_key TEXT NOT NULL, kind TEXT NOT NULL,
        title TEXT NOT NULL, source_title TEXT NOT NULL DEFAULT '', source_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        dismissed_at TEXT, PRIMARY KEY(user_id,item_key));
      CREATE INDEX IF NOT EXISTS content_updates_unread ON content_updates(user_id,created_at DESC,item_key)
        WHERE dismissed_at IS NULL;
    ''')
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'episodes' in tables:
        conn.executescript('''
          CREATE TRIGGER IF NOT EXISTS episode_content_update AFTER INSERT ON episodes BEGIN
            INSERT OR IGNORE INTO content_updates(user_id,item_key,kind,title,source_title,source_id)
            VALUES ('local','podcast:'||NEW.eid,'podcast',NEW.title,
              coalesce((SELECT title FROM podcasts WHERE id=NEW.podcast_id),''),NEW.pid);
          END;
          CREATE TRIGGER IF NOT EXISTS episode_content_delete AFTER DELETE ON episodes BEGIN
            DELETE FROM content_updates WHERE item_key='podcast:'||OLD.eid AND user_id='local';
          END;
        ''')
    if 'video_tasks' in tables:
        conn.executescript('''
          CREATE TRIGGER IF NOT EXISTS video_content_update AFTER INSERT ON video_tasks BEGIN
            INSERT OR IGNORE INTO content_updates(user_id,item_key,kind,title,source_title,source_id)
            VALUES (coalesce(NEW.user_id,'local'),'video:'||NEW.id,'video',coalesce(NEW.title,''),coalesce(NEW.channel,''),NEW.id);
          END;
          CREATE TRIGGER IF NOT EXISTS video_content_title AFTER UPDATE OF title,channel ON video_tasks BEGIN
            UPDATE content_updates SET title=coalesce(NEW.title,''),source_title=coalesce(NEW.channel,'')
              WHERE user_id=coalesce(NEW.user_id,'local') AND item_key='video:'||NEW.id;
          END;
          CREATE TRIGGER IF NOT EXISTS video_content_delete AFTER DELETE ON video_tasks BEGIN
            DELETE FROM content_updates WHERE item_key='video:'||OLD.id AND user_id=coalesce(OLD.user_id,'local');
          END;
        ''')


def list_updates(user_id: Optional[str], db_path=None):
    from config import USE_SUPABASE, DATABASE_PATH
    if USE_SUPABASE:
        if not user_id: return []
        from api.supabase_client import get_supabase_admin_client
        rows = get_supabase_admin_client().table('content_updates').select(
            'item_key,kind,title,source_title,source_id,created_at').eq('user_id',user_id).is_(
            'dismissed_at','null').order('created_at',desc=True).order('item_key').limit(100).execute().data or []
    else:
        with sqlite3.connect(str(db_path or DATABASE_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            install_sqlite_updates(conn)
            rows = [dict(r) for r in conn.execute(
                'SELECT item_key,kind,title,source_title,source_id,created_at FROM content_updates '
                'WHERE user_id=? AND dismissed_at IS NULL ORDER BY created_at DESC,item_key LIMIT 100',
                (user_id or 'local',))]
    return rows


def dismiss_updates(user_id: Optional[str], keys: list[str], db_path=None, before: Optional[datetime] = None):
    from config import USE_SUPABASE, DATABASE_PATH
    if not keys and before is None: return
    stamp = datetime.now(timezone.utc).isoformat()
    if USE_SUPABASE:
        if not user_id: return
        from api.supabase_client import get_supabase_admin_client
        query = get_supabase_admin_client().table('content_updates').update({'dismissed_at':stamp},returning='minimal').eq(
            'user_id',user_id).is_('dismissed_at','null')
        # Closing the banner acknowledges the complete unread snapshot, not just
        # its bounded first page. Notifications created later remain unread.
        query = query.lte('created_at',before.isoformat()) if before is not None else query.in_('item_key',keys)
        query.execute()
    else:
        with sqlite3.connect(str(db_path or DATABASE_PATH)) as conn:
            install_sqlite_updates(conn)
            if before is not None:
                conn.execute('UPDATE content_updates SET dismissed_at=? WHERE user_id=? AND dismissed_at IS NULL AND julianday(created_at)<=julianday(?)',
                             (stamp,user_id or 'local',before.isoformat()))
            else:
                conn.executemany('UPDATE content_updates SET dismissed_at=? WHERE user_id=? AND item_key=?',
                    [(stamp,user_id or 'local',key) for key in keys])


class DismissRequest(BaseModel):
    keys: list[str] = Field(default_factory=list,max_length=100)
    before: Optional[AwareDatetime] = None


@router.get('')
async def updates(user: Optional[User] = Depends(get_current_user)):
    rows=await run_in_threadpool(list_updates,user.id if user else None)
    if not rows: return {'items':[]}
    def created(row):
        value=datetime.fromisoformat(row['created_at'].replace('Z','+00:00'))
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    return {'items':rows,'dismiss_before':max(map(created,rows)).isoformat()}


@router.post('/dismiss')
async def dismiss(data: DismissRequest, user: Optional[User] = Depends(get_current_user)):
    await run_in_threadpool(dismiss_updates,user.id if user else None,data.keys,before=data.before)
    return {'ok': True}
