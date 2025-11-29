# fixed_asset_ai/logic/tax_rules_loader.py

import os
import json
from datetime import datetime, date


# ----------------------------------------------------------------------
# JSON Loader
# ----------------------------------------------------------------------

RULES_BASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tax_rules")


def load_json(rule_name: str):
    """
    Load a JSON rule file from tax_rules folder.
    Automatically handles missing files with a warning.

    Example:
        BONUS = load_json("bonus")
    """
    filename = os.path.join(RULES_BASE_PATH, f"{rule_name}.json")

    if not os.path.exists(filename):
        print(f"[WARNING] Tax rule file missing: {filename}")
        return {}

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------
# Load all rule files
# ----------------------------------------------------------------------

BONUS_RULES = load_json("bonus")
SEC179_RULES = load_json("section179")
QIP_RULES = load_json("qip")
QPP_RULES = load_json("qpp")
MACRS_LIFE_RULES = load_json("macrs_life")
CONVENTION_RULES = load_json("conventions")
CLASS_KEYWORDS = load_json("classification_keywords")


# ----------------------------------------------------------------------
# HELPER: Extract date safely
# ----------------------------------------------------------------------

def _safe_date(val):
    try:
        return datetime.fromisoformat(val).date()
    except (ValueError, TypeError, AttributeError):
        return None


# ----------------------------------------------------------------------
# BONUS PERCENTAGE LOGIC (TCJA + OBBBA)
# ----------------------------------------------------------------------

def get_bonus_percentage(acq_date, insvc_date, tax_year):
    """
    Determine bonus depreciation percentage using:
    - TCJA phaseout (pre-OBBBA)
    - OBBBA permanent 100% bonus for property acquired on/after 2025-01-20
    """

    # Ensure dates
    acq = acq_date
    insvc = insvc_date or acq_date or date(tax_year, 1, 1)

    # --- OBBBA rule ---
    obbba_info = BONUS_RULES.get("obbba", {})
    obbba_start = _safe_date(obbba_info.get("start_date", ""))

    if acq and obbba_start and acq >= obbba_start:
        return obbba_info.get("bonus", 100)

    # --- TCJA Phase-out before OBBBA ---
    for band in BONUS_RULES.get("tcja_phaseout", []):
        year = band.get("year")
        if not year:
            continue

        # 2025 has a "ends_on" field (1/19/25)
        if year == tax_year and "ends_on" in band:
            cutoff = _safe_date(band["ends_on"])
            if insvc <= cutoff:
                return band.get("bonus", 0)

        # Normal year mapping
        if year == tax_year:
            return band.get("bonus", 0)

    return 0


# ----------------------------------------------------------------------
# QIP detection (Qualified Improvement Property)
# ----------------------------------------------------------------------

def is_qip(description: str) -> bool:
    desc = description.lower()

    positive = QIP_RULES.get("positive_terms", [])
    negative = QIP_RULES.get("negative_terms", [])

    if any(t in desc for t in positive):
        if not any(t in desc for t in negative):
            return True

    return False


# ----------------------------------------------------------------------
# QPP detection (OBBBA §168(n) Qualified Production Property)
# ----------------------------------------------------------------------

def is_qpp(description: str, industry: str, acq_date):
    desc = description.lower()
    ind = (industry or "").lower()

    qpp_keywords = QPP_RULES.get("keywords", [])
    eligible_ind = QPP_RULES.get("eligible_industries", [])
    start_date = _safe_date(QPP_RULES.get("start_date", "2025-01-20"))

    # Must be acquired after OBBBA date
    if acq_date and start_date and acq_date < start_date:
        return False

    if any(k in desc for k in qpp_keywords):
        if any(i in ind for i in eligible_ind):
            return True

    return False


# ----------------------------------------------------------------------
# MACRS Life Resolution
# ----------------------------------------------------------------------

def get_macrs_life(category_key: str):
    """
    Lookup GDS life from the JSON MACRS life table.
    """
    categories = MACRS_LIFE_RULES.get("categories", {})
    return categories.get(category_key, None)


# ----------------------------------------------------------------------
# Convention Resolution
# ----------------------------------------------------------------------

def get_convention_for_life(life):
    """
    Return convention (HY/MM/MQ) based on default table.
    """
    defaults = CONVENTION_RULES.get("defaults", {})
    life_str = str(life)
    return defaults.get(life_str, "HY")


# ----------------------------------------------------------------------
# Section 179 Limit & Eligibility
# ----------------------------------------------------------------------

def get_section179_limits(year):
    """
    Get §179 limit and phaseout for the selected year.
    """
    if str(year) in SEC179_RULES:
        return SEC179_RULES[str(year)]
    return SEC179_RULES["default"]


def eligible_for_179(category: str):
    """
    Determine whether a category is §179-eligible.
    """
    cat = category.lower()
    allow = SEC179_RULES.get("eligibility_keywords", [])
    deny = SEC179_RULES.get("not_allowed", [])

    if any(a in cat for a in allow):
        if not any(d in cat for d in deny):
            return True

    return False


# ----------------------------------------------------------------------
# Keyword-based Classification Helpers
# ----------------------------------------------------------------------

def keyword_hit(description: str, key_group: str) -> bool:
    """
    Check if the description hits any keyword group in classification_keywords.json
    
    Example:
        keyword_hit(desc, "it_equipment") → True/False
    """
    desc = description.lower()
    arr = CLASS_KEYWORDS.get(key_group, [])
    return any(k in desc for k in arr)


# ----------------------------------------------------------------------
# Override Pattern → Life Mapping
# ----------------------------------------------------------------------

def override_life_from_text(override_text: str):
    text = override_text.lower()
    patterns = CLASS_KEYWORDS.get("override_patterns", {})

    for p, life in patterns.items():
        if p in text:
            return life
    return None  # No match, let smart logic or fallback apply


# ----------------------------------------------------------------------
# MASTER RULESET
# (optional but recommended)
# ----------------------------------------------------------------------

def load_all_rules():
    """
    Returns all rule groups in one dict for convenience.
    """
    return {
        "bonus": BONUS_RULES,
        "section179": SEC179_RULES,
        "qip": QIP_RULES,
        "qpp": QPP_RULES,
        "macrs_life": MACRS_LIFE_RULES,
        "conventions": CONVENTION_RULES,
        "classification_keywords": CLASS_KEYWORDS,
    }
