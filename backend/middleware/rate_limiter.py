"""
Rate Limiting Middleware for FA CS Automator

Implements token bucket algorithm for API rate limiting:
- Per-IP rate limiting for anonymous requests
- Per-user rate limiting for authenticated requests
- Separate limits for expensive operations (upload, classify, AI calls)

This prevents:
- DDoS attacks
- API abuse
- Runaway OpenAI API costs
"""

import time
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit bucket."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10  # Allow short bursts


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    tokens: float
    last_update: float
    rate: float  # tokens per second
    capacity: float

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        now = time.time()

        # Refill tokens based on time elapsed
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def retry_after(self) -> int:
        """Seconds until a token is available."""
        if self.tokens >= 1:
            return 0
        return int((1 - self.tokens) / self.rate) + 1


class RateLimiter:
    """
    Rate limiter with multiple buckets for different operation types.

    Usage:
        limiter = RateLimiter()

        @app.post("/upload")
        async def upload(request: Request):
            await limiter.check(request, operation="upload")
            # ... handle upload
    """

    # Default rate limits by operation type
    DEFAULT_LIMITS = {
        "default": RateLimitConfig(requests_per_minute=60, burst_size=10),
        "upload": RateLimitConfig(requests_per_minute=10, burst_size=3),
        "classify": RateLimitConfig(requests_per_minute=20, burst_size=5),
        "ai_call": RateLimitConfig(requests_per_minute=30, burst_size=5),
        "export": RateLimitConfig(requests_per_minute=20, burst_size=5),
        "read": RateLimitConfig(requests_per_minute=120, burst_size=20),
    }

    def __init__(self, limits: Optional[Dict[str, RateLimitConfig]] = None):
        self.limits = limits or self.DEFAULT_LIMITS
        # Buckets stored by (client_id, operation_type)
        self._buckets: Dict[tuple, TokenBucket] = {}
        self._cleanup_interval = 300  # Clean old buckets every 5 minutes
        self._last_cleanup = time.time()
        self._lock = asyncio.Lock()

    def _get_client_id(self, request: Request, user_id: Optional[str] = None) -> str:
        """Get client identifier from request."""
        if user_id:
            return f"user:{user_id}"

        # Use X-Forwarded-For if behind proxy, otherwise use client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take first IP in chain
            return f"ip:{forwarded.split(',')[0].strip()}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    async def _get_or_create_bucket(self, client_id: str, operation: str) -> TokenBucket:
        """Get existing bucket or create new one (thread-safe)."""
        key = (client_id, operation)

        # Fast path: bucket exists
        if key in self._buckets:
            return self._buckets[key]

        # Slow path: need to create bucket, use lock to prevent race
        async with self._lock:
            # Double-check after acquiring lock
            if key not in self._buckets:
                config = self.limits.get(operation, self.limits["default"])
                rate = config.requests_per_minute / 60.0  # Convert to per-second
                self._buckets[key] = TokenBucket(
                    tokens=config.burst_size,
                    last_update=time.time(),
                    rate=rate,
                    capacity=config.burst_size
                )

            return self._buckets[key]

    async def _cleanup_old_buckets(self):
        """Remove buckets that haven't been used in a while."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        async with self._lock:
            self._last_cleanup = now
            stale_keys = []

            for key, bucket in self._buckets.items():
                # Remove buckets unused for 10 minutes
                if now - bucket.last_update > 600:
                    stale_keys.append(key)

            for key in stale_keys:
                del self._buckets[key]

            if stale_keys:
                logger.debug(f"Cleaned up {len(stale_keys)} stale rate limit buckets")

    async def check(
        self,
        request: Request,
        operation: str = "default",
        user_id: Optional[str] = None,
        tokens: int = 1
    ) -> None:
        """
        Check rate limit and raise HTTPException if exceeded.

        Args:
            request: FastAPI request object
            operation: Type of operation (upload, classify, etc.)
            user_id: Optional user ID for per-user limiting
            tokens: Number of tokens to consume (default 1)

        Raises:
            HTTPException: 429 Too Many Requests if rate limit exceeded
        """
        # Periodic cleanup
        await self._cleanup_old_buckets()

        client_id = self._get_client_id(request, user_id)
        bucket = await self._get_or_create_bucket(client_id, operation)

        if not bucket.consume(tokens):
            retry_after = bucket.retry_after
            logger.warning(
                f"Rate limit exceeded: client={client_id}, operation={operation}, "
                f"retry_after={retry_after}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "operation": operation,
                    "retry_after_seconds": retry_after,
                    "message": f"Too many requests. Please wait {retry_after} seconds."
                },
                headers={"Retry-After": str(retry_after)}
            )

    def get_remaining(self, request: Request, operation: str = "default", user_id: Optional[str] = None) -> int:
        """Get remaining requests for this client/operation."""
        client_id = self._get_client_id(request, user_id)
        key = (client_id, operation)

        if key not in self._buckets:
            config = self.limits.get(operation, self.limits["default"])
            return config.burst_size

        return int(self._buckets[key].tokens)


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def rate_limit_middleware(request: Request, call_next):
    """
    FastAPI middleware for rate limiting.

    Add to app with:
        app.middleware("http")(rate_limit_middleware)
    """
    limiter = get_rate_limiter()

    # Determine operation type from path
    path = request.url.path.lower()

    if "/upload" in path:
        operation = "upload"
    elif "/classify" in path:
        operation = "classify"
    elif "/export" in path:
        operation = "export"
    elif request.method == "GET":
        operation = "read"
    else:
        operation = "default"

    try:
        await limiter.check(request, operation=operation)
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content=e.detail,
            headers=e.headers
        )

    response = await call_next(request)

    # Add rate limit headers
    remaining = limiter.get_remaining(request, operation)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Operation"] = operation

    return response


# Decorator for endpoint-specific rate limiting
def rate_limit(operation: str = "default", tokens: int = 1):
    """
    Decorator for rate limiting specific endpoints.

    Usage:
        @app.post("/upload")
        @rate_limit(operation="upload", tokens=2)
        async def upload_file(request: Request):
            ...
    """
    def decorator(func: Callable):
        async def wrapper(request: Request, *args, **kwargs):
            limiter = get_rate_limiter()
            await limiter.check(request, operation=operation, tokens=tokens)
            return await func(request, *args, **kwargs)

        # Preserve function metadata
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
