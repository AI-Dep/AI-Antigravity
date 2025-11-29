"""
Fixed Asset AI - Vehicle & Luxury Auto Rules Module

IRC §280F luxury auto limitations and vehicle classification rules
extracted from fa_export.py for better maintainability.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import re
from typing import Tuple, Optional
from datetime import date

import pandas as pd

from .tax_year_config import get_luxury_auto_limits, get_heavy_suv_179_limit


# ==============================================================================
# VEHICLE DETECTION
# ==============================================================================

# Keywords indicating passenger automobiles subject to §280F
PASSENGER_AUTO_KEYWORDS = [
    "car", "sedan", "coupe", "convertible", "suv", "crossover",
    "pickup", "truck", "van", "minivan",
    # Specific makes often subject to limits
    "bmw", "mercedes", "audi", "lexus", "tesla", "porsche",
    "range rover", "land rover", "jaguar", "cadillac", "lincoln",
    # Common vehicle descriptions
    "automobile", "vehicle", "auto",
]

# Keywords indicating heavy vehicles (GVWR > 6,000 lbs) - NOT subject to §280F
HEAVY_VEHICLE_KEYWORDS = [
    "heavy duty", "heavy-duty", "hd", "2500", "3500",
    "f-250", "f-350", "f250", "f350",
    "silverado 2500", "silverado 3500",
    "ram 2500", "ram 3500",
    "super duty", "duramax", "powerstroke", "cummins",
    "box truck", "flatbed", "dump truck", "tow truck",
    "commercial truck", "work truck",
]

# Explicit heavy SUV models (GVWR > 6,000 lbs but still subject to special §179 limit)
HEAVY_SUV_KEYWORDS = [
    "expedition", "suburban", "tahoe", "yukon",
    "escalade", "navigator", "sequoia", "land cruiser",
    "armada", "qx80", "gx", "lx",
    "range rover", "g wagon", "g-class", "x7", "gls",
]


def _is_passenger_auto(row) -> bool:
    """
    Determine if asset is a passenger automobile subject to IRC §280F limits.

    §280F limits apply to:
    - Passenger automobiles (cars, light trucks, SUVs)
    - GVWR <= 6,000 lbs
    - Used >50% for business

    §280F does NOT apply to:
    - Heavy vehicles (GVWR > 6,000 lbs)
    - Vehicles used for hire (taxi, limousine)
    - Ambulances, hearses
    - Vehicles modified for non-personal use

    Args:
        row: DataFrame row with asset data

    Returns:
        True if subject to §280F luxury auto limits
    """
    category = str(row.get("Final Category", "")).lower()
    description = str(row.get("Description", "")).lower()
    combined = f"{category} {description}"

    # Check if explicitly a vehicle category
    if "vehicle" not in category and "auto" not in category:
        # Check description for vehicle keywords
        if not any(kw in combined for kw in PASSENGER_AUTO_KEYWORDS):
            return False

    # Check for heavy vehicle exclusion
    if any(kw in combined for kw in HEAVY_VEHICLE_KEYWORDS):
        return False

    # Check for exempt vehicle types
    exempt_keywords = [
        "ambulance", "hearse", "taxi", "limousine", "limo",
        "bus", "modified", "wheelchair", "handicap",
    ]
    if any(kw in combined for kw in exempt_keywords):
        return False

    return True


def _is_heavy_suv(row) -> bool:
    """
    Determine if asset is a heavy SUV subject to special §179 limit.

    Heavy SUVs (GVWR > 6,000 lbs) are NOT subject to §280F depreciation caps
    BUT have a special reduced §179 limit per IRC §179(b)(5)(A):
    - 2024: $28,900
    - Adjusted annually for inflation

    Args:
        row: DataFrame row with asset data

    Returns:
        True if heavy SUV subject to §179(b)(5) limit
    """
    category = str(row.get("Final Category", "")).lower()
    description = str(row.get("Description", "")).lower()
    combined = f"{category} {description}"

    # Must be a vehicle
    if "vehicle" not in category and not any(
        kw in combined for kw in PASSENGER_AUTO_KEYWORDS + HEAVY_SUV_KEYWORDS
    ):
        return False

    # Check for heavy SUV indicators
    return any(kw in combined for kw in HEAVY_SUV_KEYWORDS)


def _is_heavy_truck(row) -> bool:
    """
    Determine if asset is a heavy truck (not subject to any vehicle limits).

    Heavy trucks with GVWR > 6,000 lbs used entirely for business are:
    - NOT subject to §280F limits
    - NOT subject to §179(b)(5) SUV limit
    - Eligible for full Section 179 and bonus

    Args:
        row: DataFrame row with asset data

    Returns:
        True if heavy truck with no special limits
    """
    category = str(row.get("Final Category", "")).lower()
    description = str(row.get("Description", "")).lower()
    combined = f"{category} {description}"

    # Check for heavy duty truck indicators
    return any(kw in combined for kw in HEAVY_VEHICLE_KEYWORDS)


# ==============================================================================
# LUXURY AUTO LIMIT APPLICATION
# ==============================================================================

def _apply_luxury_auto_caps(
    row,
    section_179: float,
    bonus: float,
    tax_year: int
) -> Tuple[float, float, str]:
    """
    Apply IRC §280F luxury automobile depreciation limits.

    §280F imposes annual dollar limits on depreciation deductions for
    passenger automobiles. The limits include all depreciation (§179 + bonus + MACRS).

    2024 Limits (Year 1):
    - Without bonus: $12,200
    - With bonus: $20,200

    IMPORTANT: §179 and bonus together cannot exceed the limit.

    Args:
        row: DataFrame row with asset data
        section_179: Section 179 amount before limits
        bonus: Bonus depreciation amount before limits
        tax_year: Current tax year

    Returns:
        Tuple of (adjusted_179, adjusted_bonus, note)
    """
    # Only applies to passenger automobiles
    if not _is_passenger_auto(row):
        return section_179, bonus, ""

    # Heavy SUVs are NOT subject to §280F limits (but have special §179 limit)
    if _is_heavy_suv(row):
        return section_179, bonus, ""

    # Get §280F limits for the tax year
    limits = get_luxury_auto_limits(tax_year)
    limit_with_bonus = limits.get("year_1_with_bonus", 20200)
    limit_without_bonus = limits.get("year_1_without_bonus", 12200)

    cost = float(row.get("Tax Cost", row.get("Cost", 0)) or 0)

    # If no bonus, use lower limit
    if bonus <= 0:
        max_deduction = limit_without_bonus
    else:
        max_deduction = limit_with_bonus

    # Calculate total deduction request
    total_requested = section_179 + bonus

    # If within limits, no adjustment needed
    if total_requested <= max_deduction:
        return section_179, bonus, ""

    # Apply limits - reduce proportionally or prioritize bonus
    # IRS allows taxpayer to allocate between 179 and bonus
    # Common approach: maximize bonus first (since 179 has income limitation)

    adjusted_bonus = min(bonus, max_deduction)
    remaining_limit = max_deduction - adjusted_bonus
    adjusted_179 = min(section_179, remaining_limit)

    note = f"§280F limit applied: ${max_deduction:,.0f} max (cost ${cost:,.0f})"

    return adjusted_179, adjusted_bonus, note


def get_vehicle_depreciation_schedule(
    cost: float,
    in_service_date: date,
    tax_year: int,
    uses_bonus: bool = True
) -> dict:
    """
    Get full depreciation schedule for a luxury automobile.

    Returns year-by-year depreciation limits per §280F.

    Args:
        cost: Vehicle cost/basis
        in_service_date: Date placed in service
        tax_year: Tax year for limits
        uses_bonus: Whether bonus depreciation applies

    Returns:
        Dict with year-by-year depreciation limits
    """
    limits = get_luxury_auto_limits(tax_year)

    if uses_bonus:
        schedule = {
            1: limits.get("year_1_with_bonus", 20200),
            2: limits.get("year_2", 19500),
            3: limits.get("year_3", 11700),
            4: limits.get("year_4_plus", 6960),  # Year 4 and beyond
        }
    else:
        schedule = {
            1: limits.get("year_1_without_bonus", 12200),
            2: limits.get("year_2", 19500),
            3: limits.get("year_3", 11700),
            4: limits.get("year_4_plus", 6960),
        }

    # Calculate how many years to fully depreciate
    remaining = cost
    year = 1
    full_schedule = {}

    while remaining > 0 and year <= 20:  # Cap at 20 years
        if year <= 3:
            limit = schedule[year]
        else:
            limit = schedule[4]

        depr = min(remaining, limit)
        full_schedule[year] = depr
        remaining -= depr
        year += 1

    return full_schedule


# ==============================================================================
# ASSET TYPE DETERMINATION
# ==============================================================================

def _determine_asset_type(row) -> str:
    """
    Determine asset type for FA CS folder classification.

    FA CS organizes assets into folders. Using "Business" puts assets
    in the Business folder rather than Miscellaneous.

    Args:
        row: DataFrame row with asset data

    Returns:
        "Business" for business assets, "" for disposals/transfers
    """
    from .fa_export_validation import _is_disposal, _is_transfer

    if _is_disposal(row) or _is_transfer(row):
        return ""

    # FA CS expects "Business" for all business assets
    return "Business"
