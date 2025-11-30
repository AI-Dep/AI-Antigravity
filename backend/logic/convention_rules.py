"""
MACRS Convention Rules (IRC §168(d))

Conventions determine how much depreciation is allowed in the first and last year:
- Half-Year (HY): Assumes all property placed in service mid-year (6 months)
- Mid-Quarter (MQ): Required if >40% of basis placed in service in Q4
- Mid-Month (MM): Used for real property only

CRITICAL: Mid-quarter convention is one of the most common IRS audit adjustments.
Using HY when MQ is required = material depreciation overstatement.
"""

from datetime import date
from typing import Dict, Tuple, List
import pandas as pd


# ==============================================================================
# MID-QUARTER CONVENTION DETECTION (IRC §168(d)(3))
# ==============================================================================

def get_quarter(in_service_date: date) -> int:
    """
    Get quarter (1-4) from in-service date.

    Q1: Jan 1 - Mar 31
    Q2: Apr 1 - Jun 30
    Q3: Jul 1 - Sep 30
    Q4: Oct 1 - Dec 31

    Args:
        in_service_date: Date asset placed in service

    Returns:
        Quarter number (1, 2, 3, or 4)
    """
    # Check for None or NaT values
    if in_service_date is None or pd.isna(in_service_date):
        return 1  # Default to Q1 if no date

    # Handle pandas Timestamp objects
    if hasattr(in_service_date, 'month'):
        month = in_service_date.month
    else:
        return 1  # Fallback if no month attribute

    if month <= 3:
        return 1
    elif month <= 6:
        return 2
    elif month <= 9:
        return 3
    else:
        return 4


def detect_mid_quarter_convention(
    df: pd.DataFrame,
    tax_year: int,
    verbose: bool = True
) -> Tuple[str, Dict]:
    """
    Detect if mid-quarter convention is required per IRC §168(d)(3).

    CRITICAL RULE: If >40% of total depreciable basis is placed in service
    in Q4 (Oct 1 - Dec 31), then mid-quarter (MQ) convention MUST be used
    for ALL personal property placed in service that year.

    Real property always uses mid-month (MM) convention regardless.

    Args:
        df: Asset dataframe with in-service dates and costs
        tax_year: Current tax year
        verbose: If True, print detailed calculation

    Returns:
        Tuple of (convention, details_dict)
        - convention: "HY" (half-year) or "MQ" (mid-quarter)
        - details_dict: Breakdown by quarter with totals
    """
    from .parse_utils import parse_date

    # Filter to current year additions of personal property only
    # (Real property always uses MM, so excluded from MQ test)
    current_year_personal_property = []

    for _, row in df.iterrows():
        # Skip disposals and transfers
        trans_type = str(row.get("Transaction Type", "")).lower()
        if "disposal" in trans_type or "transfer" in trans_type:
            continue

        # Skip real property (always uses MM)
        category = str(row.get("Final Category", ""))
        if any(x in category for x in ["Residential", "Nonresidential", "Real Property"]):
            continue

        # Check if placed in service in current tax year
        in_service = parse_date(row.get("In Service Date"))
        if not in_service:
            continue

        if in_service.year == tax_year:
            cost = float(row.get("Cost") or 0.0)
            if cost > 0:
                current_year_personal_property.append({
                    "cost": cost,
                    "in_service_date": in_service,
                    "quarter": get_quarter(in_service)
                })

    # Calculate totals by quarter
    q1_total = sum(a["cost"] for a in current_year_personal_property if a["quarter"] == 1)
    q2_total = sum(a["cost"] for a in current_year_personal_property if a["quarter"] == 2)
    q3_total = sum(a["cost"] for a in current_year_personal_property if a["quarter"] == 3)
    q4_total = sum(a["cost"] for a in current_year_personal_property if a["quarter"] == 4)

    total_basis = q1_total + q2_total + q3_total + q4_total

    # Calculate Q4 percentage
    if total_basis > 0:
        q4_percentage = q4_total / total_basis
    else:
        q4_percentage = 0.0

    # Determine convention
    if q4_percentage > 0.40:
        convention = "MQ"  # Mid-quarter REQUIRED
        reason = f"Q4 basis is {q4_percentage:.1%} of total (>40% threshold)"
    else:
        convention = "HY"  # Half-year allowed
        reason = f"Q4 basis is {q4_percentage:.1%} of total (≤40% threshold)"

    details = {
        "tax_year": tax_year,
        "q1_basis": q1_total,
        "q2_basis": q2_total,
        "q3_basis": q3_total,
        "q4_basis": q4_total,
        "total_basis": total_basis,
        "q4_percentage": q4_percentage,
        "convention_required": convention,
        "reason": reason,
        "threshold": 0.40,
    }

    if verbose and total_basis > 0:
        print("\n" + "=" * 80)
        print(f"MID-QUARTER CONVENTION TEST - {tax_year}")
        print("=" * 80)
        print(f"\nPersonal Property Placed in Service by Quarter:")
        print(f"  Q1 (Jan-Mar):  ${q1_total:>15,.2f}  ({q1_total/total_basis:>6.1%})")
        print(f"  Q2 (Apr-Jun):  ${q2_total:>15,.2f}  ({q2_total/total_basis:>6.1%})")
        print(f"  Q3 (Jul-Sep):  ${q3_total:>15,.2f}  ({q3_total/total_basis:>6.1%})")
        print(f"  Q4 (Oct-Dec):  ${q4_total:>15,.2f}  ({q4_total/total_basis:>6.1%})")
        print(f"  {'─' * 70}")
        print(f"  Total:         ${total_basis:>15,.2f}  (100.0%)")
        print(f"\nQ4 Percentage: {q4_percentage:.2%}")
        print(f"Q4 Threshold:  40.0%")
        print(f"\nConvention Required: {convention}")
        print(f"Reason: {reason}")
        print("=" * 80)

    return convention, details


def get_convention_for_asset(
    asset: Dict,
    global_convention: str,
    is_real_property: bool = False
) -> str:
    """
    Get the appropriate convention for a specific asset.

    Args:
        asset: Asset dictionary
        global_convention: "HY" or "MQ" from mid-quarter test
        is_real_property: True if asset is real property (building, land improvement)

    Returns:
        Convention: "MM" (mid-month), "MQ" (mid-quarter), or "HY" (half-year)
    """
    # Real property ALWAYS uses mid-month (MM)
    if is_real_property:
        return "MM"

    # Personal property uses global convention determined by mid-quarter test
    # (Either HY or MQ for all personal property in the year)
    return global_convention


def apply_mid_quarter_convention(df: pd.DataFrame, tax_year: int) -> pd.DataFrame:
    """
    Apply mid-quarter convention rules to all assets.

    Updates the "Convention" column based on:
    1. Mid-quarter test (>40% Q4 test)
    2. Property type (real vs personal)

    Args:
        df: Asset dataframe
        tax_year: Current tax year

    Returns:
        Updated dataframe with corrected conventions
    """
    # Run mid-quarter test
    global_convention, details = detect_mid_quarter_convention(df, tax_year, verbose=True)

    # Add MQ test results to dataframe metadata
    df.attrs["mid_quarter_test"] = details
    df.attrs["global_convention"] = global_convention

    # Update convention for each asset
    conventions = []

    for _, row in df.iterrows():
        category = str(row.get("Final Category", ""))

        # Check if real property
        is_real = any(x in category for x in ["Residential", "Nonresidential", "Real Property", "Building"])

        # Get appropriate convention
        convention = get_convention_for_asset(
            row.to_dict(),
            global_convention,
            is_real_property=is_real
        )

        conventions.append(convention)

    df["Convention"] = conventions

    return df


# ==============================================================================
# MID-QUARTER DEPRECIATION FACTORS
# ==============================================================================

# Mid-quarter depreciation percentages (first year only)
# Different percentage depending on which quarter asset was placed in service
MQ_FIRST_YEAR_FACTORS = {
    # 200% Declining Balance (5-year, 7-year, 10-year, 15-year, 20-year property)
    "200DB": {
        1: 0.350,  # Q1: 87.5% of year (10.5 months)
        2: 0.262,  # Q2: 62.5% of year (7.5 months)
        3: 0.175,  # Q3: 37.5% of year (4.5 months)
        4: 0.088,  # Q4: 12.5% of year (1.5 months)
    },

    # 150% Declining Balance (3-year property, some other property)
    "150DB": {
        1: 0.250,  # Q1: 87.5% of year
        2: 0.188,  # Q2: 62.5% of year
        3: 0.125,  # Q3: 37.5% of year
        4: 0.063,  # Q4: 12.5% of year
    },

    # Straight Line (real property uses MM, but listed here for completeness)
    "SL": {
        1: 0.088,  # Q1: 87.5% of year (for personal property on SL)
        2: 0.065,  # Q2: 62.5% of year
        3: 0.044,  # Q3: 37.5% of year
        4: 0.022,  # Q4: 12.5% of year
    },
}


def get_mid_quarter_first_year_factor(method: str, quarter: int) -> float:
    """
    Get first-year depreciation factor for mid-quarter convention.

    Args:
        method: Depreciation method ("200DB", "150DB", "SL")
        quarter: Quarter placed in service (1-4)

    Returns:
        First-year depreciation percentage as decimal
    """
    if method not in MQ_FIRST_YEAR_FACTORS:
        method = "200DB"  # Default

    if quarter not in [1, 2, 3, 4]:
        quarter = 1  # Default

    return MQ_FIRST_YEAR_FACTORS[method][quarter]


# ==============================================================================
# CONVENTION CONSISTENCY ENFORCEMENT (Issue 7.3 from IRS Audit Report)
# ==============================================================================
# IRS Rule: All personal property placed in service in a year must use
# the SAME convention (either all HY or all MQ).
# Real property always uses MM regardless.


def validate_convention_consistency(
    df: pd.DataFrame,
    tax_year: int
) -> Tuple[bool, List[str]]:
    """
    Validate that all personal property in a year uses consistent conventions.

    Per IRC §168(d): All personal property placed in service in a year must use
    either ALL half-year (HY) or ALL mid-quarter (MQ) convention. Mixing
    conventions within a year is a RED FLAG for IRS audits.

    Real property (buildings, land improvements) always uses mid-month (MM)
    regardless of personal property convention.

    Args:
        df: Asset dataframe with conventions assigned
        tax_year: Tax year to check

    Returns:
        Tuple of (is_consistent, list_of_warnings)
    """
    from .parse_utils import parse_date

    warnings = []

    # Filter to current year personal property only
    current_year_assets = []
    real_property_types = ["Residential", "Nonresidential", "Real Property", "Building", "Land"]

    for _, row in df.iterrows():
        # Skip disposals and transfers
        trans_type = str(row.get("Transaction Type", "")).lower()
        if "disposal" in trans_type or "transfer" in trans_type:
            continue

        # Check if placed in service in current tax year
        in_service = parse_date(row.get("In Service Date"))
        if not in_service or in_service.year != tax_year:
            continue

        # Check if real property (always uses MM - excluded from consistency check)
        category = str(row.get("Final Category", row.get("Final Category Used", "")))
        is_real_property = any(x in category for x in real_property_types)

        if is_real_property:
            # Real property should use MM - warn if not
            convention = str(row.get("Convention", "")).upper()
            if convention and convention != "MM":
                asset_id = row.get("Asset ID", f"Row {row.name}")
                warnings.append(
                    f"Asset {asset_id}: Real property '{category}' should use MM convention, "
                    f"not {convention}"
                )
            continue

        # Personal property - track convention
        convention = str(row.get("Convention", "")).upper()
        cost = float(row.get("Cost") or 0.0)
        asset_id = row.get("Asset ID", f"Row {row.name}")

        current_year_assets.append({
            "asset_id": asset_id,
            "convention": convention,
            "cost": cost,
            "category": category
        })

    # Check consistency of personal property conventions
    if not current_year_assets:
        return True, warnings  # No personal property to check

    conventions_used = set(a["convention"] for a in current_year_assets if a["convention"])
    # Remove MM (real property convention that might have leaked in)
    conventions_used.discard("MM")

    # Check for mixed HY/MQ (invalid)
    has_hy = "HY" in conventions_used
    has_mq = "MQ" in conventions_used

    if has_hy and has_mq:
        # CRITICAL: Mixed conventions detected
        hy_count = sum(1 for a in current_year_assets if a["convention"] == "HY")
        mq_count = sum(1 for a in current_year_assets if a["convention"] == "MQ")
        hy_cost = sum(a["cost"] for a in current_year_assets if a["convention"] == "HY")
        mq_cost = sum(a["cost"] for a in current_year_assets if a["convention"] == "MQ")

        warnings.append(
            f"CRITICAL: Mixed conventions in tax year {tax_year}! "
            f"Found {hy_count} assets (${hy_cost:,.0f}) using HY and "
            f"{mq_count} assets (${mq_cost:,.0f}) using MQ. "
            f"All personal property must use the SAME convention. "
            f"Run mid-quarter test to determine correct convention for all assets."
        )
        return False, warnings

    # Check for empty conventions
    missing_convention = [a for a in current_year_assets if not a["convention"]]
    if missing_convention:
        warnings.append(
            f"WARNING: {len(missing_convention)} current-year assets missing convention. "
            f"Asset IDs: {[a['asset_id'] for a in missing_convention[:5]]}..."
        )

    return len(warnings) == 0 or not (has_hy and has_mq), warnings


def enforce_convention_consistency(
    df: pd.DataFrame,
    tax_year: int
) -> pd.DataFrame:
    """
    Enforce convention consistency by running mid-quarter test and applying
    the correct convention to ALL personal property.

    Args:
        df: Asset dataframe
        tax_year: Tax year

    Returns:
        DataFrame with consistent conventions applied
    """
    # First validate current state
    is_consistent, warnings = validate_convention_consistency(df, tax_year)

    if warnings:
        print("\n" + "=" * 70)
        print("CONVENTION CONSISTENCY CHECK")
        print("=" * 70)
        for w in warnings:
            print(f"  {w}")
        print("=" * 70 + "\n")

    if not is_consistent:
        print("Applying mid-quarter convention test to fix inconsistency...")
        df = apply_mid_quarter_convention(df, tax_year)

    return df
