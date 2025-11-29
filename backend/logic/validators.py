# fixed_asset_ai/logic/validators.py
"""
Asset Data Validation Module

Comprehensive validation for fixed asset data including:
- Required field validation
- Data integrity checks
- Tax compliance validation
- Date chronology validation
- Duplicate detection

Aligned with:
- IRS Publication 946
- FA CS import requirements
- Common client data quality issues
"""

import pandas as pd
from typing import List, Dict, Tuple, Optional

from .logging_utils import get_logger
from .parse_utils import parse_date, validate_date_chronology
from .constants import (
    MAX_REASONABLE_USEFUL_LIFE,
    MAX_SINGLE_ASSET_COST_WARNING,
    ErrorMessages,
)

logger = get_logger(__name__)


def validate_assets(df: pd.DataFrame) -> Tuple[List[str], Dict[str, pd.DataFrame]]:
    """
    Comprehensive validation of asset dataframe.

    Returns:
        issues: list of short messages describing validation failures
        details: dict of issue_key -> DataFrame of affected rows

    Validation Categories:
    1. Required Fields (Cost, Description, In-Service Date)
    2. Data Integrity (negative values, impossible combinations)
    3. Date Validation (chronology, future dates)
    4. Duplicate Detection
    5. Transaction-Specific Validation (disposals, transfers)

    This validator is aligned with:
      - New disposal logic (no classification required)
      - Additions & Transfers using full MACRS classification
      - Required fields for FA CS export
      - Realistic data flaws from client schedules
    """

    issues = []
    details = {}

    if df.empty:
        issues.append("CRITICAL: Empty dataframe - no assets to process.")
        return issues, details

    # Helper: check column existence
    def has(*cols):
        return all(c in df.columns for c in cols)

    # Normalize transaction type for consistent checking
    if "Transaction Type" in df.columns:
        df["_ttype"] = df["Transaction Type"].astype(str).str.lower()
    else:
        df["_ttype"] = ""

    # ==========================================================================
    # 1. REQUIRED FIELD VALIDATIONS
    # ==========================================================================

    # 1a. Additions: Missing Cost
    # NOTE: Changed from "add" to "addition" - "add" is too broad, matches "address", "additional"
    if has("Cost", "_ttype"):
        mask = (df["_ttype"].str.contains("addition", na=False)) & (df["Cost"].isna())
        if mask.any():
            issues.append("Additions missing Cost.")
            details["missing_cost_additions"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Cost"] if c in df.columns]
            ].copy()

    # 1b. Missing Description
    if "Description" in df.columns:
        mask = df["Description"].astype(str).str.strip().eq("")
        if mask.any():
            issues.append("Assets missing Description.")
            details["missing_description"] = df.loc[
                mask, [c for c in ["Asset ID", "Cost", "Transaction Type"] if c in df.columns]
            ].copy()

    # 1c. Missing PIS Date (post-normalization)
    if has("In Service Date"):
        mask = df["In Service Date"].isna()
        if mask.any():
            issues.append("Assets missing In-Service Date (after fallback to Acquisition Date).")
            details["missing_pis"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Acquisition Date"] if c in df.columns]
            ].copy()

    # 1d. Classification Missing — ONLY for Additions (NOT transfers/disposals)
    # Transfers are already-classified assets being moved - they don't need new classification
    # Disposals don't need classification either - they use historical data
    if has("Final Category", "_ttype"):
        mask = (
            df["_ttype"].isin(["additions", "addition"])  # Only additions need classification
            & df["Final Category"].astype(str).str.strip().eq("")
        )
        if mask.any():
            issues.append("Missing MACRS classification for Additions.")
            details["missing_classification"] = df.loc[
                mask,
                [c for c in ["Asset ID", "Description", "Transaction Type", "Final Category"] if c in df.columns],
            ].copy()

    # ==========================================================================
    # 2. DATA INTEGRITY VALIDATIONS
    # ==========================================================================

    # 2a. Suspicious: Additions with zero cost
    # NOTE: Changed from "add" to "addition" - "add" is too broad, matches "address", "additional"
    if has("Cost", "_ttype"):
        cost_numeric = pd.to_numeric(df["Cost"], errors='coerce')
        mask = (
            df["_ttype"].str.contains("addition", na=False)
            & (cost_numeric.fillna(0) == 0)
        )
        if mask.any():
            issues.append("Additions with Cost = 0 detected (verify client data).")
            details["zero_cost_additions"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Cost"] if c in df.columns]
            ].copy()

    # 2b. Negative Costs (Data Entry Error)
    if "Cost" in df.columns:
        cost_numeric = pd.to_numeric(df["Cost"], errors='coerce')
        mask = cost_numeric < 0
        if mask.any():
            issues.append("Assets with negative cost detected (data entry error).")
            details["negative_cost"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Cost"] if c in df.columns]
            ].copy()

    # 2c. Accumulated Depreciation > Cost (Impossible - Data Error)
    if has("Cost", "Accumulated Depreciation"):
        cost_numeric = pd.to_numeric(df["Cost"], errors='coerce').fillna(0)
        accum_numeric = pd.to_numeric(df["Accumulated Depreciation"], errors='coerce').fillna(0)

        mask = accum_numeric > cost_numeric
        if mask.any():
            issues.append("CRITICAL: Accumulated Depreciation exceeds Cost (impossible - check data).")
            details["accum_depr_exceeds_cost"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Cost", "Accumulated Depreciation"] if c in df.columns]
            ].copy()

        # Check for negative accumulated depreciation (impossible - data entry error)
        negative_accum_mask = accum_numeric < 0
        if negative_accum_mask.any():
            issues.append("CRITICAL: Negative Accumulated Depreciation detected (impossible - check data).")
            details["negative_accum_depr"] = df.loc[
                negative_accum_mask, [c for c in ["Asset ID", "Description", "Accumulated Depreciation"] if c in df.columns]
            ].copy()

    # 2d. Unreasonably high cost (potential data entry error)
    if "Cost" in df.columns:
        cost_numeric = pd.to_numeric(df["Cost"], errors='coerce')
        mask = cost_numeric > MAX_SINGLE_ASSET_COST_WARNING
        if mask.any():
            issues.append(f"WARNING: Assets with cost > ${MAX_SINGLE_ASSET_COST_WARNING:,.0f} detected (verify for data entry errors).")
            details["high_cost_warning"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Cost"] if c in df.columns]
            ].copy()

    # 2e. Unreasonable useful life
    if "MACRS Life" in df.columns:
        life_numeric = pd.to_numeric(df["MACRS Life"], errors='coerce')
        # Check for negative values (impossible)
        negative_life_mask = life_numeric < 0
        if negative_life_mask.any():
            issues.append("CRITICAL: Negative MACRS Life detected (impossible - check data).")
            details["negative_macrs_life"] = df.loc[
                negative_life_mask, [c for c in ["Asset ID", "Description", "MACRS Life"] if c in df.columns]
            ].copy()
        # Check for unreasonably high values
        mask = life_numeric > MAX_REASONABLE_USEFUL_LIFE
        if mask.any():
            issues.append(f"Assets with useful life > {MAX_REASONABLE_USEFUL_LIFE} years (verify classification).")
            details["unreasonable_life"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "MACRS Life"] if c in df.columns]
            ].copy()

    # ==========================================================================
    # 3. DATE VALIDATIONS
    # ==========================================================================

    # 3a. Future In-Service Date (Cannot Depreciate Property Not Yet in Service)
    if "In Service Date" in df.columns:
        today = pd.Timestamp.now().normalize()
        in_service_dates = pd.to_datetime(df["In Service Date"], errors='coerce')
        mask = in_service_dates > today
        if mask.any():
            issues.append("WARNING: Assets with future In-Service Date detected (cannot depreciate yet).")
            details["future_in_service"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "In Service Date"] if c in df.columns]
            ].copy()

    # 3b. In-Service Date older than Acquisition Date
    # NOTE: This is LEGITIMATE in many scenarios:
    #   - Used/demo equipment purchased after it was already in service
    #   - Lease-to-own arrangements (leased equipment, then purchased)
    #   - Trial/rental period before purchase
    #   - Contributed property from partners
    # Changed from ERROR to WARNING to allow export
    if has("In Service Date", "Acquisition Date"):
        in_service = pd.to_datetime(df["In Service Date"], errors='coerce')
        acquisition = pd.to_datetime(df["Acquisition Date"], errors='coerce')

        mask = (
            in_service.notna()
            & acquisition.notna()
            & (in_service < acquisition)
        )
        if mask.any():
            issues.append("WARNING: In-Service Date earlier than Acquisition Date (verify if asset was used/leased before purchase).")
            details["pis_before_acq"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Acquisition Date", "In Service Date"] if c in df.columns]
            ].copy()

    # 3c. Disposal Date earlier than In-Service Date (impossible)
    if has("In Service Date", "Disposal Date"):
        in_service = pd.to_datetime(df["In Service Date"], errors='coerce')
        disposal = pd.to_datetime(df["Disposal Date"], errors='coerce')

        mask = (
            in_service.notna()
            & disposal.notna()
            & (disposal < in_service)
        )
        if mask.any():
            issues.append("CRITICAL: Disposal Date earlier than In-Service Date (impossible).")
            details["disposal_before_pis"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "In Service Date", "Disposal Date"] if c in df.columns]
            ].copy()

    # 3d. Full date chronology check - REMOVED
    # This was redundant with:
    #   - 3b: In-Service < Acquisition (now WARNING - legitimate for used/leased assets)
    #   - 3c: Disposal < In-Service (CRITICAL - impossible)
    # The individual checks provide better, more actionable feedback

    # ==========================================================================
    # 4. DUPLICATE DETECTION
    # ==========================================================================

    # 4a. Duplicate Asset IDs
    if "Asset ID" in df.columns:
        # Exclude empty/null Asset IDs from duplicate check
        non_empty_ids = df[df["Asset ID"].astype(str).str.strip().ne("") & df["Asset ID"].notna()]

        if not non_empty_ids.empty:
            duplicates = non_empty_ids[non_empty_ids.duplicated(subset=["Asset ID"], keep=False)]
            if not duplicates.empty:
                issues.append(f"CRITICAL: Duplicate Asset IDs detected ({duplicates['Asset ID'].nunique()} IDs, {len(duplicates)} total rows).")
                details["duplicate_asset_ids"] = duplicates[
                    [c for c in ["Asset ID", "Description", "Cost", "In Service Date"] if c in df.columns]
                ].copy().sort_values("Asset ID")

    # ==========================================================================
    # 5. TRANSACTION-SPECIFIC VALIDATIONS
    # ==========================================================================

    # 5a. Disposal rows with inconsistent Transaction Type
    if has("Transaction Type"):
        desc_has_disposal = df["Description"].astype(str).str.contains("dispos", case=False, na=False)
        trans_type_empty = df["Transaction Type"].astype(str).str.strip().eq("")
        mask = desc_has_disposal & trans_type_empty
        if mask.any():
            issues.append("Potential disposals detected in Description but Transaction Type is empty.")
            details["disposal_inconsistent"] = df.loc[
                mask, [c for c in ["Asset ID", "Description", "Transaction Type"] if c in df.columns]
            ].copy()

    # 5b. Disposal Validation - Missing Disposal Date (CRITICAL)
    # Disposals MUST have a Disposal Date for proper depreciation cutoff
    if has("_ttype"):
        is_disposal = df["_ttype"].str.contains("dispos|sold|retire", case=False, na=False)

        if is_disposal.any():
            # Check for missing Disposal Date - handle both column naming conventions
            # "Disposal Date" (display name) or "disposal_date" (normalized name)
            disposal_date_col = None
            for col_name in ["Disposal Date", "disposal_date"]:
                if col_name in df.columns:
                    disposal_date_col = col_name
                    break

            if disposal_date_col:
                # Check if disposal date values are missing or empty (but not "None" string which is a valid placeholder)
                disposal_date_empty = (
                    df[disposal_date_col].isna() |
                    (df[disposal_date_col].astype(str).str.strip().eq("")) |
                    (df[disposal_date_col].astype(str).str.lower().eq("none"))
                )
                # Only flag as missing if it's a disposal AND the date is actually empty
                # Skip rows where disposal_date has an actual date value
                mask = is_disposal & disposal_date_empty

                # Double-check: exclude rows that have valid dates (not None/NaT/empty)
                if mask.any():
                    # Re-verify: only keep rows where date is truly missing
                    for idx in mask[mask].index:
                        val = df.loc[idx, disposal_date_col]
                        # If it's a valid date (not None, not NaT, not empty string), exclude from mask
                        if pd.notna(val) and str(val).strip().lower() not in ("", "none", "nat"):
                            mask.loc[idx] = False

                if mask.any():
                    issues.append("CRITICAL: Disposals missing Disposal Date (required for depreciation cutoff).")
                    details["disposal_missing_date"] = df.loc[
                        mask, [c for c in ["Asset ID", "Description", "Transaction Type", disposal_date_col] if c in df.columns]
                    ].copy()
            else:
                # No Disposal Date column at all
                issues.append("CRITICAL: Disposal records detected but 'Disposal Date' column is missing from data.")
                details["disposal_missing_date_column"] = df.loc[
                    is_disposal, [c for c in ["Asset ID", "Description", "Transaction Type"] if c in df.columns]
                ].copy()

    # 5c. Transfer Validation - Missing From/To Information
    if has("_ttype"):
        is_transfer = df["_ttype"].isin(["transfer", "transfers"])

        if is_transfer.any():
            transfer_display_cols = ["Asset ID", "Description"]

            # Check for missing Transfer Date
            if "Transfer Date" in df.columns:
                transfer_display_cols.append("Transfer Date")
                transfer_date_empty = df["Transfer Date"].isna() | df["Transfer Date"].astype(str).str.strip().eq("")
                mask = is_transfer & transfer_date_empty
                if mask.any():
                    issues.append("Transfers missing Transfer Date.")
                    details["transfer_missing_date"] = df.loc[
                        mask, [c for c in transfer_display_cols if c in df.columns]
                    ].copy()

            # Check for missing From/To Location
            has_from_loc = "From Location" in df.columns
            has_to_loc = "To Location" in df.columns

            if has_from_loc:
                transfer_display_cols.append("From Location")
            if has_to_loc:
                transfer_display_cols.append("To Location")

            if has_from_loc or has_to_loc:
                from_empty = df["From Location"].astype(str).str.strip().eq("") if has_from_loc else pd.Series(True, index=df.index)
                to_empty = df["To Location"].astype(str).str.strip().eq("") if has_to_loc else pd.Series(True, index=df.index)
                mask = is_transfer & (from_empty | to_empty)
                if mask.any():
                    issues.append("Transfers missing From Location and/or To Location.")
                    details["transfer_missing_location"] = df.loc[
                        mask, [c for c in transfer_display_cols if c in df.columns]
                    ].copy()

            # Check for missing From/To Department
            has_from_dept = "From Department" in df.columns
            has_to_dept = "To Department" in df.columns

            if has_from_dept:
                transfer_display_cols.append("From Department")
            if has_to_dept:
                transfer_display_cols.append("To Department")

            if has_from_dept or has_to_dept:
                from_empty = df["From Department"].astype(str).str.strip().eq("") if has_from_dept else pd.Series(True, index=df.index)
                to_empty = df["To Department"].astype(str).str.strip().eq("") if has_to_dept else pd.Series(True, index=df.index)
                mask = is_transfer & (from_empty | to_empty)
                if mask.any():
                    issues.append("Transfers missing From Department and/or To Department.")
                    details["transfer_missing_department"] = df.loc[
                        mask, [c for c in transfer_display_cols if c in df.columns]
                    ].copy()

            # Info: No transfer-specific columns found at all
            if not has_from_loc and not has_to_loc and not has_from_dept and not has_to_dept and "Transfer Date" not in df.columns:
                issues.append("INFO: Transfer records detected but no transfer-specific columns (From/To Location, From/To Department, Transfer Date) found in data.")

    # ==========================================================================
    # 6. ACCUMULATED DEPRECIATION ANOMALY DETECTION
    # ==========================================================================
    # Current year additions should NOT have accumulated depreciation
    # This indicates either:
    # - Wrong in-service date (asset is actually existing, not new)
    # - Wrong accumulated depreciation (shouldn't be entered for new assets)
    # - Transferred asset that needs special handling

    # Check for accumulated depreciation column (various names)
    accum_dep_col = None
    for col_name in ["Accumulated Depreciation", "accumulated_depreciation", "Accum Dep", "AccumDep", "Prior Depreciation"]:
        if col_name in df.columns:
            accum_dep_col = col_name
            break

    if accum_dep_col and has("In Service Date"):
        # Get current year from the data (use most common year in service dates)
        try:
            in_service_dates = pd.to_datetime(df["In Service Date"], errors='coerce')
            valid_dates = in_service_dates.dropna()
            if len(valid_dates) > 0:
                # Determine "current year" as the max year in the data
                current_year = valid_dates.dt.year.max()

                # Find current year additions (in-service date in current year)
                is_current_year = in_service_dates.dt.year == current_year

                # Find those with accumulated depreciation > 0
                accum_dep_values = pd.to_numeric(df[accum_dep_col], errors='coerce').fillna(0)
                has_accum_dep = accum_dep_values > 0

                # The anomaly: current year addition WITH accumulated depreciation
                mask = is_current_year & has_accum_dep

                if mask.any():
                    count = mask.sum()
                    issues.append(
                        f"WARNING: {count} asset(s) have In-Service Date in {current_year} (current year) "
                        f"but also have Accumulated Depreciation > $0. "
                        f"This is unusual - new additions should not have prior depreciation. "
                        f"Please verify: Are these truly new assets or existing assets with wrong dates?"
                    )
                    display_cols = ["Asset ID", "Description", "In Service Date", accum_dep_col, "Cost"]
                    details["current_year_with_accum_dep"] = df.loc[
                        mask, [c for c in display_cols if c in df.columns]
                    ].copy()
        except Exception as e:
            logger.debug(f"Could not check accumulated depreciation anomaly: {e}")

    # ==========================================================================
    # 7. SECTION 179 + ZERO/NEGATIVE INCOME WARNING
    # ==========================================================================
    # If §179 amount > 0 but taxable income <= 0, this is a problem
    # §179 deduction is limited to taxable income (cannot create a loss)

    sec179_col = None
    for col_name in ["Section 179", "Section 179 Amount", "Sec 179", "179 Amount", "Sec179"]:
        if col_name in df.columns:
            sec179_col = col_name
            break

    if sec179_col:
        sec179_values = pd.to_numeric(df[sec179_col], errors='coerce').fillna(0)
        has_sec179 = sec179_values > 0

        if has_sec179.any():
            count = has_sec179.sum()
            issues.append(
                f"INFO: {count} asset(s) have Section 179 deduction. "
                f"Verify taxable income is sufficient - §179 cannot exceed business taxable income."
            )

    # ==========================================================================
    # 8. MQ CONVENTION REQUIRES QUARTER SPECIFICATION
    # ==========================================================================
    # If convention is MQ (Mid-Quarter), the quarter (1-4) must be specified

    convention_col = None
    for col_name in ["Convention", "Depr Convention", "MACRS Convention"]:
        if col_name in df.columns:
            convention_col = col_name
            break

    quarter_col = None
    for col_name in ["Quarter", "Quarter (MQ)", "MQ Quarter", "Qtr"]:
        if col_name in df.columns:
            quarter_col = col_name
            break

    if convention_col:
        convention_values = df[convention_col].astype(str).str.upper().str.strip()
        is_mq = convention_values.isin(["MQ", "MID-QUARTER", "MIDQUARTER", "MID QUARTER"])

        if is_mq.any():
            if quarter_col:
                # Check if quarter is specified for MQ assets
                quarter_values = df[quarter_col].astype(str).str.strip()
                quarter_missing = quarter_values.isin(["", "nan", "None", "NaN"]) | df[quarter_col].isna()
                mask = is_mq & quarter_missing

                if mask.any():
                    count = mask.sum()
                    issues.append(
                        f"WARNING: {count} asset(s) use Mid-Quarter (MQ) convention but Quarter (1-4) is not specified. "
                        f"FA CS requires quarter for MQ convention."
                    )
                    display_cols = ["Asset ID", "Description", convention_col, quarter_col, "In Service Date"]
                    details["mq_missing_quarter"] = df.loc[
                        mask, [c for c in display_cols if c in df.columns]
                    ].copy()
            else:
                # No quarter column at all but MQ convention is used
                count = is_mq.sum()
                issues.append(
                    f"WARNING: {count} asset(s) use Mid-Quarter (MQ) convention but no Quarter column exists. "
                    f"Add 'Quarter' column with values 1-4 for MQ assets."
                )

    # ==========================================================================
    # 9. DEPRECIABLE BASIS CROSS-CHECK
    # ==========================================================================
    # Verify: Depreciable Basis = Cost - Section 179 - Bonus Amount
    # This catches calculation errors before FA CS import

    dep_basis_col = None
    for col_name in ["Depreciable Basis", "Depr Basis", "Basis", "Tax Basis"]:
        if col_name in df.columns:
            dep_basis_col = col_name
            break

    bonus_col = None
    for col_name in ["Bonus Amount", "Bonus Depreciation", "Bonus", "Special Depreciation"]:
        if col_name in df.columns:
            bonus_col = col_name
            break

    if dep_basis_col and has("Cost"):
        cost_values = pd.to_numeric(df["Cost"], errors='coerce').fillna(0)
        dep_basis_values = pd.to_numeric(df[dep_basis_col], errors='coerce').fillna(0)
        sec179_values = pd.to_numeric(df[sec179_col], errors='coerce').fillna(0) if sec179_col else 0
        bonus_values = pd.to_numeric(df[bonus_col], errors='coerce').fillna(0) if bonus_col else 0

        # Expected: Depreciable Basis = Cost - §179 - Bonus
        expected_basis = cost_values - sec179_values - bonus_values

        # Allow small tolerance for rounding
        tolerance = 1.0  # $1 tolerance
        mismatch = abs(dep_basis_values - expected_basis) > tolerance

        # Only check where depreciable basis is actually populated
        has_dep_basis = dep_basis_values > 0
        mask = mismatch & has_dep_basis

        if mask.any():
            count = mask.sum()
            issues.append(
                f"WARNING: {count} asset(s) have Depreciable Basis that doesn't match "
                f"Cost - §179 - Bonus. Please verify calculations."
            )
            display_cols = ["Asset ID", "Description", "Cost", sec179_col, bonus_col, dep_basis_col] if sec179_col and bonus_col else ["Asset ID", "Description", "Cost", dep_basis_col]
            details["basis_mismatch"] = df.loc[
                mask, [c for c in display_cols if c in df.columns]
            ].copy()

    # ==========================================================================
    # 10. CONVENTION VALIDATION (HY, MQ, MM only)
    # ==========================================================================
    # FA CS only accepts specific convention codes

    if convention_col:
        # Valid FA CS convention codes
        valid_conventions = ["HY", "MQ", "MM", "S/L", "SL", ""]  # HY=Half-Year, MQ=Mid-Quarter, MM=Mid-Month

        convention_values = df[convention_col].astype(str).str.upper().str.strip()
        # Normalize common variations
        convention_normalized = convention_values.replace({
            "HALF-YEAR": "HY", "HALF YEAR": "HY", "HALFYEAR": "HY",
            "MID-QUARTER": "MQ", "MID QUARTER": "MQ", "MIDQUARTER": "MQ",
            "MID-MONTH": "MM", "MID MONTH": "MM", "MIDMONTH": "MM",
            "NAN": "", "NONE": ""
        })

        invalid_convention = ~convention_normalized.isin(valid_conventions)

        if invalid_convention.any():
            count = invalid_convention.sum()
            invalid_values = convention_values[invalid_convention].unique()[:5]  # Show first 5
            issues.append(
                f"WARNING: {count} asset(s) have invalid Convention. "
                f"FA CS accepts: HY (Half-Year), MQ (Mid-Quarter), MM (Mid-Month). "
                f"Found: {', '.join(invalid_values)}"
            )
            display_cols = ["Asset ID", "Description", convention_col, "In Service Date"]
            details["invalid_convention"] = df.loc[
                invalid_convention, [c for c in display_cols if c in df.columns]
            ].copy()

    # ==========================================================================
    # 11. LIFE VALIDATION (must be numeric)
    # ==========================================================================
    # Recovery period/Life must be a number (years)

    life_col = None
    for col_name in ["Life", "Recovery Period", "Useful Life", "MACRS Life", "Depr Life"]:
        if col_name in df.columns:
            life_col = col_name
            break

    if life_col:
        life_values = df[life_col].astype(str).str.strip()

        # Check if values are numeric (allow decimals like 27.5, 39)
        def is_numeric_life(val):
            if val in ["", "nan", "None", "NaN"]:
                return True  # Empty is ok (will use default)
            try:
                float(val)
                return True
            except (ValueError, TypeError):
                return False

        non_numeric = ~life_values.apply(is_numeric_life)

        if non_numeric.any():
            count = non_numeric.sum()
            bad_values = life_values[non_numeric].unique()[:5]
            issues.append(
                f"WARNING: {count} asset(s) have non-numeric Life/Recovery Period. "
                f"Must be years (e.g., 5, 7, 15, 27.5, 39). Found: {', '.join(bad_values)}"
            )
            display_cols = ["Asset ID", "Description", life_col]
            details["invalid_life"] = df.loc[
                non_numeric, [c for c in display_cols if c in df.columns]
            ].copy()

    # ==========================================================================
    # 12. TRANSACTION TYPE VALIDATION (allowed values only)
    # ==========================================================================
    # Transaction Type must be one of the predefined values

    if "Transaction Type" in df.columns:
        # Valid transaction types (case-insensitive)
        valid_types = [
            "", "addition", "current year addition", "new", "purchase",
            "existing", "existing asset", "carryover", "prior",
            "disposal", "disposed", "sold", "retired", "scrapped",
            "transfer", "transferred", "reclass", "reclassify"
        ]

        trans_values = df["Transaction Type"].astype(str).str.lower().str.strip()
        invalid_type = ~trans_values.isin(valid_types)

        if invalid_type.any():
            count = invalid_type.sum()
            bad_values = df.loc[invalid_type, "Transaction Type"].unique()[:5]
            issues.append(
                f"WARNING: {count} asset(s) have unrecognized Transaction Type. "
                f"Expected: Addition, Existing, Disposal, or Transfer. "
                f"Found: {', '.join(str(v) for v in bad_values)}"
            )
            display_cols = ["Asset ID", "Description", "Transaction Type"]
            details["invalid_trans_type"] = df.loc[
                invalid_type, [c for c in display_cols if c in df.columns]
            ].copy()

    # ==========================================================================
    # CLEANUP AND RETURN
    # ==========================================================================
    df.drop(columns=["_ttype"], inplace=True, errors="ignore")

    # Log summary
    if issues:
        logger.warning(f"Validation completed: {len(issues)} issue(s) found")
        for issue in issues:
            logger.debug(f"  - {issue}")
    else:
        logger.info("Validation completed: No issues found")

    return issues, details


def get_critical_issues(issues: List[str]) -> List[str]:
    """
    Filter to only critical issues that should block export.

    Critical issues include:
    - CRITICAL: prefixed messages
    - Data that would cause FA CS import failure

    Args:
        issues: Full list of validation issues

    Returns:
        List of critical issues only
    """
    critical = []

    for issue in issues:
        if issue.startswith("CRITICAL:"):
            critical.append(issue)
        # Also consider these as blocking
        elif "Duplicate Asset ID" in issue:
            critical.append(issue)
        elif "Disposal Date earlier than In-Service" in issue:
            critical.append(issue)

    return critical


def has_critical_issues(issues: List[str]) -> bool:
    """
    Check if any critical (blocking) issues exist.

    Args:
        issues: Full list of validation issues

    Returns:
        True if critical issues found
    """
    return len(get_critical_issues(issues)) > 0


def _categorize_issue(issue: str) -> tuple:
    """
    Categorize an issue into a step number and category name.

    Returns:
        Tuple of (step_number, category_name)
    """
    issue_lower = issue.lower()

    # Step 1: Data Preparation (missing columns, data structure)
    if any(x in issue_lower for x in ["missing required column", "column is missing", "empty dataframe"]):
        return (1, "Data Preparation")

    # Step 2: Required Fields (missing dates, costs, descriptions)
    if any(x in issue_lower for x in [
        "missing cost", "missing description", "missing in-service",
        "missing dates", "zero cost", "negative cost"
    ]):
        return (2, "Required Fields")

    # Step 3: Classification (MACRS, method, convention)
    if any(x in issue_lower for x in [
        "classification", "macrs", "method", "convention",
        "useful life", "category"
    ]):
        return (3, "Classification")

    # Step 4: Data Integrity (duplicates, chronology, impossible values)
    if any(x in issue_lower for x in [
        "duplicate", "chronology", "exceeds cost", "earlier than",
        "future", "before", "after", "impossible"
    ]):
        return (4, "Data Integrity")

    # Step 5: Transaction-Specific (disposal/transfer validations)
    if any(x in issue_lower for x in [
        "disposal", "transfer", "transaction type", "proceeds"
    ]):
        return (5, "Transaction Validation")

    # Default to uncategorized
    return (0, "Other")


def format_validation_summary(issues: List[str], details: Dict[str, pd.DataFrame]) -> str:
    """
    Format validation results as a human-readable summary with step numbers.

    Args:
        issues: List of issue messages
        details: Dict of issue key -> DataFrame

    Returns:
        Formatted summary string with issues organized by validation step
    """
    if not issues:
        return "All validations passed. No issues found."

    lines = ["VALIDATION SUMMARY", "=" * 60]

    critical = get_critical_issues(issues)
    warnings = [i for i in issues if i not in critical and not i.startswith("INFO:")]
    info = [i for i in issues if i.startswith("INFO:")]

    # Categorize issues by step
    step_issues = {}
    for issue in issues:
        step_num, step_name = _categorize_issue(issue)
        if step_num not in step_issues:
            step_issues[step_num] = {"name": step_name, "critical": [], "warning": [], "info": []}

        if issue in critical:
            step_issues[step_num]["critical"].append(issue)
        elif issue in info:
            step_issues[step_num]["info"].append(issue)
        else:
            step_issues[step_num]["warning"].append(issue)

    # Output by step (sorted by step number)
    for step_num in sorted(step_issues.keys()):
        if step_num == 0:
            continue  # Skip "Other" for now

        step = step_issues[step_num]
        step_critical = step["critical"]
        step_warning = step["warning"]
        step_info = step["info"]

        if step_critical or step_warning or step_info:
            lines.append(f"\n📋 Step {step_num}: {step['name']}")
            lines.append("-" * 40)

            for issue in step_critical:
                lines.append(f"  🔴 {issue}")
            for issue in step_warning:
                lines.append(f"  🟡 {issue}")
            for issue in step_info:
                lines.append(f"  ℹ️  {issue}")

    # Output "Other" category if any
    if 0 in step_issues:
        other = step_issues[0]
        if other["critical"] or other["warning"] or other["info"]:
            lines.append(f"\n📋 Other Issues")
            lines.append("-" * 40)
            for issue in other["critical"]:
                lines.append(f"  🔴 {issue}")
            for issue in other["warning"]:
                lines.append(f"  🟡 {issue}")
            for issue in other["info"]:
                lines.append(f"  ℹ️  {issue}")

    # Summary counts
    lines.append("\n" + "=" * 60)
    lines.append(f"Total Issues: {len(issues)}")
    lines.append(f"  🔴 Critical: {len(critical)}")
    lines.append(f"  🟡 Warnings: {len(warnings)}")
    lines.append(f"  ℹ️  Info: {len(info)}")

    if critical:
        lines.append("\n⚠️  RECOMMENDATION: Fix critical issues before exporting.")

    return "\n".join(lines)
