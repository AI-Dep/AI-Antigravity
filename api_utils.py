# fixed_asset_ai/logic/api_utils.py

import time
import logging
from typing import Callable, Any, Optional, TypeVar
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

T = TypeVar('T')


def _is_auth_error(exception: Exception) -> bool:
    """
    Detect if an exception is an authentication/authorization error.

    These errors should NOT be retried as they indicate invalid credentials
    or permissions, not transient network issues.

    Args:
        exception: The exception to check

    Returns:
        True if this is an auth error that should not be retried
    """
    # Check exception type name
    exception_type = type(exception).__name__
    if exception_type in ['AuthenticationError', 'PermissionError', 'Unauthorized']:
        return True

    # Check error message for auth-related keywords
    error_msg = str(exception).lower()
    auth_keywords = [
        'unauthorized', 'authentication', 'invalid api key',
        'invalid_api_key', 'incorrect api key', 'api key',
        '401', '403', 'forbidden', 'permission denied',
        'access denied', 'invalid credentials'
    ]

    if any(keyword in error_msg for keyword in auth_keywords):
        return True

    # Check if exception has status_code attribute (common in HTTP libraries)
    if hasattr(exception, 'status_code'):
        if exception.status_code in [401, 403]:
            return True

    # Check for response attribute with status_code (requests library pattern)
    if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
        if exception.response.status_code in [401, 403]:
            return True

    return False


def retry_with_exponential_backoff(
    max_retries: int = 4,
    initial_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 4)
        initial_delay: Initial delay in seconds before first retry (default: 2.0)
        max_delay: Maximum delay between retries in seconds (default: 60.0)
        exponential_base: Base for exponential backoff calculation (default: 2.0)
        exceptions: Tuple of exceptions to catch and retry (default: all Exception)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_exponential_backoff(max_retries=3, initial_delay=1.0)
        def call_api():
            return client.api_call()
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            retries = 0
            delay = initial_delay

            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    # CRITICAL: Don't retry authentication errors
                    # They indicate bad credentials, not transient network issues
                    if _is_auth_error(e):
                        logger.error(
                            f"{func.__name__} failed due to authentication error. "
                            f"Error: {type(e).__name__}: {str(e)}\n"
                            f"Fix: Check your API key/credentials and try again."
                        )
                        raise

                    retries += 1

                    if retries > max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} retries. "
                            f"Last error: {type(e).__name__}: {str(e)}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    wait_time = min(delay, max_delay)
                    logger.warning(
                        f"{func.__name__} failed (attempt {retries}/{max_retries}). "
                        f"Retrying in {wait_time:.1f}s... Error: {type(e).__name__}: {str(e)}"
                    )

                    time.sleep(wait_time)
                    delay *= exponential_base

            # This should never be reached, but added for type safety
            raise Exception(f"{func.__name__} failed after all retries")

        return wrapper

    return decorator


def safe_api_call(
    func: Callable[..., T],
    *args,
    fallback_value: Optional[T] = None,
    log_errors: bool = True,
    **kwargs
) -> Optional[T]:
    """
    Safely execute an API call with graceful error handling.

    Args:
        func: Function to execute
        *args: Positional arguments for the function
        fallback_value: Value to return if the call fails (default: None)
        log_errors: Whether to log errors (default: True)
        **kwargs: Keyword arguments for the function

    Returns:
        Result of func() or fallback_value if an exception occurs

    Example:
        result = safe_api_call(client.embeddings.create, model="text-embedding-3-small", input=["text"])
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"API call failed: {func.__name__} - {type(e).__name__}: {str(e)}")
        return fallback_value


# OpenAI-specific retry configurations
OPENAI_RETRY_CONFIG = {
    "max_retries": 4,
    "initial_delay": 2.0,
    "max_delay": 60.0,
    "exponential_base": 2.0,
    # Common OpenAI exceptions to retry
    "exceptions": (
        Exception,  # Catch all for network issues, rate limits, etc.
    ),
}


def openai_retry(func: Callable[..., T]) -> Callable[..., T]:
    """
    Convenience decorator with OpenAI-optimized retry settings.

    Example:
        @openai_retry
        def get_embedding(client, text):
            return client.embeddings.create(model="text-embedding-3-small", input=[text])
    """
    return retry_with_exponential_backoff(**OPENAI_RETRY_CONFIG)(func)


# =============================================================================
# CIRCUIT BREAKER INTEGRATION
# =============================================================================

def resilient_api_call(
    primary_func: Callable[..., T],
    fallback_func: Callable[..., T],
    *args,
    use_retry: bool = True,
    use_circuit_breaker: bool = True,
    **kwargs
) -> T:
    """
    Execute API call with both retry and circuit breaker protection.

    Combines:
    1. Retry with exponential backoff for transient failures
    2. Circuit breaker for sustained outages (auto-fallback)

    Args:
        primary_func: Primary API function to call
        fallback_func: Fallback function when primary fails
        *args: Arguments to pass to both functions
        use_retry: Whether to use retry logic (default: True)
        use_circuit_breaker: Whether to use circuit breaker (default: True)
        **kwargs: Keyword arguments to pass to both functions

    Returns:
        Result from primary_func or fallback_func

    Example:
        result = resilient_api_call(
            primary_func=lambda desc: gpt_classify(desc),
            fallback_func=lambda desc: rule_classify(desc),
            description
        )
    """
    from .circuit_breaker import openai_breaker

    def execute_primary():
        if use_retry:
            @retry_with_exponential_backoff(**OPENAI_RETRY_CONFIG)
            def with_retry():
                return primary_func(*args, **kwargs)
            return with_retry()
        return primary_func(*args, **kwargs)

    def execute_fallback():
        return fallback_func(*args, **kwargs)

    if use_circuit_breaker:
        return openai_breaker.call(
            primary_func=execute_primary,
            fallback_func=execute_fallback,
        )
    else:
        try:
            return execute_primary()
        except Exception as e:
            logger.warning(f"Primary call failed, using fallback: {e}")
            return execute_fallback()
