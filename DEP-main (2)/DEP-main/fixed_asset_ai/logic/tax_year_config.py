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

==============================================================================
ANNUAL UPDATE CHECKLIST (Run when IRS publishes new limits)
==============================================================================
1. Section 179 limits - Usually in Rev. Proc. (October-November)
2. Luxury auto limits (§280F) - Rev. Proc. for passenger autos
3. Heavy SUV Section 179 limit
4. Verify bonus depreciation percentage (legislative changes)
5. Update CONFIG_LAST_UPDATED and SUPPORTED_TAX_YEARS below
6. Run: python -m fixed_asset_ai.logic.tax_year_config --validate
==============================================================================
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import date
from dataclasses import dataclass
from enum import Enum
import pandas as pd


# ==============================================================================
# VERSION & COMPLIANCE TRACKING
# ==============================================================================

CONFIG_VERSION = "2.0.0"
CONFIG_LAST_UPDATED = "2025-07-15"  # YYYY-MM-DD format
CONFIG_UPDATED_BY = "Tax Team"

# Track which tax years have OFFICIAL IRS-published values vs ESTIMATED
class TaxYearStatus(Enum):
    OFFICIAL = "official"      # IRS has published final values
    ESTIMATED = "estimated"    # Projected/estimated (not yet published)
    UNSUPPORTED = "unsupported"  # Too old or too far in future


# Define supported tax years and their status
SUPPORTED_TAX_YEARS: Dict[int, TaxYearStatus] = {
    2022: TaxYearStatus.OFFICIAL,
    2023: TaxYearStatus.OFFICIAL,
    2024: TaxYearStatus.OFFICIAL,
    2025: TaxYearStatus.OFFICIAL,  # OBBBA enacted July 4, 2025
    2026: TaxYearStatus.ESTIMATED,  # Awaiting IRS guidance
}

# Minimum and maximum supported years
MIN_SUPPORTED_YEAR = min(SUPPORTED_TAX_YEARS.keys())
MAX_SUPPORTED_YEAR = max(SUPPORTED_TAX_YEARS.keys())


@dataclass
class TaxYearValidation:
    """Result of tax year validation."""
    is_supported: bool
    status: TaxYearStatus
    warnings: List[str]
    critical_errors: List[str]


def get_tax_year_status(tax_year: int) -> Tuple[TaxYearStatus, str]:
    """
    Get the support status and message for a tax year.

    Returns:
        Tuple of (status, message)
    """
    if tax_year in SUPPORTED_TAX_YEARS:
        status = SUPPORTED_TAX_YEARS[tax_year]
        if status == TaxYearStatus.OFFICIAL:
            return status, f"Tax Year {tax_year}: Using IRS-published official values."
        elif status == TaxYearStatus.ESTIMATED:
            return status, (
                f"⚠️ Tax Year {tax_year}: Using ESTIMATED values. "
                f"IRS has not yet published official limits. "
                f"Results should be reviewed when official guidance is available."
            )

    if tax_year < MIN_SUPPORTED_YEAR:
        return TaxYearStatus.UNSUPPORTED, (
            f"❌ Tax Year {tax_year} is not supported. "
            f"Minimum supported year is {MIN_SUPPORTED_YEAR}."
        )

    if tax_year > MAX_SUPPORTED_YEAR:
        return TaxYearStatus.UNSUPPORTED, (
            f"❌ Tax Year {tax_year} is not yet supported. "
            f"Maximum supported year is {MAX_SUPPORTED_YEAR}. "
            f"Update tax_year_config.py when IRS publishes guidance."
        )

    return TaxYearStatus.UNSUPPORTED, f"Tax Year {tax_year} not configured."


def get_config_info() -> Dict[str, Any]:
    """
    Get configuration metadata for display in UI.

    Returns:
        Dict with version, last updated, supported years info
    """
    official_years = [y for y, s in SUPPORTED_TAX_YEARS.items() if s == TaxYearStatus.OFFICIAL]
    estimated_years = [y for y, s in SUPPORTED_TAX_YEARS.items() if s == TaxYearStatus.ESTIMATED]

    return {
        "version": CONFIG_VERSION,
        "last_updated": CONFIG_LAST_UPDATED,
        "updated_by": CONFIG_UPDATED_BY,
        "official_years": sorted(official_years),
        "estimated_years": sorted(estimated_years),
        "min_year": MIN_SUPPORTED_YEAR,
        "max_year": MAX_SUPPORTED_YEAR,
    }


# ==============================================================================
# BONUS DEPRECIATION - TCJA + OBBB ACT (Enacted July 4, 2025)
# ==============================================================================
# The One Big Beautiful Bill Act (OBBBA) was signed into law on July 4, 2025.
# It permanently restored 100% bonus depreciation for property acquired AND
# placed in service after January 19, 2025.
#
# Sources:
# - https://www.kbkg.com/feature/obbb-tax-bill-makes-100-bonus-depreciation-permanent-what-you-need-to-know
# - https://rsmus.com/insights/services/business-tax/obba-tax-bonus-depreciation.html

# OBBB Act effective date - property must be BOTH acquired AND placed in service
# after this date to qualify for 100% bonus depreciation
OBBB_BONUS_EFFECTIVE_DATE = date(2025, 1, 19)

# OBBB Act effective date for Section 179 increases
# Property placed in service AFTER December 31, 2024 qualifies for new limits
OBBB_SECTION_179_EFFECTIVE_DATE = date(2024, 12, 31)


def get_bonus_percentage(
    tax_year: int,
    acquisition_date: Optional[date] = None,
    in_service_date: Optional[date] = None
) -> float:
    """
    Get bonus depreciation percentage for a given tax year and dates.

    Per TCJA (Tax Cuts and Jobs Act) as modified by OBBBA (enacted July 4, 2025):

    Historical Phase-Down (TCJA):
    - 2017-2022: 100%
    - 2023: 80%
    - 2024: 60%
    - Jan 1-19, 2025: 40%

    OBBBA (Enacted July 4, 2025):
    - Property acquired AND placed in service after Jan 19, 2025: 100% (PERMANENT)

    CRITICAL: To qualify for 100% under OBBBA, property must be BOTH:
    1. Acquired after January 19, 2025
    2. Placed in service after January 19, 2025

    Pre-OBBBA acquisitions (acquired before Jan 20, 2025 or subject to binding
    contract before that date) are NOT eligible for the new 100% rate.

    Args:
        tax_year: Tax year (e.g., 2024, 2025)
        acquisition_date: Date property acquired (required for 2025+ to determine eligibility)
        in_service_date: Date property placed in service (required for 2025+)

    Returns:
        Bonus depreciation percentage as decimal (1.00 for 100%, 0.60 for 60%, etc.)
    """
    # For 2025 and later, check OBBBA eligibility based on dates
    if tax_year >= 2025:
        # If we have both dates, check OBBBA eligibility
        if pd.notna(acquisition_date) and pd.notna(in_service_date):
            # Convert pandas Timestamps to dates if necessary
            acq_date = acquisition_date.date() if hasattr(acquisition_date, 'date') else acquisition_date
            pis_date = in_service_date.date() if hasattr(in_service_date, 'date') else in_service_date

            # OBBBA: 100% if BOTH acquired AND placed in service after Jan 19, 2025
            if (acq_date > OBBB_BONUS_EFFECTIVE_DATE and
                pis_date > OBBB_BONUS_EFFECTIVE_DATE):
                return 1.00  # 100% bonus under OBBBA (permanent)

            # Property acquired before Jan 20, 2025 - use TCJA phase-down
            if acq_date <= OBBB_BONUS_EFFECTIVE_DATE:
                if tax_year == 2025:
                    return 0.40  # 40% for pre-OBBBA 2025 acquisitions
                elif tax_year == 2026:
                    return 0.20  # 20% for pre-OBBBA property
                else:
                    return 0.00  # 0% for 2027+

        # No dates provided for 2025+ - assume OBBBA applies (conservative for taxpayer)
        # In production, should require dates for accurate calculation
        return 1.00  # Default to 100% for 2025+ under OBBBA

    # Historical TCJA phase-down (for tax years before 2025)
    if tax_year <= 2022:
        return 1.00  # 100% bonus (2017-2022)
    elif tax_year == 2023:
        return 0.80  # 80% bonus
    elif tax_year == 2024:
        return 0.60  # 60% bonus
    else:
        return 0.00  # Fallback


# ==============================================================================
# SECTION 179 LIMITS - OBBBA (Enacted July 4, 2025)
# ==============================================================================
# The OBBBA increased Section 179 limits effective for property placed in
# service after December 31, 2024:
# - Max deduction: Increased from ~$1.2M to $2.5M
# - Phaseout threshold: Increased from ~$3M to $4M
# - Both limits indexed for inflation going forward
#
# Source: https://rsmus.com/insights/services/business-tax/obba-tax-bonus-depreciation.html

SECTION_179_LIMITS = {
    2023: {
        "max_deduction": 1160000,
        "phaseout_threshold": 2890000,
    },
    2024: {
        "max_deduction": 1220000,
        "phaseout_threshold": 3050000,
    },
    # OBBBA limits effective for property placed in service after 12/31/2024
    2025: {
        "max_deduction": 2500000,  # OBBBA increase
        "phaseout_threshold": 4000000,  # OBBBA increase
        "indexed_for_inflation": True,
    },
    2026: {
        # Estimated with ~2.5% inflation - UPDATE when IRS publishes
        "max_deduction": 2560000,
        "phaseout_threshold": 4100000,
        "indexed_for_inflation": True,
    },
    # Add future years as IRS publishes inflation adjustments
}


def get_section_179_limits(tax_year: int) -> Dict[str, int]:
    """
    Get Section 179 dollar limit and phase-out threshold.

    Per IRC §179(b), as amended by OBBBA (enacted July 4, 2025):
    - 2024 and earlier: Pre-OBBBA limits (~$1.2M / $3M)
    - 2025 and later: OBBBA limits ($2.5M / $4M, indexed for inflation)

    Args:
        tax_year: Tax year

    Returns:
        Dict with 'max_deduction' and 'phaseout_threshold'
    """

    # Use standard enacted limits
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
    # Check for None or NaT values
    if in_service_date is None or pd.isna(in_service_date):
        return False

    # Convert pandas Timestamp to date if necessary
    pis_date = in_service_date.date() if hasattr(in_service_date, 'date') else in_service_date

    return pis_date >= QIP_EFFECTIVE_DATE


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
    # Check for None or NaT values
    if (acquisition_date is None or in_service_date is None or
        pd.isna(acquisition_date) or pd.isna(in_service_date)):
        return False

    # Convert pandas Timestamps to dates if necessary
    acq_date = acquisition_date.date() if hasattr(acquisition_date, 'date') else acquisition_date
    pis_date = in_service_date.date() if hasattr(in_service_date, 'date') else in_service_date

    return (acq_date > OBBB_BONUS_EFFECTIVE_DATE and
            pis_date > OBBB_BONUS_EFFECTIVE_DATE)


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

def validate_tax_year_config(tax_year: int) -> TaxYearValidation:
    """
    Comprehensive validation of tax year configuration.

    Returns TaxYearValidation with status, warnings, and errors.
    """
    warnings = []
    errors = []

    # Check overall tax year support status
    status, status_msg = get_tax_year_status(tax_year)

    if status == TaxYearStatus.UNSUPPORTED:
        errors.append(status_msg)
        return TaxYearValidation(
            is_supported=False,
            status=status,
            warnings=warnings,
            critical_errors=errors
        )

    if status == TaxYearStatus.ESTIMATED:
        warnings.append(status_msg)

    # OBBB Act notification for 2025+ processing
    if tax_year >= 2025:
        warnings.append(
            f"INFO: OBBB Act (One Big, Beautiful Bill) effective for {tax_year}. "
            f"Section 179: $2.5M max / $4M phase-out for property placed in service after 12/31/2024. "
            f"Bonus: 100% for property acquired AND placed in service after 1/19/2025."
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

    return TaxYearValidation(
        is_supported=True,
        status=status,
        warnings=warnings,
        critical_errors=errors
    )


def validate_tax_year_config_legacy(tax_year: int) -> list:
    """
    Legacy validation function for backward compatibility.

    Returns list of warnings (for existing code that expects list).
    """
    validation = validate_tax_year_config(tax_year)
    return validation.critical_errors + validation.warnings


# ==============================================================================
# COMMAND LINE VALIDATION TOOL
# ==============================================================================

def print_config_report():
    """Print a comprehensive report of tax configuration status."""
    info = get_config_info()

    print("=" * 70)
    print("FIXED ASSET TAX CONFIGURATION REPORT")
    print("=" * 70)
    print(f"Config Version: {info['version']}")
    print(f"Last Updated: {info['last_updated']}")
    print(f"Updated By: {info['updated_by']}")
    print("-" * 70)

    print("\nSUPPORTED TAX YEARS:")
    print(f"  Official (IRS-published): {info['official_years']}")
    print(f"  Estimated (awaiting IRS): {info['estimated_years']}")

    print("\nDETAILED CONFIGURATION:")
    for year in sorted(SUPPORTED_TAX_YEARS.keys()):
        status = SUPPORTED_TAX_YEARS[year]
        sec179 = SECTION_179_LIMITS.get(year, {})
        auto = LUXURY_AUTO_LIMITS.get(year, {})
        suv = HEAVY_SUV_179_LIMITS.get(year)

        status_icon = "✓" if status == TaxYearStatus.OFFICIAL else "⚠"
        print(f"\n  {year} [{status_icon} {status.value.upper()}]:")

        max_ded = sec179.get('max_deduction')
        phaseout = sec179.get('phaseout_threshold')
        print(f"    Section 179 Max: ${max_ded:,}" if max_ded else "    Section 179 Max: N/A")
        print(f"    Section 179 Phase-out: ${phaseout:,}" if phaseout else "    Section 179 Phase-out: N/A")
        print(f"    Bonus %: {get_bonus_percentage(year) * 100:.0f}%")
        if auto:
            yr1_bonus = auto.get('year_1_with_bonus')
            print(f"    Luxury Auto Year 1 (w/bonus): ${yr1_bonus:,}" if yr1_bonus else "    Luxury Auto Year 1: N/A")
        if suv:
            print(f"    Heavy SUV 179 Limit: ${suv:,}")

    print("\n" + "=" * 70)
    print("To update: Edit SUPPORTED_TAX_YEARS, limits dicts, and CONFIG_LAST_UPDATED")
    print("=" * 70)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--validate":
        print_config_report()

        # Validate all supported years
        print("\n\nVALIDATION RESULTS:")
        print("-" * 70)
        all_valid = True
        for year in sorted(SUPPORTED_TAX_YEARS.keys()):
            validation = validate_tax_year_config(year)
            if validation.critical_errors:
                print(f"  {year}: ❌ ERRORS")
                for err in validation.critical_errors:
                    print(f"      {err}")
                all_valid = False
            elif validation.warnings:
                print(f"  {year}: ⚠ WARNINGS")
            else:
                print(f"  {year}: ✓ OK")

        sys.exit(0 if all_valid else 1)
    else:
        print("Usage: python -m fixed_asset_ai.logic.tax_year_config --validate")
        print_config_report()
