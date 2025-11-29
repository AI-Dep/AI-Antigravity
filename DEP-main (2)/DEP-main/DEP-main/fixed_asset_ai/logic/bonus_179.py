# fixed_asset_ai/logic/bonus_179.py

import pandas as pd

def compute_bonus_179_suggestions(
    df: pd.DataFrame,
    tax_year: int,
    sec179_limit: float,
    sec179_phaseout_threshold: float,
    other_179_cost: float,
    business_income_limit: float
) -> pd.DataFrame:
    """
    Compute suggested bonus % and §179 amounts for additions, honoring:
      - §179 dollar limit & phase-out: limit reduced by (Total 179 cost - threshold)
      - Business income limitation
    We do NOT finalize elections here; we propose SuggestedBonusPct, SuggestedBonusAmt, Suggested179Amt.
    CPA can override in the review grid.
    """

    df = df.copy()

    # Ensure required columns exist
    for col, default in {
        "Transaction Type": "",
        "Cost": 0.0,
        "PIS Date": pd.NaN,
        "Section 2_179 Eligible": False,
        "Bonus Eligible": False,
        "ADS Property": False,
        "MaterialityScore": 0.0,
    }.items():
        if col not in df.columns:
            df[col] = default

    # Mask: additions that are 179-eligible
    is_add = df["Transaction Type"] == "Addition"
    is_179_eligible = df.get("Section 2_179 Eligible", False)  # keep your column name
    is_bonus_eligible = df.get("Bonus Eligible", False)
    is_ads = df.get("ADS Property", False)

    # Compute total 179-eligible cost (this schedule only)
    df["Cost_num"] = df["Cost"].apply(lambda x: float(x) if pd.notna(x) else 0.0)
    total_179_cost_this_file = df.loc[is_add & is_179_eligible, "Cost_num"].sum()

    # Phase-out adjustment on §179 limit
    # Effective limit = max(0, sec179_limit - max(0, (Total 179 property cost + other_179_cost - phaseout_threshold)))
    total_179_property = total_179_cost_this_file + other_179_cost
    phaseout_reduction = max(0.0, total_179_property - sec179_phaseout_threshold)
    effective_dollar_limit = max(0.0, sec179_limit - phaseout_reduction)

    # Effective 179 cap also limited by business income
    effective_179_cap = min(effective_dollar_limit, business_income_limit)

    # Suggested 179 amount: start with "full cost" for 179-eligible additions
    df["Suggested179Amt"] = 0.0
    mask_179 = is_add & is_179_eligible

    if mask_179.any() and effective_179_cap > 0:
        # Sort 179-eligible additions by MaterialityScore descending
        tmp = df.loc[mask_179, ["Asset ID", "Cost_num", "MaterialityScore"]].copy()
        tmp = tmp.sort_values(by=["MaterialityScore", "Cost_num"], ascending=[False, False])

        remaining = effective_179_cap
        suggestions = {}

        for _, row in tmp.iterrows():
            cid = row["Asset ID"]
            cost = row["Cost_num"]
            if remaining <= 0:
                amt = 0.0
            else:
                amt = min(cost, remaining)
            suggestions[cid] = amt
            remaining -= amt
            if remaining <= 0:
                break

        df.loc[mask_179, "Suggested179Amt"] = df.loc[mask_179, "Asset ID"].map(suggestions).fillna(0.0)

    # Bonus suggestions:
    # Basic rule: if Bonus Eligible and not ADS and life <= 20, choose statutory % based on year.
    def statutory_bonus_pct(pis):
        try:
            y = pis.year
        except Exception:
            return 0
        # Example: adjust per tax law; you can tweak these as needed for current years.
        if y >= 2023:
            return 80
        elif y == 2022:
            return 100
        else:
        # Pre-2023: 100% (placeholder)
            return 100

    df["SuggestedBonusPct"] = 0.0
    df["SuggestedBonusAmt"] = 0.0

    mask_bonus = is_add & is_bonus_eligible & (~is_ads)
    df.loc[mask_bonus, "SuggestedBonusPct"] = df.loc[mask_bonus, "PIS Date"].apply(statutory_bonus_pct)
    df.loc[mask_bonus, "SuggestedBonusAmt"] = (
        df.loc[mask_bonus, "Cost_num"] * (df.loc[mask_bonus, "SuggestedBonusPct"] / 100.0)
    ).round(2)

    # Clean up
    df.drop(columns=["Cost_num"], inplace=True)

    return df
