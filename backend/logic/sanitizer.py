# fixed_asset_ai/logic/sanitizer.py

import re
from typing import List

# Words to ignore during tokenization
_STOPWORDS = {
    "the", "and", "for", "with", "of", "to", "a", "an", "in", "on", "by", "at",
    "old", "new", "misc", "miscellaneous"
}

# Transaction-related words to remove
_TRANSACTION_WORDS = {
    "disposed", "disposal", "scrap", "scrapped", "sold", "retired",
    "writeoff", "write-off", "written off"
}

# Abbreviation expansions
_ABBREVIATIONS = {
    "m&e": "machinery and equipment",
    "m & e": "machinery and equipment",
    "equip": "equipment",
    "eqp": "equipment",
    "equipmt": "equipment",
    "equipmnt": "equipment",
    "comp": "computer",
    "pc": "computer",
    "it equip": "it equipment",
    "sys": "system",
    "xray": "x-ray",
    "diag": "diagnostic",
    "med": "medical",
    "dept": "department",
    "pos": "point of sale",
    "av": "audio visual",
    # Common client abbreviations from prior tool
    "whse": "warehouse",
    "wh": "warehouse",
    "mfg": "manufacturing",
    "manuf": "manufacturing",
    "dist": "distribution",
    "bldg": "building",
    "rm": "room",
    "furn": "furniture",
    "fac": "facility",
    "mach": "machine",
    "elec": "electrical",
    "acct": "accounting",
    "admin": "administration",
    "svr": "server",
    "srvr": "server",
    "wkst": "workstation",
    "wkstn": "workstation",
    "mon": "monitor",
    "prt": "printer",
    "prtr": "printer"
}


def _basic_clean(text: str) -> str:
    """Normalize whitespace."""
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _strip_transaction_prefix(text: str) -> str:
    """
    Remove leading disposal/scrap indicators.

    SAFETY: Only strips transaction words when NOT followed by equipment type words.
    Preserves "Disposal Equipment", "Scrap Container" etc. as these describe
    the asset TYPE, not a transaction status.
    """
    lower = text.lower()

    # Words that indicate the transaction word describes the asset TYPE, not a transaction
    # e.g., "Disposal Equipment" = equipment for disposing waste, NOT a disposed item
    equipment_type_words = {"equipment", "machinery", "system", "unit", "container",
                           "bin", "truck", "compactor", "crusher", "shredder"}

    for w in _TRANSACTION_WORDS:
        if lower.startswith(w + " "):
            remainder = text[len(w):].strip()
            remainder_lower = remainder.lower()

            # SAFETY: Don't strip if remainder starts with equipment type word
            # This preserves "Disposal Equipment", "Scrap Machinery", etc.
            if any(remainder_lower.startswith(eq_word) for eq_word in equipment_type_words):
                continue

            return remainder

    return text


def sanitize_description(raw: object) -> str:
    """
    Aggressive cleaning for classification:
    - lowercase
    - remove transaction words
    - strip parentheses with counts
    - remove punctuation except hyphens and &
    - expand abbreviations
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    s = _basic_clean(s)

    # remove ??, ###, (duplicate), etc.
    s = re.sub(r"\?{2,}", "", s)
    s = re.sub(r"\(duplicate\)", "", s, flags=re.IGNORECASE)

    # strip transactional verbs
    s = _strip_transaction_prefix(s)

    # remove (6), (3 units), etc.
    s = re.sub(r"\(\s*\d+\s*(units?|pcs?|each)?\s*\)", "", s, flags=re.IGNORECASE)
    s = _basic_clean(s)

    # lowercase for uniformity
    s = s.lower()

    # remove punctuation except hyphens and &
    s = re.sub(r"[^\w\s\-&]", " ", s)

    # expand abbreviations
    for abbr, full in _ABBREVIATIONS.items():
        s = re.sub(rf"\b{re.escape(abbr)}\b", full, s)

    return _basic_clean(s)


def tokenize_description(text: str) -> List[str]:
    """Turn sanitized description into tokens minus stopwords."""
    if not text:
        return []
    s = sanitize_description(text)
    tokens = re.findall(r"[a-z0-9]+", s)
    return [t for t in tokens if t not in _STOPWORDS]


# compatibility with app.py
def sanitize_asset_description(text: str) -> str:
    return sanitize_description(text)
