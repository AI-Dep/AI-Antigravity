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
✅ Current Year Addition: In-service date within current fiscal year
✅ Existing Asset: In-service date before current fiscal year
✅ Disposal: Transaction type or disposal date indicates sale
✅ Transfer: Transaction type indicates transfer/reclass

FISCAL YEAR SUPPORT:
- Supports both calendar year (Jan-Dec) and fiscal year (e.g., Apr-Mar, Jul-Jun)
- fy_start_month=1 for calendar year, 4 for Apr-Mar, 7 for Jul-Jun, etc.
- Example: FY 2025 with Apr start = Apr 1, 2024 to Mar 31, 2025

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
# HELPER FUNCTIONS
# ==============================================================================

def _get_year_from_date(date_value) -> Optional[int]:
    """Extract year from a date value, handling various types."""
    if date_value is None or pd.isna(date_value):
        return None
    if isinstance(date_value, (date, datetime)):
        return date_value.year
    if hasattr(date_value, 'year'):
        return date_value.year
    return None


def _get_fiscal_year_boundaries(tax_year: int, fy_start_month: int = 1) -> Tuple[date, date]:
    """
    Calculate fiscal year start and end dates.

    Args:
        tax_year: The tax/fiscal year (e.g., 2025)
        fy_start_month: First month of fiscal year (1=Jan/calendar, 4=Apr, 7=Jul, 10=Oct)

    Returns:
        Tuple of (fy_start_date, fy_end_date)

    Examples:
        Calendar year (fy_start_month=1):
            tax_year=2025 -> Jan 1, 2025 to Dec 31, 2025

        Fiscal year Apr-Mar (fy_start_month=4):
            tax_year=2025 -> Apr 1, 2024 to Mar 31, 2025
            (FY 2025 ends in calendar 2025)

        Fiscal year Jul-Jun (fy_start_month=7):
            tax_year=2025 -> Jul 1, 2024 to Jun 30, 2025
    """
    if fy_start_month == 1:
        # Calendar year: Jan 1 to Dec 31
        fy_start = date(tax_year, 1, 1)
        fy_end = date(tax_year, 12, 31)
    else:
        # Fiscal year: starts in prior calendar year, ends in tax_year
        # e.g., FY 2025 with Apr start = Apr 1, 2024 to Mar 31, 2025
        fy_start = date(tax_year - 1, fy_start_month, 1)

        # End is last day of month before fy_start_month in tax_year
        end_month = fy_start_month - 1 if fy_start_month > 1 else 12
        end_year = tax_year if fy_start_month > 1 else tax_year

        # Get last day of end month
        if end_month == 12:
            fy_end = date(end_year, 12, 31)
        else:
            # Last day of month = first day of next month - 1 day
            next_month = end_month + 1
            fy_end = date(end_year, next_month, 1) - pd.Timedelta(days=1)
            fy_end = date(fy_end.year, fy_end.month, fy_end.day)

    return fy_start, fy_end


def _is_date_in_fiscal_year(
    date_val,
    tax_year: int,
    fy_start_month: int = 1
) -> Tuple[bool, str]:
    """
    Check if a date falls within the target fiscal year.

    Args:
        date_val: Date value to check
        tax_year: The tax year (e.g., 2025)
        fy_start_month: First month of fiscal year (1=Jan/calendar, 4=Apr, 7=Jul, 10=Oct)

    Returns:
        Tuple of (is_in_fiscal_year, fiscal_year_description)
    """
    if date_val is None or pd.isna(date_val):
        return False, "no date"

    # Convert to date object
    if hasattr(date_val, 'date'):
        dt = date_val.date() if hasattr(date_val, 'date') else date_val
    elif isinstance(date_val, datetime):
        dt = date_val.date()
    elif isinstance(date_val, date):
        dt = date_val
    else:
        return False, "invalid date type"

    fy_start, fy_end = _get_fiscal_year_boundaries(tax_year, fy_start_month)

    if fy_start_month == 1:
        fy_desc = f"CY {tax_year}"
    else:
        fy_desc = f"FY {tax_year} ({fy_start.strftime('%b %Y')} - {fy_end.strftime('%b %Y')})"

    is_in_fy = fy_start <= dt <= fy_end
    return is_in_fy, fy_desc


def _get_fiscal_year_for_date(
    date_val,
    fy_start_month: int = 1
) -> Optional[int]:
    """
    Determine which fiscal year a date belongs to.

    Args:
        date_val: Date value
        fy_start_month: First month of fiscal year

    Returns:
        Fiscal year number, or None if date is invalid
    """
    if date_val is None or pd.isna(date_val):
        return None

    # Convert to date object
    if hasattr(date_val, 'date'):
        dt = date_val.date() if callable(getattr(date_val, 'date', None)) else date_val
    elif isinstance(date_val, datetime):
        dt = date_val.date()
    elif isinstance(date_val, date):
        dt = date_val
    else:
        return None

    if fy_start_month == 1:
        # Calendar year - simple
        return dt.year
    else:
        # Fiscal year - if month >= fy_start_month, it's the NEXT fiscal year
        # e.g., Apr 2024 with fy_start_month=4 -> FY 2025
        if dt.month >= fy_start_month:
            return dt.year + 1
        else:
            return dt.year


# ==============================================================================
# TRANSACTION TYPE CLASSIFICATION
# ==============================================================================

def classify_transaction_type(
    row: pd.Series,
    tax_year: int,
    fy_start_month: int = 1,
    verbose: bool = False
) -> Tuple[str, str, float]:
    """
    Properly classify transaction type based on in-service date and fiscal year.

    CRITICAL FIX: This function properly distinguishes between:
    - Current year additions (in-service date within fiscal year)
    - Existing assets (in-service date before fiscal year)
    - Current year disposals (disposal date within fiscal year) - ACTIONABLE
    - Prior year disposals (disposal date before fiscal year) - NOT ACTIONABLE (already processed)
    - Current year transfers (transfer date within fiscal year) - ACTIONABLE
    - Prior year transfers (transfer date before fiscal year) - NOT ACTIONABLE (already processed)
    - Unknown (missing date) - requires manual review

    FISCAL YEAR SUPPORT:
    - fy_start_month=1: Calendar year (Jan 1 - Dec 31)
    - fy_start_month=4: Fiscal year Apr-Mar (Apr 1, 2024 - Mar 31, 2025 for FY 2025)
    - fy_start_month=7: Fiscal year Jul-Jun (Jul 1, 2024 - Jun 30, 2025 for FY 2025)

    Date Priority:
    1. Uses "In Service Date" if available
    2. Falls back to "Acquisition Date" if no in-service date
    3. Returns "Unknown (Missing Date)" if neither date is available - NOT assumed current year

    Args:
        row: Asset row with transaction data
        tax_year: Current tax year for processing
        fy_start_month: First month of fiscal year (1=Jan, 4=Apr, 7=Jul, 10=Oct)
        verbose: Print classification details

    Returns:
        Tuple of (transaction_type, classification_reason, confidence)
        - transaction_type: "Current Year Addition", "Existing Asset", "Current Year Disposal",
          "Prior Year Disposal", "Current Year Transfer", "Prior Year Transfer", "Unknown (Missing Date)"
        - classification_reason: Explanation for classification
        - confidence: 0.0-1.0 confidence score for the classification
    """
    # Get fields
    trans_type_raw = str(row.get("Transaction Type", "")).lower().strip()
    sheet_role = str(row.get("Sheet Role", "")).lower().strip()
    in_service_date = row.get("In Service Date")
    acquisition_date = row.get("Acquisition Date")
    disposal_date = row.get("Disposal Date")
    transfer_date = row.get("Transfer Date")
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

    # Parse disposal date
    if isinstance(disposal_date, str):
        disposal_date = parse_date(disposal_date)
    if hasattr(disposal_date, 'to_pydatetime'):
        disposal_date = disposal_date.to_pydatetime()

    # Parse transfer date
    if isinstance(transfer_date, str):
        transfer_date = parse_date(transfer_date)
    if hasattr(transfer_date, 'to_pydatetime'):
        transfer_date = transfer_date.to_pydatetime()

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

    # Get fiscal year description for messages
    fy_start, fy_end = _get_fiscal_year_boundaries(tax_year, fy_start_month)
    if fy_start_month == 1:
        fy_desc = f"CY {tax_year}"
    else:
        fy_desc = f"FY {tax_year} ({fy_start.strftime('%b %Y')} - {fy_end.strftime('%b %Y')})"

    # Helper function to determine disposal type based on date
    def _get_disposal_type(disp_date, reason: str, confidence: float) -> Tuple[str, str, float]:
        """Classify as current year or prior year disposal based on disposal date."""
        is_in_fy, _ = _is_date_in_fiscal_year(disp_date, tax_year, fy_start_month)
        disp_fy = _get_fiscal_year_for_date(disp_date, fy_start_month)

        if disp_fy is not None:
            if is_in_fy:
                return "Current Year Disposal", f"{reason} (disposed in {fy_desc})", confidence
            elif disp_fy < tax_year:
                return "Prior Year Disposal", f"{reason} (disposed in FY {disp_fy}, prior to {fy_desc})", confidence
            else:
                return "Future Disposal (Data Error)", f"{reason} (disposal in FY {disp_fy} is after {fy_desc})", 0.50
        # No disposal date available - can't determine year, mark as current year disposal
        # (conservative approach - requires review)
        return "Disposal", f"{reason} (disposal date not available for year check)", confidence * 0.9

    # Check transaction type column (HIGH confidence - explicit user input)
    if any(indicator in trans_type_raw for indicator in disposal_indicators):
        return _get_disposal_type(disposal_date, f"Transaction type indicates disposal: '{trans_type_raw}'", 0.95)

    # "sold" in transaction type is more specific (user explicitly set it)
    if "sold" in trans_type_raw:
        return _get_disposal_type(disposal_date, f"Transaction type indicates disposal: '{trans_type_raw}'", 0.95)

    # Check sheet role (HIGH confidence - sheet is dedicated to disposals)
    if "disposal" in sheet_role or "retired" in sheet_role:
        return _get_disposal_type(disposal_date, f"Sheet role indicates disposal: '{sheet_role}'", 0.90)

    # Check for disposal date - this is a strong, specific indicator
    if disposal_date and not pd.isna(disposal_date):
        return _get_disposal_type(disposal_date, "Disposal date is populated", 0.95)

    # Check description for disposal indicators (MEDIUM confidence - could be contextual)
    if any(indicator in description for indicator in disposal_indicators):
        return _get_disposal_type(disposal_date, f"Description indicates disposal: '{description[:50]}...'", 0.80)

    # Check for disposal phrases (MEDIUM confidence)
    if any(phrase in description for phrase in disposal_phrases):
        return _get_disposal_type(disposal_date, f"Description indicates disposal: '{description[:50]}...'", 0.80)

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

    # Helper function to determine transfer type based on date
    def _get_transfer_type(xfer_date, reason: str, confidence: float) -> Tuple[str, str, float]:
        """Classify as current year or prior year transfer based on transfer date."""
        is_in_fy, _ = _is_date_in_fiscal_year(xfer_date, tax_year, fy_start_month)
        xfer_fy = _get_fiscal_year_for_date(xfer_date, fy_start_month)

        if xfer_fy is not None:
            if is_in_fy:
                return "Current Year Transfer", f"{reason} (transferred in {fy_desc})", confidence
            elif xfer_fy < tax_year:
                return "Prior Year Transfer", f"{reason} (transferred in FY {xfer_fy}, prior to {fy_desc})", confidence
            else:
                return "Future Transfer (Data Error)", f"{reason} (transfer in FY {xfer_fy} is after {fy_desc})", 0.50
        # No transfer date available - can't determine year, mark as current year transfer
        # (conservative approach - requires review)
        return "Transfer", f"{reason} (transfer date not available for year check)", confidence * 0.9

    # Check transaction type column (HIGH confidence - explicit user input)
    if any(indicator in trans_type_raw for indicator in transfer_indicators):
        return _get_transfer_type(transfer_date, f"Transaction type indicates transfer: '{trans_type_raw}'", 0.95)

    # Check sheet role (HIGH confidence - sheet is dedicated to transfers)
    if "transfer" in sheet_role or "reclass" in sheet_role:
        return _get_transfer_type(transfer_date, f"Sheet role indicates transfer: '{sheet_role}'", 0.90)

    # Check description - only use specific transfer terms (MEDIUM confidence)
    if any(indicator in description for indicator in transfer_indicators):
        return _get_transfer_type(transfer_date, f"Description indicates transfer: '{description[:50]}...'", 0.80)

    # Check for transfer phrases (MEDIUM confidence)
    if any(phrase in description for phrase in transfer_phrases):
        return _get_transfer_type(transfer_date, f"Description indicates transfer: '{description[:50]}...'", 0.80)

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

    # ===================================================================
    # CRITICAL DECISION: Current year vs existing (FISCAL YEAR AWARE)
    # ===================================================================
    # Use fiscal year comparison instead of simple calendar year
    is_in_fy, _ = _is_date_in_fiscal_year(date_to_use, tax_year, fy_start_month)
    asset_fy = _get_fiscal_year_for_date(date_to_use, fy_start_month)

    if asset_fy is None:
        # Can't determine fiscal year - return Unknown
        return "Unknown (Missing Date)", f"Cannot determine fiscal year from {date_source} - manual review required", 0.0

    if is_in_fy:
        # CURRENT YEAR ADDITION - asset placed in service within fiscal year
        # Eligible for Section 179 and Bonus depreciation
        return "Current Year Addition", f"Placed in service in {fy_desc} based on {date_source} (current fiscal year)", date_confidence

    elif asset_fy < tax_year:
        # EXISTING ASSET (placed in service in prior fiscal year)
        # NOT eligible for Section 179 or Bonus depreciation
        # Only regular MACRS continuing depreciation
        years_ago = tax_year - asset_fy
        return "Existing Asset", f"Placed in service in FY {asset_fy} based on {date_source} ({years_ago} years ago) - existing asset", date_confidence

    else:
        # FUTURE YEAR (asset_fy > tax year)
        # This is a data error - asset can't be placed in service in the future
        return "Future Asset (Data Error)", f"{date_source.capitalize()} is in FY {asset_fy}, after {fy_desc} - likely data entry error", 0.50


# ==============================================================================
# BATCH CLASSIFICATION FOR DATAFRAME
# ==============================================================================

def classify_all_transactions(
    df: pd.DataFrame,
    tax_year: int,
    fy_start_month: int = 1,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Classify all transactions in dataframe with proper current year vs existing logic.

    Supports fiscal years (e.g., Apr-Mar, Jul-Jun) in addition to calendar years.

    Args:
        df: Asset dataframe
        tax_year: Current tax year
        fy_start_month: First month of fiscal year (1=Jan, 4=Apr, 7=Jul, 10=Oct)
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
        trans_type, reason, confidence = classify_transaction_type(row, tax_year, fy_start_month, verbose=False)
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
        future_disposal_count = counts.get("Future Disposal (Data Error)", 0)
        future_transfer_count = counts.get("Future Transfer (Data Error)", 0)
        if future_count > 0:
            print(f"  [!!] {future_count} assets with FUTURE in-service dates (data errors!)")
        if future_disposal_count > 0:
            print(f"  [!!] {future_disposal_count} disposals with FUTURE disposal dates (data errors!)")
        if future_transfer_count > 0:
            print(f"  [!!] {future_transfer_count} transfers with FUTURE transfer dates (data errors!)")

        # Check for current year and prior year disposals
        current_disposal_count = counts.get("Current Year Disposal", 0)
        prior_disposal_count = counts.get("Prior Year Disposal", 0)
        disposal_count = counts.get("Disposal", 0)  # No date available
        if current_disposal_count > 0:
            print(f"  [OK] {current_disposal_count} current year disposals detected (ACTIONABLE)")
        if prior_disposal_count > 0:
            print(f"  [INFO] {prior_disposal_count} prior year disposals detected (already processed, not actionable)")
        if disposal_count > 0:
            print(f"  [!!] {disposal_count} disposals without date - manual review recommended")

        # Check for current year and prior year transfers
        current_transfer_count = counts.get("Current Year Transfer", 0)
        prior_transfer_count = counts.get("Prior Year Transfer", 0)
        transfer_count = counts.get("Transfer", 0)  # No date available
        if current_transfer_count > 0:
            print(f"  [OK] {current_transfer_count} current year transfers detected (ACTIONABLE)")
        if prior_transfer_count > 0:
            print(f"  [INFO] {prior_transfer_count} prior year transfers detected (already processed, not actionable)")
        if transfer_count > 0:
            print(f"  [!!] {transfer_count} transfers without date - manual review recommended")

        print("=" * 80 + "\n")

    return df


# ==============================================================================
# VALIDATION: Detect Misclassified Assets
# ==============================================================================

def validate_transaction_classification(
    df: pd.DataFrame,
    tax_year: int,
    fy_start_month: int = 1
) -> Tuple[bool, list]:
    """
    Validate that existing assets are not being treated as current year additions.

    CRITICAL: This catches the bug where prior-year assets were being treated as additions.
    Supports fiscal years (e.g., Apr-Mar, Jul-Jun).

    Args:
        df: Asset dataframe
        tax_year: Current tax year
        fy_start_month: First month of fiscal year (1=Jan, 4=Apr, 7=Jul, 10=Oct)

    Returns:
        Tuple of (is_valid, error_list)
    """
    errors = []

    # Get fiscal year description for messages
    fy_start, fy_end = _get_fiscal_year_boundaries(tax_year, fy_start_month)
    if fy_start_month == 1:
        fy_desc = f"CY {tax_year}"
    else:
        fy_desc = f"FY {tax_year} ({fy_start.strftime('%b %Y')} - {fy_end.strftime('%b %Y')})"

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

        # Determine fiscal year for the asset
        asset_fy = _get_fiscal_year_for_date(date_to_use, fy_start_month)
        is_in_fy, _ = _is_date_in_fiscal_year(date_to_use, tax_year, fy_start_month)

        if asset_fy is None:
            continue

        # ===================================================================
        # CRITICAL CHECK: Existing asset misclassified as addition?
        # ===================================================================
        if not is_in_fy and asset_fy < tax_year:
            # This is an existing asset (placed in service in prior fiscal year)

            # Check if it's being treated as a current year addition
            if "addition" in trans_type.lower() and "existing" not in trans_type.lower():
                errors.append({
                    "row": idx + 2,  # Excel row number
                    "asset_id": row.get("Asset ID", ""),
                    "description": row.get("Description", ""),
                    "in_service_date": date_to_use,
                    "in_service_year": asset_fy,
                    "tax_year": tax_year,
                    "fiscal_year_desc": fy_desc,
                    "transaction_type": trans_type,
                    "issue": f"Asset placed in service in FY {asset_fy} but classified as '{trans_type}' - should be 'Existing Asset'",
                    "impact": f"Would incorrectly claim Section 179/Bonus for {tax_year - asset_fy} year old asset"
                })

        # ===================================================================
        # CHECK: Future year asset?
        # ===================================================================
        if asset_fy > tax_year:
            errors.append({
                "row": idx + 2,
                "asset_id": row.get("Asset ID", ""),
                "description": row.get("Description", ""),
                "in_service_date": date_to_use,
                "in_service_year": asset_fy,
                "tax_year": tax_year,
                "fiscal_year_desc": fy_desc,
                "transaction_type": trans_type,
                "issue": f"Asset has FUTURE in-service date in FY {asset_fy} ({fy_desc} is current)",
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
