# fixed_asset_ai/logic/advanced_validations.py

import pandas as pd
from typing import List, Dict


def advanced_validations(df: pd.DataFrame) -> List[Dict]:
    """
    Performs deeper tax + fixed asset validations.
    This is intentionally lightweight to avoid breaking the Streamlit environment.
    
    Returns a list of issue dictionaries:
        [
            {"row": 3, "issue": "In-service date missing"},
            {"row": 7, "issue": "MACRS life seems inconsistent with category"},
        ]
    """

    issues = []

    # -------------------------
    # 1. Check In-Service Dates
    # -------------------------
    for idx, row in df.iterrows():
        if "In Service Date" in df.columns:
            if pd.isna(row.get("In Service Date")) and pd.isna(row.get("Acquisition Date")):
                issues.append({
                    "row": idx,
                    "issue": "Missing both In-Service Date and Acquisition Date"
                })

    # ---------------------------------------------
    # 2. Validate MACRS Life vs Category Consistency
    # ---------------------------------------------
    for idx, row in df.iterrows():
        cat = str(row.get("Final Category") or "").lower()
        life = row.get("MACRS Life")

        if not life:
            continue

        # Basic rule set — lightweight but useful
        if "5yr" in cat and life != 5:
            issues.append({"row": idx, "issue": f"5yr category but MACRS life = {life}"})

        if "7yr" in cat and life != 7:
            issues.append({"row": idx, "issue": f"7yr category but MACRS life = {life}"})

        if ("15yr" in cat or "land improvement" in cat) and life != 15:
            issues.append({"row": idx, "issue": f"15yr category but MACRS life = {life}"})

        if ("27" in cat or "residential" in cat) and life not in [27, 27.5]:
            issues.append({"row": idx, "issue": f"Residential property but MACRS life = {life}"})

        if ("39" in cat or "nonresidential" in cat) and life != 39:
            issues.append({"row": idx, "issue": f"39yr property but MACRS life = {life}"})

    # -------------------------
    # 3. Check negative values
    # -------------------------
    for idx, row in df.iterrows():
        if "Cost" in df.columns and pd.notna(row["Cost"]):
            try:
                if float(row["Cost"]) < 0:
                    issues.append({"row": idx, "issue": "Negative cost value detected"})
            except Exception:
                pass

    # -------------------------
    # 4. Missing Method / Convention
    # -------------------------
    for idx, row in df.iterrows():
        # Handle pandas NA when checking for missing values
        # CRITICAL: Check pd.isna() separately to avoid pd.NA boolean evaluation
        method = row.get("Method")
        is_missing_method = False
        if pd.isna(method):
            is_missing_method = True
        elif method == "" or method is None:
            is_missing_method = True

        if is_missing_method:
            issues.append({"row": idx, "issue": "Missing depreciation method"})

        convention = row.get("Convention")
        is_missing_convention = False
        if pd.isna(convention):
            is_missing_convention = True
        elif convention == "" or convention is None:
            is_missing_convention = True

        if is_missing_convention:
            issues.append({"row": idx, "issue": "Missing depreciation convention"})

    return issues
