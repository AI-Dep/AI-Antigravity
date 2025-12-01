"""
SQLite Session Storage Backend

Provides persistent session storage for single-server deployments.
Sessions survive server restarts without requiring Redis.

Features:
- File-based persistence (no external service required)
- Automatic expiration enforcement
- Thread-safe operations
- Works with existing SessionManager architecture

Configuration:
    Set SQLITE_SESSION_DB environment variable to database path
    Example: SQLITE_SESSION_DB=/var/lib/facs/sessions.db

Author: FA CS Automator Team
"""

import os
import sqlite3
import logging
import threading
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Configuration
SQLITE_SESSION_DB = os.environ.get("SQLITE_SESSION_DB", "")


class SQLiteSessionStore:
    """
    SQLite-backed session storage.

    Thread-safe with connection pooling per thread.
    Automatically creates schema on first use.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite session store.

        Args:
            db_path: Path to SQLite database file.
                     Uses SQLITE_SESSION_DB env var if not provided.
                     Uses :memory: for testing if neither is set.
        """
        self.db_path = db_path or SQLITE_SESSION_DB or ":memory:"
        self._local = threading.local()
        self._initialized = False
        self._init_lock = threading.Lock()

        # Initialize schema
        self._ensure_schema()

        logger.info(f"SQLite session store initialized: {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=30000")

        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise

    def _ensure_schema(self):
        """Create tables if they don't exist."""
        with self._init_lock:
            if self._initialized:
                return

            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                """)

                # Index for expiration cleanup
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sessions_expires
                    ON sessions(expires_at)
                """)

                conn.commit()

            self._initialized = True
            logger.debug("SQLite session schema initialized")

    def get(self, session_id: str) -> Optional[str]:
        """
        Get session data by ID.

        Args:
            session_id: Session identifier

        Returns:
            JSON string of session data, or None if not found/expired
        """
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT data FROM sessions
                WHERE session_id = ? AND expires_at > ?
                """,
                (session_id, now)
            )
            row = cursor.fetchone()

            if row:
                return row['data']
            return None

    def set(self, session_id: str, data: str, expires_at: datetime) -> None:
        """
        Store or update session data.

        Args:
            session_id: Session identifier
            data: JSON string of session data
            expires_at: Expiration datetime
        """
        now = datetime.utcnow()

        with self._get_connection() as conn:
            # Use INSERT ... ON CONFLICT to preserve created_at on updates
            conn.execute(
                """
                INSERT INTO sessions (session_id, data, created_at, last_accessed, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    data = excluded.data,
                    last_accessed = excluded.last_accessed,
                    expires_at = excluded.expires_at
                """,
                (
                    session_id,
                    data,
                    now.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat()
                )
            )
            conn.commit()

    def delete(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions.

        Returns:
            Number of sessions removed
        """
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (now,)
            )
            conn.commit()
            removed = cursor.rowcount

            if removed > 0:
                logger.info(f"SQLite: Cleaned up {removed} expired sessions")

            return removed

    def count(self) -> int:
        """Get total session count."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM sessions")
            return cursor.fetchone()['cnt']

    def get_stats(self) -> dict:
        """Get storage statistics."""
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions"
            ).fetchone()['cnt']

            active = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions WHERE expires_at > ?",
                (now,)
            ).fetchone()['cnt']

            # Get database file size
            db_size = 0
            if self.db_path != ":memory:":
                try:
                    db_size = os.path.getsize(self.db_path)
                except OSError:
                    pass

            return {
                "backend": "sqlite",
                "db_path": self.db_path,
                "total_sessions": total,
                "active_sessions": active,
                "expired_sessions": total - active,
                "db_size_bytes": db_size,
            }

    def close(self):
        """Close the database connection for current thread."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# Singleton instance
_sqlite_store: Optional[SQLiteSessionStore] = None


def get_sqlite_store() -> Optional[SQLiteSessionStore]:
    """
    Get SQLite session store singleton.

    Returns None if SQLITE_SESSION_DB is not configured.
    """
    global _sqlite_store

    if not SQLITE_SESSION_DB:
        return None

    if _sqlite_store is None:
        _sqlite_store = SQLiteSessionStore()

    return _sqlite_store


def is_sqlite_enabled() -> bool:
    """Check if SQLite session storage is enabled."""
    return bool(SQLITE_SESSION_DB)
