# fixed_asset_ai/logic/materiality.py

import pandas as pd

def compute_materiality(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds:
      - MaterialityScore (0–100)
      - ReviewPriority ('Low', 'Medium', 'High')

    Uses Cost, NBV, Transaction Type, Recapture risk, etc.
    """

    df = df.copy()

    # Base scores by size
    cost = df["Cost"].fillna(0)
    nbv = df["NBV"].fillna(0)

    # Start with magnitude-based score
    base_score = (cost.abs() + nbv.abs()) / (cost.abs().max() + 1e-6) * 60
    base_score = base_score.clip(0, 60)

    # Bump for disposals and transfers
    txn = df.get("Transaction Type", "")
    bump_disposal = (txn == "Disposal") * 20
    bump_transfer = (txn == "Transfer") * 10

    # Bump for gain/loss and recapture-like conditions
    proceeds = df.get("Proceeds", 0).fillna(0)
    gl = df.get("Book Gain/Loss", 0).fillna(0)
    bump_gain = (proceeds > nbv) * 10
    bump_large_gl = (gl.abs() > (nbv.abs() * 0.5)).astype(int) * 10  # big GL relative to NBV

    score = (base_score + bump_disposal + bump_transfer + bump_gain + bump_large_gl).clip(0, 100)

    df["MaterialityScore"] = score

    # Priority buckets
    priority = []
    for s in score:
        if s >= 70:
            priority.append("High")
        elif s >= 40:
            priority.append("Medium")
        else:
            priority.append("Low")

    df["ReviewPriority"] = priority
    return df
