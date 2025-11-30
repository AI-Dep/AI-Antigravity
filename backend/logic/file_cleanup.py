"""
File Cleanup Utility for FA CS Automator

Manages cleanup of temporary and export files:
- Removes old export files from bot_handoff
- Cleans up temporary upload files
- Monitors disk usage
- Prevents unbounded file growth

This solves:
- Disk space exhaustion
- File accumulation over time
- Orphaned temporary files
"""

import os
import glob
import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

# File retention settings (in hours)
EXPORT_FILE_RETENTION_HOURS = int(os.environ.get("EXPORT_FILE_RETENTION_HOURS", "168"))  # 7 days
TEMP_FILE_RETENTION_HOURS = int(os.environ.get("TEMP_FILE_RETENTION_HOURS", "1"))  # 1 hour
ERROR_LOG_RETENTION_HOURS = int(os.environ.get("ERROR_LOG_RETENTION_HOURS", "72"))  # 3 days

# Disk usage thresholds
DISK_WARNING_THRESHOLD = float(os.environ.get("DISK_WARNING_THRESHOLD", "0.8"))  # 80%
DISK_CRITICAL_THRESHOLD = float(os.environ.get("DISK_CRITICAL_THRESHOLD", "0.9"))  # 90%

# Cleanup interval (seconds)
CLEANUP_INTERVAL = int(os.environ.get("CLEANUP_INTERVAL", "3600"))  # 1 hour

# Maximum file size for single export (bytes)
MAX_EXPORT_FILE_SIZE = int(os.environ.get("MAX_EXPORT_FILE_SIZE", "52428800"))  # 50MB


# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class CleanupStats:
    """Statistics from a cleanup run."""
    files_deleted: int = 0
    bytes_freed: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    directories_cleaned: List[str] = None

    def __post_init__(self):
        if self.directories_cleaned is None:
            self.directories_cleaned = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_deleted": self.files_deleted,
            "bytes_freed": self.bytes_freed,
            "bytes_freed_mb": round(self.bytes_freed / (1024 * 1024), 2),
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
            "directories_cleaned": self.directories_cleaned,
        }


@dataclass
class DiskUsage:
    """Disk usage information."""
    total: int
    used: int
    free: int
    percent_used: float

    @property
    def is_warning(self) -> bool:
        return self.percent_used >= DISK_WARNING_THRESHOLD

    @property
    def is_critical(self) -> bool:
        return self.percent_used >= DISK_CRITICAL_THRESHOLD

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_gb": round(self.total / (1024**3), 2),
            "used_gb": round(self.used / (1024**3), 2),
            "free_gb": round(self.free / (1024**3), 2),
            "percent_used": round(self.percent_used * 100, 1),
            "is_warning": self.is_warning,
            "is_critical": self.is_critical,
        }


# ==============================================================================
# FILE CLEANUP
# ==============================================================================

class FileCleanupManager:
    """
    Manages file cleanup operations.

    Features:
    - Scheduled cleanup of old files
    - Disk usage monitoring
    - Configurable retention policies
    - Emergency cleanup when disk full
    """

    def __init__(self, base_path: str = None):
        self.base_path = base_path or os.getcwd()
        self._cleanup_task = None
        self._last_cleanup = None
        self._last_stats: Optional[CleanupStats] = None

    def get_disk_usage(self, path: str = None) -> DiskUsage:
        """Get disk usage for a path."""
        path = path or self.base_path
        try:
            stat = shutil.disk_usage(path)
            return DiskUsage(
                total=stat.total,
                used=stat.used,
                free=stat.free,
                percent_used=stat.used / stat.total
            )
        except Exception as e:
            logger.error(f"Failed to get disk usage: {e}")
            return DiskUsage(total=0, used=0, free=0, percent_used=0)

    def _get_file_age_hours(self, filepath: str) -> float:
        """Get file age in hours."""
        try:
            mtime = os.path.getmtime(filepath)
            age = datetime.now() - datetime.fromtimestamp(mtime)
            return age.total_seconds() / 3600
        except Exception:
            return 0

    def _delete_file(self, filepath: str) -> int:
        """Delete a file and return bytes freed."""
        try:
            size = os.path.getsize(filepath)
            os.remove(filepath)
            return size
        except Exception as e:
            logger.error(f"Failed to delete {filepath}: {e}")
            return 0

    def cleanup_directory(
        self,
        directory: str,
        pattern: str = "*",
        max_age_hours: float = 24,
        dry_run: bool = False
    ) -> CleanupStats:
        """
        Clean up files in a directory based on age.

        Args:
            directory: Directory path to clean
            pattern: Glob pattern for files (e.g., "*.xlsx")
            max_age_hours: Maximum file age in hours
            dry_run: If True, don't actually delete files

        Returns:
            CleanupStats with results
        """
        stats = CleanupStats()
        start_time = datetime.now()

        if not os.path.exists(directory):
            logger.debug(f"Directory does not exist: {directory}")
            return stats

        stats.directories_cleaned.append(directory)

        # Find matching files
        search_path = os.path.join(directory, pattern)
        files = glob.glob(search_path)

        for filepath in files:
            if os.path.isfile(filepath):
                age_hours = self._get_file_age_hours(filepath)

                if age_hours > max_age_hours:
                    if dry_run:
                        logger.info(f"[DRY RUN] Would delete: {filepath} (age: {age_hours:.1f}h)")
                        stats.files_deleted += 1
                        try:
                            stats.bytes_freed += os.path.getsize(filepath)
                        except Exception:
                            pass
                    else:
                        bytes_freed = self._delete_file(filepath)
                        if bytes_freed > 0:
                            stats.files_deleted += 1
                            stats.bytes_freed += bytes_freed
                            logger.info(f"Deleted: {filepath} (age: {age_hours:.1f}h, size: {bytes_freed})")
                        else:
                            stats.errors += 1

        stats.duration_seconds = (datetime.now() - start_time).total_seconds()
        return stats

    def cleanup_exports(self, dry_run: bool = False) -> CleanupStats:
        """Clean up old export files from bot_handoff."""
        export_dir = os.path.join(self.base_path, "bot_handoff")
        return self.cleanup_directory(
            directory=export_dir,
            pattern="*.xlsx",
            max_age_hours=EXPORT_FILE_RETENTION_HOURS,
            dry_run=dry_run
        )

    def cleanup_temp_files(self, dry_run: bool = False) -> CleanupStats:
        """Clean up temporary upload files."""
        total_stats = CleanupStats()

        # Clean temp_* files in base directory
        for pattern in ["temp_*.xlsx", "temp_*.xls", "temp_*.csv"]:
            stats = self.cleanup_directory(
                directory=self.base_path,
                pattern=pattern,
                max_age_hours=TEMP_FILE_RETENTION_HOURS,
                dry_run=dry_run
            )
            total_stats.files_deleted += stats.files_deleted
            total_stats.bytes_freed += stats.bytes_freed
            total_stats.errors += stats.errors

        return total_stats

    def cleanup_error_logs(self, dry_run: bool = False) -> CleanupStats:
        """Clean up old error log files."""
        return self.cleanup_directory(
            directory=self.base_path,
            pattern="*error*.log",
            max_age_hours=ERROR_LOG_RETENTION_HOURS,
            dry_run=dry_run
        )

    def run_full_cleanup(self, dry_run: bool = False) -> CleanupStats:
        """
        Run full cleanup of all managed directories.

        Returns combined stats from all cleanup operations.
        """
        start_time = datetime.now()
        total_stats = CleanupStats()

        # Check disk usage first
        disk = self.get_disk_usage()
        if disk.is_critical:
            logger.warning(f"CRITICAL: Disk usage at {disk.percent_used:.1%}")

        # Run all cleanup operations
        for name, cleanup_func in [
            ("exports", self.cleanup_exports),
            ("temp_files", self.cleanup_temp_files),
            ("error_logs", self.cleanup_error_logs),
        ]:
            try:
                stats = cleanup_func(dry_run=dry_run)
                total_stats.files_deleted += stats.files_deleted
                total_stats.bytes_freed += stats.bytes_freed
                total_stats.errors += stats.errors
                total_stats.directories_cleaned.extend(stats.directories_cleaned)
                logger.info(f"Cleanup {name}: {stats.files_deleted} files, {stats.bytes_freed} bytes")
            except Exception as e:
                logger.error(f"Cleanup {name} failed: {e}")
                total_stats.errors += 1

        total_stats.duration_seconds = (datetime.now() - start_time).total_seconds()
        self._last_cleanup = datetime.now()
        self._last_stats = total_stats

        logger.info(
            f"Full cleanup complete: {total_stats.files_deleted} files deleted, "
            f"{total_stats.bytes_freed / (1024*1024):.2f}MB freed"
        )

        return total_stats

    async def start_scheduled_cleanup(self):
        """Start background scheduled cleanup task."""
        async def _cleanup_loop():
            while True:
                await asyncio.sleep(CLEANUP_INTERVAL)
                try:
                    self.run_full_cleanup()
                except Exception as e:
                    logger.error(f"Scheduled cleanup failed: {e}")

        self._cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info(f"Started scheduled cleanup (interval: {CLEANUP_INTERVAL}s)")

    def stop_scheduled_cleanup(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()

    def get_status(self) -> Dict[str, Any]:
        """Get cleanup manager status."""
        disk = self.get_disk_usage()
        return {
            "disk_usage": disk.to_dict(),
            "last_cleanup": self._last_cleanup.isoformat() if self._last_cleanup else None,
            "last_stats": self._last_stats.to_dict() if self._last_stats else None,
            "config": {
                "export_retention_hours": EXPORT_FILE_RETENTION_HOURS,
                "temp_retention_hours": TEMP_FILE_RETENTION_HOURS,
                "cleanup_interval_seconds": CLEANUP_INTERVAL,
            }
        }


# ==============================================================================
# GLOBAL INSTANCE
# ==============================================================================

_cleanup_manager: Optional[FileCleanupManager] = None


def get_cleanup_manager() -> FileCleanupManager:
    """Get or create global cleanup manager."""
    global _cleanup_manager
    if _cleanup_manager is None:
        _cleanup_manager = FileCleanupManager()
    return _cleanup_manager


# ==============================================================================
# CLI COMMANDS
# ==============================================================================

def run_cleanup_now():
    """Run cleanup immediately (for CLI use)."""
    manager = get_cleanup_manager()
    stats = manager.run_full_cleanup()
    print(f"Cleanup complete: {stats.files_deleted} files deleted, "
          f"{stats.bytes_freed / (1024*1024):.2f}MB freed")
    return stats


def check_disk_status():
    """Check disk status (for CLI use)."""
    manager = get_cleanup_manager()
    status = manager.get_status()
    disk = status["disk_usage"]
    print(f"Disk Usage: {disk['percent_used']}% ({disk['used_gb']}GB / {disk['total_gb']}GB)")
    if disk["is_critical"]:
        print("CRITICAL: Disk space critically low!")
    elif disk["is_warning"]:
        print("WARNING: Disk space running low")
    return status


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "cleanup":
            run_cleanup_now()
        elif sys.argv[1] == "status":
            check_disk_status()
        else:
            print("Usage: python file_cleanup.py [cleanup|status]")
    else:
        check_disk_status()
