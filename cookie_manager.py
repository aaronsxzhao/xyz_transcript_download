"""
Platform cookie storage and retrieval using SQLite.
Stores cookies for video platforms (Bilibili, Douyin, etc.).
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

from config import DATABASE_PATH
from logger import get_logger

logger = get_logger("cookie_manager")


class CookieManager:
    """Manages platform cookies in SQLite."""

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
        """Get cookie string for a platform."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cookie_data FROM platform_cookies WHERE platform = ?",
                (platform,),
            ).fetchone()
            return row["cookie_data"] if row else ""

    def set_cookie(self, platform: str, cookie_data: str):
        """Set or update cookie for a platform."""
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
        """List all stored platform cookies (without revealing full data)."""
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


_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager
