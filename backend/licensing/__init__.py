# Licensing module for FA CS Automator
from .license_manager import (
    LicenseManager,
    LicenseInfo,
    LicenseStatus,
    LicenseError,
    get_license_manager,
)

__all__ = [
    "LicenseManager",
    "LicenseInfo",
    "LicenseStatus",
    "LicenseError",
    "get_license_manager",
]
