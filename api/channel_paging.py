"""Bounded channel reads with stable created-at/id cursors and owner predicates."""
import base64
import json
import re

FIELDS = 'id,url,platform,title,thumbnail,status,progress,message,style,duration,error,channel,channel_url,channel_avatar,published_at,created_at,updated_at'


def decode_cursor(cursor):
    if not cursor: return None
    try:
        stamp, ident = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
        if not re.fullmatch(r'[0-9T: .+Z-]{10,40}', stamp) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident): raise ValueError()
        return stamp, ident
    except Exception: raise ValueError('Invalid channel cursor')


def page(backend, channel, platform, owner, limit=40, cursor='', q='', status='', sort='newest'):
    after = decode_cursor(cursor)
    descending = sort != 'oldest'
    op = '<' if descending else '>'
    direction = 'DESC' if descending else 'ASC'
    if hasattr(backend, '_sb'):
        if not owner: return {'tasks': [], 'next_cursor': None}
        query = backend._sb.client.table('video_tasks').select(FIELDS).eq('user_id', owner).eq('channel', channel).eq('platform', platform)
        if q: query = query.ilike('title', '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        if status: query = query.eq('status', status)
        if after:
            stamp, ident = after; cmp = 'lt' if descending else 'gt'
            query = query.or_(f'created_at.{cmp}.{stamp},and(created_at.eq.{stamp},id.{cmp}.{ident})')
        rows = query.order('created_at', desc=descending).order('id', desc=descending).limit(limit + 1).execute().data or []
    else:
        clauses = ['channel = ?', 'platform = ?', 'user_id = ?' if owner else 'user_id IS NULL']
        args = [channel, platform] + ([owner] if owner else [])
        if q:
            clauses.append("title LIKE ? ESCAPE '\\'"); args.append('%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        if status: clauses.append('status = ?'); args.append(status)
        if after:
            clauses.append(f'(created_at {op} ? OR (created_at = ? AND id {op} ?))'); args.extend([after[0], after[0], after[1]])
        with backend._conn() as conn:
            rows = [dict(r) for r in conn.execute(f'SELECT {FIELDS} FROM video_tasks WHERE {" AND ".join(clauses)} ORDER BY created_at {direction}, id {direction} LIMIT ?', args + [limit + 1])]
    visible = rows[:limit]
    next_cursor = base64.urlsafe_b64encode(json.dumps([visible[-1]['created_at'], visible[-1]['id']]).encode()).decode().rstrip('=') if len(rows) > limit else None
    return {'tasks': visible, 'next_cursor': next_cursor}
