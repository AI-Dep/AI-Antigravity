# fixed_asset_ai/logic/macrs_classification.py
"""
Enhanced Fixed Asset Classification Engine
Combines rule-based matching with GPT fallback for MACRS classification
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from .sanitizer import sanitize_description, tokenize_description

try:
    from .memory_engine import memory_engine
    MEMORY_ENABLED = True
except:
    MEMORY_ENABLED = False


BASE_DIR = Path(__file__).resolve().parent
RULES_PATH = BASE_DIR / "rules.json"
OVERRIDES_PATH = BASE_DIR / "overrides.json"

LOW_CONF_THRESHOLD = 0.75  # GPT confidence threshold
MIN_RULE_SCORE = 2.0  # Minimum score for rule to be considered valid


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
    except Exception as e:
        print(f"Warning: Failed to save overrides: {e}")


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

        if cat_norm and rule_class and cat_norm in rule_class or rule_class in cat_norm:
            score += 2.0  # Bonus for matching client category

    return score


def _match_rule(asset: Dict, rules: Dict) -> Optional[tuple[Dict, float]]:
    """
    Find best matching rule for an asset

    Returns tuple of (rule dict, match_score) or None if no rule meets minimum score
    """
    desc_raw = _safe_get(asset, ["Description", "description", "desc"], "")
    desc = sanitize_description(desc_raw)
    tokens = tokenize_description(desc)

    client_category = _safe_get(asset, ["Client Category", "client_category", "category"], "")

    best_rule = None
    best_score = 0.0

    min_score = rules.get("minimum_rule_score", MIN_RULE_SCORE)

    for rule in rules.get("rules", []):
        score = _rule_score(rule, desc, tokens, client_category)

        if score > best_score:
            best_rule = rule
            best_score = score

    # Only return rule if it meets minimum score threshold
    if best_score >= min_score:
        return (best_rule, best_score)

    return None


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
    """Try to match client-provided category to MACRS class"""
    if not client_category:
        return None

    cat_norm = _normalize(client_category)

    # Direct match
    if cat_norm in COMMON_CATEGORY_MAPPINGS:
        return COMMON_CATEGORY_MAPPINGS[cat_norm]

    # Partial match
    for key, mapping in COMMON_CATEGORY_MAPPINGS.items():
        if key in cat_norm or cat_norm in key:
            return mapping

    return None


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


def _call_gpt(asset: Dict, model: str = "gpt-4o-mini") -> Dict:
    """
    Call GPT for asset classification

    Returns dict with classification results and confidence
    """
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

        resp = cli.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_filled},
            ],
            temperature=0.3,  # Lower temperature for more consistent results
        )

        data = json.loads(resp.choices[0].message.content)

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
        except:
            data["confidence"] = 0.5

        # Clamp confidence to [0, 1]
        data["confidence"] = max(0.0, min(1.0, data["confidence"]))

        return data

    except Exception as e:
        return {
            "class": None,
            "life": None,
            "method": None,
            "convention": None,
            "bonus": False,
            "qip": False,
            "confidence": 0.0,
            "reasoning": f"GPT call failed: {str(e)}"
        }


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
    # TIER 2: Rule-based Pattern Matching
    # ========================================================================
    rule_match = _match_rule(asset, rules)
    if rule_match:
        rule, match_score = rule_match

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

        # CRITICAL: Verify QIP eligibility based on in-service date
        if result.get("qip"):
            result = _verify_qip_eligibility(asset, result)

        return result

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

    is_low_conf = gpt_result.get("confidence", 0) < LOW_CONF_THRESHOLD

    result = {
        "final_class": gpt_result.get("class"),
        "final_life": gpt_result.get("life"),
        "final_method": gpt_result.get("method"),
        "final_convention": gpt_result.get("convention"),
        "bonus": gpt_result.get("bonus", False),
        "qip": gpt_result.get("qip", False),
        "source": "gpt",
        "confidence": gpt_result.get("confidence", 0.5),
        "low_confidence": is_low_conf,
        "notes": gpt_result.get("reasoning", "GPT classification")
    }

    # CRITICAL: Verify QIP eligibility based on in-service date
    if result.get("qip"):
        result = _verify_qip_eligibility(asset, result)

    return result
