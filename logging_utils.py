"""
Fixed Asset AI - Logging Framework

Provides centralized logging with:
- Console output for development
- File logging with rotation for production
- Separate audit trail for tax-critical operations
- Performance timing utilities
"""

import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from functools import wraps
from typing import Optional, Callable, Any

# Default log directory
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Log levels
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL


def setup_logging(
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_dir: str = "logs",
    max_bytes: int = 5_000_000,  # 5MB
    backup_count: int = 3
) -> None:
    """
    Configure global logging settings.

    Args:
        level: Minimum log level
        log_to_file: Whether to write logs to file
        log_dir: Directory for log files
        max_bytes: Max size per log file before rotation
        backup_count: Number of backup files to keep
    """
    global LOG_DIR
    LOG_DIR = Path(log_dir)
    LOG_DIR.mkdir(exist_ok=True)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_to_file:
        file_handler = RotatingFileHandler(
            LOG_DIR / "fixed_asset_ai.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers and not logger.parent.handlers:
        logger.setLevel(logging.INFO)

        # Console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)

        # Format with timestamp and level
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger


def log_event(message: str, log_dir: str = "logs") -> None:
    """
    Append simple text log for backward compatibility.

    Args:
        message: Message to log
        log_dir: Directory for log files
    """
    Path(log_dir).mkdir(exist_ok=True)
    logfile = Path(log_dir) / "events.log"
    timestamp = datetime.now().isoformat()
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


# ==============================================================================
# AUDIT TRAIL LOGGING (Tax-critical operations)
# ==============================================================================

def log_audit_event(
    event_type: str,
    asset_id: str,
    details: dict,
    user: str = "system"
) -> None:
    """
    Log audit trail event for tax-critical operations.

    These logs provide an audit trail for IRS compliance.

    Args:
        event_type: Type of event (e.g., "CLASSIFICATION_OVERRIDE", "EXPORT")
        asset_id: Asset identifier
        details: Dictionary of event details
        user: User who performed the action
    """
    audit_file = LOG_DIR / "audit_trail.csv"

    # Create file with headers if it doesn't exist
    if not audit_file.exists():
        with open(audit_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp", "Event Type", "Asset ID", "User", "Details"
            ])

    # Append audit event
    with open(audit_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            event_type,
            asset_id,
            user,
            str(details)
        ])


# ==============================================================================
# PERFORMANCE TIMING
# ==============================================================================

def timed(func: Callable) -> Callable:
    """
    Decorator to log function execution time.

    Usage:
        @timed
        def my_function():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        logger = get_logger(func.__module__)
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__name__} completed in {elapsed:.2f}s")
        return result
    return wrapper


def log_performance(operation: str, start_time: float) -> None:
    """
    Log performance timing for an operation.

    Args:
        operation: Name of the operation
        start_time: Start time from time.time()
    """
    elapsed = time.time() - start_time
    logger = get_logger("performance")
    logger.info(f"{operation}: {elapsed:.2f}s")


# ==============================================================================
# ERROR LOGGING
# ==============================================================================

def log_error(
    error: Exception,
    context: str,
    logger_name: Optional[str] = None
) -> str:
    """
    Log an error with context and return a user-friendly message.

    Args:
        error: The exception that occurred
        context: What was happening when the error occurred
        logger_name: Optional logger name

    Returns:
        User-friendly error message (without sensitive details)
    """
    logger = get_logger(logger_name or "error")
    logger.error(f"{context}: {type(error).__name__}: {str(error)}", exc_info=True)

    # Return sanitized message for user display
    return f"An error occurred while {context}. Please try again."


# Default logger for module
logger = get_logger(__name__)
