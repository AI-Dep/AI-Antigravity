"""
Listed Property Detection and Business Use Validation

Per IRC §280F - Special rules for listed property:
- Passenger automobiles
- Other property used for transportation
- Property used for entertainment, recreation, or amusement
- Computers (unless used exclusively at regular business establishment - pre-2018)
- Cellular phones (excluded after 2009)

CRITICAL: Listed property must have >50% business use to qualify for:
- Section 179 expensing
- Bonus depreciation
- Accelerated depreciation methods (MACRS)

If <50% business use → MUST use ADS (Alternative Depreciation System)
"""

from typing import Dict, Any, Optional, Tuple, List

try:
    import pandas as pd
except ImportError:
    pd = None


# ==============================================================================
# LISTED PROPERTY DEFINITIONS (IRC §280F)
# ==============================================================================

LISTED_PROPERTY_CATEGORIES = {
    # Passenger automobiles - ALWAYS listed property
    "Passenger Automobile": {
        "listed": True,
        "reason": "IRC §280F(d)(4)(A) - Passenger automobile",
        "requires_business_use": True,
    },

    # Transportation property
    "Trucks & Trailers": {
        "listed": True,
        "reason": "IRC §280F(d)(4)(B) - Property used for transportation",
        "requires_business_use": True,
    },

    # Entertainment/Recreation/Amusement - Detected by keywords
    # These will be flagged separately based on description
}

LISTED_PROPERTY_KEYWORDS = {
    # Vehicles (most common listed property)
    # NOTE: Use space-bounded terms for short words to avoid false matches
    # - "car" alone matches "card", "carpet", "career"
    # - "van" alone matches "advantage", "canvas", "relevant"
    # - "auto" alone matches "automatic", "automation"
    "vehicles": [
        "car ", " car", "sedan", "suv", "crossover", " van", "van ", "minivan",
        "pickup", "truck", "vehicle", "auto ", " auto", "automobile",
        "jeep", "wagon", "coupe", "convertible", "roadster"
    ],

    # Entertainment/Recreation/Amusement property
    "entertainment": [
        "video camera", "recording equipment",
        "photographic equipment", "photography equipment",
        "cinema camera", "film camera", "production camera",
        "studio equipment", "studio camera",
        "entertainment system", "sound system", "audio equipment"
    ],

    # Computers (pre-2018, but good to track)
    "computers": [
        "computer", "laptop", "desktop", "workstation",
        "tablet", "ipad", "pc", "mac", "macbook"
    ],

    # Cell phones (excluded after 2009, but track anyway)
    "phones": [
        "phone", "cell phone", "mobile phone", "smartphone",
        "iphone", "android", "cellular phone"
    ]
}


def is_listed_property(asset: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Determine if asset is listed property per IRC §280F.

    Args:
        asset: Asset dictionary with classification and description

    Returns:
        Tuple of (is_listed, reason)
    """
    final_class = asset.get("Final Category", "")
    description = str(asset.get("Description", "")).lower()

    # Check by MACRS classification
    if final_class in LISTED_PROPERTY_CATEGORIES:
        info = LISTED_PROPERTY_CATEGORIES[final_class]
        return True, info["reason"]

    # Exclusions - NOT listed property even if keywords match
    security_exclusions = [
        "security", "surveillance", "cctv", "nvr", "dvr",
        "security camera", "security system", "alarm"
    ]
    is_security_equipment = any(excl in description for excl in security_exclusions)

    # Check by keywords in description
    for category, keywords in LISTED_PROPERTY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in description:
                if category == "vehicles":
                    return True, "IRC §280F(d)(4) - Vehicle/transportation property"
                elif category == "entertainment":
                    # Exclude security/surveillance cameras from entertainment property
                    if is_security_equipment:
                        continue  # Not entertainment property
                    return True, "IRC §280F(d)(4)(C) - Entertainment/recreation property"
                elif category == "computers":
                    # Computers are listed property if not used exclusively at regular business establishment
                    return True, "IRC §280F(d)(4)(A)(iv) - Computer (verify business establishment use)"
                elif category == "phones":
                    # Cell phones excluded from listed property after 2009
                    return False, "Cell phones excluded from listed property (post-2009)"

    return False, None


def get_business_use_percentage(asset: Dict[str, Any]) -> Optional[float]:
    """
    Extract business use percentage from asset data.

    Looks for:
    - "Business Use %" or similar column
    - Defaults to 100% if not specified

    Args:
        asset: Asset dictionary

    Returns:
        Business use percentage as decimal (e.g., 0.75 for 75%)
        None if not specified
    """
    # Try various possible column names
    possible_keys = [
        "Business Use %", "Business Use Percent", "Business Use Percentage",
        "Business %", "Business Pct", "Business Use",
        "QBU", "QBU %", "Qualified Business Use",
        "business_use_pct"  # Normalized key from sheet_loader
    ]

    for key in possible_keys:
        if key in asset:
            val = asset[key]
            # Check if value is not None/NaN and not empty
            if val is not None and val != "":
                # Handle pandas NA if pandas is available
                if pd and hasattr(pd, 'isna') and pd.isna(val):
                    continue

                # Handle percentage formats
                if isinstance(val, str):
                    val = val.strip().rstrip('%')

                try:
                    pct = float(val)
                    # If value is >1, assume it's in percentage form (e.g., 75 instead of 0.75)
                    if pct > 1:
                        pct = pct / 100.0
                    return min(max(pct, 0.0), 1.0)  # Clamp to 0-1
                except (ValueError, TypeError):
                    continue

    # Default: If not specified, assume 100% business use
    return None


def validate_business_use_for_incentives(
    asset: Dict[str, Any],
    allow_section_179: bool,
    allow_bonus: bool
) -> Tuple[bool, bool, List[str]]:
    """
    Validate business use percentage for listed property.

    CRITICAL: Listed property must have >50% business use to qualify for
    Section 179 and bonus depreciation per IRC §280F(d)(1).

    Args:
        asset: Asset dictionary
        allow_section_179: Whether Section 179 would otherwise be allowed
        allow_bonus: Whether bonus would otherwise be allowed

    Returns:
        Tuple of (allow_section_179, allow_bonus, warnings)
    """
    warnings = []

    is_listed, reason = is_listed_property(asset)

    if not is_listed:
        # Not listed property - no restrictions
        return allow_section_179, allow_bonus, warnings

    # Listed property - check business use
    business_use_pct = get_business_use_percentage(asset)

    if business_use_pct is None:
        # No business use % specified for listed property
        warnings.append(
            f"WARNING: Listed property ({reason}) missing business use %. "
            "Assuming 100% business use. Verify with client."
        )
        business_use_pct = 1.0  # Conservative assumption

    if business_use_pct <= 0.50:
        # CRITICAL: ≤50% business use = NO Section 179, NO bonus, MUST use ADS
        warnings.append(
            f"CRITICAL: Listed property with {business_use_pct:.0%} business use. "
            "IRC §280F requires >50% business use for Section 179/bonus. "
            "MUST use ADS (Alternative Depreciation System)."
        )
        return False, False, warnings

    # >50% business use - listed property qualifies for incentives
    if business_use_pct < 1.0:
        warnings.append(
            f"INFO: Listed property with {business_use_pct:.0%} business use. "
            "Qualifies for Section 179/bonus (>50% test met)."
        )

    return allow_section_179, allow_bonus, warnings


def requires_ads(asset: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Determine if asset requires ADS (Alternative Depreciation System).

    ADS required for:
    1. Listed property with ≤50% business use (IRC §280F)
    2. Tax-exempt use property
    3. Tax-exempt bond financed property
    4. Imported property (certain cases)
    5. Farming property electing out of 163(j)

    Args:
        asset: Asset dictionary

    Returns:
        Tuple of (requires_ads, reason)
    """
    is_listed, listed_reason = is_listed_property(asset)

    if is_listed:
        business_use_pct = get_business_use_percentage(asset)

        if business_use_pct is None:
            # Conservative: if listed property and no business use specified,
            # don't force ADS (assume 100% business use)
            return False, None

        if business_use_pct <= 0.50:
            return True, f"Listed property with ≤50% business use ({business_use_pct:.0%})"

    # Check for other ADS triggers
    # (tax-exempt use, bond financing, etc. - not implemented yet)

    return False, None
