"""
Request Timeout Middleware for FA CS Automator

Implements request timeouts to prevent:
- Long-running requests blocking workers
- Runaway processing consuming resources
- Poor user experience from hanging requests

Features:
- Configurable timeout per operation type
- Graceful timeout handling
- Proper cleanup on timeout
"""

import asyncio
import logging
from typing import Dict, Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# Default timeouts by operation (in seconds)
DEFAULT_TIMEOUTS = {
    "upload": 120,      # File uploads can be slow
    "export": 60,       # Export generation
    "classify": 90,     # Classification with AI
    "default": 30,      # Standard requests
    "health": 5,        # Health checks
}


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces request timeouts.

    Usage:
        app.add_middleware(TimeoutMiddleware, default_timeout=30)
    """

    def __init__(self, app, default_timeout: int = 30, timeouts: Dict[str, int] = None):
        super().__init__(app)
        self.default_timeout = default_timeout
        self.timeouts = timeouts or DEFAULT_TIMEOUTS

    def _get_timeout(self, request: Request) -> int:
        """Determine timeout based on request path."""
        path = request.url.path.lower()

        if "/upload" in path:
            return self.timeouts.get("upload", 120)
        elif "/export" in path:
            return self.timeouts.get("export", 60)
        elif "/classify" in path:
            return self.timeouts.get("classify", 90)
        elif path in ["/", "/health", "/check-facs"]:
            return self.timeouts.get("health", 5)
        else:
            return self.timeouts.get("default", self.default_timeout)

    async def dispatch(self, request: Request, call_next):
        timeout = self._get_timeout(request)

        try:
            # Wrap the request handler in a timeout
            response = await asyncio.wait_for(
                call_next(request),
                timeout=timeout
            )
            return response

        except asyncio.TimeoutError:
            logger.warning(
                f"Request timeout: path={request.url.path}, "
                f"method={request.method}, timeout={timeout}s"
            )

            return JSONResponse(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                content={
                    "error": "Request timeout",
                    "detail": f"Request took longer than {timeout} seconds",
                    "path": str(request.url.path),
                    "suggestion": "Try with a smaller file or fewer assets"
                }
            )

        except Exception as e:
            logger.error(f"Unexpected error in timeout middleware: {e}")
            raise


class AsyncTimeout:
    """
    Context manager for async timeouts.

    Usage:
        async with AsyncTimeout(30):
            await long_running_operation()
    """

    def __init__(self, seconds: int, message: str = None):
        self.seconds = seconds
        self.message = message or f"Operation timed out after {seconds} seconds"
        self._task = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def start(self) -> 'AsyncTimeout':
        """Start the timeout timer."""
        async def _timeout_handler():
            await asyncio.sleep(self.seconds)
            raise asyncio.TimeoutError(self.message)

        self._task = asyncio.create_task(_timeout_handler())
        return self

    def cancel(self):
        """Cancel the timeout."""
        if self._task and not self._task.done():
            self._task.cancel()


def with_timeout(seconds: int):
    """
    Decorator to add timeout to async functions.

    Usage:
        @with_timeout(30)
        async def process_file(file):
            ...
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                    detail=f"Operation timed out after {seconds} seconds"
                )

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
