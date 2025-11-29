"""
ADS (Alternative Depreciation System) Implementation

Per IRC §168(g) - Alternative Depreciation System:
- Required for certain property (listed property <50% business use, etc.)
- Uses longer recovery periods than MACRS
- Straight-line method only
- No bonus depreciation allowed
- No Section 179 allowed for ADS property

ADS Class Lives per IRS Publication 946, Appendix B
"""

from typing import Dict, Tuple, Optional


# ==============================================================================
# ADS CLASS LIVES (IRC §168(g))
# ==============================================================================

# ADS lives are generally longer than MACRS lives
# Key differences:
# - MACRS 5-year property → ADS 6-year (or class life if longer)
# - MACRS 7-year property → ADS 12-year (or class life if longer)
# - MACRS 15-year property → ADS 20-year
# - MACRS 27.5-year residential → ADS 30-year
# - MACRS 39-year nonresidential → ADS 40-year

ADS_RECOVERY_PERIODS = {
    # Personal Property
    "3-Year Property": 4,   # Certain horses, tractor units for over-the-road use
    "5-Year Property": 6,   # Computers, autos, light trucks, R&D equipment
    "7-Year Property": 12,  # Office furniture, most machinery & equipment
    "10-Year Property": 16, # Vessels, barges, tugs, single-purpose agricultural structures
    "15-Year Property": 20, # Land improvements, restaurant property, retail improvements
    "20-Year Property": 25, # Farm buildings, municipal sewers

    # Real Property
    "Residential Rental Property": 30,    # Was 27.5-year under MACRS
    "Nonresidential Real Property": 40,   # Was 39-year under MACRS

    # Specific Categories
    "Passenger Automobile": 5,           # IRC §280F - Listed property
    "Light Trucks & Vans": 5,            # IRC §280F - Listed property
    "Trucks & Trailers": 6,              # Heavy trucks
    "Computers & Peripherals": 5,        # Listed property (pre-2018)
    "Office Furniture": 10,              # Class life
    "Machinery & Equipment": 12,         # General 7-year equivalent

    # QIP - Qualified Improvement Property
    "Qualified Improvement Property": 20, # ADS for QIP is 20 years

    # Land (not depreciable)
    "Land": 0,
}


# Class life to ADS recovery period mapping
# If we know the MACRS class, we can determine ADS life
MACRS_TO_ADS = {
    # MACRS Life → ADS Life
    3: 4,
    5: 6,
    7: 12,
    10: 16,
    15: 20,
    20: 25,
    27.5: 30,   # Residential
    39: 40,     # Nonresidential
}


def get_ads_recovery_period(
    macrs_class: str = None,
    macrs_life: int = None,
    category: str = None
) -> Optional[int]:
    """
    Get ADS recovery period for an asset.

    Args:
        macrs_class: MACRS classification (e.g., "5-Year Property")
        macrs_life: MACRS life in years (e.g., 5)
        category: Asset category (e.g., "Passenger Automobile")

    Returns:
        ADS recovery period in years, or None if cannot determine
    """
    # Try category-specific lookup first
    if category:
        if category in ADS_RECOVERY_PERIODS:
            return ADS_RECOVERY_PERIODS[category]

    # Try MACRS class lookup
    if macrs_class:
        # Normalize class name
        macrs_class_norm = macrs_class.strip()
        if macrs_class_norm in ADS_RECOVERY_PERIODS:
            return ADS_RECOVERY_PERIODS[macrs_class_norm]

    # Try MACRS life mapping
    if macrs_life:
        if macrs_life in MACRS_TO_ADS:
            return MACRS_TO_ADS[macrs_life]

    # Default: If 7-year property equivalent
    return 12


def get_ads_method() -> str:
    """
    Get ADS depreciation method.

    ADS ALWAYS uses straight-line method (SL).
    No accelerated methods (200DB, 150DB) allowed under ADS.

    Returns:
        "SL" (Straight Line)
    """
    return "SL"


def get_ads_convention(is_real_property: bool = False) -> str:
    """
    Get ADS depreciation convention.

    Args:
        is_real_property: True for real property, False for personal property

    Returns:
        "MM" for real property (mid-month)
        "HY" for personal property (half-year)
        Note: Mid-quarter (MQ) can also apply for personal property
    """
    if is_real_property:
        return "MM"  # Mid-month for real property
    else:
        return "HY"  # Half-year for personal property (or MQ if applicable)


def apply_ads_to_asset(asset: Dict) -> Dict:
    """
    Convert MACRS classification to ADS.

    Args:
        asset: Asset dictionary with MACRS classification

    Returns:
        Updated asset dict with ADS classification
    """
    macrs_class = asset.get("MACRS Class", "")
    macrs_life = asset.get("MACRS Life")
    final_category = asset.get("Final Category", "")

    # Determine ADS recovery period
    ads_life = get_ads_recovery_period(
        macrs_class=macrs_class,
        macrs_life=macrs_life,
        category=final_category
    )

    # Determine if real property
    is_real = any(x in final_category.upper() for x in [
        "REAL PROPERTY", "BUILDING", "RESIDENTIAL", "NONRESIDENTIAL"
    ])

    # Apply ADS
    asset["ADS Life"] = ads_life
    asset["ADS Method"] = get_ads_method()
    asset["ADS Convention"] = get_ads_convention(is_real)
    asset["Using ADS"] = True

    # Override MACRS values with ADS
    asset["Final Life"] = ads_life
    asset["Final Method"] = "SL"
    asset["Final Convention"] = asset["ADS Convention"]

    return asset


def should_use_ads(asset: Dict) -> Tuple[bool, Optional[str]]:
    """
    Determine if asset should use ADS instead of MACRS.

    Per IRC §168(g), ADS required for:
    1. Listed property with ≤50% business use (IRC §280F)
    2. Tax-exempt use property
    3. Tax-exempt bond financed property
    4. Imported property covered by executive order
    5. Farming property electing out of 163(j)

    Args:
        asset: Asset dictionary

    Returns:
        Tuple of (should_use_ads, reason)
    """
    # Import here to avoid circular dependency
    from .listed_property import requires_ads

    # Check listed property with <50% business use
    needs_ads, reason = requires_ads(asset)
    if needs_ads:
        return True, reason

    # Check for explicit ADS election
    # (Some taxpayers elect ADS for certain property even if not required)
    if asset.get("ADS Elected") or asset.get("Elect ADS"):
        return True, "Taxpayer elected ADS (IRC §168(g)(7))"

    # Check for tax-exempt use property
    # (Would need additional data fields to detect)

    # Check for tax-exempt bond financing
    # (Would need additional data fields to detect)

    return False, None


# ==============================================================================
# ADS DEPRECIATION RESTRICTIONS
# ==============================================================================

def ads_allows_section_179() -> bool:
    """
    Check if ADS property qualifies for Section 179.

    Per IRC §179(d)(1)(B)(ii), property using ADS does NOT qualify
    for Section 179 expensing.

    Returns:
        False (ADS property never qualifies for Section 179)
    """
    return False


def ads_allows_bonus() -> bool:
    """
    Check if ADS property qualifies for bonus depreciation.

    Per IRC §168(k)(2)(D)(i), ADS property does NOT qualify
    for bonus depreciation.

    Returns:
        False (ADS property never qualifies for bonus)
    """
    return False
