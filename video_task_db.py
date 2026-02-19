"""
Video task storage with dual backend support (SQLite local / Supabase cloud).

Routes to the appropriate backend based on USE_SUPABASE configuration,
following the same pattern as api/db.py for podcast data.
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Generator

from config import DATABASE_PATH, USE_SUPABASE
from logger import get_logger

logger = get_logger("video_task_db")


class _SQLiteVideoTaskDB:
    """SQLite backend for video tasks (local development)."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_PATH
        self._init_tables()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self):
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_tasks (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    thumbnail TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress REAL DEFAULT 0,
                    message TEXT DEFAULT '',
                    markdown TEXT DEFAULT '',
                    transcript_json TEXT DEFAULT '',
                    style TEXT DEFAULT 'detailed',
                    model TEXT DEFAULT '',
                    formats TEXT DEFAULT '[]',
                    quality TEXT DEFAULT 'medium',
                    video_quality TEXT DEFAULT '720',
                    extras TEXT DEFAULT '',
                    video_understanding INTEGER DEFAULT 0,
                    video_interval INTEGER DEFAULT 4,
                    grid_cols INTEGER DEFAULT 3,
                    grid_rows INTEGER DEFAULT 3,
                    duration REAL DEFAULT 0,
                    max_output_tokens INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    user_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_task_versions (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    style TEXT DEFAULT '',
                    model_name TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES video_tasks(id) ON DELETE CASCADE
                )
            """)
            for col, default in [
                ("video_quality TEXT", "'720'"),
                ("max_output_tokens INTEGER", "0"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE video_tasks ADD COLUMN {col} DEFAULT {default}")
                except sqlite3.OperationalError:
                    pass
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vtasks_user ON video_tasks(user_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vversions_task ON video_task_versions(task_id)
            """)
            conn.commit()

    def create_task(self, task_data: dict) -> str:
        task_id = task_data.get("id") or str(uuid.uuid4())[:12]
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO video_tasks
                   (id, url, platform, title, status, style, model, formats, quality,
                    video_quality, extras, video_understanding, video_interval,
                    grid_cols, grid_rows, max_output_tokens, user_id)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    task_data.get("url", ""),
                    task_data.get("platform", ""),
                    task_data.get("title", ""),
                    task_data.get("style", "detailed"),
                    task_data.get("model", ""),
                    json.dumps(task_data.get("formats", [])),
                    task_data.get("quality", "medium"),
                    task_data.get("video_quality", "720"),
                    task_data.get("extras", ""),
                    1 if task_data.get("video_understanding") else 0,
                    task_data.get("video_interval", 4),
                    task_data.get("grid_cols", 3),
                    task_data.get("grid_rows", 3),
                    task_data.get("max_output_tokens", 0),
                    task_data.get("user_id"),
                ),
            )
            conn.commit()
        return task_id

    def update_task(self, task_id: str, updates: dict):
        allowed = {
            "status", "progress", "message", "markdown", "transcript_json",
            "title", "thumbnail", "duration", "error", "model",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE video_tasks SET {set_clause} WHERE id = ?",
                values,
            )
            conn.commit()

    def get_task(self, task_id: str, user_id: str = None) -> Optional[dict]:
        with self._conn() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT * FROM video_tasks WHERE id = ? AND user_id = ?",
                    (task_id, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM video_tasks WHERE id = ? AND user_id IS NULL",
                    (task_id,),
                ).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def list_tasks(self, user_id: str = None, limit: int = 100) -> List[dict]:
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM video_tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM video_tasks WHERE user_id IS NULL ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def delete_task(self, task_id: str, user_id: str = None) -> bool:
        with self._conn() as conn:
            if user_id:
                cursor = conn.execute(
                    "DELETE FROM video_tasks WHERE id = ? AND user_id = ?",
                    (task_id, user_id),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM video_tasks WHERE id = ? AND user_id IS NULL",
                    (task_id,),
                )
            conn.execute("DELETE FROM video_task_versions WHERE task_id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def add_version(self, task_id: str, content: str, style: str = "", model_name: str = "") -> str:
        ver_id = str(uuid.uuid4())[:8]
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO video_task_versions (id, task_id, content, style, model_name)
                   VALUES (?, ?, ?, ?, ?)""",
                (ver_id, task_id, content, style, model_name),
            )
            conn.commit()
        return ver_id

    def get_versions(self, task_id: str) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM video_task_versions WHERE task_id = ? ORDER BY created_at DESC",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        try:
            d["formats"] = json.loads(d.get("formats", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["formats"] = []
        try:
            if d.get("transcript_json"):
                d["transcript"] = json.loads(d["transcript_json"])
            else:
                d["transcript"] = None
        except (json.JSONDecodeError, TypeError):
            d["transcript"] = None
        d.pop("transcript_json", None)
        d["video_understanding"] = bool(d.get("video_understanding"))
        return d


class _SupabaseVideoTaskDB:
    """Supabase backend for video tasks (cloud deployment)."""

    def __init__(self):
        from api.supabase_db import get_supabase_database
        self._sb = get_supabase_database()

    def create_task(self, task_data: dict) -> str:
        task_id = task_data.get("id") or str(uuid.uuid4())[:12]
        user_id = task_data.get("user_id")
        if not user_id:
            logger.warning("create_task called without user_id in Supabase mode")
        return self._sb.create_video_task(user_id, task_id, task_data)

    def update_task(self, task_id: str, updates: dict):
        self._sb.update_video_task(task_id, updates)

    def get_task(self, task_id: str, user_id: str = None) -> Optional[dict]:
        return self._sb.get_video_task(task_id, user_id)

    def list_tasks(self, user_id: str = None, limit: int = 100) -> List[dict]:
        if not user_id:
            return []
        return self._sb.list_video_tasks(user_id, limit)

    def delete_task(self, task_id: str, user_id: str = None) -> bool:
        return self._sb.delete_video_task(task_id, user_id)

    def add_version(self, task_id: str, content: str, style: str = "", model_name: str = "") -> str:
        ver_id = str(uuid.uuid4())[:8]
        return self._sb.add_video_task_version(task_id, ver_id, content, style, model_name)

    def get_versions(self, task_id: str) -> List[dict]:
        return self._sb.get_video_task_versions(task_id)


class VideoTaskDB:
    """
    Unified video task DB interface.
    Routes to SQLite (local) or Supabase (cloud) based on USE_SUPABASE.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if USE_SUPABASE:
            self._backend = _SupabaseVideoTaskDB()
            logger.info("VideoTaskDB using Supabase backend")
        else:
            self._backend = _SQLiteVideoTaskDB(db_path)
            logger.info("VideoTaskDB using SQLite backend")

    def create_task(self, task_data: dict) -> str:
        return self._backend.create_task(task_data)

    def update_task(self, task_id: str, updates: dict):
        self._backend.update_task(task_id, updates)

    def get_task(self, task_id: str, user_id: str = None) -> Optional[dict]:
        return self._backend.get_task(task_id, user_id)

    def list_tasks(self, user_id: str = None, limit: int = 100) -> List[dict]:
        return self._backend.list_tasks(user_id, limit)

    def delete_task(self, task_id: str, user_id: str = None) -> bool:
        return self._backend.delete_task(task_id, user_id)

    def add_version(self, task_id: str, content: str, style: str = "", model_name: str = "") -> str:
        return self._backend.add_version(task_id, content, style, model_name)

    def get_versions(self, task_id: str) -> List[dict]:
        return self._backend.get_versions(task_id)


_video_task_db: Optional[VideoTaskDB] = None


def get_video_task_db() -> VideoTaskDB:
    global _video_task_db
    if _video_task_db is None:
        _video_task_db = VideoTaskDB()
    return _video_task_db
