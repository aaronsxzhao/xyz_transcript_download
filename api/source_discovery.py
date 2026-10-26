"""Save a small discovery batch without reading/writing each imported note."""
import json
import uuid


def save_discoveries(backend, rows: list[dict], owner: str | None) -> int:
    # Stable IDs make replay after a lost HTTP acknowledgement harmless. Never
    # upsert content over an existing processed task.
    rows = list({row['url']: {**row, 'user_id': owner,
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, f'discovery:{owner}:{row["url"]}'))}
        for row in rows}.values())
    if not rows:
        return 0
    urls = [row['url'] for row in rows]
    if hasattr(backend, '_conn'):
        with backend._conn() as conn:
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                placeholders = ','.join('?' for _ in urls)
                existing = {row['url']: dict(row) for row in conn.execute(
                    f'SELECT id,url,published_at FROM video_tasks WHERE user_id IS ? AND url IN ({placeholders})', [owner, *urls])}
                created = 0
                for row in rows:
                    old = existing.get(row['url'])
                    if old:
                        if not old['published_at'] and row.get('published_at'):
                            conn.execute('UPDATE video_tasks SET published_at=? WHERE id=? AND user_id IS ?',
                                         [row['published_at'], old['id'], owner])
                        continue
                    columns = list(row)
                    values = [json.dumps(value) if key == 'formats' else value for key, value in row.items()]
                    created += conn.execute(f'INSERT OR IGNORE INTO video_tasks ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', values).rowcount
                return created

    client = backend._sb.client
    if not client or not owner:
        raise RuntimeError('Authenticated discovery storage is unavailable')
    existing = {row['url']: row for row in client.table('video_tasks').select('id,url,published_at')
                .eq('user_id', owner).in_('url', urls).execute().data}
    new = [row for row in rows if row['url'] not in existing]
    # Batch the common path into one insert, ignore ID conflicts on replay.
    dates = {}
    for row in rows:
        old = existing.get(row['url'])
        if old and not old.get('published_at') and row.get('published_at'):
            dates.setdefault((row['published_at'], old.get('published_at')), []).append(old['id'])
    for (date, previous), ids in dates.items():
        query = client.table('video_tasks').update({'published_at': date}).eq('user_id', owner).in_('id', ids)
        query = query.is_('published_at', 'null') if previous is None else query.eq('published_at', previous)
        query.execute()
    return len(client.table('video_tasks').upsert(new, on_conflict='id', ignore_duplicates=True).execute().data) if new else 0
