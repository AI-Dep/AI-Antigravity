"""
Depreciation Recapture Calculations

Per IRC §1245 and §1250:
- Section 1245: Personal property - recapture ALL depreciation as ordinary income
- Section 1250: Real property - recapture accelerated depreciation (if any) as ordinary income
- Unrecaptured §1250 gain: Straight-line depreciation taxed at 25% (not at capital gains rate)

CRITICAL: Recapture can never exceed the gain on sale.
"""

import pandas as pd
from typing import Dict, Tuple


def safe_cols(df, cols):
    """Return only the columns that actually exist in df."""
    return [c for c in cols if c in df.columns]


# ==============================================================================
# SECTION 1245 RECAPTURE - Personal Property (IRC §1245)
# ==============================================================================

def calculate_section_1245_recapture(
    cost: float,
    accumulated_depreciation: float,
    proceeds: float,
    section_179_taken: float = 0.0,
    bonus_taken: float = 0.0
) -> Dict[str, float]:
    """
    Calculate Section 1245 recapture for personal property.

    IRC §1245 - Depreciation recapture on personal property:
    - ALL depreciation (including bonus + Section 179) is recaptured as ordinary income
    - Recapture limited to gain on sale
    - Applies to: machinery, equipment, vehicles, computers, etc.

    Args:
        cost: Original cost basis
        accumulated_depreciation: Total depreciation taken (MACRS + bonus + 179)
        proceeds: Sale proceeds
        section_179_taken: Section 179 expensing taken
        bonus_taken: Bonus depreciation taken

    Returns:
        Dict with recapture amounts:
        - total_depreciation: All depreciation taken
        - adjusted_basis: Cost minus depreciation
        - gain_on_sale: Proceeds minus adjusted basis
        - section_1245_recapture: Ordinary income recapture (lesser of depreciation or gain)
        - capital_gain: Remaining gain (if any) taxed as capital gain
    """
    # Total depreciation includes MACRS + bonus + Section 179
    total_depreciation = accumulated_depreciation + section_179_taken + bonus_taken

    # Adjusted basis = cost minus all depreciation
    adjusted_basis = cost - total_depreciation

    # Gain/loss on sale
    gain_on_sale = proceeds - adjusted_basis

    if gain_on_sale <= 0:
        # No gain = no recapture (loss on sale)
        return {
            "total_depreciation": total_depreciation,
            "adjusted_basis": adjusted_basis,
            "gain_on_sale": gain_on_sale,
            "section_1245_recapture": 0.0,
            "capital_gain": 0.0,
            "capital_loss": abs(gain_on_sale) if gain_on_sale < 0 else 0.0,
        }

    # Section 1245 recapture = LESSER of (depreciation taken OR gain on sale)
    # This is ORDINARY INCOME
    section_1245_recapture = min(total_depreciation, gain_on_sale)

    # Remaining gain (if any) is capital gain
    capital_gain = max(gain_on_sale - section_1245_recapture, 0.0)

    return {
        "total_depreciation": total_depreciation,
        "adjusted_basis": adjusted_basis,
        "gain_on_sale": gain_on_sale,
        "section_1245_recapture": section_1245_recapture,
        "capital_gain": capital_gain,
        "capital_loss": 0.0,
    }


# ==============================================================================
# SECTION 1250 RECAPTURE - Real Property (IRC §1250)
# ==============================================================================

def calculate_section_1250_recapture(
    cost: float,
    accumulated_depreciation: float,
    proceeds: float,
    accelerated_depreciation: float = 0.0
) -> Dict[str, float]:
    """
    Calculate Section 1250 recapture for real property.

    IRC §1250 - Depreciation recapture on real property:
    - Only ACCELERATED depreciation over straight-line is recaptured as ordinary income
    - For property placed in service after 1986: ALL real property uses straight-line (no recapture)
    - Unrecaptured §1250 gain: Straight-line depreciation is taxed at 25% (not cap gains rate)

    NOTE: For modern MACRS real property (post-1986), there is NO Section 1250 recapture
    because real property uses straight-line only. However, there IS unrecaptured §1250 gain.

    Args:
        cost: Original cost basis
        accumulated_depreciation: Total straight-line depreciation taken
        proceeds: Sale proceeds
        accelerated_depreciation: Excess of accelerated over straight-line (usually 0 for post-1986)

    Returns:
        Dict with recapture amounts:
        - total_depreciation: All depreciation taken
        - adjusted_basis: Cost minus depreciation
        - gain_on_sale: Proceeds minus adjusted basis
        - section_1250_recapture: Ordinary income (excess accelerated, usually $0 for post-1986)
        - unrecaptured_1250_gain: Straight-line depreciation taxed at 25%
        - capital_gain: Remaining gain taxed at capital gains rates
    """
    # Adjusted basis = cost minus depreciation
    adjusted_basis = cost - accumulated_depreciation

    # Gain/loss on sale
    gain_on_sale = proceeds - adjusted_basis

    if gain_on_sale <= 0:
        # No gain = no recapture
        return {
            "total_depreciation": accumulated_depreciation,
            "adjusted_basis": adjusted_basis,
            "gain_on_sale": gain_on_sale,
            "section_1250_recapture": 0.0,
            "unrecaptured_1250_gain": 0.0,
            "capital_gain": 0.0,
            "capital_loss": abs(gain_on_sale) if gain_on_sale < 0 else 0.0,
        }

    # Section 1250 recapture (accelerated over straight-line)
    # For post-1986 property using SL: this is $0
    section_1250_recapture = min(accelerated_depreciation, gain_on_sale)

    # Unrecaptured §1250 gain = straight-line depreciation (taxed at 25%)
    # Limited to remaining gain after Section 1250 recapture
    remaining_gain_after_1250 = gain_on_sale - section_1250_recapture
    unrecaptured_1250_gain = min(accumulated_depreciation, remaining_gain_after_1250)

    # Capital gain = remaining gain (taxed at 0/15/20% rates)
    capital_gain = max(remaining_gain_after_1250 - unrecaptured_1250_gain, 0.0)

    return {
        "total_depreciation": accumulated_depreciation,
        "adjusted_basis": adjusted_basis,
        "gain_on_sale": gain_on_sale,
        "section_1250_recapture": section_1250_recapture,
        "unrecaptured_1250_gain": unrecaptured_1250_gain,
        "capital_gain": capital_gain,
        "capital_loss": 0.0,
    }


# ==============================================================================
# RECAPTURE DETERMINATION - Which section applies?
# ==============================================================================

def determine_recapture_type(final_category: str) -> str:
    """
    Determine if asset is subject to Section 1245 or 1250 recapture.

    Args:
        final_category: MACRS classification

    Returns:
        "1245" for personal property (machinery, equipment, vehicles)
        "1250" for real property (buildings, land improvements)
        "none" for non-depreciable property (land)
    """
    category_upper = final_category.upper()

    # Section 1250 - Real Property
    if any(x in category_upper for x in [
        "REAL PROPERTY", "RESIDENTIAL", "NONRESIDENTIAL",
        "BUILDING", "LAND IMPROVEMENT"
    ]):
        return "1250"

    # Land - not depreciable
    if "LAND" in category_upper and "IMPROVEMENT" not in category_upper:
        return "none"

    # Everything else - Section 1245 (personal property)
    # Machinery, equipment, vehicles, computers, furniture, etc.
    return "1245"

def recapture_analysis(df: pd.DataFrame):
    """
    Returns:
      - messages: list[str]
      - details: dict(issue_key -> DataFrame)

    Automatically tolerates missing columns (no KeyErrors).
    """

    messages = []
    details = {}

    # Must have these for disposal logic to work
    required = ["Transaction Type", "Final Category Used", "NBV", "Proceeds"]
    if not all(col in df.columns for col in required):
        return messages, details  # nothing to analyze

    is_disposal = df["Transaction Type"] == "Disposal"

    # ------------------------------------------
    # 1. Section 1245 Recapture Risk
    # ------------------------------------------
    mask_1245 = (
        is_disposal &
        df["Final Category Used"].str.contains(
            "Equipment|Machinery|Computer|Vehicle|Office Equipment",
            case=False, na=False
        ) &
        (df["Proceeds"].fillna(0) > df["NBV"].fillna(0))
    )

    if mask_1245.any():
        messages.append("Section 1245 Recapture Risk detected.")
        details["sec1245_recapture_risk"] = df.loc[
            mask_1245,
            safe_cols(df, [
                "Asset ID", "Description", "Final Category Used",
                "Cost", "Accum Dep", "NBV", "Proceeds", "Book Gain/Loss"
            ])
        ]

    # ------------------------------------------
    # 2. Section 1250 Unrecaptured Gain (Real Property)
    # ------------------------------------------
    mask_1250 = (
        is_disposal &
        df["Final Category Used"].str.contains(
            "Real Property|Residential|Nonresidential",
            case=False, na=False
        ) &
        (df["Proceeds"].fillna(0) > df["NBV"].fillna(0))
    )

    if mask_1250.any():
        messages.append("Section 1250 unrecaptured gain potential.")
        details["sec1250_unrecaptured_gain"] = df.loc[
            mask_1250,
            safe_cols(df, [
                "Asset ID", "Description", "Final Category Used",
                "Cost", "Accum Dep", "NBV", "Proceeds"
            ])
        ]

    # ------------------------------------------
    # 3. Ordinary Income / Bad NBV
    # ------------------------------------------
    mask_bad_nbv = (
        is_disposal &
        df["NBV"].notna() &
        (df["NBV"] < 0)
    )
    if mask_bad_nbv.any():
        messages.append("Negative NBV detected — potential bad depreciation or ordinary income issue.")
        details["negative_nbv"] = df.loc[
            mask_bad_nbv,
            safe_cols(df, ["Asset ID", "Description", "NBV", "Cost", "Accum Dep"])
        ]

    mask_missing_gainloss = (
        is_disposal &
        (df["Proceeds"].fillna(0) != df["NBV"].fillna(0)) &
        ("Book Gain/Loss" in df.columns and df["Book Gain/Loss"].isna())
    )
    if mask_missing_gainloss.any():
        messages.append("Disposals missing Gain/Loss despite NBV ≠ Proceeds.")
        details["missing_gainloss"] = df.loc[
            mask_missing_gainloss,
            safe_cols(df, ["Asset ID", "Description", "Proceeds", "NBV"])
        ]

    # ------------------------------------------
    # 4. Possible Abandonment
    # ------------------------------------------
    if "Disposal Type" in df.columns:
        mask_abandon = (
            is_disposal &
            (df["Proceeds"].fillna(0) == 0) &
            df["Disposal Type"].str.contains("sale", case=False, na=False)
        )
        if mask_abandon.any():
            messages.append("Marked SALE but Proceeds = 0 — possible abandonment.")
            details["possible_abandonment"] = df.loc[
                mask_abandon,
                safe_cols(df, ["Asset ID", "Description", "Disposal Type", "Proceeds", "NBV"])
            ]

    # ------------------------------------------
    # 5. Selling Fees but No Proceeds
    # ------------------------------------------
    if "Selling Fees" in df.columns:
        mask_fees = (
            is_disposal &
            df["Selling Fees"].notna() &
            (df["Proceeds"].fillna(0) == 0)
        )
        if mask_fees.any():
            messages.append("Selling Fees exist but Proceeds = 0 — inconsistent.")
            details["fees_without_proceeds"] = df.loc[
                mask_fees,
                safe_cols(df, ["Asset ID", "Description", "Selling Fees", "Proceeds"])
            ]

    # ------------------------------------------
    # 6. Improvement disposal without Parent ID
    # ------------------------------------------
    if "Parent Asset ID" in df.columns:
        mask_imp = (
            is_disposal &
            df["Final Category Used"].str.contains(
                "Improvement|Build|Roof|HVAC",
                case=False, na=False
            ) &
            (df["Parent Asset ID"].astype(str).str.strip() == "")
        )
        if mask_imp.any():
            messages.append("Possible improvement disposal with missing Parent Asset ID.")
            details["improvement_missing_parent"] = df.loc[
                mask_imp,
                safe_cols(df, ["Asset ID", "Description", "Parent Asset ID", "Final Category Used"])
            ]

    return messages, details
