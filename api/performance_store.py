"""Bounded durable account metrics. No content, URLs or credential storage."""
from contextlib import contextmanager
import json
import sqlite3
from config import DATA_DIR, USE_SUPABASE


@contextmanager
def connection():
    conn = sqlite3.connect(DATA_DIR / 'page-performance.sqlite', timeout=3)
    conn.execute('CREATE TABLE IF NOT EXISTS samples (user_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    try:
        with conn: yield conn
    finally: conn.close()


def append(owner, sample):
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        get_supabase_admin_client().rpc('append_page_performance', {'owner_id':owner,'sample':sample}).execute()
    else:
        with connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT payload FROM samples WHERE user_id=?', (owner,)).fetchone()
            rows = (json.loads(row[0]) if row else []) + [sample]
            conn.execute('INSERT OR REPLACE INTO samples VALUES (?,?)', (owner,json.dumps(rows[-128:])))


def read(owner):
    if USE_SUPABASE:
        from api.supabase_client import get_supabase_admin_client
        rows = get_supabase_admin_client().table('page_performance').select('samples').eq('user_id',owner).limit(1).execute().data
        return rows[0]['samples'] if rows else []
    with connection() as conn:
        row = conn.execute('SELECT payload FROM samples WHERE user_id=?', (owner,)).fetchone()
        return json.loads(row[0]) if row else []
