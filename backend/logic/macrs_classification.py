# fixed_asset_ai/logic/macrs_classification.py
"""
Enhanced Fixed Asset Classification Engine
Combines rule-based matching with GPT fallback for MACRS classification

Features:
- Multi-tier classification: Overrides -> Rules -> Client Category -> GPT -> Keyword Fallback
- Graceful degradation when GPT API unavailable
- Confidence scoring for all classifications
- Audit trail with timestamps for overrides
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from .sanitizer import sanitize_description, tokenize_description
from .logging_utils import get_logger
from .constants import LOW_CONFIDENCE_THRESHOLD, MIN_RULE_SCORE, GPT_TEMPERATURE
from .api_utils import retry_with_exponential_backoff

# Import OpenAI with graceful fallback
# Only consider OpenAI available if:
# 1. The library is installed
# 2. use_ai_classification is enabled in config
# 3. The API key is configured in config.json (not just env var)
import os
try:
    from openai import OpenAI
    from .config_manager import get_config

    # Check config_manager settings - this respects config.json settings
    _config = get_config()
    _use_ai = _config.get('use_ai_classification', True)
    _config_api_key = _config.get('openai_api_key', '')

    # Accept API key from config.json OR environment variable
    _env_api_key = os.environ.get('OPENAI_API_KEY', '')
    _api_key = _config_api_key or _env_api_key

    # Check env override flag - allows explicit disabling for fast local dev
    _disable_gpt = os.environ.get('DISABLE_GPT_CLASSIFICATION', '').lower() in ('true', '1', 'yes')

    # Enable OpenAI if:
    # - use_ai_classification is True in config (default: True)
    # - API key is set (in config.json OR environment variable)
    # - DISABLE_GPT_CLASSIFICATION is not set
    OPENAI_AVAILABLE = bool(_use_ai and _api_key and len(_api_key) > 10 and not _disable_gpt)

    if _disable_gpt:
        print("[MACRS] GPT classification disabled via DISABLE_GPT_CLASSIFICATION - using fast rule-based classification")
    elif not _use_ai:
        print("[MACRS] AI classification disabled in config - using fast rule-based classification")
    elif not _api_key or len(_api_key) <= 10:
        print("[MACRS] OpenAI API key not configured - using rule-based classification")
        print("[MACRS] To enable GPT: set OPENAI_API_KEY env var or add to config.json")
    else:
        _key_source = "config.json" if _config_api_key else "environment variable"
        print(f"[MACRS] OpenAI API enabled for classification (key from {_key_source})")
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

try:
    from .memory_engine import memory_engine
    MEMORY_ENABLED = True
except ImportError:
    MEMORY_ENABLED = False


logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
RULES_PATH = CONFIG_DIR / "rules.json"
OVERRIDES_PATH = CONFIG_DIR / "overrides.json"

# Use constants from constants.py
LOW_CONF_THRESHOLD = LOW_CONFIDENCE_THRESHOLD


# ===================================================================================
# JSON HELPERS
# ===================================================================================

def _load_json(path: Path, default: Any):
    """Load JSON file with fallback to default"""
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {path}: {e}")
    return default


def load_rules():
    """Load classification rules from rules.json"""
    return _load_json(RULES_PATH, {"rules": [], "minimum_rule_score": MIN_RULE_SCORE})


def load_overrides():
    """Load user overrides from overrides.json"""
    return _load_json(OVERRIDES_PATH, {"by_asset_id": {}, "by_client_category": {}})


def save_overrides(overrides: Dict[str, Any]):
    """Save overrides to overrides.json"""
    try:
        with OVERRIDES_PATH.open("w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(overrides.get('by_asset_id', {}))} asset overrides")
    except Exception as e:
        logger.error(f"Failed to save overrides: {e}")


def add_override(
    asset_id: str,
    classification: Dict[str, Any],
    reason: str = "",
    user: str = "system"
) -> bool:
    """
    Add or update an override for a specific asset with audit trail.

    Args:
        asset_id: Asset ID to override
        classification: Dict with class, life, method, convention, bonus, qip
        reason: Reason for the override
        user: User who made the override

    Returns:
        True if successful
    """
    try:
        overrides = load_overrides()

        # Add timestamp and audit info
        override_entry = {
            "class": classification.get("class"),
            "life": classification.get("life"),
            "method": classification.get("method"),
            "convention": classification.get("convention"),
            "bonus": classification.get("bonus", False),
            "qip": classification.get("qip", False),
            "reason": reason,
            "created_by": user,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        # Preserve history if updating existing override
        if asset_id in overrides.get("by_asset_id", {}):
            existing = overrides["by_asset_id"][asset_id]
            override_entry["created_at"] = existing.get("created_at", override_entry["created_at"])
            override_entry["created_by"] = existing.get("created_by", user)

            # Keep history of changes
            history = existing.get("history", [])
            history.append({
                "previous_class": existing.get("class"),
                "changed_at": datetime.now().isoformat(),
                "changed_by": user,
            })
            override_entry["history"] = history

        if "by_asset_id" not in overrides:
            overrides["by_asset_id"] = {}

        overrides["by_asset_id"][asset_id] = override_entry
        save_overrides(overrides)

        logger.info(f"Added override for asset {asset_id}: {classification.get('class')}")
        return True

    except Exception as e:
        logger.error(f"Failed to add override for {asset_id}: {e}")
        return False


def get_override_audit_trail(asset_id: str) -> Optional[Dict]:
    """
    Get audit trail for an asset's overrides.

    Args:
        asset_id: Asset ID to look up

    Returns:
        Dict with override info and history, or None if not found
    """
    overrides = load_overrides()
    return overrides.get("by_asset_id", {}).get(asset_id)


# ===================================================================================
# RULE ENGINE - Pattern matching with scoring
# ===================================================================================

def _normalize(s):
    """Normalize string for comparison"""
    return str(s).strip().lower() if s else ""


def _safe_get(d, keys: List[str], default=""):
    """Safely get value from dict or pandas Series using multiple possible keys"""
    # Handle both dict and pandas Series
    if not hasattr(d, 'get') and not hasattr(d, '__getitem__'):
        return default

    for k in keys:
        try:
            if hasattr(d, 'get'):
                # Dict-like object
                val = d.get(k)
            else:
                # Series-like object
                val = d[k] if k in d else None

            if val is not None and val != "":
                return val
        except (KeyError, AttributeError):
            continue

    return default


def _safe_float(value: Any, default: float = 0.7) -> float:
    """
    Safely convert value to float with fallback.

    Handles:
    - None → default
    - Numeric values (int, float) → float
    - Numeric strings → float
    - Word confidence levels ("high", "medium", "low") → mapped float
    - Invalid values → default

    Args:
        value: The value to convert
        default: Fallback value (default 0.7)

    Returns:
        Float value
    """
    if value is None:
        return default

    # Already numeric
    if isinstance(value, (int, float)):
        return float(value)

    # String handling
    if isinstance(value, str):
        value_lower = value.strip().lower()

        # Word confidence levels
        confidence_map = {
            "high": 0.9,
            "very high": 0.95,
            "medium": 0.7,
            "moderate": 0.7,
            "low": 0.5,
            "very low": 0.3,
        }
        if value_lower in confidence_map:
            return confidence_map[value_lower]

        # Try numeric conversion
        try:
            return float(value)
        except ValueError:
            return default

    # Any other type
    return default


def _rule_score(rule: Dict, desc: str, tokens: List[str], client_category: str = "") -> float:
    """
    Calculate match score for a rule

    Args:
        rule: Rule definition with keywords, exclude, weight
        desc: Sanitized description (lowercase)
        tokens: Tokenized description
        client_category: Client-provided category (if any)

    Returns:
        Score (higher is better, 0 means no match)
    """
    score = 0.0

    kw = [k.lower() for k in rule.get("keywords", [])]
    excl = [x.lower() for x in rule.get("exclude", [])]
    weight = float(rule.get("weight", 1.0))

    # Exclusions - immediate disqualification
    for e in excl:
        if e in desc:
            return 0.0

    token_set = set(tokens)
    joined = " ".join(tokens)

    # Keyword matching with different scoring
    for k in kw:
        if " " in k:
            # Multi-word phrase
            if k in desc or k in joined:
                score += 3.0 * weight
        else:
            # Single word
            if k in token_set:
                # Exact token match
                score += 2.0 * weight
            elif k in desc:
                # Substring match (less valuable)
                score += 0.5 * weight

    # Bonus for client category match
    if client_category:
        cat_norm = _normalize(client_category)
        rule_class = _normalize(rule.get("class", ""))

        # Fixed: Added parentheses to fix operator precedence bug
        # Without parens: (cat_norm and rule_class and cat_norm in rule_class) or (rule_class in cat_norm)
        # Which incorrectly runs second condition even if cat_norm/rule_class is empty
        if cat_norm and rule_class and (cat_norm in rule_class or rule_class in cat_norm):
            score += 2.0  # Bonus for matching client category

    return score


def _match_rule(asset: Dict, rules: Dict, return_top_n: int = 1) -> Optional[tuple[Dict, float]]:
    """
    Find best matching rule(s) for an asset

    Args:
        asset: Asset dict with Description, Cost, etc.
        rules: Rules dict from rules.json
        return_top_n: Number of top matches to return (default 1 for backward compatibility)

    Returns:
        If return_top_n=1: tuple of (rule dict, match_score) or None
        If return_top_n>1: list of (rule dict, match_score) tuples, sorted by score descending
    """
    desc_raw = _safe_get(asset, ["Description", "description", "desc"], "")
    desc = sanitize_description(desc_raw)
    tokens = tokenize_description(desc)

    client_category = _safe_get(asset, ["Client Category", "client_category", "category"], "")

    min_score = rules.get("minimum_rule_score", MIN_RULE_SCORE)

    # Score all rules
    scored_rules = []
    for rule in rules.get("rules", []):
        score = _rule_score(rule, desc, tokens, client_category)
        if score >= min_score:
            scored_rules.append((rule, score))

    # Sort by score descending
    scored_rules.sort(key=lambda x: x[1], reverse=True)

    if return_top_n == 1:
        # Backward compatible: return single best match or None
        return scored_rules[0] if scored_rules else None
    else:
        # Return top N matches
        return scored_rules[:return_top_n] if scored_rules else []


# ===================================================================================
# CLIENT CATEGORY MAPPING
# ===================================================================================

COMMON_CATEGORY_MAPPINGS = {
    # Computer equipment
    "computer": {"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY"},
    "computers": {"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY"},
    "it equipment": {"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY"},
    "technology": {"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY"},
    "tech equipment": {"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY"},
    "hardware": {"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY"},
    "it hardware": {"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY"},

    # Office furniture
    "furniture": {"class": "Office Furniture", "life": 7, "method": "200DB", "convention": "HY"},
    "office furniture": {"class": "Office Furniture", "life": 7, "method": "200DB", "convention": "HY"},
    "ff&e": {"class": "Office Furniture", "life": 7, "method": "200DB", "convention": "HY"},
    "ffe": {"class": "Office Furniture", "life": 7, "method": "200DB", "convention": "HY"},
    "fixtures": {"class": "Office Furniture", "life": 7, "method": "200DB", "convention": "HY"},

    # Office equipment
    "office equipment": {"class": "Office Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "office machines": {"class": "Office Equipment", "life": 7, "method": "200DB", "convention": "HY"},

    # Machinery - NOTE: "equipment" alone is too broad, removed to prevent misclassification
    "machinery": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "m&e": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "machinery & equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "manufacturing equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "production equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "industrial equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "process equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "plant equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},

    # Vehicles
    "vehicle": {"class": "Passenger Automobile", "life": 5, "method": "200DB", "convention": "HY"},
    "vehicles": {"class": "Passenger Automobile", "life": 5, "method": "200DB", "convention": "HY"},
    "auto": {"class": "Passenger Automobile", "life": 5, "method": "200DB", "convention": "HY"},
    "automobile": {"class": "Passenger Automobile", "life": 5, "method": "200DB", "convention": "HY"},
    "car": {"class": "Passenger Automobile", "life": 5, "method": "200DB", "convention": "HY"},
    "truck": {"class": "Trucks & Trailers", "life": 5, "method": "200DB", "convention": "HY"},
    "trucks": {"class": "Trucks & Trailers", "life": 5, "method": "200DB", "convention": "HY"},

    # Restaurant
    "restaurant equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "kitchen equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "food service": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "food service equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},

    # Medical
    "medical equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "healthcare equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},
    "dental equipment": {"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY"},

    # Leasehold improvements
    "leasehold": {"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "qip": True},
    "leasehold improvements": {"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "qip": True},
    "tenant improvement": {"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "qip": True},
    "tenant improvements": {"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "qip": True},
    "ti": {"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "qip": True},
    "qip": {"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "qip": True},
    "interior improvements": {"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "qip": True},

    # Land improvements
    "land improvement": {"class": "Land Improvement", "life": 15, "method": "150DB", "convention": "HY"},
    "land improvements": {"class": "Land Improvement", "life": 15, "method": "150DB", "convention": "HY"},
    "site improvement": {"class": "Land Improvement", "life": 15, "method": "150DB", "convention": "HY"},
    "site improvements": {"class": "Land Improvement", "life": 15, "method": "150DB", "convention": "HY"},

    # Building systems
    "building equipment": {"class": "Building Equipment", "life": 15, "method": "150DB", "convention": "HY"},
    "hvac": {"class": "Building Equipment", "life": 15, "method": "150DB", "convention": "HY"},
    "electrical": {"class": "Building Equipment", "life": 15, "method": "150DB", "convention": "HY"},
    "plumbing": {"class": "Building Equipment", "life": 15, "method": "150DB", "convention": "HY"},

    # Building
    "building": {"class": "Nonresidential Real Property", "life": 39, "method": "SL", "convention": "MM"},
    "building improvement": {"class": "Building Improvement", "life": 39, "method": "SL", "convention": "MM"},
    "building improvements": {"class": "Building Improvement", "life": 39, "method": "SL", "convention": "MM"},
    "real property": {"class": "Nonresidential Real Property", "life": 39, "method": "SL", "convention": "MM"},
    "nonresidential": {"class": "Nonresidential Real Property", "life": 39, "method": "SL", "convention": "MM"},

    # Software
    "software": {"class": "Software", "life": 3, "method": "SL", "convention": "HY"},
    "computer software": {"class": "Software", "life": 3, "method": "SL", "convention": "HY"},

    # Land
    "land": {"class": "Nondepreciable Land", "life": None, "method": None, "convention": None},
    "land only": {"class": "Nondepreciable Land", "life": None, "method": None, "convention": None},
}


def _match_client_category(client_category: str) -> Optional[Dict]:
    """
    Try to match client-provided category to MACRS class.

    Uses conservative matching to avoid false positives:
    1. Exact match (highest priority)
    2. Word-bounded partial match (e.g., "office furniture" matches "furniture")
    3. Avoids substring matches that would cause misclassification
       (e.g., "machine" in "vending machine" should NOT map to generic machinery)
    """
    if not client_category:
        return None

    cat_norm = _normalize(client_category)

    # Direct exact match (highest priority)
    if cat_norm in COMMON_CATEGORY_MAPPINGS:
        return COMMON_CATEGORY_MAPPINGS[cat_norm]

    # Word-bounded partial match (safer than pure substring)
    # Split category into words and check for exact word matches
    cat_words = set(cat_norm.split())

    best_match = None
    best_match_score = 0

    for key, mapping in COMMON_CATEGORY_MAPPINGS.items():
        key_words = set(key.split())

        # Check if any key word is a full word in category (not substring)
        # e.g., "furniture" as word matches "office furniture" but not "furniturestore"
        matching_words = cat_words & key_words

        if matching_words:
            # Score based on how many words match
            score = len(matching_words)

            # Bonus for exact multi-word key match
            if key in cat_norm:
                score += 2

            if score > best_match_score:
                best_match = mapping
                best_match_score = score

    # Only return if we have a meaningful match (at least 1 word)
    if best_match and best_match_score >= 1:
        return best_match

    return None


# ===================================================================================
# VALID MACRS CATEGORIES - For validating GPT responses
# ===================================================================================

# Official MACRS categories per IRS Pub 946 and IRC §168
# GPT responses are validated against this list to prevent hallucinated categories
VALID_MACRS_CATEGORIES = {
    # 3-year property
    "Software",

    # 5-year property (IRC §168(e)(3)(B))
    "Computer Equipment",
    "Office Equipment",
    "Passenger Automobile",
    "Trucks & Trailers",
    "Vehicles",

    # 7-year property (IRC §168(e)(3)(C))
    "Office Furniture",
    "Machinery & Equipment",

    # 15-year property (IRC §168(e)(3)(E))
    "Land Improvement",
    "Land Improvements",  # Allow plural
    "QIP - Qualified Improvement Property",
    "Building Equipment",

    # 27.5-year property (IRC §168(c)(1))
    "Residential Rental Property",

    # 39-year property (IRC §168(c)(1))
    "Nonresidential Real Property",
    "Building Improvement",

    # Non-depreciable
    "Nondepreciable Land",
}


def _validate_gpt_category(gpt_result: Dict) -> Dict:
    """
    Validate GPT classification against approved MACRS categories.

    If GPT returns a hallucinated category, map it to closest valid category
    and lower confidence to flag for review.

    SAFETY: Uses case-insensitive matching and word-boundary checks to prevent
    false corrections (e.g., "Computer Equipment" won't match "equipment" rule).

    Args:
        gpt_result: Raw GPT classification result

    Returns:
        Validated result with corrected category if needed
    """
    category = gpt_result.get("class") or gpt_result.get("final_class")

    if not category:
        return gpt_result

    # SAFETY FIX: Case-insensitive check against valid categories
    # Build lowercase lookup set for case-insensitive matching
    valid_categories_lower = {cat.lower(): cat for cat in VALID_MACRS_CATEGORIES}

    # Check if category is valid (case-insensitive)
    category_lower = category.lower().strip()
    if category_lower in valid_categories_lower:
        # Normalize to canonical case and return
        result = gpt_result.copy()
        canonical = valid_categories_lower[category_lower]
        result["class"] = canonical
        result["final_class"] = canonical
        return result

    # Category not in approved list - try to map to closest valid category
    # SAFETY: Use EXACT phrase matching first, then word-boundary matching
    # Order matters: more specific phrases MUST come before generic terms

    # Exact phrase corrections (highest priority)
    exact_corrections = {
        "computer equipment": "Computer Equipment",
        "it equipment": "Computer Equipment",
        "office equipment": "Office Equipment",
        "office furniture": "Office Furniture",
        "office furniture and fixtures": "Office Furniture",
        "machinery & equipment": "Machinery & Equipment",
        "machinery and equipment": "Machinery & Equipment",
        "passenger automobile": "Passenger Automobile",
        "land improvement": "Land Improvement",
        "land improvements": "Land Improvements",
        "site improvement": "Land Improvement",
        "qualified improvement property": "QIP - Qualified Improvement Property",
        "leasehold improvement": "QIP - Qualified Improvement Property",
        "tenant improvement": "QIP - Qualified Improvement Property",
        "nonresidential real property": "Nonresidential Real Property",
        "residential rental property": "Residential Rental Property",
        "building improvement": "Building Improvement",
        "building equipment": "Building Equipment",
        "nondepreciable land": "Nondepreciable Land",
        "trucks & trailers": "Trucks & Trailers",
        "trucks and trailers": "Trucks & Trailers",
    }

    # Check exact phrase match first
    if category_lower in exact_corrections:
        result = gpt_result.copy()
        result["class"] = exact_corrections[category_lower]
        result["final_class"] = exact_corrections[category_lower]
        # Exact phrase match = minor correction, keep confidence
        result["notes"] = f"Normalized '{category}' to '{result['class']}'. {result.get('notes', '')}"
        return result

    # Word-boundary fallback corrections (lower priority)
    # SAFETY: Only match if the KEY is a complete word/phrase in the category
    # Uses word boundaries to prevent "Medical Equipment" matching "equipment"
    word_corrections = [
        # Order: most specific to least specific
        (r"\bcomputer\b", "Computer Equipment"),
        (r"\bfurniture\b", "Office Furniture"),
        (r"\bvehicle\b", "Passenger Automobile"),
        (r"\bautomobile\b", "Passenger Automobile"),
        (r"\btruck\b", "Trucks & Trailers"),
        (r"\bqip\b", "QIP - Qualified Improvement Property"),
        (r"\bsoftware\b", "Software"),
        # Generic terms LAST (catches "Medical Equipment", "Restaurant Equipment", etc.)
        (r"\bequipment\b", "Machinery & Equipment"),
        (r"\bmachinery\b", "Machinery & Equipment"),
        (r"\bbuilding\b", "Nonresidential Real Property"),
        (r"\bland\b", "Nondepreciable Land"),
        (r"\bresidential\b", "Residential Rental Property"),
    ]

    for pattern, valid_cat in word_corrections:
        if re.search(pattern, category_lower):
            result = gpt_result.copy()
            result["class"] = valid_cat
            result["final_class"] = valid_cat
            original_conf = result.get("confidence", 0.7)
            result["confidence"] = min(original_conf, 0.70)  # Cap at 70% for word-boundary corrections
            result["low_confidence"] = True
            result["notes"] = f"GPT returned '{category}' (not in approved list), corrected to '{valid_cat}'. {result.get('notes', '')}"
            return result

    # No correction found - default to 7-year equipment with low confidence
    result = gpt_result.copy()
    result["class"] = "Machinery & Equipment"
    result["final_class"] = "Machinery & Equipment"
    result["final_life"] = 7
    result["final_method"] = "200DB"
    result["final_convention"] = "HY"
    result["confidence"] = 0.50
    result["low_confidence"] = True
    result["notes"] = f"GPT returned unknown category '{category}' - defaulted to 7-year equipment. Manual review required."
    return result


# ===================================================================================
# GPT FALLBACK - Enhanced prompts with tax context
# ===================================================================================

SYSTEM_PROMPT = """You are a senior US tax CPA specializing in fixed asset depreciation and MACRS classifications.

Your task is to classify business assets into proper MACRS depreciation categories based on IRS Publication 946 and tax law.

Key MACRS Categories:
- Computer Equipment: 5-year, 200DB, HY (computers, servers, printers, POS systems)
- Office Equipment: 5-year or 7-year, 200DB, HY (printers, copiers, phones)
- Office Furniture: 7-year, 200DB, HY (desks, chairs, cabinets)
- Machinery & Equipment: 7-year, 200DB, HY (manufacturing, restaurant, medical equipment)
- Passenger Automobile: 5-year, 200DB, HY (cars, vans, light trucks)
- Land Improvement: 15-year, 150DB, HY (parking lots, fencing, landscaping)
- QIP (Qualified Improvement Property): 15-year, SL, HY (interior improvements post-2017)
- Building Equipment: 15-year, 150DB, HY (HVAC, electrical, plumbing)
- Nonresidential Real Property: 39-year, SL, MM (building structures)
- Nondepreciable Land: Not depreciable

Methods:
- 200DB = 200% Declining Balance
- 150DB = 150% Declining Balance
- SL = Straight Line

Conventions:
- HY = Half-Year
- MM = Mid-Month (real property only)

Return JSON only."""


GPT_PROMPT = """Classify this asset for MACRS depreciation purposes.

Asset Information:
{asset_json}

Required JSON Response Format:
{{
  "class": "exact MACRS category name",
  "life": number or null,
  "method": "200DB" or "150DB" or "SL" or null,
  "convention": "HY" or "MM" or null,
  "bonus": true or false (eligible for bonus depreciation),
  "qip": true or false (qualified improvement property),
  "confidence": 0.0 to 1.0 (your confidence in this classification),
  "reasoning": "brief explanation of why you chose this classification"
}}

Classification Examples:
- "Dell Optiplex Desktop Computer" → {{"class": "Computer Equipment", "life": 5, "method": "200DB", "convention": "HY", "bonus": true, "qip": false, "confidence": 0.95}}
- "Office Desk and Chair Set" → {{"class": "Office Furniture", "life": 7, "method": "200DB", "convention": "HY", "bonus": true, "qip": false, "confidence": 0.9}}
- "CNC Milling Machine" → {{"class": "Machinery & Equipment", "life": 7, "method": "200DB", "convention": "HY", "bonus": true, "qip": false, "confidence": 0.92}}
- "Interior Office Remodel" → {{"class": "QIP - Qualified Improvement Property", "life": 15, "method": "SL", "convention": "HY", "bonus": true, "qip": true, "confidence": 0.88}}
- "HVAC Rooftop Unit" → {{"class": "Building Equipment", "life": 15, "method": "150DB", "convention": "HY", "bonus": true, "qip": false, "confidence": 0.9}}
- "Parking Lot Paving" → {{"class": "Land Improvement", "life": 15, "method": "150DB", "convention": "HY", "bonus": true, "qip": false, "confidence": 0.9}}
- "2023 Ford F-150" → {{"class": "Passenger Automobile", "life": 5, "method": "200DB", "convention": "HY", "bonus": true, "qip": false, "confidence": 0.95}}

Classification Rules:
1. Use exact category names from the list above
2. Be conservative - when uncertain, use more general categories
3. QIP applies only to interior improvements post-2017 (not structural, elevators, HVAC, racking)
4. Land is never depreciable
5. Software is typically 3-year, SL
6. Most business equipment is 5 or 7-year property
7. Confidence should be high (0.8+) for clear matches, lower (0.5-0.7) for ambiguous items
8. If description is vague or incomplete, assign lower confidence

Return only valid JSON."""


# ===================================================================================
# BATCH GPT CLASSIFICATION - 10x faster for large asset lists
# ===================================================================================

BATCH_GPT_PROMPT = """Classify these {count} assets for MACRS depreciation purposes.

Assets to classify:
{assets_json}

Return a JSON object with an "assets" array containing one classification per asset, in the same order.

Required JSON Response Format:
{{
  "assets": [
    {{
      "id": "asset identifier from input",
      "class": "exact MACRS category name",
      "life": number or null,
      "method": "200DB" or "150DB" or "SL" or null,
      "convention": "HY" or "MM" or null,
      "bonus": true or false,
      "qip": true or false,
      "confidence": 0.0 to 1.0,
      "reasoning": "brief explanation"
    }},
    ...
  ]
}}

Classification Rules (apply to ALL assets):
1. Computer/IT equipment: 5-year, 200DB, HY
2. Office furniture: 7-year, 200DB, HY
3. Machinery/equipment: 7-year, 200DB, HY
4. Vehicles: 5-year, 200DB, HY
5. Land improvements: 15-year, 150DB, HY
6. QIP (interior improvements): 15-year, SL, HY, qip=true
7. Buildings: 39-year (commercial) or 27.5-year (residential), SL, MM
8. Software: 3-year, SL, HY
9. Land: NOT depreciable (life=null)

Return only valid JSON with exactly {count} classifications."""


def classify_assets_batch(
    assets: List[Dict],
    client=None,
    model: str = "gpt-4o-mini",
    rules: Optional[Dict] = None,
    overrides: Optional[Dict] = None,
    batch_size: int = 30
) -> List[Dict]:
    """
    Classify multiple assets in batches for improved performance.

    Processes assets in batches of batch_size to reduce API calls.
    A batch of 30 assets = 1 API call instead of 30 calls (30x reduction).

    Args:
        assets: List of asset dicts with Description, Cost, etc.
        client: OpenAI client (optional)
        model: GPT model to use
        rules: Rules dict (will load if not provided)
        overrides: Overrides dict (will load if not provided)
        batch_size: Number of assets per batch (default: 30)

    Returns:
        List of classification dicts in same order as input
    """
    if not assets:
        return []

    rules = rules or load_rules()
    overrides = overrides or load_overrides()

    results = []

    # Process assets that need GPT (not matched by rules/overrides)
    gpt_needed = []
    gpt_indices = []

    for i, asset in enumerate(assets):
        # Try rule-based first (fast)
        result = _try_fast_classification(asset, rules, overrides)
        if result:
            results.append((i, result))
        else:
            gpt_needed.append(asset)
            gpt_indices.append(i)

    # Batch GPT calls for remaining assets
    if gpt_needed and OPENAI_AVAILABLE:
        gpt_results = _batch_gpt_classify(gpt_needed, model, batch_size)
        for idx, result in zip(gpt_indices, gpt_results):
            results.append((idx, result))
    elif gpt_needed:
        # Fallback to keyword classification
        for idx, asset in zip(gpt_indices, gpt_needed):
            results.append((idx, _keyword_fallback_classification(asset)))

    # Sort by original index and return just results
    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]


def _try_fast_classification(asset: Dict, rules: Dict, overrides: Dict) -> Optional[Dict]:
    """
    Try to classify asset using rules/overrides/memory/keywords (no GPT needed).
    Returns None if GPT is needed.

    Classification order (MUST match classify_asset for consistency):
    1. User overrides (100% confidence)
    2. Rule engine (80-98% confidence) - BEFORE quick keywords for consistency
    3. Memory engine (up to 90% confidence)
    4. Quick keyword fallback (75% confidence) - Only if rules don't match
    Returns None → triggers GPT fallback
    """
    # Check override first
    aid = _normalize(_safe_get(asset, ["Asset ID", "asset_id"], ""))
    if aid and aid in overrides.get("by_asset_id", {}):
        override = overrides["by_asset_id"][aid]
        return {
            "final_class": override.get("class"),
            "final_life": override.get("life"),
            "final_method": override.get("method"),
            "final_convention": override.get("convention"),
            "bonus": override.get("bonus", False),
            "qip": override.get("qip", False),
            "source": "override",
            "confidence": 1.0,
            "low_confidence": False,
            "notes": "User override"
        }

    desc = sanitize_description(_safe_get(asset, ["Description", "description"], "")).lower()

    # TIER 2: Check rule match FIRST (for consistency with classify_asset)
    rule_match = _match_rule(asset, rules)
    if rule_match:
        rule, match_score = rule_match
        if match_score >= 4:
            confidence = 0.95 if match_score >= 10 else (0.90 if match_score >= 6 else 0.80)
            return {
                "final_class": rule.get("class"),
                "final_life": rule.get("life"),
                "final_method": rule.get("method"),
                "final_convention": rule.get("convention"),
                "bonus": rule.get("bonus", False),
                "qip": rule.get("qip", False),
                "source": "rule",
                "confidence": confidence,
                "low_confidence": confidence < 0.85,
                "notes": f"Rule match: {rule.get('name', 'unnamed')} (score: {match_score:.1f})"
            }

    # Check memory engine for learned patterns
    if MEMORY_ENABLED:
        try:
            memory_match = memory_engine.query_similar(desc, threshold=0.82)
            if memory_match:
                mem_class = memory_match.get("classification", {})
                similarity = memory_match.get("similarity", 0.82)
                return {
                    "final_class": mem_class.get("class") or mem_class.get("final_class"),
                    "final_life": mem_class.get("life") or mem_class.get("final_life"),
                    "final_method": mem_class.get("method") or mem_class.get("final_method"),
                    "final_convention": mem_class.get("convention") or mem_class.get("final_convention"),
                    "bonus": mem_class.get("bonus", False),
                    "qip": mem_class.get("qip", False),
                    "source": "memory_engine",
                    "confidence": min(0.90, similarity),
                    "low_confidence": False,
                    "notes": f"Memory match (similarity: {similarity:.2f})"
                }
        except Exception as e:
            logger.debug(f"Memory engine check failed: {e}")

    return None  # Need GPT


def _batch_gpt_classify(assets: List[Dict], model: str, batch_size: int) -> List[Dict]:
    """
    Classify assets using batched GPT calls with parallel execution.

    PERFORMANCE: Uses ThreadPoolExecutor to run multiple GPT batch calls
    in parallel, dramatically reducing wall-clock time for large asset lists.

    Example: 100 assets with batch_size=30
    - Sequential: 4 batches × 2s each = 8 seconds
    - Parallel:   4 batches in parallel = ~2 seconds (4x faster)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not assets:
        return []

    # Split assets into batches
    batches = []
    for i in range(0, len(assets), batch_size):
        batches.append(assets[i:i + batch_size])

    if len(batches) == 1:
        # Single batch - no parallelization needed
        return _call_gpt_batch(batches[0], model)

    # PARALLEL EXECUTION: Run all batches concurrently
    # Max workers = number of batches, capped at 5 to avoid rate limits
    max_workers = min(len(batches), 5)
    results_by_batch = [None] * len(batches)

    logger.info(f"[GPT] Parallel classification: {len(assets)} assets in {len(batches)} batches (max {max_workers} concurrent)")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batch jobs
        future_to_idx = {
            executor.submit(_call_gpt_batch, batch, model): idx
            for idx, batch in enumerate(batches)
        }

        # Collect results as they complete
        for future in as_completed(future_to_idx):
            batch_idx = future_to_idx[future]
            try:
                results_by_batch[batch_idx] = future.result()
            except Exception as e:
                logger.warning(f"[GPT] Batch {batch_idx} failed: {e} - using fallback")
                # Fallback for failed batch
                results_by_batch[batch_idx] = [
                    _keyword_fallback_classification(a) for a in batches[batch_idx]
                ]

    # Flatten results in original order
    results = []
    for batch_result in results_by_batch:
        results.extend(batch_result)

    return results


def _call_gpt_batch(assets: List[Dict], model: str = "gpt-4o-mini") -> List[Dict]:
    """
    Call GPT for a batch of assets.
    """
    if not OPENAI_AVAILABLE:
        return [_keyword_fallback_classification(a) for a in assets]

    # Build batch payload
    batch_data = []
    for i, asset in enumerate(assets):
        desc = sanitize_description(_safe_get(asset, ["Description", "description"], ""))
        batch_data.append({
            "id": str(i),
            "description": desc,
            "category": _safe_get(asset, ["Client Category", "client_category", "category"], ""),
            "cost": _safe_get(asset, ["Cost", "cost"], "")
        })

    try:
        cli = OpenAI()
        prompt = BATCH_GPT_PROMPT.format(
            count=len(assets),
            assets_json=json.dumps(batch_data, indent=2)
        )

        @retry_with_exponential_backoff(max_retries=3, initial_delay=2.0, max_delay=30.0)
        def _api_call():
            return cli.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

        resp = _api_call()
        content = resp.choices[0].message.content
        data = json.loads(content)

        # Parse batch results
        results = []
        gpt_results = data.get("assets", [])

        for i, asset in enumerate(assets):
            if i < len(gpt_results):
                r = gpt_results[i]
                # Use _safe_float to handle non-numeric confidence values (e.g., "high", "medium")
                conf = _safe_float(r.get("confidence"), 0.7)
                raw_result = {
                    "final_class": r.get("class"),
                    "final_life": r.get("life"),
                    "final_method": r.get("method"),
                    "final_convention": r.get("convention"),
                    "bonus": r.get("bonus", False),
                    "qip": r.get("qip", False),
                    "source": "gpt_batch",
                    "confidence": conf,
                    "low_confidence": conf < LOW_CONF_THRESHOLD,
                    "notes": r.get("reasoning", "GPT batch classification")
                }
                # Validate GPT category against approved list
                validated_result = _validate_gpt_category(raw_result)
                results.append(validated_result)
            else:
                # Fallback for missing results
                results.append(_keyword_fallback_classification(asset))

        return results

    except Exception as e:
        logger.warning(f"Batch GPT failed: {e} - using keyword fallback")
        return [_keyword_fallback_classification(a) for a in assets]


def _keyword_fallback_classification(asset: Dict) -> Dict:
    """
    Keyword-based fallback classification when GPT is unavailable.

    This provides a reasonable classification based on common keywords
    in asset descriptions. Less accurate than GPT but always available.

    Args:
        asset: Asset dict with Description

    Returns:
        Classification dict with final_class, final_life, final_method, final_convention, confidence
    """
    desc_raw = _safe_get(asset, ["Description", "description"], "")
    desc = sanitize_description(desc_raw).lower()

    # Keyword patterns with classifications (ordered by specificity)
    keyword_patterns = [
        # Computer equipment (5-year)
        (["computer", "laptop", "desktop", "server", "monitor", "printer", "scanner",
          "pos system", "workstation", "tablet", "ipad", "macbook"], {
            "final_class": "Computer Equipment", "final_life": 5, "final_method": "200DB",
            "final_convention": "HY", "bonus": True, "qip": False, "confidence": 0.75
        }),

        # Software (3-year)
        (["software", "license", "subscription", "saas"], {
            "final_class": "Software", "final_life": 3, "final_method": "SL",
            "final_convention": "HY", "bonus": True, "qip": False, "confidence": 0.70
        }),

        # Furniture (7-year)
        (["desk", "chair", "table", "cabinet", "bookcase", "credenza", "sofa",
          "couch", "reception", "conference"], {
            "final_class": "Office Furniture", "final_life": 7, "final_method": "200DB",
            "final_convention": "HY", "bonus": True, "qip": False, "confidence": 0.75
        }),

        # Vehicles (5-year)
        # NOTE: Use space-bounded terms for short words to avoid false matches
        # - "car" alone matches "card", "carpet" - use "car ", " car"
        # - "van" alone matches "advantage", "canvas" - use " van", "van "
        (["vehicle", "car ", " car", "truck", " van", "van ", "automobile", "ford", "chevy",
          "toyota", "honda", "suv"], {
            "final_class": "Passenger Automobile", "final_life": 5, "final_method": "200DB",
            "final_convention": "HY", "bonus": True, "qip": False, "confidence": 0.70
        }),

        # Land improvements (15-year)
        (["parking lot", "paving", "fence", "fencing", "landscaping", "sidewalk",
          "driveway", "signage", "sign"], {
            "final_class": "Land Improvement", "final_life": 15, "final_method": "150DB",
            "final_convention": "HY", "bonus": True, "qip": False, "confidence": 0.70
        }),

        # QIP (15-year)
        (["interior", "leasehold", "tenant improvement", "remodel", "renovation",
          "flooring", "carpet", "painting", "lighting fixture"], {
            "final_class": "QIP - Qualified Improvement Property", "final_life": 15, "final_method": "SL",
            "final_convention": "HY", "bonus": True, "qip": True, "confidence": 0.65
        }),

        # Building systems (15-year)
        (["hvac", "air conditioning", "heating", "electrical", "plumbing",
          "roof", "elevator", "fire alarm", "security system"], {
            "final_class": "Building Equipment", "final_life": 15, "final_method": "150DB",
            "final_convention": "HY", "bonus": True, "qip": False, "confidence": 0.65
        }),

        # Building (39-year)
        (["building", "warehouse", "office building", "structure"], {
            "final_class": "Nonresidential Real Property", "final_life": 39, "final_method": "SL",
            "final_convention": "MM", "bonus": False, "qip": False, "confidence": 0.60
        }),

        # Land (not depreciable)
        (["land", "lot", "property", "acreage"], {
            "final_class": "Nondepreciable Land", "final_life": None, "final_method": None,
            "final_convention": None, "bonus": False, "qip": False, "confidence": 0.65
        }),

        # General equipment (7-year default)
        (["equipment", "machine", "appliance", "tool"], {
            "final_class": "Machinery & Equipment", "final_life": 7, "final_method": "200DB",
            "final_convention": "HY", "bonus": True, "qip": False, "confidence": 0.60
        }),
    ]

    # Check each pattern
    for keywords, classification in keyword_patterns:
        for kw in keywords:
            if kw in desc:
                result = classification.copy()
                result["source"] = "keyword_fallback"
                result["low_confidence"] = result["confidence"] < LOW_CONF_THRESHOLD
                result["notes"] = f"Keyword fallback: matched '{kw}' in description"
                logger.debug(f"Keyword fallback matched '{kw}' -> {result['final_class']}")
                return result

    # Default fallback: 7-year equipment (most common)
    logger.warning(f"No keyword match for description: {desc[:50]}... using default")
    return {
        "final_class": "Machinery & Equipment",
        "final_life": 7,
        "final_method": "200DB",
        "final_convention": "HY",
        "bonus": True,
        "qip": False,
        "confidence": 0.40,
        "source": "default_fallback",
        "low_confidence": True,
        "notes": "No keyword match - using default 7-year equipment classification"
    }


def _make_gpt_api_call(cli, model: str, prompt_filled: str) -> Dict:
    """
    Make the actual GPT API call with retry logic.
    This function is separated to enable retry decorator.
    """
    @retry_with_exponential_backoff(max_retries=3, initial_delay=2.0, max_delay=30.0)
    def _api_call():
        return cli.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_filled},
            ],
            temperature=0.3,  # Lower temperature for more consistent results
        )

    return _api_call()


def _call_gpt(asset: Dict, model: str = "gpt-4o-mini") -> Dict:
    """
    Call GPT for asset classification with fallback when unavailable.

    Returns dict with classification results and confidence.
    If OpenAI is unavailable, falls back to keyword-based classification.

    Features:
    - Automatic retry with exponential backoff (2s, 4s, 8s) for transient errors
    - Graceful fallback to keyword classification on persistent failures
    - Rate limit and quota error detection
    """
    # Check if OpenAI is available
    if not OPENAI_AVAILABLE:
        logger.warning("OpenAI not available - using keyword fallback classification")
        return _keyword_fallback_classification(asset)

    desc_raw = _safe_get(asset, ["Description", "description"], "")
    desc = sanitize_description(desc_raw)
    tokens = tokenize_description(desc)
    client_category = _safe_get(asset, ["Client Category", "client_category", "category"], "")
    cost = _safe_get(asset, ["Cost", "cost"], "")
    location = _safe_get(asset, ["Location", "location"], "")

    # Build contextual payload
    payload = {
        "description": desc,
        "tokens": tokens,
    }

    if client_category:
        payload["client_provided_category"] = client_category
    if cost:
        payload["cost"] = cost
    if location:
        payload["location"] = location

    try:
        cli = OpenAI()

        prompt_filled = GPT_PROMPT.format(asset_json=json.dumps(payload, indent=2))

        # Use retry-wrapped API call
        resp = _make_gpt_api_call(cli, model, prompt_filled)

        # HIGH PRIORITY: Validate GPT response structure
        if not resp:
            raise ValueError("GPT API returned empty response")

        if not hasattr(resp, 'choices') or not resp.choices:
            raise ValueError("GPT API response missing 'choices' field")

        if len(resp.choices) == 0:
            raise ValueError("GPT API response has empty choices array")

        first_choice = resp.choices[0]
        if not hasattr(first_choice, 'message'):
            raise ValueError("GPT API response choice missing 'message' field")

        if not hasattr(first_choice.message, 'content'):
            raise ValueError("GPT API response message missing 'content' field")

        content = first_choice.message.content
        if not content or content.strip() == "":
            raise ValueError("GPT API returned empty content")

        # Parse JSON response
        try:
            data = json.loads(content)
        except json.JSONDecodeError as je:
            raise ValueError(f"GPT API returned invalid JSON: {je}. Content: {content[:200]}")

        # Validate and normalize
        data.setdefault("class", None)
        data.setdefault("life", None)
        data.setdefault("method", None)
        data.setdefault("convention", None)
        data.setdefault("bonus", False)
        data.setdefault("qip", False)
        data.setdefault("reasoning", "")

        # Fix confidence type
        try:
            data["confidence"] = float(data.get("confidence", 0.5))
        except (ValueError, TypeError):
            data["confidence"] = 0.5

        # Clamp confidence to [0, 1]
        data["confidence"] = max(0.0, min(1.0, data["confidence"]))

        return data

    except Exception as e:
        # Log the error and fall back to keyword classification
        logger.warning(f"GPT API error: {e} - falling back to keyword classification")

        # Use keyword fallback instead of returning empty result
        fallback_result = _keyword_fallback_classification(asset)
        fallback_result["reasoning"] = f"GPT failed ({str(e)[:50]}...) - {fallback_result.get('reasoning', 'keyword fallback')}"

        return fallback_result


# ===================================================================================
# QIP DATE VERIFICATION - Tax Compliance
# ===================================================================================

def _verify_qip_eligibility(asset: Dict, qip_result: Dict) -> Dict:
    """
    Verify QIP eligibility based on placed-in-service date.

    Per IRC §168(e)(6), QIP only applies to improvements placed in service
    after December 31, 2017. Pre-2018 interior improvements are 39-year
    nonresidential real property.

    Args:
        asset: Asset dict with In Service Date
        qip_result: Classification result indicating QIP

    Returns:
        Modified result dict with correct classification based on date
    """
    from .parse_utils import parse_date
    from datetime import date

    # Get in-service date
    pis_date = _safe_get(asset, ["In Service Date", "in_service_date", "Date In Service"], None)

    if pis_date:
        pis_date = parse_date(pis_date)

    # If we have a date and it's before 2018, QIP is NOT allowed
    if pis_date:
        # Convert pandas Timestamp to date if necessary
        pis_date_compare = pis_date.date() if hasattr(pis_date, 'date') else pis_date
        if pis_date_compare < date(2018, 1, 1):
            # Pre-2018: Should be 39-year real property, NOT QIP
            return {
                "final_class": "Nonresidential Real Property",
                "final_life": 39,
                "final_method": "SL",
                "final_convention": "MM",
                "bonus": False,  # No bonus for pre-2018
                "qip": False,
                "source": qip_result.get("source", "rule"),
                "confidence": qip_result.get("confidence", 0.85),
                "low_confidence": False,
                "notes": f"Interior improvement placed in service {pis_date_compare.strftime('%Y-%m-%d')} - Pre-2018, classified as 39-year property per IRC \u00a7168(e)(2). Original suggestion was QIP but date verification corrected this."
            }

    # Post-2018 or no date: QIP is allowed (return original)
    # Add note about date verification
    notes = qip_result.get("notes", "")
    if pis_date:
        # Convert pandas Timestamp to date if necessary
        pis_date_for_notes = pis_date.date() if hasattr(pis_date, 'date') else pis_date
        notes += f" | QIP verified: placed in service {pis_date_for_notes.strftime('%Y-%m-%d')} (post-2017)"
    else:
        notes += " | WARNING: No in-service date provided - QIP classification not verified. Confirm date >= 2018-01-01"
        qip_result["low_confidence"] = True

    qip_result["notes"] = notes
    return qip_result


# ===================================================================================
# CLASSIFICATION PIPELINE
# ===================================================================================

def classify_asset(
    asset: Dict,
    client=None,
    model: str = "gpt-4o-mini",
    rules: Optional[Dict] = None,
    overrides: Optional[Dict] = None,
    strategy: str = "rule_then_gpt"
) -> Dict:
    """
    Classify a single asset using multi-tier approach

    Classification Priority:
    1. User overrides (by asset ID)
    2. Rule-based pattern matching
    3. Client category mapping
    4. GPT fallback

    Args:
        asset: Asset dict with Description, Cost, etc.
        client: OpenAI client (optional, will create if needed)
        model: GPT model to use
        rules: Rules dict (will load if not provided)
        overrides: Overrides dict (will load if not provided)
        strategy: Classification strategy (currently only "rule_then_gpt")

    Returns:
        Dict with final_class, final_life, final_method, final_convention,
        bonus, qip, source, confidence, low_confidence, notes
    """
    rules = rules or load_rules()
    overrides = overrides or load_overrides()

    # ========================================================================
    # TIER 1: User Overrides (by asset ID)
    # ========================================================================
    aid = _normalize(_safe_get(asset, ["Asset ID", "asset_id"], ""))
    if aid and aid in overrides.get("by_asset_id", {}):
        override = overrides["by_asset_id"][aid]
        return {
            "final_class": override.get("class"),
            "final_life": override.get("life"),
            "final_method": override.get("method"),
            "final_convention": override.get("convention"),
            "bonus": override.get("bonus", False),
            "qip": override.get("qip", False),
            "source": "override",
            "confidence": 1.0,
            "low_confidence": False,
            "notes": "User override"
        }

    # ========================================================================
    # TIER 2: Rule-based Pattern Matching with Top-2 Guesses
    # ========================================================================
    top_matches = _match_rule(asset, rules, return_top_n=2)
    if top_matches:
        # Handle both single match (backward compat) and list formats
        if isinstance(top_matches, tuple):
            top_matches = [top_matches]

        rule, match_score = top_matches[0]

        # Calculate confidence based on match strength
        # Scores typically range from 2.0 (minimum) to 15+ (strong match)
        # Map to confidence: 2-4 → 0.85, 4-8 → 0.9, 8+ → 0.95+
        if match_score >= 10:
            confidence = 0.98
        elif match_score >= 6:
            confidence = 0.95
        elif match_score >= 4:
            confidence = 0.90
        else:
            confidence = 0.85

        result = {
            "final_class": rule.get("class"),
            "final_life": rule.get("life"),
            "final_method": rule.get("method"),
            "final_convention": rule.get("convention"),
            "bonus": rule.get("bonus", False),
            "qip": rule.get("qip", False),
            "source": "rule",
            "confidence": confidence,
            "low_confidence": False,
            "notes": f"Matched rule: {rule.get('name', 'unnamed')} (score: {match_score:.1f})"
        }

        # Add secondary guess if available (Top-2 classification)
        if len(top_matches) > 1:
            second_rule, second_score = top_matches[1]
            second_confidence = 0.95 if second_score >= 10 else (0.90 if second_score >= 6 else 0.80)
            result["secondary_guess"] = {
                "class": second_rule.get("class"),
                "life": second_rule.get("life"),
                "method": second_rule.get("method"),
                "convention": second_rule.get("convention"),
                "confidence": second_confidence,
                "rule_name": second_rule.get("name", "unnamed"),
                "score": second_score
            }

        # CRITICAL: Verify QIP eligibility based on in-service date
        if result.get("qip"):
            result = _verify_qip_eligibility(asset, result)

        return result

    # ========================================================================
    # TIER 2.5: Memory Engine - Learned patterns from prior classifications
    # ========================================================================
    if MEMORY_ENABLED:
        try:
            desc_raw = _safe_get(asset, ["Description", "description"], "")
            desc = sanitize_description(desc_raw)

            # Query memory engine for similar past classifications
            memory_match = memory_engine.query_similar(desc, threshold=0.82)

            if memory_match:
                mem_class = memory_match.get("classification", {})
                similarity = memory_match.get("similarity", 0.82)

                # Use memory classification if similarity is high enough
                result = {
                    "final_class": mem_class.get("class") or mem_class.get("final_class"),
                    "final_life": mem_class.get("life") or mem_class.get("final_life"),
                    "final_method": mem_class.get("method") or mem_class.get("final_method"),
                    "final_convention": mem_class.get("convention") or mem_class.get("final_convention"),
                    "bonus": mem_class.get("bonus", False),
                    "qip": mem_class.get("qip", False),
                    "source": "memory_engine",
                    "confidence": min(0.90, similarity),  # Cap at 0.90 for memory matches
                    "low_confidence": False,
                    "notes": f"Memory match (similarity: {similarity:.2f}) from prior classification"
                }

                # CRITICAL: Verify QIP eligibility based on in-service date
                if result.get("qip"):
                    result = _verify_qip_eligibility(asset, result)

                logger.info(f"Memory engine matched: '{desc[:40]}...' -> {result['final_class']}")
                return result

        except Exception as e:
            logger.warning(f"Memory engine error (non-fatal): {e}")
            # Continue to next tier if memory engine fails

    # ========================================================================
    # TIER 3: Client Category Mapping
    # ========================================================================
    # CRITICAL: Some client categories are too broad and need GPT verification
    # Example: "Leasehold Improvements" could be QIP (interior lighting) OR
    # 39-year property (elevator, expansion) - need to analyze description
    AMBIGUOUS_CATEGORIES_REQUIRING_GPT = [
        "leasehold", "leasehold improvements", "tenant improvement", "tenant improvements",
        "building improvement", "building improvements", "interior improvements"
    ]

    client_category = _safe_get(asset, ["Client Category", "client_category", "category"], "")
    if client_category:
        cat_match = _match_client_category(client_category)
        if cat_match:
            # Check if this is an ambiguous category that maps to QIP
            cat_normalized = _normalize(client_category)
            is_ambiguous_qip = (
                cat_match.get("qip", False) and
                cat_normalized in AMBIGUOUS_CATEGORIES_REQUIRING_GPT
            )

            # If ambiguous QIP category, use GPT to verify it's truly QIP
            # (not elevator, expansion, or structural framework)
            if is_ambiguous_qip and client:
                gpt_result = _call_gpt(asset, model=model)

                # If GPT says it's NOT QIP, trust GPT over blind category mapping
                if not gpt_result.get("qip", False):
                    result = {
                        "final_class": gpt_result.get("class"),
                        "final_life": gpt_result.get("life"),
                        "final_method": gpt_result.get("method"),
                        "final_convention": gpt_result.get("convention"),
                        "bonus": gpt_result.get("bonus", False),
                        "qip": False,
                        "source": "gpt_qip_verification",
                        "confidence": gpt_result.get("confidence", 0.7),
                        "low_confidence": gpt_result.get("confidence", 0.7) < LOW_CONF_THRESHOLD,
                        "notes": f"Client category '{client_category}' suggested QIP, but GPT analysis: {gpt_result.get('reasoning', 'not QIP')}"
                    }

                    # Still verify date eligibility
                    if result.get("qip"):
                        result = _verify_qip_eligibility(asset, result)

                    return result

                # GPT confirms QIP - use GPT's detailed classification
                else:
                    result = {
                        "final_class": gpt_result.get("class"),
                        "final_life": gpt_result.get("life"),
                        "final_method": gpt_result.get("method"),
                        "final_convention": gpt_result.get("convention"),
                        "bonus": gpt_result.get("bonus", True),
                        "qip": True,
                        "source": "gpt_qip_verified",
                        "confidence": gpt_result.get("confidence", 0.85),
                        "low_confidence": False,
                        "notes": f"QIP verified by GPT: {gpt_result.get('reasoning', 'qualified improvement property')}"
                    }

                    # Verify date eligibility
                    if result.get("qip"):
                        result = _verify_qip_eligibility(asset, result)

                    return result

            # Non-ambiguous category mapping (or GPT not available)
            result = {
                "final_class": cat_match.get("class"),
                "final_life": cat_match.get("life"),
                "final_method": cat_match.get("method"),
                "final_convention": cat_match.get("convention"),
                "bonus": cat_match.get("bonus", True),
                "qip": cat_match.get("qip", False),
                "source": "client_category",
                "confidence": 0.85,
                "low_confidence": False,
                "notes": f"Mapped from client category: {client_category}"
            }

            # CRITICAL: Verify QIP eligibility based on in-service date
            if result.get("qip"):
                result = _verify_qip_eligibility(asset, result)

            return result

    # ========================================================================
    # TIER 4: GPT Fallback
    # ========================================================================
    gpt_result = _call_gpt(asset, model=model)

    # Validate GPT category against approved MACRS categories
    gpt_result = _validate_gpt_category(gpt_result)

    is_low_conf = gpt_result.get("confidence", 0) < LOW_CONF_THRESHOLD

    result = {
        "final_class": gpt_result.get("class") or gpt_result.get("final_class"),
        "final_life": gpt_result.get("life") or gpt_result.get("final_life"),
        "final_method": gpt_result.get("method") or gpt_result.get("final_method"),
        "final_convention": gpt_result.get("convention") or gpt_result.get("final_convention"),
        "bonus": gpt_result.get("bonus", False),
        "qip": gpt_result.get("qip", False),
        "source": "gpt",
        "confidence": gpt_result.get("confidence", 0.5),
        "low_confidence": is_low_conf or gpt_result.get("low_confidence", False),
        "notes": gpt_result.get("notes") or gpt_result.get("reasoning", "GPT classification")
    }

    # CRITICAL: Verify QIP eligibility based on in-service date
    if result.get("qip"):
        result = _verify_qip_eligibility(asset, result)

    # Store successful GPT classification in memory for future similar assets
    if MEMORY_ENABLED and result.get("final_class") and result.get("confidence", 0) >= 0.7:
        try:
            desc_raw = _safe_get(asset, ["Description", "description"], "")
            desc = sanitize_description(desc_raw)

            # Store the classification for future reference
            memory_engine.store(desc, {
                "class": result["final_class"],
                "life": result["final_life"],
                "method": result["final_method"],
                "convention": result["final_convention"],
                "bonus": result.get("bonus", False),
                "qip": result.get("qip", False),
            })
            logger.info(f"Stored GPT classification in memory: '{desc[:40]}...' -> {result['final_class']}")
        except Exception as e:
            logger.warning(f"Failed to store in memory engine: {e}")

    return result
