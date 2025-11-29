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
    if not in_service_date:
        return 1  # Default to Q1 if no date

    month = in_service_date.month

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
