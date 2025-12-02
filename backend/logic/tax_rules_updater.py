"""
Tax Rules Auto-Updater

Fetches latest tax rules from S3 bucket on startup.
Allows updating Section 179 limits, Bonus rates, etc. without app updates.

Usage:
    from backend.logic.tax_rules_updater import check_and_update_tax_rules

    # On startup
    await check_and_update_tax_rules()

Configuration (via environment variables or config.json):
    TAX_RULES_S3_BUCKET: S3 bucket name
    TAX_RULES_S3_KEY: S3 object key (default: tax_rules.json)
    TAX_RULES_S3_REGION: AWS region (default: us-east-1)
    AWS_ACCESS_KEY_ID: AWS credentials (optional if using IAM roles)
    AWS_SECRET_ACCESS_KEY: AWS credentials (optional if using IAM roles)
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Local path where tax rules are stored
LOCAL_RULES_DIR = Path(__file__).parent / "config"
LOCAL_RULES_FILE = LOCAL_RULES_DIR / "tax_rules.json"
LOCAL_RULES_HASH_FILE = LOCAL_RULES_DIR / ".tax_rules_hash"

# S3 Configuration (from environment)
def get_s3_config() -> Dict[str, str]:
    """Get S3 configuration from environment variables."""
    return {
        "bucket": os.getenv("TAX_RULES_S3_BUCKET", ""),
        "key": os.getenv("TAX_RULES_S3_KEY", "tax_rules.json"),
        "region": os.getenv("TAX_RULES_S3_REGION", "us-east-1"),
    }


# ==============================================================================
# S3 FETCHER
# ==============================================================================

async def fetch_from_s3(bucket: str, key: str, region: str) -> Optional[Dict[str, Any]]:
    """
    Fetch tax rules JSON from S3 bucket.

    Uses boto3 if available, falls back to HTTP request for public buckets.
    """
    try:
        # Try boto3 first (supports private buckets with credentials)
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        try:
            s3_client = boto3.client('s3', region_name=region)
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            data = json.loads(content)

            logger.info(f"Successfully fetched tax rules from s3://{bucket}/{key}")
            return data

        except NoCredentialsError:
            logger.warning("AWS credentials not found, trying public URL...")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"Tax rules file not found in S3: {key}")
                return None
            raise

    except ImportError:
        logger.info("boto3 not installed, trying public URL...")

    # Fallback: Try public S3 URL (for public buckets)
    try:
        import aiohttp

        public_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

        async with aiohttp.ClientSession() as session:
            async with session.get(public_url, timeout=10) as response:
                if response.status == 200:
                    content = await response.text()
                    data = json.loads(content)
                    logger.info(f"Successfully fetched tax rules from public URL")
                    return data
                else:
                    logger.warning(f"Failed to fetch from public URL: HTTP {response.status}")
                    return None

    except ImportError:
        logger.warning("aiohttp not installed, cannot fetch from public URL")
    except Exception as e:
        logger.warning(f"Failed to fetch from public URL: {e}")

    return None


def compute_hash(data: Dict[str, Any]) -> str:
    """Compute SHA256 hash of JSON data for change detection."""
    json_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()


def get_local_hash() -> Optional[str]:
    """Get hash of currently installed tax rules."""
    try:
        if LOCAL_RULES_HASH_FILE.exists():
            return LOCAL_RULES_HASH_FILE.read_text().strip()
    except Exception:
        pass
    return None


def save_local_hash(hash_value: str) -> None:
    """Save hash of current tax rules."""
    try:
        LOCAL_RULES_HASH_FILE.write_text(hash_value)
    except Exception as e:
        logger.warning(f"Could not save rules hash: {e}")


def save_tax_rules(data: Dict[str, Any]) -> bool:
    """
    Save updated tax rules to local config directory.
    Creates a backup of existing rules first.
    """
    try:
        # Create backup of existing rules
        if LOCAL_RULES_FILE.exists():
            backup_path = LOCAL_RULES_FILE.with_suffix('.json.bak')
            LOCAL_RULES_FILE.rename(backup_path)
            logger.info(f"Backed up existing rules to {backup_path}")

        # Save new rules
        LOCAL_RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCAL_RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        # Save hash for future comparison
        save_local_hash(compute_hash(data))

        logger.info(f"Saved updated tax rules to {LOCAL_RULES_FILE}")
        return True

    except Exception as e:
        logger.error(f"Failed to save tax rules: {e}")
        return False


# ==============================================================================
# MAIN UPDATE FUNCTION
# ==============================================================================

async def check_and_update_tax_rules() -> Dict[str, Any]:
    """
    Check S3 for updated tax rules and download if newer version available.

    Returns:
        Dict with update status:
        - updated: bool - Whether rules were updated
        - version: str - Current rules version
        - source: str - Where rules came from ('s3', 'local', 'bundled')
        - message: str - Human-readable status message
    """
    result = {
        "updated": False,
        "version": "unknown",
        "source": "bundled",
        "message": "Using bundled tax rules",
        "timestamp": datetime.now().isoformat(),
    }

    # Get S3 configuration
    s3_config = get_s3_config()

    if not s3_config["bucket"]:
        logger.info("S3 bucket not configured, using local tax rules")
        result["message"] = "S3 not configured, using local rules"
        return result

    logger.info(f"Checking for tax rules updates from s3://{s3_config['bucket']}/{s3_config['key']}")

    try:
        # Fetch from S3
        remote_data = await fetch_from_s3(
            s3_config["bucket"],
            s3_config["key"],
            s3_config["region"]
        )

        if remote_data is None:
            logger.info("Could not fetch remote rules, using local copy")
            result["message"] = "S3 fetch failed, using local rules"
            result["source"] = "local"
            return result

        # Check if update is needed
        remote_hash = compute_hash(remote_data)
        local_hash = get_local_hash()

        if remote_hash == local_hash:
            logger.info("Tax rules are up to date")
            result["message"] = "Tax rules are current"
            result["source"] = "local"
            result["version"] = remote_data.get("version", "unknown")
            return result

        # New version available - update local copy
        logger.info("New tax rules version detected, updating...")

        if save_tax_rules(remote_data):
            result["updated"] = True
            result["source"] = "s3"
            result["version"] = remote_data.get("version", "unknown")
            result["message"] = f"Updated to version {result['version']} from S3"
            logger.info(f"Tax rules updated successfully: {result['message']}")
        else:
            result["message"] = "Failed to save updated rules"
            logger.error("Failed to save tax rules update")

    except Exception as e:
        logger.error(f"Error checking for tax rules updates: {e}")
        result["message"] = f"Update check failed: {str(e)}"

    return result


# ==============================================================================
# COMBINED RULES LOADER
# ==============================================================================

def load_all_tax_rules() -> Dict[str, Any]:
    """
    Load all tax rules from the config directory.
    Combines individual JSON files into a single structure.
    """
    rules = {
        "version": "local",
        "last_updated": datetime.now().isoformat(),
        "section179": {},
        "bonus": {},
        "macrs": {},
        "conventions": {},
    }

    config_dir = LOCAL_RULES_DIR

    # Load individual rule files
    rule_files = {
        "section179": "section179.json",
        "bonus": "bonus.json",
        "macrs_life": "macrs_life.json",
        "conventions": "conventions.json",
        "qip": "qip.json",
        "qpp": "qpp.json",
    }

    for key, filename in rule_files.items():
        filepath = config_dir / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    rules[key] = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load {filename}: {e}")

    return rules


# ==============================================================================
# CLI FOR TESTING
# ==============================================================================

if __name__ == "__main__":
    import asyncio

    async def main():
        print("Checking for tax rules updates...")
        result = await check_and_update_tax_rules()
        print(f"Result: {json.dumps(result, indent=2)}")

    asyncio.run(main())
