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
UNKNOWN_CHANNEL_SENTINEL = "__unknown__"


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
                ("channel TEXT", "''"),
                ("channel_url TEXT", "''"),
                ("channel_avatar TEXT", "''"),
                ("published_at TEXT", "''"),
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
        status = task_data.get("status", "pending")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO video_tasks
                   (id, url, platform, title, status, style, model, formats, quality,
                    video_quality, extras, video_understanding, video_interval,
                    grid_cols, grid_rows, max_output_tokens, user_id,
                    thumbnail, duration, channel, channel_url, channel_avatar,
                    published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    task_data.get("url", ""),
                    task_data.get("platform", ""),
                    task_data.get("title", ""),
                    status,
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
                    task_data.get("thumbnail", ""),
                    task_data.get("duration", 0),
                    task_data.get("channel", ""),
                    task_data.get("channel_url", ""),
                    task_data.get("channel_avatar", ""),
                    task_data.get("published_at", ""),
                ),
            )
            conn.commit()
        return task_id

    def count_channel_tasks(self, channel: str, user_id: str = None) -> int:
        with self._conn() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT COUNT(*) FROM video_tasks WHERE channel = ? AND user_id = ?",
                    (channel, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM video_tasks WHERE channel = ?",
                    (channel,),
                ).fetchone()
            return row[0] if row else 0

    def get_existing_urls(self, urls: list, user_id: str = None) -> set:
        """Return the subset of *urls* that already have tasks for this user."""
        if not urls:
            return set()
        placeholders = ",".join("?" * len(urls))
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    f"SELECT url FROM video_tasks WHERE url IN ({placeholders}) AND user_id = ?",
                    (*urls, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT url FROM video_tasks WHERE url IN ({placeholders})",
                    urls,
                ).fetchall()
            return {r[0] for r in rows}

    def get_distinct_channels(self, user_id: str = None) -> List[dict]:
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT DISTINCT channel, channel_url, channel_avatar, platform FROM video_tasks "
                    "WHERE channel != '' AND channel IS NOT NULL AND user_id = ?",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT channel, channel_url, channel_avatar, platform FROM video_tasks "
                    "WHERE channel != '' AND channel IS NOT NULL AND user_id IS NULL",
                ).fetchall()
            return [dict(r) for r in rows]

    def list_channels_with_stats(self, user_id: str = None) -> List[dict]:
        """Return one row per channel with count, done count, and latest updated_at."""
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    """SELECT channel, channel_url, channel_avatar, platform,
                              COUNT(*) as total,
                              SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as done,
                              MAX(updated_at) as last_updated,
                              (SELECT thumbnail FROM video_tasks vt2
                               WHERE vt2.channel = vt.channel
                               AND (vt2.user_id = ? OR (? IS NULL AND vt2.user_id IS NULL))
                               AND vt2.thumbnail != '' AND vt2.thumbnail IS NOT NULL
                               LIMIT 1) as thumbnail
                       FROM video_tasks vt
                       WHERE channel != '' AND channel IS NOT NULL AND user_id = ?
                       GROUP BY channel, channel_url, channel_avatar, platform
                       ORDER BY MAX(updated_at) DESC""",
                    (user_id, user_id, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT channel, channel_url, channel_avatar, platform,
                              COUNT(*) as total,
                              SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as done,
                              MAX(updated_at) as last_updated,
                              (SELECT thumbnail FROM video_tasks vt2
                               WHERE vt2.channel = vt.channel
                               AND vt2.user_id IS NULL
                               AND vt2.thumbnail != '' AND vt2.thumbnail IS NOT NULL
                               LIMIT 1) as thumbnail
                       FROM video_tasks vt
                       WHERE channel != '' AND channel IS NOT NULL AND user_id IS NULL
                       GROUP BY channel, channel_url, channel_avatar, platform
                       ORDER BY MAX(updated_at) DESC""",
                ).fetchall()
            return [dict(r) for r in rows]

    def list_tasks_by_channel(self, channel: str, platform: str, user_id: str = None) -> List[dict]:
        """Return all tasks for a specific channel+platform, ordered newest first."""
        order = "ORDER BY (CASE WHEN published_at IS NOT NULL AND published_at != '' THEN 0 ELSE 1 END), published_at DESC, created_at DESC"
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    f"SELECT * FROM video_tasks WHERE channel = ? AND platform = ? AND user_id = ? {order}",
                    (channel, platform, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM video_tasks WHERE channel = ? AND platform = ? AND user_id IS NULL {order}",
                    (channel, platform),
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def update_task(self, task_id: str, updates: dict):
        allowed = {
            "status", "progress", "message", "markdown", "transcript_json",
            "title", "thumbnail", "duration", "error", "model",
            "channel", "channel_url", "channel_avatar",
            "style", "formats", "quality", "video_quality", "published_at",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        if "formats" in fields and isinstance(fields["formats"], list):
            fields["formats"] = json.dumps(fields["formats"])
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

    def get_task_by_url(self, url: str, user_id: str = None) -> Optional[dict]:
        with self._conn() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT * FROM video_tasks WHERE url = ? AND user_id = ? LIMIT 1",
                    (url, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM video_tasks WHERE url = ? AND user_id IS NULL LIMIT 1",
                    (url,),
                ).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def list_tasks(self, user_id: str = None, limit: int = 2000) -> List[dict]:
        order = "ORDER BY (CASE WHEN published_at IS NOT NULL AND published_at != '' THEN 0 ELSE 1 END), published_at DESC, created_at DESC"
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    f"SELECT * FROM video_tasks WHERE user_id = ? {order} LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM video_tasks WHERE user_id IS NULL {order} LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def list_recent_success_tasks(self, user_id: str = None, limit: int = 6) -> List[dict]:
        order = "ORDER BY updated_at DESC, created_at DESC"
        cols = (
            "id, url, platform, title, thumbnail, status, progress, message, "
            "style, duration, error, channel, channel_url, channel_avatar, "
            "published_at, created_at, updated_at"
        )
        with self._conn() as conn:
            if user_id:
                rows = conn.execute(
                    f"SELECT {cols} FROM video_tasks WHERE user_id = ? AND status = 'success' {order} LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {cols} FROM video_tasks WHERE user_id IS NULL AND status = 'success' {order} LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def count_distinct_channels(self, user_id: str = None) -> int:
        with self._conn() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT COUNT(DISTINCT channel) FROM video_tasks "
                    "WHERE channel != '' AND channel IS NOT NULL AND user_id = ?",
                    (user_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(DISTINCT channel) FROM video_tasks "
                    "WHERE channel != '' AND channel IS NOT NULL AND user_id IS NULL",
                ).fetchone()
            return row[0] if row else 0

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

    def delete_channel(self, channel: str, user_id: str = None) -> int:
        with self._conn() as conn:
            if channel == UNKNOWN_CHANNEL_SENTINEL:
                if user_id:
                    rows = conn.execute(
                        "SELECT id FROM video_tasks WHERE (channel = '' OR channel IS NULL) AND user_id = ?",
                        (user_id,),
                    ).fetchall()
                    conn.execute(
                        "DELETE FROM video_tasks WHERE (channel = '' OR channel IS NULL) AND user_id = ?",
                        (user_id,),
                    )
                else:
                    rows = conn.execute(
                        "SELECT id FROM video_tasks WHERE (channel = '' OR channel IS NULL) AND user_id IS NULL",
                    ).fetchall()
                    conn.execute(
                        "DELETE FROM video_tasks WHERE (channel = '' OR channel IS NULL) AND user_id IS NULL",
                    )
            elif user_id:
                rows = conn.execute(
                    "SELECT id FROM video_tasks WHERE channel = ? AND user_id = ?",
                    (channel, user_id),
                ).fetchall()
                conn.execute(
                    "DELETE FROM video_tasks WHERE channel = ? AND user_id = ?",
                    (channel, user_id),
                )
            else:
                rows = conn.execute(
                    "SELECT id FROM video_tasks WHERE channel = ? AND user_id IS NULL",
                    (channel,),
                ).fetchall()
                conn.execute(
                    "DELETE FROM video_tasks WHERE channel = ? AND user_id IS NULL",
                    (channel,),
                )
            for r in rows:
                conn.execute("DELETE FROM video_task_versions WHERE task_id = ?", (r[0],))
            conn.commit()
            return len(rows)

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
    """Supabase backend for video tasks (cloud deployment).

    Uses an in-memory write-behind cache to avoid blocking the processing
    pipeline on Supabase HTTP round-trips for every progress tick.
    Only flushes to Supabase on status transitions, every FLUSH_INTERVAL
    seconds, or when markdown/transcript data changes.
    """

    FLUSH_INTERVAL = 3.0  # seconds between periodic Supabase writes
    TERMINAL_STATUSES = {"success", "failed", "cancelled"}
    MILESTONE_FIELDS = {"status", "markdown", "transcript_json", "error",
                        "title", "thumbnail", "channel"}

    def __init__(self):
        from api.supabase_db import get_supabase_database
        self._sb = get_supabase_database()
        self._cache: dict[str, dict] = {}  # task_id -> merged fields
        self._dirty: dict[str, dict] = {}  # task_id -> pending DB writes
        self._last_flush: dict[str, float] = {}  # task_id -> monotonic time
        import threading
        self._lock = threading.Lock()

    def _should_flush(self, task_id: str, updates: dict) -> bool:
        import time
        now = time.monotonic()
        if any(k in updates for k in self.MILESTONE_FIELDS):
            return True
        if updates.get("status") in self.TERMINAL_STATUSES:
            return True
        last = self._last_flush.get(task_id, 0)
        if now - last >= self.FLUSH_INTERVAL:
            return True
        return False

    def _flush(self, task_id: str):
        import time
        with self._lock:
            pending = self._dirty.pop(task_id, None)
        if pending:
            try:
                self._sb.update_video_task(task_id, pending)
            except Exception as e:
                logger.warning(f"Supabase flush failed for {task_id}: {e}")
                with self._lock:
                    existing = self._dirty.get(task_id, {})
                    pending.update(existing)
                    self._dirty[task_id] = pending
            self._last_flush[task_id] = time.monotonic()

    def create_task(self, task_data: dict) -> str:
        task_id = task_data.get("id") or str(uuid.uuid4())[:12]
        user_id = task_data.get("user_id")
        if not user_id:
            logger.warning("create_task called without user_id in Supabase mode")
        result = self._sb.create_video_task(user_id, task_id, task_data)
        with self._lock:
            self._cache[task_id] = dict(task_data, id=task_id, user_id=user_id)
        return result

    def update_task(self, task_id: str, updates: dict):
        with self._lock:
            if task_id in self._cache:
                self._cache[task_id].update(updates)
            else:
                self._cache[task_id] = dict(updates)
            dirty = self._dirty.get(task_id, {})
            dirty.update(updates)
            self._dirty[task_id] = dirty

        if self._should_flush(task_id, updates):
            self._flush(task_id)

    def get_task(self, task_id: str, user_id: str = None) -> Optional[dict]:
        with self._lock:
            cached = self._cache.get(task_id)
        if cached is not None:
            return self._cached_to_dict(cached)
        task = self._sb.get_video_task(task_id, user_id)
        if task:
            with self._lock:
                self._cache[task_id] = task
        return task

    def get_task_by_url(self, url: str, user_id: str = None) -> Optional[dict]:
        if not user_id or not url:
            return None
        return self._sb.get_video_task_by_url(url, user_id)

    def flush_task(self, task_id: str):
        """Force-flush any pending writes for a task.

        Keeps the cache intact so subsequent get_task calls still return the
        full task data instead of falling back to a minimal partial entry
        created by a later update_task call.
        """
        self._flush(task_id)
        with self._lock:
            self._last_flush.pop(task_id, None)

    def list_tasks(self, user_id: str = None, limit: int = 2000) -> List[dict]:
        if not user_id:
            return []
        server_tasks = self._sb.list_video_tasks(user_id, limit)
        return self._merge_cached_task_list(
            server_tasks,
            user_id=user_id,
            limit=limit,
        )

    def _merge_cached_task_list(
        self,
        server_tasks: List[dict],
        *,
        user_id: str,
        limit: int,
        predicate=None,
    ) -> List[dict]:
        with self._lock:
            cached_tasks = [
                self._cached_to_dict(dict(task))
                for task in self._cache.values()
                if task.get("user_id") == user_id and (predicate(task) if predicate else True)
            ]
            dirty_ids = set(self._dirty.keys())

        if not cached_tasks:
            return server_tasks

        server_ids = {task.get("id") for task in server_tasks if task.get("id")}
        merged_by_id: dict[str, dict] = {}
        ordered_tasks: list[dict] = []

        for server_task in server_tasks:
            task_id = server_task.get("id")
            if not task_id:
                continue
            merged_by_id[task_id] = dict(server_task)

        for cached_task in cached_tasks:
            task_id = cached_task.get("id")
            if not task_id:
                continue
            existing = merged_by_id.get(task_id, {})
            merged_by_id[task_id] = {**existing, **cached_task}

        for server_task in server_tasks:
            task_id = server_task.get("id")
            if task_id and task_id in merged_by_id:
                ordered_tasks.append(merged_by_id.pop(task_id))

        extra_cached_tasks = [
            task for task_id, task in merged_by_id.items()
            if task_id not in server_ids and (
                task.get("status") not in self.TERMINAL_STATUSES or task_id in dirty_ids
            )
        ]
        extra_cached_tasks.sort(
            key=lambda task: (
                task.get("published_at") or "",
                task.get("updated_at") or "",
                task.get("created_at") or "",
            ),
            reverse=True,
        )

        return (ordered_tasks + extra_cached_tasks)[:limit]

    def list_recent_success_tasks(self, user_id: str = None, limit: int = 6) -> List[dict]:
        if not user_id:
            return []
        return self._sb.list_recent_success_video_tasks(user_id, limit)

    def count_tasks(self, user_id: str = None) -> dict:
        if not user_id:
            return {"total": 0, "completed": 0}
        return self._sb.count_video_tasks(user_id)

    def count_distinct_channels(self, user_id: str = None) -> int:
        if not user_id:
            return 0
        return self._sb.count_distinct_video_channels(user_id)

    def count_channel_tasks(self, channel: str, user_id: str = None) -> int:
        if not user_id or not channel:
            return 0
        return self._sb.count_channel_tasks(channel, user_id)

    def get_existing_urls(self, urls: list, user_id: str = None) -> set:
        if not urls or not user_id:
            return set()
        return self._sb.get_existing_video_urls(urls, user_id)

    def get_distinct_channels(self, user_id: str = None) -> List[dict]:
        if not user_id:
            return []
        return self._sb.get_distinct_video_channels(user_id)

    def list_channels_with_stats(self, user_id: str = None) -> List[dict]:
        if not user_id:
            return []
        return self._sb.list_video_channels_with_stats(user_id)

    def list_tasks_by_channel(self, channel: str, platform: str, user_id: str = None) -> List[dict]:
        if not user_id or not channel:
            return []
        server_tasks = self._sb.list_video_tasks_by_channel(channel, platform, user_id)
        return self._merge_cached_task_list(
            server_tasks,
            user_id=user_id,
            limit=max(len(server_tasks), 2000),
            predicate=lambda task: task.get("channel") == channel and task.get("platform") == platform,
        )

    def delete_task(self, task_id: str, user_id: str = None) -> bool:
        with self._lock:
            self._cache.pop(task_id, None)
            self._dirty.pop(task_id, None)
            self._last_flush.pop(task_id, None)
        return self._sb.delete_video_task(task_id, user_id)

    def delete_channel(self, channel: str, user_id: str = None) -> int:
        if not user_id or not channel:
            return 0
        with self._lock:
            if channel == UNKNOWN_CHANNEL_SENTINEL:
                to_remove = [
                    tid for tid, c in self._cache.items()
                    if not c.get("channel")
                ]
            else:
                to_remove = [tid for tid, c in self._cache.items() if c.get("channel") == channel]
            for tid in to_remove:
                self._cache.pop(tid, None)
                self._dirty.pop(tid, None)
                self._last_flush.pop(tid, None)
        return self._sb.delete_video_channel(channel, user_id)

    def add_version(self, task_id: str, content: str, style: str = "", model_name: str = "") -> str:
        ver_id = str(uuid.uuid4())[:8]
        return self._sb.add_video_task_version(task_id, ver_id, content, style, model_name)

    def get_versions(self, task_id: str) -> List[dict]:
        return self._sb.get_video_task_versions(task_id)

    @staticmethod
    def _cached_to_dict(cached: dict) -> dict:
        d = dict(cached)
        if isinstance(d.get("formats"), str):
            try:
                d["formats"] = json.loads(d["formats"])
            except (json.JSONDecodeError, TypeError):
                d["formats"] = []
        elif not isinstance(d.get("formats"), list):
            d["formats"] = []
        if "transcript_json" in d and "transcript" not in d:
            try:
                tj = d["transcript_json"]
                d["transcript"] = json.loads(tj) if tj else None
            except (json.JSONDecodeError, TypeError):
                d["transcript"] = None
        return d


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

    def get_task_by_url(self, url: str, user_id: str = None) -> Optional[dict]:
        return self._backend.get_task_by_url(url, user_id)

    def list_tasks(self, user_id: str = None, limit: int = 2000) -> List[dict]:
        return self._backend.list_tasks(user_id, limit)

    def list_recent_success_tasks(self, user_id: str = None, limit: int = 6) -> List[dict]:
        if hasattr(self._backend, "list_recent_success_tasks"):
            return self._backend.list_recent_success_tasks(user_id, limit)
        tasks = self._backend.list_tasks(user_id, limit * 3)
        success = [t for t in tasks if t.get("status") == "success"]
        return success[:limit]

    def count_tasks(self, user_id: str = None) -> dict:
        if hasattr(self._backend, "count_tasks"):
            return self._backend.count_tasks(user_id)
        tasks = self._backend.list_tasks(user_id)
        return {"total": len(tasks), "completed": sum(1 for t in tasks if t.get("status") == "success")}

    def count_distinct_channels(self, user_id: str = None) -> int:
        if hasattr(self._backend, "count_distinct_channels"):
            return self._backend.count_distinct_channels(user_id)
        channels = self._backend.get_distinct_channels(user_id)
        return len(channels)

    def count_channel_tasks(self, channel: str, user_id: str = None) -> int:
        return self._backend.count_channel_tasks(channel, user_id)

    def get_existing_urls(self, urls: list, user_id: str = None) -> set:
        return self._backend.get_existing_urls(urls, user_id)

    def get_distinct_channels(self, user_id: str = None) -> List[dict]:
        return self._backend.get_distinct_channels(user_id)

    def list_channels_with_stats(self, user_id: str = None) -> List[dict]:
        if hasattr(self._backend, "list_channels_with_stats"):
            return self._backend.list_channels_with_stats(user_id)
        # Fallback: derive from full task list
        tasks = self._backend.list_tasks(user_id)
        channels: dict = {}
        for t in tasks:
            ch = t.get("channel") or ""
            pl = t.get("platform") or ""
            if not ch:
                continue
            key = (ch, pl)
            if key not in channels:
                channels[key] = {
                    "channel": ch, "platform": pl,
                    "channel_url": t.get("channel_url", ""),
                    "channel_avatar": t.get("channel_avatar", ""),
                    "thumbnail": t.get("thumbnail", ""),
                    "total": 0, "done": 0,
                    "last_updated": t.get("updated_at", ""),
                }
            entry = channels[key]
            entry["total"] += 1
            if t.get("status") == "success":
                entry["done"] += 1
            if not entry["thumbnail"] and t.get("thumbnail"):
                entry["thumbnail"] = t["thumbnail"]
            if (t.get("updated_at") or "") > (entry["last_updated"] or ""):
                entry["last_updated"] = t["updated_at"]
        return sorted(channels.values(), key=lambda x: x["last_updated"] or "", reverse=True)

    def list_tasks_by_channel(self, channel: str, platform: str, user_id: str = None) -> List[dict]:
        if hasattr(self._backend, "list_tasks_by_channel"):
            return self._backend.list_tasks_by_channel(channel, platform, user_id)
        # Fallback
        tasks = self._backend.list_tasks(user_id)
        return [t for t in tasks if t.get("channel") == channel and t.get("platform") == platform]

    def delete_task(self, task_id: str, user_id: str = None) -> bool:
        return self._backend.delete_task(task_id, user_id)

    def delete_channel(self, channel: str, user_id: str = None) -> int:
        return self._backend.delete_channel(channel, user_id)

    def add_version(self, task_id: str, content: str, style: str = "", model_name: str = "") -> str:
        return self._backend.add_version(task_id, content, style, model_name)

    def get_versions(self, task_id: str) -> List[dict]:
        return self._backend.get_versions(task_id)

    def flush_task(self, task_id: str):
        """Flush pending writes (Supabase cache). No-op for SQLite."""
        if hasattr(self._backend, "flush_task"):
            self._backend.flush_task(task_id)


_video_task_db: Optional[VideoTaskDB] = None


def get_video_task_db() -> VideoTaskDB:
    global _video_task_db
    if _video_task_db is None:
        _video_task_db = VideoTaskDB()
    return _video_task_db
