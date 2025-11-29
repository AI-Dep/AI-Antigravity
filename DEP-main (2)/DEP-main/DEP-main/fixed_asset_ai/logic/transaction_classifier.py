"""
Transaction Type Classification - CRITICAL FIX

ISSUE: The system was defaulting ALL assets to "addition" even if they were
placed in service in prior years (e.g., 2020 assets being treated as 2024 additions).

This caused:
❌ Section 179 claimed on old assets (NOT ALLOWED)
❌ Bonus depreciation on old assets (NOT ALLOWED)
❌ Massive tax deduction overstatement
❌ IRS audit risk

SOLUTION: Proper classification based on in-service date vs tax year:
✅ Current Year Addition: In-service date = current tax year
✅ Existing Asset: In-service date < current tax year
✅ Disposal: Transaction type or disposal date indicates sale
✅ Transfer: Transaction type indicates transfer/reclass

CRITICAL TAX COMPLIANCE:
- Section 179: ONLY for property placed in service in the current tax year (IRC §179)
- Bonus depreciation: ONLY for property placed in service in the current tax year (IRC §168(k))
- Existing assets: Regular MACRS depreciation only
"""

import pandas as pd
from datetime import date, datetime
from typing import Optional, Tuple

from .parse_utils import parse_date


# ==============================================================================
# TRANSACTION TYPE CLASSIFICATION
# ==============================================================================

def classify_transaction_type(
    row: pd.Series,
    tax_year: int,
    verbose: bool = False
) -> Tuple[str, str]:
    """
    Properly classify transaction type based on in-service date and tax year.

    CRITICAL FIX: This function properly distinguishes between:
    - Current year additions (in-service date = tax year)
    - Existing assets (in-service date < tax year)
    - Disposals (disposal indicators)
    - Transfers (transfer indicators)

    Date Priority:
    1. Uses "In Service Date" if available
    2. Falls back to "Acquisition Date" if no in-service date
    3. Assumes current year if neither date is available

    Args:
        row: Asset row with transaction data
        tax_year: Current tax year for processing
        verbose: Print classification details

    Returns:
        Tuple of (transaction_type, classification_reason)
        - transaction_type: "Current Year Addition", "Existing Asset", "Disposal", "Transfer"
        - classification_reason: Explanation for classification
    """
    # Get fields
    trans_type_raw = str(row.get("Transaction Type", "")).lower().strip()
    sheet_role = str(row.get("Sheet Role", "")).lower().strip()
    in_service_date = row.get("In Service Date")
    acquisition_date = row.get("Acquisition Date")
    disposal_date = row.get("Disposal Date")
    description = str(row.get("Description", "")).lower()

    # Parse in-service date
    if isinstance(in_service_date, str):
        in_service_date = parse_date(in_service_date)

    # Parse acquisition date
    if isinstance(acquisition_date, str):
        acquisition_date = parse_date(acquisition_date)

    # ===================================================================
    # STEP 1: Check for DISPOSAL (highest priority)
    # ===================================================================
    disposal_indicators = ["dispos", "sold", "retire", "sale", "delete", "scrap", "writeoff", "write-off"]

    # Check transaction type column
    if any(indicator in trans_type_raw for indicator in disposal_indicators):
        return "Disposal", f"Transaction type indicates disposal: '{trans_type_raw}'"

    # Check sheet role
    if "disposal" in sheet_role:
        return "Disposal", f"Sheet role indicates disposal: '{sheet_role}'"

    # Check for disposal date
    if disposal_date and not pd.isna(disposal_date):
        return "Disposal", "Disposal date is populated"

    # Check description
    if any(indicator in description for indicator in disposal_indicators):
        return "Disposal", f"Description indicates disposal: '{description[:50]}...'"

    # ===================================================================
    # STEP 2: Check for TRANSFER (second priority)
    # ===================================================================
    transfer_indicators = ["transfer", "xfer", "reclass", "reclassify", "move", "relocate"]

    # Check transaction type column
    if any(indicator in trans_type_raw for indicator in transfer_indicators):
        return "Transfer", f"Transaction type indicates transfer: '{trans_type_raw}'"

    # Check sheet role
    if "transfer" in sheet_role:
        return "Transfer", f"Sheet role indicates transfer: '{sheet_role}'"

    # Check description
    if any(indicator in description for indicator in transfer_indicators):
        return "Transfer", f"Description indicates transfer: '{description[:50]}...'"

    # ===================================================================
    # STEP 3: Distinguish CURRENT YEAR ADDITION vs EXISTING ASSET
    # ===================================================================
    # CRITICAL: Use in-service date if available, otherwise fall back to acquisition date

    # Determine which date to use for classification
    date_to_use = None
    date_source = None

    if in_service_date and not pd.isna(in_service_date):
        date_to_use = in_service_date
        date_source = "in-service date"
    elif acquisition_date and not pd.isna(acquisition_date):
        # Fall back to acquisition date if no in-service date
        date_to_use = acquisition_date
        date_source = "acquisition date"
    else:
        # No date available - assume current year addition (conservative)
        return "Current Year Addition", "No in-service or acquisition date - assumed current year"

    # Get year from the date
    if isinstance(date_to_use, (date, datetime)):
        date_year = date_to_use.year
    else:
        # Can't determine year - assume current (conservative)
        return "Current Year Addition", f"Cannot determine year from {date_source} - assumed current year"

    # ===================================================================
    # CRITICAL DECISION: Current year vs existing
    # ===================================================================
    if date_year == tax_year:
        # CURRENT YEAR ADDITION
        # Eligible for Section 179 and Bonus depreciation
        return "Current Year Addition", f"Placed in service in {tax_year} based on {date_source} (current tax year)"

    elif date_year < tax_year:
        # EXISTING ASSET (placed in service in prior year)
        # NOT eligible for Section 179 or Bonus depreciation
        # Only regular MACRS continuing depreciation
        years_ago = tax_year - date_year
        return "Existing Asset", f"Placed in service in {date_year} based on {date_source} ({years_ago} years ago) - existing asset"

    else:
        # FUTURE YEAR (date_year > tax year)
        # This is a data error - asset can't be placed in service in the future
        return "Future Asset (Data Error)", f"{date_source.capitalize()} {date_year} is after tax year {tax_year} - likely data entry error"


# ==============================================================================
# BATCH CLASSIFICATION FOR DATAFRAME
# ==============================================================================

def classify_all_transactions(
    df: pd.DataFrame,
    tax_year: int,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Classify all transactions in dataframe with proper current year vs existing logic.

    Args:
        df: Asset dataframe
        tax_year: Current tax year
        verbose: Print classification summary

    Returns:
        Updated dataframe with proper classification
    """
    df = df.copy()

    # Classify each row
    transaction_types = []
    classification_reasons = []

    for idx, row in df.iterrows():
        trans_type, reason = classify_transaction_type(row, tax_year, verbose=False)
        transaction_types.append(trans_type)
        classification_reasons.append(reason)

    # Update dataframe
    df["Transaction Type"] = transaction_types
    df["Classification Reason"] = classification_reasons

    if verbose:
        # Print summary
        print("\n" + "=" * 80)
        print(f"TRANSACTION CLASSIFICATION SUMMARY - Tax Year {tax_year}")
        print("=" * 80)

        counts = df["Transaction Type"].value_counts()

        print("\nAsset Counts by Transaction Type:")
        for trans_type, count in counts.items():
            print(f"  {trans_type:.<40} {count:>6}")

        print()
        print("CRITICAL COMPLIANCE CHECK:")

        # Check for existing assets being treated as additions
        existing_count = counts.get("Existing Asset", 0)
        addition_count = counts.get("Current Year Addition", 0)

        if existing_count > 0:
            print(f"  ✓ {existing_count} existing assets properly identified")
            print(f"    (NOT eligible for Section 179 or Bonus)")

        if addition_count > 0:
            print(f"  ✓ {addition_count} current year additions identified")
            print(f"    (Eligible for Section 179 and Bonus)")

        # Check for data errors
        future_count = counts.get("Future Asset (Data Error)", 0)
        if future_count > 0:
            print(f"  ⚠️  {future_count} assets with FUTURE in-service dates (data errors!)")

        print("=" * 80 + "\n")

    return df


# ==============================================================================
# VALIDATION: Detect Misclassified Assets
# ==============================================================================

def validate_transaction_classification(
    df: pd.DataFrame,
    tax_year: int
) -> Tuple[bool, list]:
    """
    Validate that existing assets are not being treated as current year additions.

    CRITICAL: This catches the bug where 2020 assets were being treated as 2024 additions.

    Args:
        df: Asset dataframe
        tax_year: Current tax year

    Returns:
        Tuple of (is_valid, error_list)
    """
    errors = []

    for idx, row in df.iterrows():
        trans_type = str(row.get("Transaction Type", ""))
        in_service_date = row.get("In Service Date")

        # Parse in-service date
        if isinstance(in_service_date, str):
            in_service_date = parse_date(in_service_date)

        if not in_service_date or pd.isna(in_service_date):
            continue

        if isinstance(in_service_date, (date, datetime)):
            in_service_year = in_service_date.year
        else:
            continue

        # ===================================================================
        # CRITICAL CHECK: Existing asset misclassified as addition?
        # ===================================================================
        if in_service_year < tax_year:
            # This is an existing asset (placed in service in prior year)

            # Check if it's being treated as a current year addition
            if "addition" in trans_type.lower() and "existing" not in trans_type.lower():
                errors.append({
                    "row": idx + 2,  # Excel row number
                    "asset_id": row.get("Asset ID", ""),
                    "description": row.get("Description", ""),
                    "in_service_date": in_service_date,
                    "in_service_year": in_service_year,
                    "tax_year": tax_year,
                    "transaction_type": trans_type,
                    "issue": f"Asset placed in service in {in_service_year} but classified as '{trans_type}' - should be 'Existing Asset'",
                    "impact": f"Would incorrectly claim Section 179/Bonus for {tax_year - in_service_year} year old asset"
                })

        # ===================================================================
        # CHECK: Future year asset?
        # ===================================================================
        if in_service_year > tax_year:
            errors.append({
                "row": idx + 2,
                "asset_id": row.get("Asset ID", ""),
                "description": row.get("Description", ""),
                "in_service_date": in_service_date,
                "in_service_year": in_service_year,
                "tax_year": tax_year,
                "transaction_type": trans_type,
                "issue": f"Asset has FUTURE in-service date {in_service_year} (tax year is {tax_year})",
                "impact": "Likely data entry error - cannot depreciate future assets"
            })

    is_valid = len(errors) == 0

    if not is_valid and errors:
        print("\n" + "🔴" * 40)
        print("CRITICAL: TRANSACTION CLASSIFICATION ERRORS DETECTED")
        print("🔴" * 40)
        print()
        print(f"Found {len(errors)} assets with incorrect classification:")
        print()

        for i, error in enumerate(errors[:10], 1):  # Show first 10
            print(f"{i}. Row {error['row']} - {error['asset_id']}")
            print(f"   In-Service: {error['in_service_date']} (year {error['in_service_year']})")
            print(f"   Issue: {error['issue']}")
            print(f"   Impact: {error['impact']}")
            print()

        if len(errors) > 10:
            print(f"   ... and {len(errors) - 10} more errors")
            print()

        print("⚠️  FIX REQUIRED: These assets must be reclassified before proceeding.")
        print("   Use classify_all_transactions() to fix automatically.")
        print("🔴" * 40 + "\n")

    return is_valid, errors
