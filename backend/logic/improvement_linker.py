# fixed_asset_ai/logic/improvement_linker.py

import pandas as pd

IMPROVEMENT_KEYWORDS = ["improvement", "roof", "hvac", "tenant", "ti", "build-out", "build out", "renovation", "remodel"]

def suggest_improvement_parents(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds:
      - Suggested Parent Asset ID (for improvement-like assets)

    Very heuristic: matches improvements to assets with similar description
    or to assets marked as 'Building' / 'Real Property'.
    """

    df = df.copy()

    if "Description" not in df.columns or "Asset ID" not in df.columns:
        return df

    # Identify improvement-like assets
    desc = df["Description"].astype(str).str.lower()
    is_improvement = desc.str.contains("|".join(IMPROVEMENT_KEYWORDS), na=False)

    suggested = []

    # Pre-split buildings / real property for parent candidates
    if "Final Category Used" in df.columns:
        building_mask = df["Final Category Used"].astype(str).str.contains(
            "Real Property|Building|Nonresidential|Residential",
            case=False, na=False
        )
        building_df = df[building_mask]
    else:
        building_df = df

    for idx, row in df.iterrows():
        if not is_improvement.iloc[idx]:
            suggested.append("")
            continue

        # Try to match by text hints
        desc_words = str(row["Description"]).lower().split()
        candidate = ""

        # 1) Try match by building_df description intersection
        best_score = 0
        for _, prow in building_df.iterrows():
            pdesc = str(prow["Description"]).lower().split()
            overlap = len(set(desc_words) & set(pdesc))
            if overlap > best_score:
                best_score = overlap
                candidate = prow.get("Asset ID", "")

        suggested.append(candidate)

    df["Suggested Parent Asset ID"] = suggested
    return df
