import pandas as pd

def safe(df, col):
    return col in df.columns

def advanced_validations(df: pd.DataFrame):
    """
    Return:
        messages: list[str]
        details: dict[issue_key -> df]
    """

    msgs = []
    details = {}

    # -------------------------------
    # A1. Completeness Checks Across Sheets
    # -------------------------------
    if safe(df, "Asset ID"):
        dup_ids = df["Asset ID"][df["Asset ID"].duplicated()]
        if len(dup_ids) > 0:
            msgs.append("Duplicate Asset IDs detected across sheets.")
            details["duplicate_asset_ids"] = df[df["Asset ID"].isin(dup_ids)][["Asset ID", "Description"]]

    # -------------------------------
    # A2. Asset ID Integrity Validation
    # -------------------------------
    if safe(df, "Asset ID"):
        mask_bad = df["Asset ID"].astype(str).str.strip().isin(["", "nan", "None"])
        if mask_bad.any():
            msgs.append("Blank or invalid Asset IDs found.")
            details["blank_asset_ids"] = df.loc[mask_bad, ["Description"]]

    # -------------------------------
    # A3. Rollforward Reasonableness (light version)
    # -------------------------------
    if all(safe(df, col) for col in ["Cost", "NBV", "Transaction Type"]):
        additions_cost = df[df["Transaction Type"] == "Addition"]["Cost"].sum()
        disposals_nbv = df[df["Transaction Type"] == "Disposal"]["NBV"].sum()

        snapshot_total_nbv = df["NBV"].sum()

        if additions_cost < 0 or disposals_nbv < 0:
            msgs.append("Unusual rollforward: negative additions or disposals.")
            details["rollforward_negative"] = pd.DataFrame({
                "Total Additions Cost": [additions_cost],
                "Total Disposals NBV": [disposals_nbv],
                "Snapshot Total NBV": [snapshot_total_nbv],
            })

    # -------------------------------
    # A4. Book vs Tax Reconciliation (if book columns exist)
    # -------------------------------
    candidate_book_cols = ["Book Cost", "Book NBV", "Book Accum Dep"]
    if any(safe(df, col) for col in candidate_book_cols):

        if safe(df, "Book Cost") and safe(df, "Cost"):
            mask = df["Book Cost"].notna() & df["Cost"].notna() & (df["Book Cost"] != df["Cost"])
            if mask.any():
                msgs.append("Book vs Tax cost mismatch detected.")
                details["book_tax_cost_mismatch"] = df.loc[mask, ["Asset ID", "Description", "Book Cost", "Cost"]]

        if safe(df, "Book NBV") and safe(df, "NBV"):
            mask = df["Book NBV"].notna() & df["NBV"].notna() & (df["Book NBV"] != df["NBV"])
            if mask.any():
                msgs.append("Book vs Tax NBV mismatch detected.")
                details["book_tax_nbv_mismatch"] = df.loc[mask, ["Asset ID", "Description", "Book NBV", "NBV"]]

    # -------------------------------
    # A5. Method/Life/Convention Reconciliation
    # -------------------------------
    if safe(df, "Final Category Used"):
        for idx, row in df.iterrows():
            cat = row["Final Category Used"]
            life = row.get("Final Life Used")
            method = row.get("Final Method Used", "")

            if pd.isna(life) or pd.isna(method):
                # skip unclassified for now
                continue

            # Category → expected life mapping:
            if "Equipment" in cat and life not in [5, 7]:
                msgs.append("Unexpected life for Equipment asset.")
                details.setdefault("life_mismatch_equipment", pd.DataFrame())
                details["life_mismatch_equipment"] = pd.concat(
                    [details["life_mismatch_equipment"], df.loc[[idx], ["Asset ID", "Description", "Final Category Used", "Final Life Used"]]]
                )

            if "Land Improvement" in cat and life not in [15]:
                msgs.append("Unexpected life for Land Improvement asset.")
                details.setdefault("life_mismatch_land_impr", pd.DataFrame())
                details["life_mismatch_land_impr"] = pd.concat(
                    [details["life_mismatch_land_impr"], df.loc[[idx], ["Asset ID", "Description", "Final Category Used", "Final Life Used"]]]
                )

    # -------------------------------
    # A6. Depreciation Drift Test (NBV vs Cost - Accum Dep)
    # -------------------------------
    if safe(df, "Accum Dep") and safe(df, "Cost") and safe(df, "NBV"):
        mask = df["Cost"].notna() & df["Accum Dep"].notna() & df["NBV"].notna()
        mismatch = df.loc[mask][
            abs(df["Cost"] - df["Accum Dep"] - df["NBV"]) > 5  # allow small rounding error
        ]

        if len(mismatch) > 0:
            msgs.append("Possible depreciation drift: Cost - Accum Dep != NBV.")
            details["depreciation_drift"] = mismatch[["Asset ID", "Description", "Cost", "Accum Dep", "NBV"]]

    # -------------------------------
    # A7. Addition/Disposal Year Cutoff
    # -------------------------------
    if safe(df, "PIS Date") and safe(df, "Transaction Type"):
        # detect additions posted to wrong year
        mask = (
            df["Transaction Type"] == "Addition"
        ) & (
            df["PIS Date"].dt.year < df["PIS Date"].dt.year.min()
        )
        if mask.any():
            msgs.append("Possible late-posted addition (PIS date suspicious).")
            details["late_additions"] = df.loc[mask, ["Asset ID", "Description", "PIS Date"]]

    # -------------------------------
    # A8. Improvement Linking Test
    # -------------------------------
    if safe(df, "Parent Asset ID") and safe(df, "Final Category Used"):
        mask = (
            df["Final Category Used"].str.contains("Improvement|Roof|HVAC|Flooring|Build", case=False, na=False)
        ) & (
            df["Parent Asset ID"].astype(str).str.strip() == ""
        )
        if mask.any():
            msgs.append("Improvement assets missing parent linkage.")
            details["improvement_missing_parent"] = df.loc[mask, ["Asset ID", "Description", "Final Category Used"]]

    # A9 — Suggested Parent Exists but Parent Asset not in data
    if safe(df, "Suggested Parent Asset ID"):
        mask = df["Suggested Parent Asset ID"].astype(str).str.strip() != ""
        missing_parent = df.loc[mask]["Suggested Parent Asset ID"].isin(df["Asset ID"]) == False

        if missing_parent.any():
            msgs.append("Suggested parent asset not found in dataset (possible incomplete file).")
            details["suggested_parent_missing"] = df.loc[
                missing_parent,
                ["Asset ID", "Description", "Suggested Parent Asset ID"]
            ]

    return msgs, details
