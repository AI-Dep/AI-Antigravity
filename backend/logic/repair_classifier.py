# fixed_asset_ai/logic/repair_classifier.py

import pandas as pd

REPAIR_KEYWORDS = [
    "repair", "patch", "fix", "maintenance", "service",
    "tune-up", "tune up", "cleaning", "paint", "repaint",
    "minor", "small", "replace part", "replacement part"
]

IMPROVEMENT_KEYWORDS = [
    "addition", "expansion", "new unit", "upgrade", "improvement",
    "renovation", "remodel", "build-out", "build out", "overhaul"
]

def classify_repair_vs_capital(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds:
      - RepairCapitalFlag: 'Likely Repair', 'Likely Capital', 'Ambiguous'
    Based only on description text for now (no GPT to keep it cheap and fast).
    """

    df = df.copy()
    flags = []

    if "Description" not in df.columns:
        df["RepairCapitalFlag"] = ""
        return df

    descs = df["Description"].astype(str).str.lower()

    for d in descs:
        is_repair = any(w in d for w in REPAIR_KEYWORDS)
        is_improv = any(w in d for w in IMPROVEMENT_KEYWORDS)

        if is_repair and not is_improv:
            flags.append("Likely Repair")
        elif is_improv and not is_repair:
            flags.append("Likely Capital")
        elif is_repair and is_improv:
            flags.append("Ambiguous")
        else:
            flags.append("Unclear")

    df["RepairCapitalFlag"] = flags
    return df
