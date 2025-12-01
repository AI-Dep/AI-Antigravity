"""
SQLite Job Storage Backend

Provides persistent job storage for background task queue.
Jobs survive server restarts without requiring Redis.

Features:
- File-based persistence (no external service required)
- Automatic expiration enforcement
- Thread-safe operations
- Progress tracking persistence

Configuration:
    Set SQLITE_JOB_DB environment variable to database path
    Example: SQLITE_JOB_DB=/var/lib/facs/jobs.db

    Or shares the session database if SQLITE_SESSION_DB is set

Author: FA CS Automator Team
"""

import os
import sqlite3
import json
import logging
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Configuration - use job-specific DB or fall back to session DB path
SQLITE_JOB_DB = os.environ.get(
    "SQLITE_JOB_DB",
    os.environ.get("SQLITE_SESSION_DB", "").replace("sessions.db", "jobs.db") if os.environ.get("SQLITE_SESSION_DB") else ""
)


class SQLiteJobStore:
    """
    SQLite-backed job storage.

    Thread-safe with connection pooling per thread.
    Automatically creates schema on first use.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite job store.

        Args:
            db_path: Path to SQLite database file.
                     Uses SQLITE_JOB_DB env var if not provided.
                     Uses :memory: for testing if neither is set.
        """
        self.db_path = db_path or SQLITE_JOB_DB or ":memory:"
        self._local = threading.local()
        self._initialized = False
        self._init_lock = threading.Lock()

        # Initialize schema
        self._ensure_schema()

        logger.info(f"SQLite job store initialized: {self.db_path}")

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
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        job_type TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        expires_at TEXT NOT NULL,
                        session_id TEXT,
                        user_id TEXT,
                        progress_current INTEGER DEFAULT 0,
                        progress_total INTEGER DEFAULT 0,
                        progress_message TEXT DEFAULT '',
                        progress_percentage REAL DEFAULT 0.0,
                        metadata TEXT DEFAULT '{}',
                        result TEXT,
                        error TEXT
                    )
                """)

                # Index for status queries
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_jobs_status
                    ON jobs(status)
                """)

                # Index for session queries
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_jobs_session
                    ON jobs(session_id)
                """)

                # Index for expiration cleanup
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_jobs_expires
                    ON jobs(expires_at)
                """)

                conn.commit()

            self._initialized = True
            logger.debug("SQLite job schema initialized")

    def save_job(self, job_data: Dict[str, Any]) -> None:
        """
        Save or update a job.

        Args:
            job_data: Dictionary with job fields
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, job_type, status, created_at, started_at, completed_at,
                    expires_at, session_id, user_id, progress_current, progress_total,
                    progress_message, progress_percentage, metadata, result, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    progress_current = excluded.progress_current,
                    progress_total = excluded.progress_total,
                    progress_message = excluded.progress_message,
                    progress_percentage = excluded.progress_percentage,
                    result = excluded.result,
                    error = excluded.error
                """,
                (
                    job_data['job_id'],
                    job_data['job_type'],
                    job_data['status'],
                    job_data['created_at'],
                    job_data.get('started_at'),
                    job_data.get('completed_at'),
                    job_data['expires_at'],
                    job_data.get('session_id'),
                    job_data.get('user_id'),
                    job_data.get('progress_current', 0),
                    job_data.get('progress_total', 0),
                    job_data.get('progress_message', ''),
                    job_data.get('progress_percentage', 0.0),
                    json.dumps(job_data.get('metadata', {})),
                    json.dumps(job_data.get('result')) if job_data.get('result') else None,
                    job_data.get('error')
                )
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job data dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()

            if row:
                return self._row_to_dict(row)
            return None

    def get_jobs_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all jobs for a session."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,)
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_pending_jobs(self) -> List[Dict[str, Any]]:
        """Get all pending jobs (for recovery after restart)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE status IN ('pending', 'running') ORDER BY created_at ASC"
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_expired(self) -> int:
        """Remove all expired completed/failed jobs."""
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM jobs
                WHERE expires_at <= ?
                AND status IN ('completed', 'failed', 'cancelled')
                """,
                (now,)
            )
            conn.commit()
            removed = cursor.rowcount

            if removed > 0:
                logger.info(f"SQLite: Cleaned up {removed} expired jobs")

            return removed

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            'job_id': row['job_id'],
            'job_type': row['job_type'],
            'status': row['status'],
            'created_at': row['created_at'],
            'started_at': row['started_at'],
            'completed_at': row['completed_at'],
            'expires_at': row['expires_at'],
            'session_id': row['session_id'],
            'user_id': row['user_id'],
            'progress_current': row['progress_current'],
            'progress_total': row['progress_total'],
            'progress_message': row['progress_message'],
            'progress_percentage': row['progress_percentage'],
            'metadata': json.loads(row['metadata']) if row['metadata'] else {},
            'result': json.loads(row['result']) if row['result'] else None,
            'error': row['error'],
        }

    def get_stats(self) -> dict:
        """Get storage statistics."""
        with self._get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM jobs"
            ).fetchone()['cnt']

            by_status = {}
            for status in ['pending', 'running', 'completed', 'failed', 'cancelled']:
                count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM jobs WHERE status = ?",
                    (status,)
                ).fetchone()['cnt']
                by_status[status] = count

            return {
                "backend": "sqlite",
                "db_path": self.db_path,
                "total_jobs": total,
                "by_status": by_status,
            }

    def close(self):
        """Close the database connection for current thread."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# Singleton instance
_job_store: Optional[SQLiteJobStore] = None


def get_job_store() -> Optional[SQLiteJobStore]:
    """
    Get SQLite job store singleton.

    Returns None if SQLITE_JOB_DB is not configured.
    """
    global _job_store

    if not SQLITE_JOB_DB:
        return None

    if _job_store is None:
        _job_store = SQLiteJobStore()

    return _job_store


def is_job_store_enabled() -> bool:
    """Check if SQLite job storage is enabled."""
    return bool(SQLITE_JOB_DB)
