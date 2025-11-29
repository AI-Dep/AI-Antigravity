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
) -> Tuple[str, str, float]:
    """
    Properly classify transaction type based on in-service date and tax year.

    CRITICAL FIX: This function properly distinguishes between:
    - Current year additions (in-service date = tax year)
    - Existing assets (in-service date < tax year)
    - Disposals (disposal indicators)
    - Transfers (transfer indicators)
    - Unknown (missing date) - requires manual review

    Date Priority:
    1. Uses "In Service Date" if available
    2. Falls back to "Acquisition Date" if no in-service date
    3. Returns "Unknown (Missing Date)" if neither date is available - NOT assumed current year

    Args:
        row: Asset row with transaction data
        tax_year: Current tax year for processing
        verbose: Print classification details

    Returns:
        Tuple of (transaction_type, classification_reason, confidence)
        - transaction_type: "Current Year Addition", "Existing Asset", "Disposal", "Transfer", "Unknown (Missing Date)"
        - classification_reason: Explanation for classification
        - confidence: 0.0-1.0 confidence score for the classification
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
    # Convert pandas Timestamp to datetime
    if hasattr(in_service_date, 'to_pydatetime'):
        in_service_date = in_service_date.to_pydatetime()

    # Parse acquisition date
    if isinstance(acquisition_date, str):
        acquisition_date = parse_date(acquisition_date)
    # Convert pandas Timestamp to datetime
    if hasattr(acquisition_date, 'to_pydatetime'):
        acquisition_date = acquisition_date.to_pydatetime()

    # ===================================================================
    # STEP 1: Check for DISPOSAL (highest priority)
    # ===================================================================
    # NOTE: Be careful with broad keywords that cause false positives:
    # - "sale" alone matches "Sales Rep", "Sales Dept" - REMOVED
    # - "delete" matches "delete key" on keyboard - REMOVED
    disposal_indicators = [
        "dispos", "retire", "scrap", "writeoff", "write-off",
        "written off", "end of life", "eol", "decommission", "abandon",
        "removed from service", "out of service", "terminated", "scrapped"
    ]
    # More specific phrases that won't match common business terms
    disposal_phrases = [
        "sold to", "sale of", " sold ", "asset sold", "was sold",
        "no longer in use", "fully depreciated and removed", "taken out of service"
    ]

    # Check transaction type column (HIGH confidence - explicit user input)
    if any(indicator in trans_type_raw for indicator in disposal_indicators):
        return "Disposal", f"Transaction type indicates disposal: '{trans_type_raw}'", 0.95

    # "sold" in transaction type is more specific (user explicitly set it)
    if "sold" in trans_type_raw:
        return "Disposal", f"Transaction type indicates disposal: '{trans_type_raw}'", 0.95

    # Check sheet role (HIGH confidence - sheet is dedicated to disposals)
    if "disposal" in sheet_role or "retired" in sheet_role:
        return "Disposal", f"Sheet role indicates disposal: '{sheet_role}'", 0.90

    # Check for disposal date - this is a strong, specific indicator
    if disposal_date and not pd.isna(disposal_date):
        return "Disposal", "Disposal date is populated", 0.95

    # Check description for disposal indicators (MEDIUM confidence - could be contextual)
    if any(indicator in description for indicator in disposal_indicators):
        return "Disposal", f"Description indicates disposal: '{description[:50]}...'", 0.80

    # Check for disposal phrases (MEDIUM confidence)
    if any(phrase in description for phrase in disposal_phrases):
        return "Disposal", f"Description indicates disposal: '{description[:50]}...'", 0.80

    # ===================================================================
    # STEP 2: Check for TRANSFER (second priority)
    # ===================================================================
    # NOTE: Removed overly broad keywords:
    # - "move" matches "removal", "movement", "improvements" - REMOVED
    # - "relocate" could match normal descriptions - REMOVED
    transfer_indicators = [
        "transfer", "xfer", "reclass", "reclassify",
        "reassign", "department change", "location change",
        "moved to", "relocated to", "assigned to"
    ]
    # More specific transfer phrases
    transfer_phrases = [
        "transferred from", "transferred to", "change of location",
        "change of department", "interdepartmental", "intercompany transfer"
    ]

    # Check transaction type column (HIGH confidence - explicit user input)
    if any(indicator in trans_type_raw for indicator in transfer_indicators):
        return "Transfer", f"Transaction type indicates transfer: '{trans_type_raw}'", 0.95

    # Check sheet role (HIGH confidence - sheet is dedicated to transfers)
    if "transfer" in sheet_role or "reclass" in sheet_role:
        return "Transfer", f"Sheet role indicates transfer: '{sheet_role}'", 0.90

    # Check description - only use specific transfer terms (MEDIUM confidence)
    if any(indicator in description for indicator in transfer_indicators):
        return "Transfer", f"Description indicates transfer: '{description[:50]}...'", 0.80

    # Check for transfer phrases (MEDIUM confidence)
    if any(phrase in description for phrase in transfer_phrases):
        return "Transfer", f"Description indicates transfer: '{description[:50]}...'", 0.80

    # ===================================================================
    # STEP 3: Distinguish CURRENT YEAR ADDITION vs EXISTING ASSET
    # ===================================================================
    # CRITICAL: Use in-service date if available, otherwise fall back to acquisition date

    # Determine which date to use for classification
    date_to_use = None
    date_source = None
    date_confidence = 1.0  # Adjust based on date source

    if in_service_date and not pd.isna(in_service_date):
        date_to_use = in_service_date
        date_source = "in-service date"
        date_confidence = 0.95  # In-service date is most reliable
    elif acquisition_date and not pd.isna(acquisition_date):
        # Fall back to acquisition date if no in-service date
        date_to_use = acquisition_date
        date_source = "acquisition date"
        date_confidence = 0.85  # Acquisition date is less reliable (may differ from in-service)
    else:
        # No date available - DO NOT assume current year (dangerous for tax compliance)
        # Return "Unknown" to force manual review
        return "Unknown (Missing Date)", "No in-service or acquisition date - manual review required", 0.0

    # Get year from the date
    if isinstance(date_to_use, (date, datetime)):
        date_year = date_to_use.year
    else:
        # Can't determine year - return Unknown
        return "Unknown (Missing Date)", f"Cannot determine year from {date_source} - manual review required", 0.0

    # ===================================================================
    # CRITICAL DECISION: Current year vs existing
    # ===================================================================
    if date_year == tax_year:
        # CURRENT YEAR ADDITION
        # Eligible for Section 179 and Bonus depreciation
        return "Current Year Addition", f"Placed in service in {tax_year} based on {date_source} (current tax year)", date_confidence

    elif date_year < tax_year:
        # EXISTING ASSET (placed in service in prior year)
        # NOT eligible for Section 179 or Bonus depreciation
        # Only regular MACRS continuing depreciation
        years_ago = tax_year - date_year
        return "Existing Asset", f"Placed in service in {date_year} based on {date_source} ({years_ago} years ago) - existing asset", date_confidence

    else:
        # FUTURE YEAR (date_year > tax year)
        # This is a data error - asset can't be placed in service in the future
        return "Future Asset (Data Error)", f"{date_source.capitalize()} {date_year} is after tax year {tax_year} - likely data entry error", 0.50


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
        Updated dataframe with proper classification and confidence scores
    """
    df = df.copy()

    # Classify each row
    transaction_types = []
    classification_reasons = []
    classification_confidences = []

    for idx, row in df.iterrows():
        trans_type, reason, confidence = classify_transaction_type(row, tax_year, verbose=False)
        transaction_types.append(trans_type)
        classification_reasons.append(reason)
        classification_confidences.append(confidence)

    # Update dataframe
    df["Transaction Type"] = transaction_types
    df["Classification Reason"] = classification_reasons
    df["Transaction Type Confidence"] = classification_confidences

    if verbose:
        # Print summary
        print("\n" + "=" * 80)
        print(f"TRANSACTION CLASSIFICATION SUMMARY - Tax Year {tax_year}")
        print("=" * 80)

        counts = df["Transaction Type"].value_counts()

        print("\nAsset Counts by Transaction Type:")
        for trans_type, count in counts.items():
            print(f"  {trans_type:.<40} {count:>6}")

        # Confidence summary
        avg_confidence = df["Transaction Type Confidence"].mean()
        low_confidence_count = len(df[df["Transaction Type Confidence"] < 0.80])
        print(f"\nClassification Confidence:")
        print(f"  Average confidence: {avg_confidence:.1%}")
        print(f"  Low confidence (<80%): {low_confidence_count} assets")

        print()
        print("CRITICAL COMPLIANCE CHECK:")

        # Check for existing assets being treated as additions
        existing_count = counts.get("Existing Asset", 0)
        addition_count = counts.get("Current Year Addition", 0)

        if existing_count > 0:
            print(f"  [OK] {existing_count} existing assets properly identified")
            print(f"    (NOT eligible for Section 179 or Bonus)")

        if addition_count > 0:
            print(f"  [OK] {addition_count} current year additions identified")
            print(f"    (Eligible for Section 179 and Bonus)")

        # Check for missing dates (Unknown)
        unknown_count = counts.get("Unknown (Missing Date)", 0)
        if unknown_count > 0:
            print(f"  [!!] {unknown_count} assets with MISSING DATES - manual review required!")
            print(f"    (Cannot determine if current year addition or existing)")

        # Check for data errors
        future_count = counts.get("Future Asset (Data Error)", 0)
        if future_count > 0:
            print(f"  [!!] {future_count} assets with FUTURE in-service dates (data errors!)")

        # Check for transfers and disposals
        transfer_count = counts.get("Transfer", 0)
        disposal_count = counts.get("Disposal", 0)
        if transfer_count > 0:
            print(f"  [OK] {transfer_count} transfers detected")
        if disposal_count > 0:
            print(f"  [OK] {disposal_count} disposals detected")

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
        acquisition_date = row.get("Acquisition Date")

        # Parse in-service date (handle strings)
        if isinstance(in_service_date, str):
            in_service_date = parse_date(in_service_date)
        # Convert pandas Timestamp to datetime
        if hasattr(in_service_date, 'to_pydatetime'):
            in_service_date = in_service_date.to_pydatetime()

        # Parse acquisition date (handle strings)
        if isinstance(acquisition_date, str):
            acquisition_date = parse_date(acquisition_date)
        # Convert pandas Timestamp to datetime
        if hasattr(acquisition_date, 'to_pydatetime'):
            acquisition_date = acquisition_date.to_pydatetime()

        # Use same date fallback logic as classify_transaction_type
        date_to_use = None
        if in_service_date and not pd.isna(in_service_date):
            date_to_use = in_service_date
        elif acquisition_date and not pd.isna(acquisition_date):
            date_to_use = acquisition_date
        else:
            # No date available - skip validation (matches classify logic)
            continue

        # Extract year from date
        asset_year = None
        if isinstance(date_to_use, (date, datetime)):
            asset_year = date_to_use.year
        elif hasattr(date_to_use, 'year'):
            # Handle any other date-like object with .year attribute
            asset_year = date_to_use.year

        if asset_year is None:
            continue

        # ===================================================================
        # CRITICAL CHECK: Existing asset misclassified as addition?
        # ===================================================================
        if asset_year < tax_year:
            # This is an existing asset (placed in service in prior year)

            # Check if it's being treated as a current year addition
            if "addition" in trans_type.lower() and "existing" not in trans_type.lower():
                errors.append({
                    "row": idx + 2,  # Excel row number
                    "asset_id": row.get("Asset ID", ""),
                    "description": row.get("Description", ""),
                    "in_service_date": date_to_use,
                    "in_service_year": asset_year,
                    "tax_year": tax_year,
                    "transaction_type": trans_type,
                    "issue": f"Asset placed in service in {asset_year} but classified as '{trans_type}' - should be 'Existing Asset'",
                    "impact": f"Would incorrectly claim Section 179/Bonus for {tax_year - asset_year} year old asset"
                })

        # ===================================================================
        # CHECK: Future year asset?
        # ===================================================================
        if asset_year > tax_year:
            errors.append({
                "row": idx + 2,
                "asset_id": row.get("Asset ID", ""),
                "description": row.get("Description", ""),
                "in_service_date": date_to_use,
                "in_service_year": asset_year,
                "tax_year": tax_year,
                "transaction_type": trans_type,
                "issue": f"Asset has FUTURE in-service date {asset_year} (tax year is {tax_year})",
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
