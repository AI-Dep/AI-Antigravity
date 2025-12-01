# fixed_asset_ai/logic/sanitizer.py
"""
Asset Description Sanitizer

Provides text cleaning and PII removal for asset descriptions before
sending to external APIs (e.g., OpenAI GPT).

SECURITY: This module is critical for SOC 2 compliance. All asset
descriptions MUST pass through sanitize_description() before being
sent to any external service.

PII Patterns Removed:
- Email addresses
- Phone numbers (US formats)
- Social Security Numbers (SSN)
- Employer Identification Numbers (EIN)
- Credit card numbers
- IP addresses
- URLs with potential tracking parameters
"""

import re
from typing import List

# ==============================================================================
# PII DETECTION PATTERNS (SOC 2 Compliance)
# ==============================================================================

# Email pattern: user@domain.tld
_EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    re.IGNORECASE
)

# US Phone patterns: (123) 456-7890, 123-456-7890, 123.456.7890, 1234567890
_PHONE_PATTERN = re.compile(
    r'\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b'
)

# SSN pattern: 123-45-6789 or 123456789
_SSN_PATTERN = re.compile(
    r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'
)

# EIN pattern: 12-3456789
_EIN_PATTERN = re.compile(
    r'\b\d{2}[-]?\d{7}\b'
)

# Credit card patterns (major formats)
_CREDIT_CARD_PATTERN = re.compile(
    r'\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b'
)

# IP address pattern
_IP_PATTERN = re.compile(
    r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
)

# URL pattern (remove URLs that might contain tracking info)
_URL_PATTERN = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+',
    re.IGNORECASE
)

# Common name prefixes that might indicate personal names
_NAME_PREFIXES = re.compile(
    r'\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Jr|Sr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?',
    re.IGNORECASE
)

# Replacement text for redacted PII
_PII_REPLACEMENT = "[REDACTED]"


def _remove_pii(text: str) -> str:
    """
    Remove Personally Identifiable Information (PII) from text.

    This function is CRITICAL for SOC 2 compliance and must be called
    before sending any text to external APIs.

    Args:
        text: Input text potentially containing PII

    Returns:
        Text with PII replaced by [REDACTED]
    """
    if not text:
        return text

    # Remove in order of specificity (most specific patterns first)

    # Remove credit card numbers
    text = _CREDIT_CARD_PATTERN.sub(_PII_REPLACEMENT, text)

    # Remove SSN (before general number patterns)
    text = _SSN_PATTERN.sub(_PII_REPLACEMENT, text)

    # Remove EIN
    text = _EIN_PATTERN.sub(_PII_REPLACEMENT, text)

    # Remove email addresses
    text = _EMAIL_PATTERN.sub(_PII_REPLACEMENT, text)

    # Remove phone numbers
    text = _PHONE_PATTERN.sub(_PII_REPLACEMENT, text)

    # Remove IP addresses
    text = _IP_PATTERN.sub(_PII_REPLACEMENT, text)

    # Remove URLs
    text = _URL_PATTERN.sub(_PII_REPLACEMENT, text)

    # Remove name prefixes with names (Mr. John Smith -> [REDACTED])
    text = _NAME_PREFIXES.sub(_PII_REPLACEMENT, text)

    # Clean up multiple consecutive [REDACTED] markers
    text = re.sub(r'(\[REDACTED\]\s*)+', '[REDACTED] ', text)

    return text.strip()


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


def sanitize_description(raw: object, remove_pii: bool = True) -> str:
    """
    Aggressive cleaning for classification with PII removal.

    SECURITY: This function removes PII before text is sent to external APIs.
    Always use this function before sending asset descriptions to GPT.

    Processing steps:
    1. Remove PII (emails, phones, SSN, etc.) - SOC 2 compliance
    2. Lowercase normalization
    3. Remove transaction words
    4. Strip parentheses with counts
    5. Remove punctuation except hyphens and &
    6. Expand abbreviations

    Args:
        raw: Input text (any type, will be converted to string)
        remove_pii: Whether to remove PII patterns (default: True)

    Returns:
        Sanitized text safe for external API calls
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    s = _basic_clean(s)

    # CRITICAL: Remove PII FIRST before any other processing
    # This ensures PII is never sent to external APIs
    if remove_pii:
        s = _remove_pii(s)

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


# ==============================================================================
# PII DETECTION UTILITIES (For auditing/logging)
# ==============================================================================

def contains_pii(text: str) -> bool:
    """
    Check if text contains any PII patterns.

    Useful for logging/auditing to detect if PII was present before sanitization.

    Args:
        text: Text to check

    Returns:
        True if PII patterns detected
    """
    if not text:
        return False

    patterns = [
        _EMAIL_PATTERN,
        _PHONE_PATTERN,
        _SSN_PATTERN,
        _EIN_PATTERN,
        _CREDIT_CARD_PATTERN,
        _IP_PATTERN,
        _URL_PATTERN,
        _NAME_PREFIXES,
    ]

    return any(pattern.search(text) for pattern in patterns)


def get_pii_types_found(text: str) -> list:
    """
    Get list of PII types found in text.

    Useful for audit logging to document what PII was redacted.

    Args:
        text: Text to check

    Returns:
        List of PII type names found (e.g., ["email", "phone"])
    """
    if not text:
        return []

    found = []

    pattern_names = [
        (_EMAIL_PATTERN, "email"),
        (_PHONE_PATTERN, "phone"),
        (_SSN_PATTERN, "ssn"),
        (_EIN_PATTERN, "ein"),
        (_CREDIT_CARD_PATTERN, "credit_card"),
        (_IP_PATTERN, "ip_address"),
        (_URL_PATTERN, "url"),
        (_NAME_PREFIXES, "name"),
    ]

    for pattern, name in pattern_names:
        if pattern.search(text):
            found.append(name)

    return found


# Export PII removal function for use in other modules
remove_pii = _remove_pii
