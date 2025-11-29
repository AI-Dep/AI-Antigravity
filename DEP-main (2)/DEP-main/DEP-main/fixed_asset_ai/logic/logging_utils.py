import csv
import logging
import sys
from datetime import datetime
from pathlib import Path


def log_event(message: str, log_dir="logs"):
    """
    Append simple text log. For serious environments,
    you'd send this to a database or log service.
    """
    Path(log_dir).mkdir(exist_ok=True)
    logfile = Path(log_dir) / "events.log"
    timestamp = datetime.now().isoformat()
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with the given name

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
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


# Default logger for module
logger = get_logger(__name__)
