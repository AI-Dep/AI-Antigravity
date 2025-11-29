# fixed_asset_ai/logic/risk_engine.py

"""
Risk Scoring Engine – Enterprise Edition

Outputs per asset:
- RiskScore (0–100)
- IssueSeverity: OK / WARN / ERROR
- RiskFlags: list of flagged issues
"""

import pandas as pd


def add_flag(flags: list, msg: str):
    if msg not in flags:
        flags.append(msg)


def evaluate_asset_risk(row: pd.Series, tax_year: int) -> dict:
    flags = []
    score = 100

    desc = str(row.get("Description") or "").lower()
    cat_label = str(row.get("Final Category Used") or "").lower()
    rule_conf = row.get("Rule Confidence") or 0
    typo_score = row.get("TypoScore") or 100
    txn_type = row.get("Transaction Type") or ""

    life = row.get("Final Life Used")
    method = str(row.get("Final Method Used") or "")
    conv = row.get("Final Conv Used")

    cost = row.get("Cost")
    accum = row.get("Accum Dep")
    nbv = row.get("NBV")
    pis_date = row.get("PIS Date")
    disp_date = row.get("Disposal Date")

    # ---------------- Typo Severity ----------------
    if typo_score < 60:
        add_flag(flags, "Critical typos detected")
        score -= 25
    elif typo_score < 90:
        add_flag(flags, "Minor typos detected")
        score -= 10

    # ---------------- Classification Confidence ----------------
    if rule_conf < 0.5:
        add_flag(flags, "Low rule-engine confidence")
        score -= 20
    elif rule_conf < 0.75:
        add_flag(flags, "Medium classification uncertainty")
        score -= 10

    # ---------------- Missing Life / Method / Conv ----------------
    # NOTE: Skip these checks for disposals and transfers
    # - Disposals use historical depreciation data (no new method/convention needed)
    # - Transfers are already-classified assets being moved
    txn_type_lower = str(txn_type).lower()
    is_disposal_or_transfer = any(x in txn_type_lower for x in [
        "disposal", "dispose", "sold", "retire", "transfer", "xfer"
    ])

    if not is_disposal_or_transfer:
        if life in (None, "", 0):
            add_flag(flags, "Missing useful life")
            score -= 30

        if not method:
            add_flag(flags, "Missing depreciation method")
            score -= 30

        if not conv:
            add_flag(flags, "Missing convention")
            score -= 10

    # ---------------- SL Method Sanity ----------------
    m_norm = method.upper().replace(".", "").strip()
    if m_norm == "SL":
        # SL allowed only for software and real property
        if not (
            "software" in cat_label
            or "real property" in cat_label
            or "rental property" in cat_label
        ):
            add_flag(flags, "SL method used for non-SL category (check MACRS method)")
            score -= 35

    # ---------------- QIP Risk ----------------
    if "qip" in desc or "interior" in desc:
        if str(life) == "39":
            add_flag(flags, "Possible QIP misclassified as 39-year")
            score -= 35

    # ---------------- Building Component Risk ----------------
    BUILDING_COMPONENTS = ["roof", "hvac", "lighting", "condenser", "air handler"]
    if any(bc in desc for bc in BUILDING_COMPONENTS):
        if str(life) == "39" and "qip" not in desc and "interior" not in desc:
            add_flag(flags, "Capital building component – verify treatment")
            score -= 15

    # ---------------- NBV Drift ----------------
    try:
        if cost is not None and accum is not None and nbv is not None:
            drift = abs((cost - accum) - (nbv or 0))
            if drift > 5:
                add_flag(flags, "NBV drift detected (Cost - Accum ≠ NBV)")
                score -= 20
    except Exception:
        pass

    # ---------------- Transaction anomalies ----------------
    if txn_type == "Disposal":
        if disp_date is None:
            add_flag(flags, "Disposal without disposal date")
            score -= 20
        if nbv and nbv > 10:
            add_flag(flags, "Disposal NBV > 0 (check gain/loss)")
            score -= 20

    if txn_type == "Addition":
        if pis_date is None:
            add_flag(flags, "Addition without PIS Date")
            score -= 20
        elif pis_date.year != tax_year:
            add_flag(flags, "Addition PIS date not in selected tax year")
            score -= 15

    # ---------------- Category–Description mismatch ----------------
    if "vehicle" in desc and "vehicle" not in cat_label:
        add_flag(flags, "Description suggests vehicle but category does not")
        score -= 15

    if "software" in desc and "software" not in cat_label:
        add_flag(flags, "Description suggests software but category does not")
        score -= 15

    if "rack" in desc and "machinery" not in cat_label and "equipment" not in cat_label:
        add_flag(flags, "Racking likely 7-year equipment")
        score -= 10

    # ---------------- High-risk Keywords ----------------
    HIGH_RISK_WORDS = [
        "roof", "hvac", "furnace", "heat pump", "cooling",
        "condenser", "improvement", "lighting", "retrofit",
        "leasehold", "tenant"
    ]
    if any(w in desc for w in HIGH_RISK_WORDS):
        add_flag(flags, "High-risk asset: verify QIP vs Building treatment")
        score -= 10

    # ---------------- Final Score / Severity ----------------
    score = max(0, min(score, 100))

    if score >= 85:
        severity = "OK"
    elif score >= 60:
        severity = "WARN"
    else:
        severity = "ERROR"

    return {
        "RiskScore": score,
        "IssueSeverity": severity,
        "RiskFlags": flags,
    }


def run_risk_engine(df: pd.DataFrame, tax_year: int) -> pd.DataFrame:
    results = df.apply(lambda r: evaluate_asset_risk(r, tax_year), axis=1)

    df["RiskScore"] = results.apply(lambda x: x["RiskScore"])
    df["IssueSeverity"] = results.apply(lambda x: x["IssueSeverity"])
    df["RiskFlags"] = results.apply(lambda x: x["RiskFlags"])

    return df
