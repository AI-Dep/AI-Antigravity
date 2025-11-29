# fixed_asset_ai/logic/tax_year_config.py
"""
Tax Year Configuration Module

Centralizes all tax year-dependent values (indexed for inflation).
Updates annually per IRS guidance.

CRITICAL: This file must be updated each year when IRS publishes
inflation-adjusted amounts (typically November for next year).

References:
- IRC §179(b) - Section 179 limits
- IRC §280F - Luxury auto limits
- Rev. Proc. published annually
"""

from typing import Dict, Any, Optional
from datetime import date


# ==============================================================================
# BONUS DEPRECIATION PHASE-DOWN (TCJA Sunset) + OBBB ACT RESTORATION
# ==============================================================================

# OBBB Act (One Big, Beautiful Bill) - Passed July 4, 2025
# Restores 100% bonus depreciation for property BOTH acquired AND placed in service
# after January 19, 2025
OBBB_BONUS_EFFECTIVE_DATE = date(2025, 1, 19)


def get_bonus_percentage(
    tax_year: int,
    acquisition_date: Optional[date] = None,
    in_service_date: Optional[date] = None
) -> float:
    """
    Get bonus depreciation percentage for a given tax year and dates.

    Per TCJA (Tax Cuts and Jobs Act) with OBBB Act override:

    OBBB ACT (effective 1/19/2025):
    - Property acquired AND placed in service after 1/19/2025: 100%

    TCJA Phase-Down (pre-OBBB or not meeting OBBB requirements):
    - 2023-2025: 80%
    - 2026: 60%
    - 2027: 40%
    - 2028: 20%
    - 2029+: 0%

    Args:
        tax_year: Tax year (e.g., 2024)
        acquisition_date: Date property acquired (optional)
        in_service_date: Date property placed in service (optional)

    Returns:
        Bonus depreciation percentage as decimal (e.g., 1.00 for 100%, 0.80 for 80%)
    """
    # OBBB Act: 100% bonus if BOTH dates after 1/19/2025
    if acquisition_date and in_service_date:
        # Convert pandas Timestamps to dates if necessary
        acq_date = acquisition_date.date() if hasattr(acquisition_date, 'date') else acquisition_date
        pis_date = in_service_date.date() if hasattr(in_service_date, 'date') else in_service_date

        if (acq_date > OBBB_BONUS_EFFECTIVE_DATE and
            pis_date > OBBB_BONUS_EFFECTIVE_DATE):
            return 1.00  # 100% bonus under OBBB

    # Fall back to TCJA phase-down schedule
    if tax_year <= 2025:
        return 0.80  # 80% bonus
    elif tax_year == 2026:
        return 0.60
    elif tax_year == 2027:
        return 0.40
    elif tax_year == 2028:
        return 0.20
    else:  # 2029+
        return 0.00


# ==============================================================================
# SECTION 179 LIMITS (Inflation-Adjusted Annually)
# ==============================================================================

# OBBB Act effective for property placed in service after 12/31/2024
OBBB_SECTION_179_EFFECTIVE_DATE = date(2024, 12, 31)

SECTION_179_LIMITS = {
    2024: {
        "max_deduction": 1220000,
        "phaseout_threshold": 3050000,
    },
    2025: {
        # OBBB Act (One Big, Beautiful Bill) - Passed July 4, 2025
        # Property placed in service after 12/31/2024
        "max_deduction": 2500000,  # Increased from $1M to $2.5M
        "phaseout_threshold": 4000000,  # Increased from $2.5M to $4M
        "indexed_for_inflation": True,  # Both limits indexed going forward
    },
    2026: {
        # Placeholder - update when IRS publishes inflation adjustments
        "max_deduction": 2560000,  # Estimated with 2.4% inflation
        "phaseout_threshold": 4100000,  # Estimated
        "indexed_for_inflation": True,
    },
    # Add future years as IRS publishes
}


def get_section_179_limits(tax_year: int) -> Dict[str, int]:
    """
    Get Section 179 dollar limit and phase-out threshold.

    Per IRC §179(b), adjusted annually for inflation.

    Args:
        tax_year: Tax year

    Returns:
        Dict with 'max_deduction' and 'phaseout_threshold'
    """
    if tax_year in SECTION_179_LIMITS:
        return SECTION_179_LIMITS[tax_year]

    # If year not defined, use latest available (with warning)
    latest_year = max(SECTION_179_LIMITS.keys())
    return SECTION_179_LIMITS[latest_year]


# ==============================================================================
# IRC §280F LUXURY AUTO LIMITS (Inflation-Adjusted Annually)
# ==============================================================================

LUXURY_AUTO_LIMITS = {
    2024: {
        "year_1_without_bonus": 20200,
        "year_1_with_bonus": 28200,
        "year_2": 19500,
        "year_3": 11700,
        "year_4_plus": 6960,
    },
    2025: {
        # Update these when IRS publishes Rev. Proc. for 2025
        "year_1_without_bonus": 20600,  # Estimated
        "year_1_with_bonus": 28600,  # Estimated
        "year_2": 19900,  # Estimated
        "year_3": 11900,  # Estimated
        "year_4_plus": 7100,  # Estimated
    },
}


def get_luxury_auto_limits(tax_year: int, asset_year: int = 1) -> int:
    """
    Get IRC §280F luxury automobile depreciation limit.

    Per Rev. Proc. published annually (e.g., Rev. Proc. 2023-34 for 2024).

    Args:
        tax_year: Tax year
        asset_year: Year of depreciation (1, 2, 3, 4+)

    Returns:
        Depreciation limit for that year
    """
    if tax_year not in LUXURY_AUTO_LIMITS:
        # Use latest available
        tax_year = max(LUXURY_AUTO_LIMITS.keys())

    limits = LUXURY_AUTO_LIMITS[tax_year]

    if asset_year == 1:
        # Will be determined at runtime based on bonus eligibility
        return limits
    elif asset_year == 2:
        return limits["year_2"]
    elif asset_year == 3:
        return limits["year_3"]
    else:  # 4+
        return limits["year_4_plus"]


# ==============================================================================
# HEAVY SUV SECTION 179 LIMIT
# ==============================================================================

HEAVY_SUV_179_LIMITS = {
    2024: 28900,
    2025: 29500,  # Estimated
}


def get_heavy_suv_179_limit(tax_year: int) -> int:
    """
    Get Section 179 limit for heavy SUVs (>6,000 lbs GVWR).

    Args:
        tax_year: Tax year

    Returns:
        Section 179 limit for heavy SUVs
    """
    if tax_year in HEAVY_SUV_179_LIMITS:
        return HEAVY_SUV_179_LIMITS[tax_year]

    latest_year = max(HEAVY_SUV_179_LIMITS.keys())
    return HEAVY_SUV_179_LIMITS[latest_year]


# ==============================================================================
# QIP ELIGIBILITY DATE
# ==============================================================================

QIP_EFFECTIVE_DATE = date(2018, 1, 1)  # Per TCJA


def is_qip_eligible_date(in_service_date: date) -> bool:
    """
    Check if asset placed in service on or after QIP effective date.

    Per IRC §168(e)(6), QIP only applies to property placed in service
    after December 31, 2017.

    Args:
        in_service_date: Date asset placed in service

    Returns:
        True if eligible for QIP classification
    """
    return in_service_date >= QIP_EFFECTIVE_DATE


def qualifies_for_obbb_bonus(acquisition_date: Optional[date], in_service_date: Optional[date]) -> bool:
    """
    Check if property qualifies for OBBB Act 100% bonus depreciation.

    Per OBBB Act (One Big, Beautiful Bill), passed July 4, 2025:
    Property must be BOTH acquired AND placed in service after January 19, 2025.

    Args:
        acquisition_date: Date property acquired
        in_service_date: Date property placed in service

    Returns:
        True if qualifies for 100% bonus under OBBB
    """
    if not acquisition_date or not in_service_date:
        return False

    return (acquisition_date > OBBB_BONUS_EFFECTIVE_DATE and
            in_service_date > OBBB_BONUS_EFFECTIVE_DATE)


# ==============================================================================
# CONFIGURATION SUMMARY
# ==============================================================================

def get_tax_config(tax_year: int) -> Dict[str, Any]:
    """
    Get all tax configuration for a given year.

    Args:
        tax_year: Tax year

    Returns:
        Dict with all tax configuration values
    """
    return {
        "tax_year": tax_year,
        "bonus_percentage": get_bonus_percentage(tax_year),  # Note: Without dates, returns TCJA schedule
        "section_179": get_section_179_limits(tax_year),
        "luxury_auto_limits": LUXURY_AUTO_LIMITS.get(
            tax_year,
            LUXURY_AUTO_LIMITS[max(LUXURY_AUTO_LIMITS.keys())]
        ),
        "heavy_suv_179_limit": get_heavy_suv_179_limit(tax_year),
        "qip_effective_date": QIP_EFFECTIVE_DATE,
        "obbb_bonus_effective_date": OBBB_BONUS_EFFECTIVE_DATE,
        "obbb_section_179_effective_date": OBBB_SECTION_179_EFFECTIVE_DATE,
    }


# ==============================================================================
# VALIDATION
# ==============================================================================

def validate_tax_year_config(tax_year: int) -> list:
    """
    Validate that all required tax year config exists.

    Returns list of warnings if using estimated/outdated values.
    """
    warnings = []

    # OBBB Act notification for 2025+ processing
    if tax_year >= 2025:
        warnings.append(
            f"INFO: OBBB Act (One Big, Beautiful Bill) effective for {tax_year}. "
            f"Section 179: $2.5M max / $4M phase-out for property placed in service after 12/31/2024. "
            f"Bonus: 100% for property acquired AND placed in service after 1/19/2025 (otherwise 80% TCJA schedule)."
        )

    # Check Section 179
    if tax_year not in SECTION_179_LIMITS:
        warnings.append(
            f"WARNING: Section 179 limits for {tax_year} not defined. "
            f"Using {max(SECTION_179_LIMITS.keys())} values. "
            "Update tax_year_config.py with IRS published amounts."
        )

    # Check luxury auto limits
    if tax_year not in LUXURY_AUTO_LIMITS:
        warnings.append(
            f"WARNING: Luxury auto limits for {tax_year} not defined. "
            f"Using {max(LUXURY_AUTO_LIMITS.keys())} values. "
            "Update tax_year_config.py with Rev. Proc. published amounts."
        )

    # Check heavy SUV limits
    if tax_year not in HEAVY_SUV_179_LIMITS:
        warnings.append(
            f"WARNING: Heavy SUV limits for {tax_year} not defined. "
            f"Using {max(HEAVY_SUV_179_LIMITS.keys())} values."
        )

    return warnings
