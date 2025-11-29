# fixed_asset_ai/logic/advanced_validations.py

import pandas as pd
from typing import List, Dict


def _safe_get(row, col_name, default=None):
    """Safely get a value from a row, handling missing columns and NA values."""
    try:
        val = row.get(col_name, default)
        if pd.isna(val):
            return default
        return val
    except Exception:
        return default


def _is_empty(val) -> bool:
    """Check if a value is empty, None, or NA."""
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(val, str) and val.strip() == "":
        return True
    return False


def advanced_validations(df: pd.DataFrame) -> List[Dict]:
    """
    Performs deeper tax + fixed asset validations.
    This is intentionally lightweight to avoid breaking the Streamlit environment.

    Now with improved error handling - returns partial results even if some
    validations fail, and gracefully handles missing columns.

    Returns a list of issue dictionaries:
        [
            {"row": 3, "issue": "In-service date missing"},
            {"row": 7, "issue": "MACRS life seems inconsistent with category"},
        ]
    """
    issues = []

    # Early return if DataFrame is empty or invalid
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return issues

    # Get available columns (case-insensitive lookup helper)
    available_cols = set(df.columns.tolist())

    def has_column(name: str) -> bool:
        """Check if column exists in DataFrame."""
        return name in available_cols

    # -------------------------
    # 1. Check In-Service Dates
    # -------------------------
    try:
        has_in_service = has_column("In Service Date")
        has_acquisition = has_column("Acquisition Date")

        if has_in_service or has_acquisition:
            for idx, row in df.iterrows():
                in_service_missing = True
                acquisition_missing = True

                if has_in_service:
                    in_service_missing = _is_empty(_safe_get(row, "In Service Date"))
                if has_acquisition:
                    acquisition_missing = _is_empty(_safe_get(row, "Acquisition Date"))

                if in_service_missing and acquisition_missing and (has_in_service or has_acquisition):
                    issues.append({
                        "row": idx,
                        "issue": "Missing both In-Service Date and Acquisition Date"
                    })
    except (KeyError, ValueError, TypeError) as e:
        # Log and continue if date validation fails
        import logging
        logging.debug(f"Date validation error: {e}")
        pass

    # ---------------------------------------------
    # 2. Validate MACRS Life vs Category Consistency
    # ---------------------------------------------
    try:
        has_category = has_column("Final Category")
        has_life = has_column("MACRS Life")

        if has_category and has_life:
            for idx, row in df.iterrows():
                cat = str(_safe_get(row, "Final Category", "")).lower()
                life = _safe_get(row, "MACRS Life")

                if _is_empty(life):
                    continue

                # Try to convert life to numeric for comparison
                try:
                    life_num = float(life)
                except (TypeError, ValueError):
                    continue

                # Basic rule set - lightweight but useful
                if "5yr" in cat and life_num != 5:
                    issues.append({"row": idx, "issue": f"5yr category but MACRS life = {life}"})

                if "7yr" in cat and life_num != 7:
                    issues.append({"row": idx, "issue": f"7yr category but MACRS life = {life}"})

                if ("15yr" in cat or "land improvement" in cat) and life_num != 15:
                    issues.append({"row": idx, "issue": f"15yr category but MACRS life = {life}"})

                if ("27" in cat or "residential" in cat) and life_num not in [27, 27.5]:
                    issues.append({"row": idx, "issue": f"Residential property but MACRS life = {life}"})

                if ("39" in cat or "nonresidential" in cat) and life_num != 39:
                    issues.append({"row": idx, "issue": f"39yr property but MACRS life = {life}"})
    except (KeyError, ValueError, TypeError) as e:
        # Log and continue if category validation fails
        import logging
        logging.debug(f"Category validation error: {e}")
        pass

    # -------------------------
    # 3. Check negative values
    # -------------------------
    try:
        if has_column("Cost"):
            for idx, row in df.iterrows():
                cost = _safe_get(row, "Cost")
                if cost is not None:
                    try:
                        if float(cost) < 0:
                            issues.append({"row": idx, "issue": "Negative cost value detected"})
                    except (TypeError, ValueError):
                        pass
    except (KeyError, ValueError, TypeError) as e:
        # Log and continue if cost validation fails
        import logging
        logging.debug(f"Cost validation error: {e}")
        pass

    # -------------------------
    # 4. Missing Method / Convention
    # -------------------------
    # NOTE: Skip validation for disposals and transfers:
    #   - Disposals use historical depreciation data (no new method/convention needed)
    #   - Transfers are already-classified assets being moved (no new classification)
    # Only additions and existing assets need method/convention for new depreciation calculations
    try:
        has_method = has_column("Method")
        has_convention = has_column("Convention")
        has_trans_type = has_column("Transaction Type")

        if has_method or has_convention:
            for idx, row in df.iterrows():
                # Skip disposals and transfers - they don't need new method/convention
                if has_trans_type:
                    trans_type = str(_safe_get(row, "Transaction Type", "")).lower()
                    is_disposal_or_transfer = any(x in trans_type for x in [
                        "disposal", "dispose", "sold", "retire", "transfer", "xfer"
                    ])
                    if is_disposal_or_transfer:
                        continue

                # Check method
                if has_method:
                    method = _safe_get(row, "Method")
                    if _is_empty(method):
                        issues.append({"row": idx, "issue": "Missing depreciation method"})

                # Check convention
                if has_convention:
                    convention = _safe_get(row, "Convention")
                    if _is_empty(convention):
                        issues.append({"row": idx, "issue": "Missing depreciation convention"})
    except (KeyError, ValueError, TypeError) as e:
        # Log and continue if method/convention validation fails
        import logging
        logging.debug(f"Method/convention validation error: {e}")
        pass

    return issues
