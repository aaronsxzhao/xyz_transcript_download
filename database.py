"""
SQLite database module for storing podcasts, episodes, and processing status.
Includes WAL mode, error handling, and integrity checks.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Generator

from config import DATABASE_PATH
from logger import get_logger

logger = get_logger("database")


class ProcessingStatus(Enum):
    """Status of episode processing."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PodcastRecord:
    """Database record for a podcast."""
    id: int
    pid: str
    title: str
    author: str
    description: str
    cover_url: str
    last_checked: str
    created_at: str


@dataclass
class EpisodeRecord:
    """Database record for an episode."""
    id: int
    eid: str
    pid: str
    podcast_id: int
    title: str
    description: str
    duration: int
    pub_date: str
    audio_url: str
    status: ProcessingStatus
    error_message: str
    created_at: str
    updated_at: str


class Database:
    """SQLite database for podcast data management with WAL mode."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_PATH
        self._init_db()

    def _init_db(self):
        """Initialize database with WAL mode and tables."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Enable WAL mode for better concurrency
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=10000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                
                # Run integrity check on startup
                result = cursor.execute("PRAGMA integrity_check").fetchone()
                if result[0] != "ok":
                    logger.error(f"Database integrity check failed: {result[0]}")
                
                # Podcasts table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS podcasts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pid TEXT UNIQUE NOT NULL,
                        title TEXT NOT NULL,
                        author TEXT DEFAULT '',
                        description TEXT DEFAULT '',
                        cover_url TEXT DEFAULT '',
                        last_checked TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Episodes table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS episodes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        eid TEXT UNIQUE NOT NULL,
                        pid TEXT NOT NULL,
                        podcast_id INTEGER,
                        title TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        duration INTEGER DEFAULT 0,
                        pub_date TEXT,
                        audio_url TEXT,
                        status TEXT DEFAULT 'pending',
                        error_message TEXT DEFAULT '',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (podcast_id) REFERENCES podcasts(id)
                    )
                """)

                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_episodes_pid ON episodes(pid)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status)
                """)

                conn.commit()
                logger.debug("Database initialized successfully")
                
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection as a context manager with timeout."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    # Podcast operations

    def add_podcast(
        self,
        pid: str,
        title: str,
        author: str = "",
        description: str = "",
        cover_url: str = "",
    ) -> Optional[int]:
        """
        Add a new podcast to the database.
        
        Returns:
            Podcast ID if successful, None if already exists
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO podcasts (pid, title, author, description, cover_url)
                    VALUES (?, ?, ?, ?, ?)
                """, (pid, title, author, description, cover_url))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Already exists
                return None

    def get_podcast(self, pid: str) -> Optional[PodcastRecord]:
        """Get a podcast by its PID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM podcasts WHERE pid = ?", (pid,))
            row = cursor.fetchone()
            
            if row:
                return PodcastRecord(
                    id=row["id"],
                    pid=row["pid"],
                    title=row["title"],
                    author=row["author"],
                    description=row["description"],
                    cover_url=row["cover_url"],
                    last_checked=row["last_checked"] or "",
                    created_at=row["created_at"],
                )
            return None

    def get_podcast_by_id(self, podcast_id: int) -> Optional[PodcastRecord]:
        """Get a podcast by its database ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM podcasts WHERE id = ?", (podcast_id,))
            row = cursor.fetchone()
            
            if row:
                return PodcastRecord(
                    id=row["id"],
                    pid=row["pid"],
                    title=row["title"],
                    author=row["author"],
                    description=row["description"],
                    cover_url=row["cover_url"],
                    last_checked=row["last_checked"] or "",
                    created_at=row["created_at"],
                )
            return None

    def get_all_podcasts(self) -> List[PodcastRecord]:
        """Get all subscribed podcasts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM podcasts ORDER BY title")
            
            podcasts = []
            for row in cursor.fetchall():
                podcasts.append(PodcastRecord(
                    id=row["id"],
                    pid=row["pid"],
                    title=row["title"],
                    author=row["author"],
                    description=row["description"],
                    cover_url=row["cover_url"],
                    last_checked=row["last_checked"] or "",
                    created_at=row["created_at"],
                ))
            return podcasts

    def update_podcast_checked(self, pid: str):
        """Update the last checked timestamp for a podcast."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE podcasts SET last_checked = ? WHERE pid = ?
            """, (datetime.now().isoformat(), pid))
            conn.commit()

    def delete_podcast(self, pid: str) -> bool:
        """Delete a podcast and its episodes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get podcast ID first
            cursor.execute("SELECT id FROM podcasts WHERE pid = ?", (pid,))
            row = cursor.fetchone()
            if not row:
                return False

            podcast_id = row["id"]

            # Delete episodes
            cursor.execute("DELETE FROM episodes WHERE podcast_id = ?", (podcast_id,))
            
            # Delete podcast
            cursor.execute("DELETE FROM podcasts WHERE id = ?", (podcast_id,))
            
            conn.commit()
            return True

    # Episode operations

    def add_episode(
        self,
        eid: str,
        pid: str,
        podcast_id: int,
        title: str,
        description: str = "",
        duration: int = 0,
        pub_date: str = "",
        audio_url: str = "",
    ) -> Optional[int]:
        """
        Add a new episode to the database.
        
        Returns:
            Episode ID if successful, None if already exists
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO episodes 
                    (eid, pid, podcast_id, title, description, duration, pub_date, audio_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (eid, pid, podcast_id, title, description, duration, pub_date, audio_url))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

    def get_episode(self, eid: str) -> Optional[EpisodeRecord]:
        """Get an episode by its EID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes WHERE eid = ?", (eid,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_episode(row)
            return None

    def get_episodes_by_podcast(
        self,
        pid: str,
        status: Optional[ProcessingStatus] = None,
    ) -> List[EpisodeRecord]:
        """Get all episodes for a podcast, optionally filtered by status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT * FROM episodes 
                    WHERE pid = ? AND status = ?
                    ORDER BY pub_date DESC
                """, (pid, status.value))
            else:
                cursor.execute("""
                    SELECT * FROM episodes 
                    WHERE pid = ?
                    ORDER BY pub_date DESC
                """, (pid,))
            
            return [self._row_to_episode(row) for row in cursor.fetchall()]

    def get_pending_episodes(self) -> List[EpisodeRecord]:
        """Get all episodes that need processing."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM episodes 
                WHERE status IN ('pending', 'downloaded', 'transcribed')
                ORDER BY created_at ASC
            """)
            return [self._row_to_episode(row) for row in cursor.fetchall()]

    def update_episode_status(
        self,
        eid: str,
        status: ProcessingStatus,
        error_message: str = "",
    ):
        """Update the processing status of an episode."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE episodes 
                SET status = ?, error_message = ?, updated_at = ?
                WHERE eid = ?
            """, (status.value, error_message, datetime.now().isoformat(), eid))
            conn.commit()

    def update_episode_audio_url(self, eid: str, audio_url: str):
        """Update the audio URL for an episode."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE episodes SET audio_url = ?, updated_at = ? WHERE eid = ?
            """, (audio_url, datetime.now().isoformat(), eid))
            conn.commit()

    def episode_exists(self, eid: str) -> bool:
        """Check if an episode exists in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM episodes WHERE eid = ?", (eid,))
            return cursor.fetchone() is not None

    def delete_episode(self, eid: str) -> bool:
        """Delete an episode from the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM episodes WHERE eid = ?", (eid,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_episode(self, row: sqlite3.Row) -> EpisodeRecord:
        """Convert a database row to an EpisodeRecord."""
        return EpisodeRecord(
            id=row["id"],
            eid=row["eid"],
            pid=row["pid"],
            podcast_id=row["podcast_id"],
            title=row["title"],
            description=row["description"],
            duration=row["duration"],
            pub_date=row["pub_date"] or "",
            audio_url=row["audio_url"] or "",
            status=ProcessingStatus(row["status"]),
            error_message=row["error_message"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # Statistics

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM podcasts")
            podcast_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM episodes")
            episode_count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT status, COUNT(*) FROM episodes GROUP BY status
            """)
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}

            return {
                "podcasts": podcast_count,
                "episodes": episode_count,
                "status_counts": status_counts,
            }


# Global database instance
_db: Optional[Database] = None


def get_database() -> Database:
    """Get or create the global Database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
