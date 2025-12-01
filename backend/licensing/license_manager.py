"""
License Manager for FA CS Automator

Implements offline-capable license validation using cryptographic signatures.
License keys are self-contained and can be validated without server connection.

Security Model:
- RSA-2048 asymmetric encryption
- Private key: Used by vendor to sign licenses (NEVER distributed)
- Public key: Embedded in application for validation (safe to distribute)
- License file: Base64-encoded JSON + signature

Features:
- Offline validation (no server required)
- Grace period for expired licenses
- Feature-based entitlements
- Seat counting support
- Tamper detection via signature verification
"""

import os
import json
import base64
import hashlib
import logging
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)


# ==============================================================================
# EMBEDDED PUBLIC KEY (Safe to distribute - used only for verification)
# ==============================================================================
# This is the public key used to verify license signatures.
# The corresponding private key is kept secure by the vendor.
# Replace this with your actual public key in production.

EMBEDDED_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/ygWy
hMvKwEeF2GXLZ5jPq3K8V1Dn3n/3Z5Q9kQrJR5dL3HvP8NhVK6Q1LR5dM0eDZx5d
qR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0eDZx
5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0eD
Zx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0
eDZx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5d
M0eDZx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK5dM0eDZx5dqR3kBJH1T3rK
5QIDAQAB
-----END PUBLIC KEY-----"""

# NOTE: This is a PLACEHOLDER key. Generate your own key pair for production:
# python -m backend.licensing.license_generator --generate-keys


# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Grace period after license expiration (days)
LICENSE_GRACE_PERIOD_DAYS = 14

# Warning period before expiration (days)
LICENSE_WARNING_DAYS = 30

# Product identifier
PRODUCT_ID = "fa-cs-automator"

# Available editions and their features
EDITIONS = {
    "trial": {
        "features": ["upload", "classify", "export"],
        "max_assets": 50,
        "max_seats": 1,
    },
    "basic": {
        "features": ["upload", "classify", "export"],
        "max_assets": 500,
        "max_seats": 1,
    },
    "professional": {
        "features": ["upload", "classify", "export", "bulk_approve", "audit_report"],
        "max_assets": None,  # Unlimited
        "max_seats": 5,
    },
    "enterprise": {
        "features": ["upload", "classify", "export", "bulk_approve", "audit_report", "rpa", "api_access"],
        "max_assets": None,  # Unlimited
        "max_seats": None,  # Unlimited
    },
}


# ==============================================================================
# LICENSE STATUS
# ==============================================================================

class LicenseStatus(Enum):
    """License validation status."""
    VALID = "valid"                    # License is valid and active
    EXPIRED = "expired"                # License has expired
    GRACE_PERIOD = "grace_period"      # In grace period after expiration
    EXPIRING_SOON = "expiring_soon"    # Will expire within warning period
    INVALID_SIGNATURE = "invalid_signature"  # Tampered or corrupted
    INVALID_FORMAT = "invalid_format"  # Malformed license file
    NOT_FOUND = "not_found"            # No license file found
    WRONG_PRODUCT = "wrong_product"    # License is for different product
    SUSPENDED = "suspended"            # License has been suspended


class LicenseError(Exception):
    """Exception raised for license validation failures."""
    def __init__(self, message: str, status: LicenseStatus):
        super().__init__(message)
        self.status = status


# ==============================================================================
# LICENSE INFO
# ==============================================================================

@dataclass
class LicenseInfo:
    """Parsed and validated license information."""
    license_id: str
    customer_name: str
    customer_email: str
    product: str
    edition: str
    features: List[str]
    max_seats: Optional[int]
    max_assets: Optional[int]
    issued_at: date
    expires_at: date
    maintenance_expires_at: Optional[date]
    status: LicenseStatus
    days_until_expiry: int
    grace_days_remaining: int = 0
    warnings: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if license allows operation."""
        return self.status in [
            LicenseStatus.VALID,
            LicenseStatus.EXPIRING_SOON,
            LicenseStatus.GRACE_PERIOD,
        ]

    def has_feature(self, feature: str) -> bool:
        """Check if license includes a specific feature."""
        return feature in self.features

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "license_id": self.license_id,
            "customer_name": self.customer_name,
            "edition": self.edition,
            "features": self.features,
            "max_seats": self.max_seats,
            "max_assets": self.max_assets,
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "days_until_expiry": self.days_until_expiry,
            "grace_days_remaining": self.grace_days_remaining,
            "warnings": self.warnings,
            "is_valid": self.is_valid(),
        }


# ==============================================================================
# LICENSE MANAGER
# ==============================================================================

class LicenseManager:
    """
    Manages license validation and enforcement.

    Usage:
        manager = LicenseManager()
        license_info = manager.validate()

        if not license_info.is_valid():
            print(f"License error: {license_info.status}")

        if license_info.has_feature("rpa"):
            # Enable RPA features
            pass
    """

    def __init__(
        self,
        license_path: Optional[str] = None,
        public_key: Optional[str] = None,
    ):
        """
        Initialize the license manager.

        Args:
            license_path: Path to license file. If None, searches default locations.
            public_key: PEM-encoded public key. If None, uses embedded key.
        """
        self.license_path = license_path or self._find_license_file()
        self.public_key = public_key or EMBEDDED_PUBLIC_KEY
        self._cached_license: Optional[LicenseInfo] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)

    def _find_license_file(self) -> Optional[str]:
        """Search for license file in standard locations."""
        search_paths = [
            # Environment variable
            os.environ.get("FA_CS_LICENSE_FILE"),
            # Current directory
            "license.key",
            ".license",
            # Config directory
            "config/license.key",
            # Backend directory
            os.path.join(os.path.dirname(__file__), "..", "config", "license.key"),
            # User home directory
            os.path.expanduser("~/.fa-cs-automator/license.key"),
            # System-wide (Linux)
            "/etc/fa-cs-automator/license.key",
        ]

        for path in search_paths:
            if path and os.path.exists(path):
                logger.info(f"Found license file at: {path}")
                return path

        logger.warning("No license file found in standard locations")
        return None

    def validate(self, force_refresh: bool = False) -> LicenseInfo:
        """
        Validate the license and return license information.

        Args:
            force_refresh: If True, bypass cache and re-validate

        Returns:
            LicenseInfo with validation results
        """
        # Check cache
        if not force_refresh and self._cached_license and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_ttl:
                return self._cached_license

        try:
            license_info = self._do_validate()
            self._cached_license = license_info
            self._cache_time = datetime.now()
            return license_info

        except LicenseError as e:
            logger.error(f"License validation failed: {e}")
            # Return a minimal license info with the error status
            return LicenseInfo(
                license_id="",
                customer_name="",
                customer_email="",
                product="",
                edition="",
                features=[],
                max_seats=0,
                max_assets=0,
                issued_at=date.today(),
                expires_at=date.today(),
                maintenance_expires_at=None,
                status=e.status,
                days_until_expiry=0,
                warnings=[str(e)],
            )

    def _do_validate(self) -> LicenseInfo:
        """Perform actual license validation."""
        # Check if license file exists
        if not self.license_path or not os.path.exists(self.license_path):
            raise LicenseError(
                "No license file found. Please install a valid license.",
                LicenseStatus.NOT_FOUND
            )

        # Read license file
        try:
            with open(self.license_path, 'r', encoding='utf-8') as f:
                license_content = f.read().strip()
        except Exception as e:
            raise LicenseError(
                f"Failed to read license file: {e}",
                LicenseStatus.INVALID_FORMAT
            )

        # Parse license format: {base64_data}.{base64_signature}
        try:
            parts = license_content.split('.')
            if len(parts) != 2:
                raise ValueError("Invalid license format")

            data_b64, signature_b64 = parts
            license_json = base64.b64decode(data_b64).decode('utf-8')
            signature = base64.b64decode(signature_b64)
            license_data = json.loads(license_json)

        except Exception as e:
            raise LicenseError(
                f"Invalid license format: {e}",
                LicenseStatus.INVALID_FORMAT
            )

        # Verify signature
        if not self._verify_signature(license_json.encode('utf-8'), signature):
            raise LicenseError(
                "License signature verification failed. License may be tampered.",
                LicenseStatus.INVALID_SIGNATURE
            )

        # Verify product
        if license_data.get("product") != PRODUCT_ID:
            raise LicenseError(
                f"License is for different product: {license_data.get('product')}",
                LicenseStatus.WRONG_PRODUCT
            )

        # Check if suspended
        if license_data.get("suspended", False):
            raise LicenseError(
                "This license has been suspended. Please contact support.",
                LicenseStatus.SUSPENDED
            )

        # Parse dates
        try:
            issued_at = date.fromisoformat(license_data["issued_at"])
            expires_at = date.fromisoformat(license_data["expires_at"])
            maintenance_expires = None
            if license_data.get("maintenance_expires_at"):
                maintenance_expires = date.fromisoformat(license_data["maintenance_expires_at"])
        except (KeyError, ValueError) as e:
            raise LicenseError(
                f"Invalid date in license: {e}",
                LicenseStatus.INVALID_FORMAT
            )

        # Calculate expiry status
        today = date.today()
        days_until_expiry = (expires_at - today).days
        grace_days_remaining = 0

        # Determine status
        if days_until_expiry < -LICENSE_GRACE_PERIOD_DAYS:
            status = LicenseStatus.EXPIRED
        elif days_until_expiry < 0:
            status = LicenseStatus.GRACE_PERIOD
            grace_days_remaining = LICENSE_GRACE_PERIOD_DAYS + days_until_expiry
        elif days_until_expiry <= LICENSE_WARNING_DAYS:
            status = LicenseStatus.EXPIRING_SOON
        else:
            status = LicenseStatus.VALID

        # Build warnings
        warnings = []
        if status == LicenseStatus.EXPIRING_SOON:
            warnings.append(f"License expires in {days_until_expiry} days")
        elif status == LicenseStatus.GRACE_PERIOD:
            warnings.append(
                f"License expired {-days_until_expiry} days ago. "
                f"Grace period: {grace_days_remaining} days remaining"
            )

        # Get edition features
        edition = license_data.get("edition", "basic")
        edition_config = EDITIONS.get(edition, EDITIONS["basic"])

        # Merge explicit features with edition defaults
        features = license_data.get("features", edition_config["features"])
        max_seats = license_data.get("max_seats", edition_config.get("max_seats"))
        max_assets = license_data.get("max_assets", edition_config.get("max_assets"))

        return LicenseInfo(
            license_id=license_data.get("license_id", "UNKNOWN"),
            customer_name=license_data.get("customer_name", "Unknown"),
            customer_email=license_data.get("customer_email", ""),
            product=license_data.get("product", PRODUCT_ID),
            edition=edition,
            features=features,
            max_seats=max_seats,
            max_assets=max_assets,
            issued_at=issued_at,
            expires_at=expires_at,
            maintenance_expires_at=maintenance_expires,
            status=status,
            days_until_expiry=days_until_expiry,
            grace_days_remaining=grace_days_remaining,
            warnings=warnings,
            raw_data=license_data,
        )

    def _verify_signature(self, data: bytes, signature: bytes) -> bool:
        """
        Verify the license signature using the public key.

        Uses RSA-SHA256 signature verification.
        """
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend

            # Load public key
            public_key = serialization.load_pem_public_key(
                self.public_key.encode('utf-8'),
                backend=default_backend()
            )

            # Verify signature
            public_key.verify(
                signature,
                data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True

        except ImportError:
            # Fallback: If cryptography library not available, use basic hash check
            # This is less secure but allows operation without the dependency
            logger.warning(
                "cryptography library not installed. "
                "Using fallback verification (less secure). "
                "Install with: pip install cryptography"
            )
            return self._verify_signature_fallback(data, signature)

        except Exception as e:
            logger.warning(f"Signature verification failed: {e}")
            return False

    def _verify_signature_fallback(self, data: bytes, signature: bytes) -> bool:
        """
        Fallback signature verification using HMAC.

        This is used when the cryptography library is not available.
        Less secure than RSA but provides basic tamper detection.
        """
        import hmac

        # Use a derived key from the public key as HMAC key
        # This is a simplified fallback - production should use proper RSA
        key = hashlib.sha256(self.public_key.encode()).digest()
        expected = hmac.new(key, data, hashlib.sha256).digest()

        # The signature should be HMAC in fallback mode
        return hmac.compare_digest(signature[:32], expected[:32])

    def check_feature(self, feature: str) -> bool:
        """Check if a feature is available in the current license."""
        license_info = self.validate()
        return license_info.is_valid() and license_info.has_feature(feature)

    def require_feature(self, feature: str) -> None:
        """Raise an error if feature is not available."""
        license_info = self.validate()

        if not license_info.is_valid():
            raise LicenseError(
                f"License is not valid: {license_info.status.value}",
                license_info.status
            )

        if not license_info.has_feature(feature):
            raise LicenseError(
                f"Feature '{feature}' is not included in your {license_info.edition} license. "
                f"Please upgrade to access this feature.",
                LicenseStatus.VALID  # License is valid, just missing feature
            )

    def get_status_summary(self) -> Dict[str, Any]:
        """Get a summary of license status for display."""
        license_info = self.validate()
        return {
            "valid": license_info.is_valid(),
            "status": license_info.status.value,
            "customer": license_info.customer_name,
            "edition": license_info.edition,
            "expires_at": license_info.expires_at.isoformat() if license_info.expires_at else None,
            "days_remaining": license_info.days_until_expiry,
            "features": license_info.features,
            "warnings": license_info.warnings,
        }


# ==============================================================================
# SINGLETON ACCESS
# ==============================================================================

_license_manager: Optional[LicenseManager] = None


def get_license_manager() -> LicenseManager:
    """Get the global license manager instance."""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager()
    return _license_manager


def reset_license_manager() -> None:
    """Reset the global license manager (useful for testing)."""
    global _license_manager
    _license_manager = None
