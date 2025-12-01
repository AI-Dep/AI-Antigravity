#!/usr/bin/env python3
"""
License Generator for FA CS Automator

VENDOR-SIDE TOOL - DO NOT DISTRIBUTE TO CUSTOMERS

This tool generates cryptographically signed license keys.
The private key used for signing must be kept secure.

Usage:
    # Generate new key pair
    python -m backend.licensing.license_generator --generate-keys

    # Generate a license
    python -m backend.licensing.license_generator \\
        --customer "Acme CPA Firm" \\
        --email "admin@acme.com" \\
        --edition professional \\
        --seats 5 \\
        --days 365 \\
        --output license.key

    # Generate trial license
    python -m backend.licensing.license_generator \\
        --customer "Trial User" \\
        --email "trial@example.com" \\
        --edition trial \\
        --days 14

Security Notes:
    - NEVER commit the private key to version control
    - Store the private key in a secure vault (AWS Secrets Manager, etc.)
    - The public key can be safely embedded in the application
"""

import os
import sys
import json
import base64
import argparse
import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import uuid


# Default paths
DEFAULT_KEYS_DIR = Path(__file__).parent / "keys"
PRIVATE_KEY_FILE = "private_key.pem"
PUBLIC_KEY_FILE = "public_key.pem"

PRODUCT_ID = "fa-cs-automator"


def generate_key_pair(keys_dir: Path) -> tuple:
    """
    Generate a new RSA key pair for license signing.

    Returns:
        Tuple of (private_key_pem, public_key_pem)
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        # Generate 2048-bit RSA key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Serialize private key
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Serialize public key
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # Save keys
        keys_dir.mkdir(parents=True, exist_ok=True)

        private_path = keys_dir / PRIVATE_KEY_FILE
        private_path.write_bytes(private_pem)
        os.chmod(private_path, 0o600)  # Restrict permissions
        print(f"Private key saved to: {private_path}")
        print("  WARNING: Keep this file secure! Never commit to version control.")

        public_path = keys_dir / PUBLIC_KEY_FILE
        public_path.write_bytes(public_pem)
        print(f"Public key saved to: {public_path}")
        print("  This key should be embedded in license_manager.py")

        # Also output public key for embedding
        print("\n" + "=" * 60)
        print("PUBLIC KEY (copy this to license_manager.py):")
        print("=" * 60)
        print(public_pem.decode('utf-8'))

        return private_pem, public_pem

    except ImportError:
        print("ERROR: cryptography library required")
        print("Install with: pip install cryptography")
        sys.exit(1)


def sign_license(license_data: bytes, private_key_path: Path) -> bytes:
    """
    Sign license data using the private key.

    Args:
        license_data: UTF-8 encoded license JSON
        private_key_path: Path to PEM-encoded private key

    Returns:
        Signature bytes
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        # Load private key
        private_pem = private_key_path.read_bytes()
        private_key = serialization.load_pem_private_key(
            private_pem,
            password=None,
            backend=default_backend()
        )

        # Sign with RSA-SHA256
        signature = private_key.sign(
            license_data,
            padding.PKCS1v15(),
            hashes.SHA256()
        )

        return signature

    except ImportError:
        print("ERROR: cryptography library required")
        print("Install with: pip install cryptography")
        sys.exit(1)

    except FileNotFoundError:
        print(f"ERROR: Private key not found at {private_key_path}")
        print("Generate keys first with: --generate-keys")
        sys.exit(1)


def sign_license_fallback(license_data: bytes, public_key_path: Path) -> bytes:
    """
    Fallback signing using HMAC (for environments without RSA support).

    This is less secure but provides basic tamper detection.
    """
    import hmac

    # Use public key content as HMAC key (matches fallback verification)
    public_pem = public_key_path.read_bytes()
    key = hashlib.sha256(public_pem).digest()

    signature = hmac.new(key, license_data, hashlib.sha256).digest()
    return signature


def generate_license(
    customer_name: str,
    customer_email: str,
    edition: str = "professional",
    max_seats: Optional[int] = None,
    max_assets: Optional[int] = None,
    features: Optional[list] = None,
    days_valid: int = 365,
    private_key_path: Optional[Path] = None,
    use_fallback: bool = False,
) -> str:
    """
    Generate a signed license key.

    Args:
        customer_name: Customer/organization name
        customer_email: Customer email for support
        edition: License edition (trial, basic, professional, enterprise)
        max_seats: Maximum concurrent users (None for unlimited)
        max_assets: Maximum assets per session (None for unlimited)
        features: Explicit feature list (None uses edition defaults)
        days_valid: Number of days until expiration
        private_key_path: Path to private key file
        use_fallback: Use HMAC fallback instead of RSA

    Returns:
        License key string (base64_data.base64_signature)
    """
    # Set defaults based on edition
    edition_defaults = {
        "trial": {"max_seats": 1, "max_assets": 50, "features": ["upload", "classify", "export"]},
        "basic": {"max_seats": 1, "max_assets": 500, "features": ["upload", "classify", "export"]},
        "professional": {"max_seats": 5, "max_assets": None, "features": ["upload", "classify", "export", "bulk_approve", "audit_report"]},
        "enterprise": {"max_seats": None, "max_assets": None, "features": ["upload", "classify", "export", "bulk_approve", "audit_report", "rpa", "api_access"]},
    }

    defaults = edition_defaults.get(edition, edition_defaults["basic"])

    # Build license data
    license_id = f"LIC-{date.today().year}-{uuid.uuid4().hex[:8].upper()}"
    today = date.today()
    expires = today + timedelta(days=days_valid)
    maintenance_expires = expires  # Maintenance tied to license by default

    license_data = {
        "license_id": license_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "product": PRODUCT_ID,
        "edition": edition,
        "features": features or defaults["features"],
        "max_seats": max_seats if max_seats is not None else defaults["max_seats"],
        "max_assets": max_assets if max_assets is not None else defaults["max_assets"],
        "issued_at": today.isoformat(),
        "expires_at": expires.isoformat(),
        "maintenance_expires_at": maintenance_expires.isoformat(),
        "suspended": False,
    }

    # Serialize to JSON
    license_json = json.dumps(license_data, sort_keys=True, separators=(',', ':'))
    license_bytes = license_json.encode('utf-8')

    # Sign the license
    if private_key_path is None:
        private_key_path = DEFAULT_KEYS_DIR / PRIVATE_KEY_FILE

    if use_fallback:
        public_key_path = DEFAULT_KEYS_DIR / PUBLIC_KEY_FILE
        signature = sign_license_fallback(license_bytes, public_key_path)
    else:
        signature = sign_license(license_bytes, private_key_path)

    # Encode as base64
    data_b64 = base64.b64encode(license_bytes).decode('ascii')
    sig_b64 = base64.b64encode(signature).decode('ascii')

    # Combine into license key
    license_key = f"{data_b64}.{sig_b64}"

    return license_key, license_data


def main():
    parser = argparse.ArgumentParser(
        description="Generate license keys for FA CS Automator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate key pair (do this once)
    python -m backend.licensing.license_generator --generate-keys

    # Generate professional license for 1 year
    python -m backend.licensing.license_generator \\
        --customer "Acme CPA" --email "admin@acme.com" \\
        --edition professional --days 365

    # Generate trial license
    python -m backend.licensing.license_generator \\
        --customer "Trial User" --email "user@example.com" \\
        --edition trial --days 14
        """
    )

    parser.add_argument("--generate-keys", action="store_true",
                       help="Generate new RSA key pair")
    parser.add_argument("--keys-dir", type=Path, default=DEFAULT_KEYS_DIR,
                       help="Directory for key storage")
    parser.add_argument("--customer", type=str,
                       help="Customer name")
    parser.add_argument("--email", type=str,
                       help="Customer email")
    parser.add_argument("--edition", type=str, default="professional",
                       choices=["trial", "basic", "professional", "enterprise"],
                       help="License edition")
    parser.add_argument("--seats", type=int, default=None,
                       help="Maximum seats (default: edition default)")
    parser.add_argument("--assets", type=int, default=None,
                       help="Maximum assets (default: edition default)")
    parser.add_argument("--days", type=int, default=365,
                       help="Days until expiration (default: 365)")
    parser.add_argument("--output", "-o", type=str, default=None,
                       help="Output file (default: stdout)")
    parser.add_argument("--fallback", action="store_true",
                       help="Use HMAC fallback instead of RSA")

    args = parser.parse_args()

    # Generate keys mode
    if args.generate_keys:
        print("Generating new RSA key pair...")
        generate_key_pair(args.keys_dir)
        return

    # Generate license mode
    if not args.customer or not args.email:
        parser.error("--customer and --email are required for license generation")

    print(f"Generating {args.edition} license for: {args.customer}")
    print(f"Valid for {args.days} days")

    license_key, license_data = generate_license(
        customer_name=args.customer,
        customer_email=args.email,
        edition=args.edition,
        max_seats=args.seats,
        max_assets=args.assets,
        days_valid=args.days,
        private_key_path=args.keys_dir / PRIVATE_KEY_FILE,
        use_fallback=args.fallback,
    )

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(license_key)
        print(f"\nLicense saved to: {args.output}")
    else:
        print("\n" + "=" * 60)
        print("LICENSE KEY:")
        print("=" * 60)
        print(license_key)

    print("\n" + "=" * 60)
    print("LICENSE DETAILS:")
    print("=" * 60)
    for key, value in license_data.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
