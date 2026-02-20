"""
Platform cookie storage and retrieval.
Routes to SQLite (local) or Supabase (cloud) based on USE_SUPABASE.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

from config import DATABASE_PATH, USE_SUPABASE
from logger import get_logger

logger = get_logger("cookie_manager")


class _SQLiteCookieManager:
    """SQLite backend for cookies (local development)."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_PATH
        self._init_table()

    def _init_table(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS platform_cookies (
                    platform TEXT PRIMARY KEY,
                    cookie_data TEXT NOT NULL DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def get_cookie(self, platform: str) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cookie_data FROM platform_cookies WHERE platform = ?",
                (platform,),
            ).fetchone()
            return row["cookie_data"] if row else ""

    def set_cookie(self, platform: str, cookie_data: str):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO platform_cookies (platform, cookie_data, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(platform) DO UPDATE SET
                     cookie_data = excluded.cookie_data,
                     updated_at = excluded.updated_at""",
                (platform, cookie_data),
            )
            conn.commit()
        logger.info(f"Cookie updated for platform: {platform}")

    def delete_cookie(self, platform: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM platform_cookies WHERE platform = ?", (platform,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_cookies(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT platform, length(cookie_data) as length, updated_at FROM platform_cookies"
            ).fetchall()
            return [
                {
                    "platform": r["platform"],
                    "has_cookie": r["length"] > 0,
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]


class _SupabaseCookieManager:
    """
    Supabase backend for cookies (cloud deployment).
    Persists cookies across container restarts.

    Requires table in Supabase (run in SQL Editor):

        CREATE TABLE IF NOT EXISTS platform_cookies (
            id BIGSERIAL PRIMARY KEY,
            platform TEXT UNIQUE NOT NULL,
            cookie_data TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- No RLS needed: cookies are server-wide, accessed only via service role key.
        ALTER TABLE platform_cookies ENABLE ROW LEVEL SECURITY;
        CREATE POLICY "Service role full access" ON platform_cookies
            FOR ALL USING (true) WITH CHECK (true);
    """

    def __init__(self):
        from api.supabase_client import get_supabase_admin_client
        self.client = get_supabase_admin_client()
        if not self.client:
            raise RuntimeError("Supabase admin client not available for cookie storage")
        logger.info("CookieManager using Supabase backend")

    def get_cookie(self, platform: str) -> str:
        try:
            result = (
                self.client.table("platform_cookies")
                .select("cookie_data")
                .eq("platform", platform)
                .maybe_single()
                .execute()
            )
            if result.data:
                return result.data.get("cookie_data", "")
            return ""
        except Exception as e:
            logger.error(f"Supabase get_cookie failed for {platform}: {e}")
            return ""

    def set_cookie(self, platform: str, cookie_data: str):
        try:
            from datetime import datetime, timezone
            self.client.table("platform_cookies").upsert(
                {
                    "platform": platform,
                    "cookie_data": cookie_data,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="platform",
            ).execute()
            logger.info(f"Cookie updated for platform: {platform} (Supabase)")
        except Exception as e:
            logger.error(f"Supabase set_cookie failed for {platform}: {e}")
            raise

    def delete_cookie(self, platform: str) -> bool:
        try:
            result = (
                self.client.table("platform_cookies")
                .delete()
                .eq("platform", platform)
                .execute()
            )
            return len(result.data) > 0 if result.data else False
        except Exception as e:
            logger.error(f"Supabase delete_cookie failed for {platform}: {e}")
            return False

    def list_cookies(self) -> list:
        try:
            result = (
                self.client.table("platform_cookies")
                .select("platform, cookie_data, updated_at")
                .execute()
            )
            return [
                {
                    "platform": r["platform"],
                    "has_cookie": bool(r.get("cookie_data")),
                    "updated_at": r.get("updated_at", ""),
                }
                for r in (result.data or [])
            ]
        except Exception as e:
            logger.error(f"Supabase list_cookies failed: {e}")
            return []


class CookieManager:
    """
    Unified cookie manager.
    Routes to SQLite (local) or Supabase (cloud) based on USE_SUPABASE.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if USE_SUPABASE:
            try:
                self._backend = _SupabaseCookieManager()
            except Exception as e:
                logger.warning(f"Supabase cookie backend failed, falling back to SQLite: {e}")
                self._backend = _SQLiteCookieManager(db_path)
        else:
            self._backend = _SQLiteCookieManager(db_path)
            logger.info("CookieManager using SQLite backend")

    def get_cookie(self, platform: str) -> str:
        return self._backend.get_cookie(platform)

    def set_cookie(self, platform: str, cookie_data: str):
        self._backend.set_cookie(platform, cookie_data)

    def delete_cookie(self, platform: str) -> bool:
        return self._backend.delete_cookie(platform)

    def list_cookies(self) -> list:
        return self._backend.list_cookies()


_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager
