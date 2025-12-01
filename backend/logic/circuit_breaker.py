"""
Fixed Asset AI - Circuit Breaker Pattern

Provides resilience for external API calls (OpenAI, etc.) by:
- Tracking consecutive failures
- Opening circuit after threshold failures
- Auto-fallback to rule engine during outages
- Gradual recovery with half-open state

This prevents cascade failures when OpenAI API is unavailable
and ensures the app remains functional with rule-based classification.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, TypeVar, Optional, Any, Dict
from functools import wraps
from threading import Lock

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, calls go through
    OPEN = "open"          # Failure threshold reached, calls blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitStats:
    """Statistics for circuit breaker monitoring"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    fallback_calls: int = 0
    circuit_opens: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_calls == 0:
            return 100.0
        return (self.successful_calls / self.total_calls) * 100

    @property
    def fallback_rate(self) -> float:
        """Calculate fallback usage rate"""
        if self.total_calls == 0:
            return 0.0
        return (self.fallback_calls / self.total_calls) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Export stats as dictionary"""
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "fallback_calls": self.fallback_calls,
            "circuit_opens": self.circuit_opens,
            "success_rate": f"{self.success_rate:.1f}%",
            "fallback_rate": f"{self.fallback_rate:.1f}%",
        }


class CircuitBreaker:
    """
    Circuit Breaker for external API resilience.

    States:
    - CLOSED: Normal operation, all calls go through
    - OPEN: Too many failures, calls are blocked and fallback is used
    - HALF_OPEN: Testing recovery, allowing limited calls through

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        # With decorator
        @breaker.protect(fallback=rule_based_classify)
        def gpt_classify(description):
            return openai_client.classify(description)

        # Or manual
        result = breaker.call(
            primary_func=lambda: gpt_classify(desc),
            fallback_func=lambda: rule_classify(desc)
        )
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 2,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker
            failure_threshold: Consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before trying again (half-open)
            half_open_max_calls: Max calls allowed in half-open state
            success_threshold: Successes needed in half-open to close circuit
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = Lock()

        self.stats = CircuitStats()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for recovery timeout"""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                    logger.info(f"Circuit '{self.name}' entering HALF_OPEN state")
            return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)"""
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)"""
        return self.state == CircuitState.CLOSED

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to try recovery"""
        if self._last_failure_time is None:
            return True
        return (time.time() - self._last_failure_time) >= self.recovery_timeout

    def record_success(self):
        """Record a successful call"""
        with self._lock:
            self._failure_count = 0
            self.stats.successful_calls += 1
            self.stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    logger.info(f"Circuit '{self.name}' CLOSED - service recovered")

    def _is_rate_limit_error(self, error: Optional[Exception]) -> bool:
        """Check if error is a rate limit (429) response - shouldn't open circuit."""
        if error is None:
            return False

        # Check for common rate limit indicators
        error_str = str(error).lower()
        if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
            return True

        # Check for status_code attribute (requests/httpx style)
        if hasattr(error, 'status_code') and error.status_code == 429:
            return True

        # Check for response attribute with status_code
        if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
            if error.response.status_code == 429:
                return True

        return False

    def record_failure(self, error: Optional[Exception] = None):
        """Record a failed call.

        Note: Rate limit (429) errors are NOT counted as failures since they
        indicate the service is healthy but throttling - circuit should stay closed.
        """
        # SAFETY: Don't count rate limits as circuit-breaking failures
        if self._is_rate_limit_error(error):
            logger.info(f"Circuit '{self.name}': Rate limit detected - not counting as failure")
            self.stats.failed_calls += 1  # Still count for stats
            return  # Don't increment failure_count or potentially open circuit

        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            self.stats.failed_calls += 1
            self.stats.last_failure_time = time.time()

            if error:
                logger.warning(f"Circuit '{self.name}' failure #{self._failure_count}: {error}")

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens circuit
                self._state = CircuitState.OPEN
                self.stats.circuit_opens += 1
                logger.warning(f"Circuit '{self.name}' OPEN - recovery failed")

            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self.stats.circuit_opens += 1
                logger.warning(
                    f"Circuit '{self.name}' OPEN after {self._failure_count} failures. "
                    f"Fallback will be used for {self.recovery_timeout}s"
                )

    def record_fallback(self):
        """Record that fallback was used"""
        with self._lock:
            self.stats.fallback_calls += 1

    def allow_request(self) -> bool:
        """Check if a request should be allowed through"""
        state = self.state

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.OPEN:
            return False

        # HALF_OPEN: allow limited calls
        with self._lock:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def call(
        self,
        primary_func: Callable[[], T],
        fallback_func: Callable[[], T],
        record_stats: bool = True,
    ) -> T:
        """
        Execute call with circuit breaker protection.

        Args:
            primary_func: Primary function to call (e.g., OpenAI API)
            fallback_func: Fallback function (e.g., rule engine)
            record_stats: Whether to record call statistics

        Returns:
            Result from primary_func or fallback_func
        """
        if record_stats:
            self.stats.total_calls += 1

        if not self.allow_request():
            # Circuit is open, use fallback
            if record_stats:
                self.record_fallback()
            logger.debug(f"Circuit '{self.name}' open, using fallback")
            return fallback_func()

        try:
            result = primary_func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            if record_stats:
                self.record_fallback()
            logger.info(f"Circuit '{self.name}' primary failed, using fallback: {e}")
            return fallback_func()

    def protect(
        self,
        fallback: Optional[Callable] = None,
        fallback_value: Any = None,
    ):
        """
        Decorator to protect a function with circuit breaker.

        Args:
            fallback: Fallback function with same signature
            fallback_value: Static value to return on fallback (if no fallback func)

        Example:
            @breaker.protect(fallback=rule_classify)
            def gpt_classify(description):
                return openai.classify(description)
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            def wrapper(*args, **kwargs) -> T:
                self.stats.total_calls += 1

                if not self.allow_request():
                    self.record_fallback()
                    if fallback:
                        return fallback(*args, **kwargs)
                    return fallback_value

                try:
                    result = func(*args, **kwargs)
                    self.record_success()
                    return result
                except Exception as e:
                    self.record_failure(e)
                    self.record_fallback()
                    if fallback:
                        return fallback(*args, **kwargs)
                    return fallback_value

            return wrapper
        return decorator

    def reset(self):
        """Reset circuit breaker to initial state"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0
            logger.info(f"Circuit '{self.name}' reset to CLOSED")

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "stats": self.stats.to_dict(),
        }


# =============================================================================
# GLOBAL CIRCUIT BREAKERS
# =============================================================================

# Circuit breaker for OpenAI API calls
openai_breaker = CircuitBreaker(
    name="openai",
    failure_threshold=5,      # Open after 5 consecutive failures
    recovery_timeout=60.0,    # Try recovery after 60 seconds
    half_open_max_calls=3,    # Allow 3 test calls in half-open
    success_threshold=2,      # Need 2 successes to close
)

# Circuit breaker for any external API
external_api_breaker = CircuitBreaker(
    name="external_api",
    failure_threshold=3,
    recovery_timeout=30.0,
    half_open_max_calls=2,
    success_threshold=1,
)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def classify_with_fallback(
    description: str,
    client_category: Optional[str] = None,
    gpt_classifier: Optional[Callable] = None,
    rule_classifier: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Classify asset with automatic fallback to rule engine.

    Uses circuit breaker to detect OpenAI API issues and
    automatically falls back to rule-based classification.

    Args:
        description: Asset description to classify
        client_category: Optional client-provided category
        gpt_classifier: GPT classification function
        rule_classifier: Rule-based classification function

    Returns:
        Classification result dict with source indicator
    """
    # If no classifiers provided, return basic fallback
    if not gpt_classifier and not rule_classifier:
        return {
            "category": client_category or "Unclassified",
            "confidence": 0.0,
            "source": "fallback_none",
            "reason": "No classifiers available",
        }

    # If only rule classifier, use it directly
    if not gpt_classifier:
        result = rule_classifier(description, client_category)
        result["source"] = "rule_engine"
        return result

    # If only GPT classifier, use it with basic fallback
    if not rule_classifier:
        def basic_fallback():
            return {
                "category": client_category or "Unclassified",
                "confidence": 0.0,
                "source": "fallback_client_category",
            }

        return openai_breaker.call(
            primary_func=lambda: {**gpt_classifier(description), "source": "gpt"},
            fallback_func=basic_fallback,
        )

    # Both available - use circuit breaker
    def gpt_call():
        result = gpt_classifier(description)
        result["source"] = "gpt"
        return result

    def rule_call():
        result = rule_classifier(description, client_category)
        result["source"] = "rule_engine_fallback"
        return result

    return openai_breaker.call(
        primary_func=gpt_call,
        fallback_func=rule_call,
    )


def get_circuit_status() -> Dict[str, Any]:
    """Get status of all circuit breakers"""
    return {
        "openai": openai_breaker.get_status(),
        "external_api": external_api_breaker.get_status(),
    }


def reset_all_circuits():
    """Reset all circuit breakers to closed state"""
    openai_breaker.reset()
    external_api_breaker.reset()
    logger.info("All circuit breakers reset")
