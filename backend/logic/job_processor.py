"""
Background Job Processor for FA CS Automator

Handles async processing of long-running tasks:
- File upload processing
- Batch classification
- Export generation

This solves:
- Request timeouts for large files
- UI blocking during processing
- Better user experience with progress tracking
"""

import os
import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
import traceback

logger = logging.getLogger(__name__)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "4"))
JOB_TTL_HOURS = int(os.environ.get("JOB_TTL_HOURS", "24"))
JOB_CLEANUP_INTERVAL = 300  # 5 minutes


# ==============================================================================
# DATA MODELS
# ==============================================================================

class JobStatus(Enum):
    """Job status states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Types of background jobs."""
    UPLOAD = "upload"
    CLASSIFY = "classify"
    EXPORT = "export"
    CLEANUP = "cleanup"


@dataclass
class JobProgress:
    """Job progress tracking."""
    current: int = 0
    total: int = 0
    message: str = ""
    percentage: float = 0.0

    def update(self, current: int, total: int = None, message: str = None):
        """Update progress."""
        self.current = current
        if total is not None:
            self.total = total
        if message is not None:
            self.message = message
        if self.total > 0:
            self.percentage = round((self.current / self.total) * 100, 1)


@dataclass
class Job:
    """Background job representation."""
    job_id: str
    job_type: JobType
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: JobProgress = field(default_factory=JobProgress)
    result: Optional[Any] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress": {
                "current": self.progress.current,
                "total": self.progress.total,
                "percentage": self.progress.percentage,
                "message": self.progress.message,
            },
            "error": self.error,
            "has_result": self.result is not None,
        }

    def is_expired(self) -> bool:
        """Check if job has expired."""
        expiry = self.created_at + timedelta(hours=JOB_TTL_HOURS)
        return datetime.utcnow() > expiry


# ==============================================================================
# JOB PROCESSOR
# ==============================================================================

class JobProcessor:
    """
    Manages background job execution with optional SQLite persistence.

    Features:
    - Async job submission
    - Progress tracking
    - Result retrieval
    - Automatic cleanup
    - SQLite persistence (survives restarts)
    - Job recovery on startup
    """

    def __init__(self, max_workers: int = MAX_CONCURRENT_JOBS):
        self._jobs: Dict[str, Job] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = Lock()
        self._cleanup_task = None
        self._handlers: Dict[JobType, Callable] = {}
        self._sqlite_store = None
        self._use_sqlite = False

        # Initialize SQLite persistence if configured
        self._init_sqlite()

    def _init_sqlite(self):
        """Initialize SQLite job storage."""
        from backend.logic.job_sqlite import is_job_store_enabled, get_job_store

        if not is_job_store_enabled():
            logger.info("SQLite job storage not configured, using memory only")
            return

        try:
            self._sqlite_store = get_job_store()
            if self._sqlite_store:
                self._use_sqlite = True
                logger.info(f"SQLite job storage enabled: {self._sqlite_store.db_path}")

                # Recover interrupted jobs
                self._recover_jobs()
        except Exception as e:
            logger.warning(f"Failed to initialize SQLite job storage: {e}")
            self._use_sqlite = False

    def _recover_jobs(self):
        """Recover interrupted jobs after restart."""
        if not self._use_sqlite or not self._sqlite_store:
            return

        try:
            pending_jobs = self._sqlite_store.get_pending_jobs()
            recovered = 0

            for job_data in pending_jobs:
                # Mark running jobs as failed (they were interrupted)
                if job_data['status'] == 'running':
                    job_data['status'] = 'failed'
                    job_data['error'] = 'Job interrupted by server restart'
                    job_data['completed_at'] = datetime.utcnow().isoformat()
                    self._sqlite_store.save_job(job_data)
                    logger.warning(f"Marked interrupted job as failed: {job_data['job_id']}")
                    recovered += 1

            if recovered > 0:
                logger.info(f"Recovered {recovered} interrupted jobs")
        except Exception as e:
            logger.error(f"Error recovering jobs: {e}")

    def register_handler(self, job_type: JobType, handler: Callable):
        """Register a handler function for a job type."""
        self._handlers[job_type] = handler
        logger.info(f"Registered handler for job type: {job_type.value}")

    def submit(
        self,
        job_type: JobType,
        params: Dict[str, Any] = None,
        session_id: str = None,
        user_id: str = None
    ) -> Job:
        """
        Submit a job for background processing.

        Args:
            job_type: Type of job
            params: Parameters to pass to handler
            session_id: Session ID for result storage
            user_id: User ID for tracking

        Returns:
            Job object with job_id for tracking
        """
        job_id = str(uuid.uuid4())

        job = Job(
            job_id=job_id,
            job_type=job_type,
            session_id=session_id,
            user_id=user_id,
            metadata=params or {}
        )

        with self._lock:
            self._jobs[job_id] = job

        # Persist to SQLite
        self._persist_job(job)

        # Submit to thread pool
        self._executor.submit(self._run_job, job_id)

        logger.info(f"Submitted job {job_id} of type {job_type.value}")
        return job

    def _persist_job(self, job: Job) -> None:
        """Persist job to SQLite storage."""
        if not self._use_sqlite or not self._sqlite_store:
            return

        try:
            expires_at = job.created_at + timedelta(hours=JOB_TTL_HOURS)
            job_data = {
                'job_id': job.job_id,
                'job_type': job.job_type.value,
                'status': job.status.value,
                'created_at': job.created_at.isoformat(),
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'expires_at': expires_at.isoformat(),
                'session_id': job.session_id,
                'user_id': job.user_id,
                'progress_current': job.progress.current,
                'progress_total': job.progress.total,
                'progress_message': job.progress.message,
                'progress_percentage': job.progress.percentage,
                'metadata': job.metadata,
                'result': job.result,
                'error': job.error,
            }
            self._sqlite_store.save_job(job_data)
        except Exception as e:
            logger.error(f"Failed to persist job {job.job_id}: {e}")

    def _run_job(self, job_id: str):
        """Execute a job (runs in thread pool)."""
        job = self._jobs.get(job_id)
        if not job:
            return

        handler = self._handlers.get(job.job_type)
        if not handler:
            job.status = JobStatus.FAILED
            job.error = f"No handler registered for job type: {job.job_type.value}"
            self._persist_job(job)
            return

        try:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.progress.message = "Starting..."
            self._persist_job(job)  # Persist running state

            # Track last persist time for throttling
            last_persist = time.time()
            persist_interval = 2.0  # Persist progress every 2 seconds max

            # Create progress callback with persistence
            def on_progress(current: int, total: int = None, message: str = None):
                nonlocal last_persist
                job.progress.update(current, total, message)

                # Throttle persistence to avoid excessive writes
                now = time.time()
                if now - last_persist >= persist_interval:
                    self._persist_job(job)
                    last_persist = now

            # Run handler
            result = handler(
                job=job,
                params=job.metadata,
                on_progress=on_progress
            )

            job.result = result
            job.status = JobStatus.COMPLETED
            job.progress.percentage = 100.0
            job.progress.message = "Complete"

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            logger.error(traceback.format_exc())
            job.status = JobStatus.FAILED
            job.error = str(e)

        finally:
            job.completed_at = datetime.utcnow()
            self._persist_job(job)  # Always persist final state

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status as dictionary."""
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def get_job_result(self, job_id: str) -> Optional[Any]:
        """Get job result if completed."""
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.COMPLETED:
            return job.result
        return None

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job."""
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.utcnow()
            self._persist_job(job)  # Persist cancellation
            return True
        return False

    def get_jobs_by_session(self, session_id: str) -> List[Job]:
        """Get all jobs for a session."""
        return [j for j in self._jobs.values() if j.session_id == session_id]

    def cleanup_expired(self) -> int:
        """Remove expired jobs. Returns count removed."""
        removed = 0

        # Clean memory cache
        expired = []
        with self._lock:
            for job_id, job in self._jobs.items():
                if job.is_expired() and job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    expired.append(job_id)

            for job_id in expired:
                del self._jobs[job_id]

        removed += len(expired)

        # Clean SQLite
        if self._use_sqlite and self._sqlite_store:
            try:
                sqlite_removed = self._sqlite_store.cleanup_expired()
                removed += sqlite_removed
            except Exception as e:
                logger.error(f"SQLite job cleanup error: {e}")

        if removed > 0:
            logger.info(f"Cleaned up {removed} expired jobs")

        return removed

    async def start_cleanup_task(self):
        """Start background cleanup task."""
        async def _cleanup_loop():
            while True:
                await asyncio.sleep(JOB_CLEANUP_INTERVAL)
                try:
                    self.cleanup_expired()
                except Exception as e:
                    logger.error(f"Job cleanup error: {e}")

        self._cleanup_task = asyncio.create_task(_cleanup_loop())

    def shutdown(self):
        """Shutdown the job processor."""
        self._executor.shutdown(wait=True)
        if self._cleanup_task:
            self._cleanup_task.cancel()

    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics."""
        jobs = list(self._jobs.values())

        stats = {
            "total_jobs": len(jobs),
            "pending": sum(1 for j in jobs if j.status == JobStatus.PENDING),
            "running": sum(1 for j in jobs if j.status == JobStatus.RUNNING),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "max_workers": MAX_CONCURRENT_JOBS,
            "using_sqlite": self._use_sqlite,
            "storage_backend": "sqlite" if self._use_sqlite else "memory",
        }

        # Include SQLite stats if enabled
        if self._use_sqlite and self._sqlite_store:
            try:
                sqlite_stats = self._sqlite_store.get_stats()
                stats["sqlite"] = sqlite_stats
            except Exception as e:
                logger.debug(f"Failed to get SQLite job stats: {e}")

        return stats


# ==============================================================================
# GLOBAL INSTANCE
# ==============================================================================

_job_processor: Optional[JobProcessor] = None


def get_job_processor() -> JobProcessor:
    """Get or create global job processor."""
    global _job_processor
    if _job_processor is None:
        _job_processor = JobProcessor()
    return _job_processor


# ==============================================================================
# JOB HANDLERS
# ==============================================================================

def upload_job_handler(job: Job, params: Dict[str, Any], on_progress: Callable) -> Dict[str, Any]:
    """
    Handle file upload and processing job.

    This is called by the job processor in a background thread.
    """
    from backend.services.importer import ImporterService
    from backend.services.classifier import ClassifierService

    file_path = params.get("file_path")
    tax_year = params.get("tax_year")

    if not file_path or not os.path.exists(file_path):
        raise ValueError("File not found")

    on_progress(0, 100, "Parsing Excel file...")

    # Parse file
    importer = ImporterService()
    assets = importer.parse_excel(file_path)

    if not assets:
        raise ValueError("No assets found in file")

    on_progress(30, 100, f"Classifying {len(assets)} assets...")

    # Classify assets
    classifier = ClassifierService()
    if tax_year:
        classifier.set_tax_year(tax_year)

    classified = classifier.classify_batch(assets, tax_year=tax_year)

    on_progress(90, 100, "Finalizing...")

    # Clean up temp file
    try:
        os.remove(file_path)
    except Exception:
        pass

    on_progress(100, 100, "Complete")

    return {
        "assets": [a.dict() for a in classified],
        "count": len(classified),
    }


def export_job_handler(job: Job, params: Dict[str, Any], on_progress: Callable) -> Dict[str, Any]:
    """Handle export generation job."""
    from backend.services.exporter import ExporterService
    from backend.models.asset import Asset

    assets_data = params.get("assets", [])

    on_progress(0, 100, "Preparing assets for export...")

    # Convert dicts back to Asset objects
    assets = [Asset(**a) for a in assets_data]

    on_progress(30, 100, "Generating export file...")

    exporter = ExporterService()
    excel_bytes = exporter.generate_fa_cs_export(assets)

    on_progress(100, 100, "Export complete")

    return {
        "file_bytes": excel_bytes.getvalue(),
        "filename": f"FA_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
    }


# Register default handlers
def init_job_handlers():
    """Initialize default job handlers."""
    processor = get_job_processor()
    processor.register_handler(JobType.UPLOAD, upload_job_handler)
    processor.register_handler(JobType.EXPORT, export_job_handler)
