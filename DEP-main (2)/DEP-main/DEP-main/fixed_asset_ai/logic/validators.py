import pandas as pd


def validate_assets(df: pd.DataFrame):
    """
    Returns:
        issues: list of short messages
        details: dict of issue_key -> DataFrame of affected rows

    This validator is aligned with:
      - New disposal logic (no classification required)
      - Additions & Transfers using full MACRS classification
      - Required fields for FA CS export
      - Realistic data flaws from client schedules
    """

    issues = []
    details = {}

    # Helper: check column existence
    def has(*cols):
        return all(c in df.columns for c in cols)

    # Normalize case
    if "Transaction Type" in df.columns:
        df["_ttype"] = df["Transaction Type"].astype(str).str.lower()
    else:
        df["_ttype"] = ""

    # ----------------------------------------------------------------------
    # 1. Additions: Missing Cost
    # ----------------------------------------------------------------------
    if has("Cost", "_ttype"):
        mask = (df["_ttype"].str.contains("add")) & (df["Cost"].isna())
        if mask.any():
            issues.append("Additions missing Cost.")
            details["missing_cost_additions"] = df.loc[
                mask, ["Asset ID", "Description", "Cost"]
            ]

    # ----------------------------------------------------------------------
    # 2. Missing Description
    # ----------------------------------------------------------------------
    if "Description" in df.columns:
        mask = df["Description"].astype(str).str.strip().eq("")
        if mask.any():
            issues.append("Assets missing Description.")
            details["missing_description"] = df.loc[
                mask, ["Asset ID", "Cost", "Transaction Type"]
            ]

    # ----------------------------------------------------------------------
    # 3. Missing PIS Date (post-normalization)
    # ----------------------------------------------------------------------
    if has("In Service Date"):
        mask = df["In Service Date"].isna()
        if mask.any():
            issues.append("Assets missing In-Service Date (after fallback to Acquisition Date).")
            details["missing_pis"] = df.loc[
                mask, ["Asset ID", "Description", "Acquisition Date"]
            ]

    # ----------------------------------------------------------------------
    # 4. Classification Missing — ONLY for Additions + Transfers
    # ----------------------------------------------------------------------
    if has("Final Category", "_ttype"):
        mask = (
            df["_ttype"].isin(["additions", "addition", "transfer", "transfers"])
            & df["Final Category"].astype(str).str.strip().eq("")
        )
        if mask.any():
            issues.append("Missing MACRS classification for Additions/Transfers.")
            details["missing_classification"] = df.loc[
                mask,
                ["Asset ID", "Description", "Transaction Type", "Final Category"],
            ]

    # ----------------------------------------------------------------------
    # 5. Suspicious: Additions with zero cost
    # ----------------------------------------------------------------------
    if has("Cost", "_ttype"):
        mask = (
            df["_ttype"].str.contains("add")
            & (df["Cost"].fillna(0) == 0)
        )
        if mask.any():
            issues.append("Additions with Cost = 0 detected (verify client data).")
            details["zero_cost_additions"] = df.loc[
                mask, ["Asset ID", "Description", "Cost"]
            ]

    # ----------------------------------------------------------------------
    # 6. In-Service Date older than Acquisition Date (client data error)
    # ----------------------------------------------------------------------
    if has("In Service Date", "Acquisition Date"):
        mask = (
            df["In Service Date"].notna()
            & df["Acquisition Date"].notna()
            & (df["In Service Date"] < df["Acquisition Date"])
        )
        if mask.any():
            issues.append("In-Service Date earlier than Acquisition Date (client input error).")
            details["pis_before_acq"] = df.loc[
                mask, ["Asset ID", "Description", "Acquisition Date", "In Service Date"]
            ]

    # ----------------------------------------------------------------------
    # 7. Disposal rows WITHOUT Transaction Type properly detected
    # ----------------------------------------------------------------------
    if has("Transaction Type"):
        mask = (
            df["Transaction Type"].astype(str).str.contains("dispos", case=False)
            & df["Transaction Type"].astype(str).str.strip().eq("")
        )
        if mask.any():
            issues.append("Disposals detected but Transaction Type string inconsistent.")
            details["disposal_inconsistent"] = df.loc[
                mask, ["Asset ID", "Description", "Transaction Type"]
            ]

    # ----------------------------------------------------------------------
    # DONE
    # ----------------------------------------------------------------------
    df.drop(columns=["_ttype"], inplace=True, errors="ignore")
    return issues, details
