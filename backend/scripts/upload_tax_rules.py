#!/usr/bin/env python3
"""
Tax Rules S3 Uploader

Uploads combined tax rules to S3 bucket for remote distribution.
Run this when tax rules change (e.g., IRS updates Section 179 limits).

Usage:
    python upload_tax_rules.py --bucket YOUR_BUCKET_NAME

Prerequisites:
    - AWS CLI configured with appropriate credentials
    - Or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def load_local_rules() -> dict:
    """Load and combine all local tax rule files."""
    config_dir = Path(__file__).parent.parent / "logic" / "config"

    rules = {
        "version": datetime.now().strftime("%Y.%m.%d"),
        "last_updated": datetime.now().isoformat(),
        "updated_by": os.environ.get("USER", "admin"),
        "rules": {}
    }

    # Files to include
    rule_files = [
        "section179.json",
        "bonus.json",
        "macrs_life.json",
        "conventions.json",
        "qip.json",
        "qpp.json",
        "classification_keywords.json",
    ]

    for filename in rule_files:
        filepath = config_dir / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    key = filename.replace('.json', '')
                    rules["rules"][key] = json.load(f)
                    print(f"  ✓ Loaded {filename}")
            except Exception as e:
                print(f"  ✗ Failed to load {filename}: {e}")
        else:
            print(f"  - Skipped {filename} (not found)")

    return rules


def upload_to_s3(rules: dict, bucket: str, key: str = "tax_rules.json", region: str = "us-east-1") -> bool:
    """Upload rules to S3 bucket."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        s3_client = boto3.client('s3', region_name=region)

        # Convert to JSON
        json_content = json.dumps(rules, indent=2)

        # Upload
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json_content.encode('utf-8'),
            ContentType='application/json',
            # Make publicly readable (optional - remove if bucket is private)
            # ACL='public-read'
        )

        print(f"\n✓ Successfully uploaded to s3://{bucket}/{key}")
        print(f"  Version: {rules['version']}")
        print(f"  Size: {len(json_content)} bytes")

        return True

    except ImportError:
        print("\n✗ boto3 not installed. Install with: pip install boto3")
        return False
    except ClientError as e:
        print(f"\n✗ S3 upload failed: {e}")
        return False


def save_local_combined(rules: dict, output_path: Path) -> None:
    """Save combined rules locally for reference."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=2)
    print(f"\n✓ Saved local copy to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Upload tax rules to S3")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--key", default="tax_rules.json", help="S3 object key")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--local-only", action="store_true", help="Only save locally, don't upload")

    args = parser.parse_args()

    print("=" * 60)
    print("Tax Rules S3 Uploader")
    print("=" * 60)

    # Load rules
    print("\nLoading local tax rules...")
    rules = load_local_rules()

    # Save local combined copy
    local_output = Path(__file__).parent.parent / "logic" / "config" / "tax_rules_combined.json"
    save_local_combined(rules, local_output)

    if args.local_only:
        print("\n--local-only specified, skipping S3 upload")
        return

    # Upload to S3
    print(f"\nUploading to S3 bucket: {args.bucket}")
    success = upload_to_s3(rules, args.bucket, args.key, args.region)

    if success:
        print("\n" + "=" * 60)
        print("SUCCESS! Tax rules are now available at:")
        print(f"  s3://{args.bucket}/{args.key}")
        print("\nClients will automatically fetch updates on next startup.")
        print("=" * 60)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
