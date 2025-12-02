# backend/config/s3_config_loader.py
"""
S3 Configuration Loader for Tax Rules

Fetches tax_rules.json from AWS S3 bucket with local caching and fallback.

CONFIGURATION:
    Set these environment variables:
    - TAX_RULES_S3_BUCKET: S3 bucket name (e.g., fa-cs-automator-config-prod)
    - TAX_RULES_S3_KEY: Object key (default: tax_rules.json)
    - TAX_RULES_S3_REGION: AWS region (default: ap-northeast-2)
    - AWS_ACCESS_KEY_ID: AWS credentials (or use IAM role)
    - AWS_SECRET_ACCESS_KEY: AWS credentials (or use IAM role)

FALLBACK ORDER:
    1. S3 bucket (if configured)
    2. Local file (backend/config/tax_rules.json)
    3. Embedded defaults in tax_year_config.py

CACHING:
    - S3 config is cached locally after successful fetch
    - Cache TTL configurable via TAX_RULES_CACHE_TTL_SECONDS (default: 3600)
    - Cache stored at: backend/config/.tax_rules_cache.json
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_FILENAME = ".tax_rules_cache.json"
DEFAULT_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_s3_config() -> Dict[str, Optional[str]]:
    """Get S3 configuration from environment variables."""
    return {
        "bucket": os.environ.get("TAX_RULES_S3_BUCKET"),
        "key": os.environ.get("TAX_RULES_S3_KEY", "tax_rules.json"),
        "region": os.environ.get("TAX_RULES_S3_REGION", "ap-northeast-2"),
    }


def _get_cache_path() -> Path:
    """Get path to local cache file."""
    config_dir = Path(__file__).parent
    return config_dir / CACHE_FILENAME


def _get_cache_ttl() -> int:
    """Get cache TTL from environment or use default."""
    try:
        return int(os.environ.get("TAX_RULES_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS))
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS


def _is_cache_valid() -> bool:
    """Check if local cache exists and is not expired."""
    cache_path = _get_cache_path()
    if not cache_path.exists():
        return False

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        cached_at = cache_data.get("_cache_meta", {}).get("cached_at", 0)
        ttl = _get_cache_ttl()

        if time.time() - cached_at < ttl:
            return True

        logger.debug(f"Cache expired (age: {time.time() - cached_at:.0f}s, TTL: {ttl}s)")
        return False

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Invalid cache file: {e}")
        return False


def _load_from_cache() -> Optional[Dict[str, Any]]:
    """Load configuration from local cache."""
    cache_path = _get_cache_path()

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        # Remove cache metadata before returning
        config = {k: v for k, v in cache_data.items() if k != "_cache_meta"}

        cache_meta = cache_data.get("_cache_meta", {})
        logger.info(
            f"Loaded tax rules from cache "
            f"(cached: {cache_meta.get('cached_at_str', 'unknown')}, "
            f"source: {cache_meta.get('source', 'unknown')})"
        )
        return config

    except Exception as e:
        logger.warning(f"Failed to load from cache: {e}")
        return None


def _save_to_cache(config: Dict[str, Any], source: str) -> bool:
    """Save configuration to local cache with metadata."""
    cache_path = _get_cache_path()

    try:
        cache_data = config.copy()
        cache_data["_cache_meta"] = {
            "cached_at": time.time(),
            "cached_at_str": datetime.utcnow().isoformat() + "Z",
            "source": source,
            "ttl_seconds": _get_cache_ttl(),
        }

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)

        logger.debug(f"Saved tax rules to cache: {cache_path}")
        return True

    except Exception as e:
        logger.warning(f"Failed to save to cache: {e}")
        return False


def _fetch_from_s3() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Fetch tax rules configuration from S3.

    Returns:
        Tuple of (config_dict, error_message)
        - On success: (config, None)
        - On failure: (None, error_message)
    """
    s3_config = _get_s3_config()

    if not s3_config["bucket"]:
        return None, "S3 bucket not configured (TAX_RULES_S3_BUCKET not set)"

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
    except ImportError:
        return None, "boto3 not installed - run: pip install boto3"

    bucket = s3_config["bucket"]
    key = s3_config["key"]
    region = s3_config["region"]

    logger.info(f"Fetching tax rules from S3: s3://{bucket}/{key}")

    try:
        s3_client = boto3.client('s3', region_name=region)

        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        config = json.loads(content)

        # Log version info
        meta = config.get("_meta", {})
        logger.info(
            f"Successfully loaded tax rules from S3 "
            f"(version: {meta.get('version', 'unknown')}, "
            f"updated: {meta.get('last_updated', 'unknown')})"
        )

        return config, None

    except NoCredentialsError:
        return None, "AWS credentials not configured"
    except EndpointConnectionError as e:
        return None, f"Cannot connect to S3 endpoint: {e}"
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'NoSuchKey':
            return None, f"Config file not found in S3: s3://{bucket}/{key}"
        elif error_code == 'NoSuchBucket':
            return None, f"S3 bucket does not exist: {bucket}"
        elif error_code == 'AccessDenied':
            return None, f"Access denied to S3 bucket: {bucket}"
        else:
            return None, f"S3 error ({error_code}): {e}"
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in S3 config: {e}"
    except Exception as e:
        return None, f"Unexpected error fetching from S3: {e}"


def load_config_from_s3() -> Optional[Dict[str, Any]]:
    """
    Load tax rules configuration from S3 with caching.

    This is the main entry point for S3 configuration loading.

    Behavior:
        1. Check if valid cache exists -> return cached config
        2. Try fetching from S3 -> cache and return
        3. If S3 fails, try returning stale cache (with warning)
        4. Return None if all sources fail

    Returns:
        Configuration dict or None if unavailable
    """
    s3_config = _get_s3_config()

    # If S3 is not configured, return None immediately
    if not s3_config["bucket"]:
        logger.debug("S3 not configured - skipping S3 config loader")
        return None

    # Check for valid cache first
    if _is_cache_valid():
        cached_config = _load_from_cache()
        if cached_config:
            return cached_config

    # Try fetching from S3
    config, error = _fetch_from_s3()

    if config:
        # Success - cache and return
        _save_to_cache(config, f"s3://{s3_config['bucket']}/{s3_config['key']}")
        return config

    # S3 fetch failed
    logger.warning(f"S3 fetch failed: {error}")

    # Try returning stale cache as fallback
    cache_path = _get_cache_path()
    if cache_path.exists():
        logger.warning("Using stale cache as fallback due to S3 failure")
        stale_config = _load_from_cache()
        if stale_config:
            return stale_config

    # All S3-related sources failed
    logger.warning("S3 configuration unavailable - will fall back to local file")
    return None


def invalidate_cache() -> bool:
    """
    Invalidate the local cache, forcing a fresh S3 fetch on next load.

    Returns:
        True if cache was invalidated, False if no cache existed
    """
    cache_path = _get_cache_path()

    if cache_path.exists():
        try:
            cache_path.unlink()
            logger.info("Tax rules cache invalidated")
            return True
        except Exception as e:
            logger.error(f"Failed to invalidate cache: {e}")
            return False

    return False


def get_config_source_info() -> Dict[str, Any]:
    """
    Get information about the current configuration source.

    Useful for debugging and displaying in UI.

    Returns:
        Dict with source information
    """
    s3_config = _get_s3_config()
    cache_path = _get_cache_path()

    info = {
        "s3_configured": bool(s3_config["bucket"]),
        "s3_bucket": s3_config["bucket"],
        "s3_key": s3_config["key"],
        "s3_region": s3_config["region"],
        "cache_path": str(cache_path),
        "cache_exists": cache_path.exists(),
        "cache_valid": _is_cache_valid(),
        "cache_ttl_seconds": _get_cache_ttl(),
    }

    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            cache_meta = cache_data.get("_cache_meta", {})
            info["cache_source"] = cache_meta.get("source")
            info["cache_timestamp"] = cache_meta.get("cached_at_str")
        except Exception:
            pass

    return info


# CLI utility for testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG)

    print("=" * 60)
    print("S3 Config Loader Test")
    print("=" * 60)

    # Show current configuration
    info = get_config_source_info()
    print("\nConfiguration:")
    for key, value in info.items():
        print(f"  {key}: {value}")

    print("\n" + "-" * 60)

    if len(sys.argv) > 1 and sys.argv[1] == "--fetch":
        print("\nAttempting S3 fetch...")
        config = load_config_from_s3()

        if config:
            print("\nSuccess! Configuration loaded:")
            meta = config.get("_meta", {})
            print(f"  Version: {meta.get('version', 'unknown')}")
            print(f"  Updated: {meta.get('last_updated', 'unknown')}")
            print(f"  Years: {list(config.get('supported_years', {}).keys())}")
        else:
            print("\nFailed to load configuration from S3")
            sys.exit(1)

    elif len(sys.argv) > 1 and sys.argv[1] == "--invalidate":
        print("\nInvalidating cache...")
        if invalidate_cache():
            print("Cache invalidated successfully")
        else:
            print("No cache to invalidate")

    else:
        print("\nUsage:")
        print("  python -m backend.config.s3_config_loader --fetch      # Test S3 fetch")
        print("  python -m backend.config.s3_config_loader --invalidate # Clear cache")
