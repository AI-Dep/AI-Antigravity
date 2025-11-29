"""
Fixed Asset AI - Column Detection Module

Header keys, fuzzy matching, and column mapping logic
extracted from sheet_loader.py for better maintainability.

Enhanced with hybrid token-based matching for better handling
of messy client headers (e.g., "Asset Desc" -> "Property Description").

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz


# ====================================================================================
# CONFIGURATION & CONSTANTS
# ====================================================================================

# Fuzzy matching thresholds
FUZZY_MATCH_THRESHOLD = 75
FUZZY_MATCH_SUBSTRING_MIN_LENGTH = 4
FUZZY_MATCH_REVERSE_SUBSTRING_MIN_LENGTH = 6

# Token matching thresholds
TOKEN_MATCH_THRESHOLD = 0.65  # Minimum token overlap ratio
HYBRID_SCORE_THRESHOLD = 0.70  # Minimum hybrid score for match

# Scoring weights for hybrid matching
TOKEN_WEIGHT = 0.70  # Weight for token/synonym matching
FUZZY_WEIGHT = 0.30  # Weight for fuzzy string matching

# Confidence levels for CPA review
CONFIDENCE_HIGH = 0.90  # Auto-accept
CONFIDENCE_MEDIUM = 0.75  # Likely correct, show for verification
CONFIDENCE_LOW = 0.65  # Needs CPA review


# ====================================================================================
# FIXED ASSET SYNONYM DICTIONARY
# ====================================================================================
# Maps common variations to canonical tokens for better matching.
# This enables "Asset Desc" to match "Property Description".

FA_SYNONYMS = {
    # Asset identification
    "asset": {"property", "item", "equipment", "fa", "fixed"},
    "property": {"asset", "item", "equipment"},
    "id": {"number", "no", "num", "#", "identifier"},
    "number": {"id", "no", "num", "#"},
    "tag": {"id", "number", "label"},

    # Description
    "description": {"desc", "name", "details", "item", "asset", "particulars"},
    "desc": {"description", "name"},
    "name": {"description", "title", "label"},
    "particulars": {"description", "details"},

    # Cost/value
    "cost": {"basis", "amount", "value", "price"},
    "basis": {"cost", "value", "amount"},
    "amount": {"cost", "value", "price"},
    "value": {"cost", "basis", "amount"},
    "price": {"cost", "amount", "value"},

    # Dates
    "date": {"dt"},
    "acquisition": {"purchase", "acquired", "bought", "acq"},
    "purchase": {"acquisition", "acquired", "bought"},
    "acq": {"acquisition", "purchase"},
    "service": {"pis", "placed", "operational", "start"},
    "pis": {"service", "placed", "in service"},
    "placed": {"service", "pis", "start"},
    "disposal": {"disposed", "sold", "sale", "retire", "retired"},
    "disposed": {"disposal", "sold", "retired"},
    "sold": {"disposal", "sale", "disposed"},
    "retire": {"retired", "disposal", "disposed"},

    # Depreciation
    "depreciation": {"depr", "dep", "depn"},
    "depr": {"depreciation", "dep"},
    "accumulated": {"accum", "prior", "total", "cumulative"},
    "accum": {"accumulated", "prior", "total"},
    "prior": {"accumulated", "previous", "historical"},

    # Life/period
    "life": {"period", "years", "useful", "recovery"},
    "recovery": {"life", "period", "years"},
    "period": {"life", "years", "term"},
    "useful": {"life", "recovery"},

    # Method/convention
    "method": {"convention", "type", "system"},
    "convention": {"method", "type"},

    # Category/class
    "category": {"class", "type", "group", "classification"},
    "class": {"category", "type", "group"},
    "type": {"category", "class", "kind"},

    # Tax-specific
    "tax": {"federal", "irs", "macrs"},
    "federal": {"tax", "irs"},
    "macrs": {"tax", "federal", "irs"},
    "book": {"gaap", "accounting", "financial"},
    "gaap": {"book", "accounting"},

    # Section 179/Bonus
    "179": {"section179", "sec179", "s179"},
    "section": {"sec", "s"},
    "bonus": {"special", "additional", "firstyear"},

    # Location/department
    "location": {"site", "facility", "plant", "building"},
    "site": {"location", "facility"},
    "department": {"dept", "division", "costcenter"},
    "dept": {"department", "division"},

    # Transfer
    "transfer": {"xfer", "move", "reclass"},
    "xfer": {"transfer", "move"},
    "from": {"old", "prior", "source", "original"},
    "to": {"new", "target", "destination"},
}

# Common abbreviations and expansions
FA_ABBREVIATIONS = {
    "acq": "acquisition",
    "accum": "accumulated",
    "amt": "amount",
    "bus": "business",
    "cat": "category",
    "conv": "convention",
    "cur": "current",
    "dept": "department",
    "dep": "depreciation",
    "depr": "depreciation",
    "desc": "description",
    "disp": "disposal",
    "dt": "date",
    "eq": "equipment",
    "fa": "fixed asset",
    "furn": "furniture",
    "fix": "fixtures",
    "hist": "historical",
    "id": "identifier",
    "imp": "improvement",
    "ltd": "life to date",
    "nbv": "net book value",
    "no": "number",
    "num": "number",
    "orig": "original",
    "pct": "percent",
    "pis": "placed in service",
    "prop": "property",
    "purch": "purchase",
    "qip": "qualified improvement property",
    "rec": "recovery",
    "ret": "retired",
    "sec": "section",
    "svc": "service",
    "xfer": "transfer",
    "yr": "year",
    "ytd": "year to date",
}

# Stopwords to ignore in token matching
FA_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "in", "on", "at",
    "to", "by", "is", "as", "be", "&"
}


# ====================================================================================
# DATA CLASSES
# ====================================================================================

@dataclass
class ColumnMapping:
    """Represents a column mapping with confidence score and audit details"""
    logical_name: str
    excel_column: str
    match_type: str  # "exact", "substring", "substring_reverse", "fuzzy", "token", "hybrid"
    confidence: float
    # Additional audit fields for transparency
    token_score: float = 0.0  # Token-based match score
    fuzzy_score: float = 0.0  # Fuzzy string match score
    matched_keyword: str = ""  # Which keyword triggered the match
    synonym_applied: bool = False  # Whether synonyms were used

    @property
    def confidence_level(self) -> str:
        """Get human-readable confidence level for CPA review."""
        if self.confidence >= CONFIDENCE_HIGH:
            return "HIGH"
        elif self.confidence >= CONFIDENCE_MEDIUM:
            return "MEDIUM"
        else:
            return "LOW"

    @property
    def needs_review(self) -> bool:
        """Whether this mapping should be flagged for CPA review."""
        return self.confidence < CONFIDENCE_MEDIUM

    def __repr__(self) -> str:
        review = " [REVIEW]" if self.needs_review else ""
        return f"{self.logical_name} -> {self.excel_column} ({self.match_type}, {self.confidence:.2f}){review}"


@dataclass
class TokenMatchResult:
    """Result of token-based matching"""
    score: float
    matched_tokens: Set[str] = field(default_factory=set)
    synonym_matches: Dict[str, str] = field(default_factory=dict)  # original -> matched via synonym
    missing_tokens: Set[str] = field(default_factory=set)


# ====================================================================================
# TOKEN NORMALIZATION & MATCHING
# ====================================================================================

def _tokenize(text: str) -> List[str]:
    """
    Tokenize text for matching.

    - Lowercase
    - Remove special characters
    - Split into tokens
    - Remove stopwords
    - Expand abbreviations

    Args:
        text: Raw text to tokenize

    Returns:
        List of normalized tokens
    """
    if not text or not isinstance(text, str):
        return []

    # Lowercase and remove special chars except alphanumeric
    normalized = str(text).lower().strip()
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)

    # Split into tokens
    tokens = normalized.split()

    # Remove stopwords and expand abbreviations
    result = []
    for token in tokens:
        if token in FA_STOPWORDS:
            continue
        # Expand abbreviations to canonical form
        expanded = FA_ABBREVIATIONS.get(token, token)
        # Handle multi-word expansions
        result.extend(expanded.split())

    return result


@lru_cache(maxsize=1024)
def _get_synonyms(token: str) -> Set[str]:
    """
    Get all synonyms for a token (including the token itself).

    Uses bidirectional synonym lookup.

    Args:
        token: Token to find synonyms for

    Returns:
        Set of synonyms including original token
    """
    synonyms = {token}

    # Direct synonyms
    if token in FA_SYNONYMS:
        synonyms.update(FA_SYNONYMS[token])

    # Reverse lookup (find tokens that have this as a synonym)
    for key, values in FA_SYNONYMS.items():
        if token in values:
            synonyms.add(key)
            synonyms.update(values)

    return synonyms


def _tokens_match(token1: str, token2: str) -> bool:
    """
    Check if two tokens match (exact or via synonym).

    Args:
        token1: First token
        token2: Second token

    Returns:
        True if tokens match directly or via synonym
    """
    if token1 == token2:
        return True

    # Check synonyms
    return token2 in _get_synonyms(token1)


def _calculate_token_score(
    target_tokens: List[str],
    candidate_tokens: List[str]
) -> TokenMatchResult:
    """
    Calculate token-based match score.

    Measures what percentage of target tokens are found in candidate
    (either directly or via synonyms).

    Args:
        target_tokens: Tokens from the target/keyword
        candidate_tokens: Tokens from the candidate header

    Returns:
        TokenMatchResult with score and match details
    """
    if not target_tokens:
        return TokenMatchResult(score=0.0)

    matched = set()
    synonym_matches = {}
    missing = set()

    candidate_set = set(candidate_tokens)
    candidate_synonyms = {}
    for ct in candidate_tokens:
        candidate_synonyms[ct] = _get_synonyms(ct)

    for target in target_tokens:
        target_syns = _get_synonyms(target)
        found = False

        # Direct match
        if target in candidate_set:
            matched.add(target)
            found = True
        else:
            # Synonym match
            for candidate in candidate_tokens:
                if target in candidate_synonyms.get(candidate, set()) or candidate in target_syns:
                    matched.add(target)
                    synonym_matches[target] = candidate
                    found = True
                    break

        if not found:
            missing.add(target)

    score = len(matched) / len(target_tokens) if target_tokens else 0.0

    return TokenMatchResult(
        score=score,
        matched_tokens=matched,
        synonym_matches=synonym_matches,
        missing_tokens=missing
    )


# ====================================================================================
# HEADER DETECTION KEYS - Comprehensive mappings for all possible column names
# ====================================================================================

HEADER_KEYS = {
    "asset_id": [
        # Standard
        "asset", "asset id", "asset_id", "assetid", "id", "asset number", "asset #",
        "asst id", "asst #", "item id", "item number", "item #",
        # Variations
        "fixed asset id", "fixed asset number", "fa id", "fa #",
        "property id", "property number", "prop id", "prop #",
        "tag", "tag number", "asset tag", "equipment id", "equipment number",
        "serial", "serial number", "serial #",
        # Alternate
        "number", "no", "no.", "#", "ref", "reference"
    ],

    "description": [
        # Standard
        "description", "desc", "asset description", "item description",
        "property", "property description", "asset name", "item name",
        # Variations
        "equipment description", "equipment", "details", "item",
        "asset details", "name", "title", "asset",
        # Specific
        "make/model", "make and model", "model", "type/description",
        # Additional common variations
        "fixed asset", "fa description", "fa desc", "asset desc",
        "asset detail", "asset info", "information", "particulars",
        "equipment name", "property name", "item details"
    ],

    "category": [
        # Standard
        "category", "class", "asset class", "asset category",
        "type", "asset type", "classification", "fa class",
        # Tax specific
        "tax category", "depreciation class", "macrs class",
        "life class", "property class", "property type",
        # Alternate
        "group", "asset group", "class code", "category code"
    ],

    "cost": [
        # Standard
        "cost", "amount", "value", "purchase price", "price",
        "original cost", "acquisition cost", "basis", "cost basis",
        # Variations
        "historical cost", "book value", "capitalized cost",
        "total cost", "net cost", "gross cost",
        # Specific
        "cost/basis", "cost or basis", "unadjusted basis",
        "depreciable basis", "tax basis"
    ],

    "acquisition_date": [
        # Standard
        "acquisition date", "acq date", "acq. date",
        "purchase date", "purch date", "buy date",
        # Variations
        "acquired", "date acquired", "date of acquisition",
        "date purchased", "date of purchase",
        # Specific
        "original acquisition date", "acquisition", "purch"
    ],

    "in_service_date": [
        # Standard
        "in service date", "in-service date", "service date",
        "placed in service", "pis date", "pis",
        # Variations
        "start date", "begin date", "started",
        "date in service", "date placed in service",
        # Tax specific
        "depreciation start date", "tax start date"
    ],

    "location": [
        # Standard
        "location", "site", "facility",
        # Variations
        "plant", "branch", "office",
        "room", "building", "floor"
    ],

    "department": [
        # Standard
        "department", "dept", "division",
        "cost center", "business unit"
    ],

    "disposal_date": [
        # Standard
        "disposal date", "disposed date", "sold date", "sale date",
        "retirement date", "retire date", "retired",
        # Variations
        "date disposed", "date sold", "date retired",
        "writeoff date", "write-off date"
    ],

    "proceeds": [
        # Standard
        "proceeds", "sale proceeds", "sales price",
        "disposal proceeds", "salvage value"
    ],

    "method": [
        # Standard
        "method", "depreciation method", "depr method",
        # Variations
        "macrs method", "tax method", "convention"
    ],

    "life": [
        # Standard
        "life", "useful life", "recovery period",
        "class life", "macrs life", "years"
    ],

    "tax_life": [
        "tax life", "useful life tax", "tax useful life",
        "tax recovery period", "federal life", "macrs life"
    ],

    "book_life": [
        "book life", "useful life book", "gaap life",
        "book recovery period", "accounting life", "book useful life"
    ],

    "tax_method": [
        "tax method", "tax depreciation method", "federal method",
        "macrs method", "tax depr method"
    ],

    "book_method": [
        "book method", "book depreciation method", "gaap method",
        "accounting method", "book depr method"
    ],

    "transaction_type": [
        # Standard
        "transaction type", "trans type", "type", "status",
        # Variations
        "action", "activity", "change type", "transaction",
        "movement type", "adjustment type"
    ],

    "business_use_pct": [
        # Standard
        "business use %", "business use percent", "business use",
        "business percentage", "bus use %", "bus %",
        # Listed property specific
        "listed property %", "qbu %", "qualified business use",
        # Variations
        "work use %", "work percentage", "professional use %",
        "deductible %", "deductible percentage", "business pct"
    ],

    "accumulated_depreciation": [
        "accumulated depreciation", "accum depreciation", "accum depr",
        "accumulated depr", "prior depreciation", "depr taken",
        "total depreciation", "depreciation to date", "ytd depreciation",
        "life to date depreciation", "ltd depreciation",
        "cumulative depreciation", "total depr"
    ],

    "section_179_taken": [
        "section 179 taken", "179 taken", "sec 179 taken",
        "prior 179", "historical 179"
    ],

    "bonus_taken": [
        "bonus taken", "bonus depreciation taken",
        "prior bonus", "historical bonus"
    ],

    "net_book_value": [
        "net book value", "nbv", "book value", "carrying value",
        "undepreciated value", "remaining value", "net value",
        "adjusted basis", "current basis", "remaining basis",
        "tax basis", "federal basis"
    ],

    # Transfer-specific fields
    "transfer_date": ["transfer date", "xfer date", "date transferred"],
    "from_location": ["from location", "old location", "prior location", "source location"],
    "to_location": ["to location", "new location", "destination", "target location"],
    "from_department": ["from department", "old department", "prior department", "source department"],
    "to_department": ["to department", "new department", "target department"],
    "transfer_type": ["transfer type", "transfer reason", "reason for transfer"],
    "old_category": ["old category", "prior category", "original category", "from category"],
}

# Column mapping priorities
CRITICAL_FIELDS = ["asset_id", "description"]
IMPORTANT_FIELDS = ["acquisition_date", "in_service_date", "disposal_date", "cost"]
CATEGORY_LOCATION_FIELDS = ["category", "location", "department"]
OPTIONAL_FIELDS = [
    "method", "life", "transaction_type", "business_use_pct", "proceeds",
    "accumulated_depreciation", "section_179_taken", "bonus_taken",
    "net_book_value", "tax_life", "book_life", "tax_method", "book_method"
]
TRANSFER_FIELDS = [
    "transfer_date", "from_location", "to_location",
    "from_department", "to_department", "transfer_type", "old_category"
]


# ====================================================================================
# HEADER NORMALIZATION
# ====================================================================================

def _normalize_header(header: str) -> str:
    """
    Normalize header text for matching.

    - Lowercase
    - Remove special characters except spaces
    - Collapse multiple spaces

    Args:
        header: Raw header text

    Returns:
        Normalized header string
    """
    if not header or not isinstance(header, str):
        return ""

    normalized = str(header).lower().strip()
    # Remove special chars except alphanumeric and space
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


# ====================================================================================
# HYBRID MATCHING (Token + Fuzzy)
# ====================================================================================

def _calculate_hybrid_score(
    column_header: str,
    keyword: str,
    is_critical: bool = False,
    is_important: bool = False
) -> Tuple[float, str, float, float, bool]:
    """
    Calculate hybrid match score combining token-based and fuzzy matching.

    Uses weighted combination:
    - Token match with synonyms (70% weight)
    - Fuzzy string similarity (30% weight)

    Args:
        column_header: Raw column header
        keyword: Keyword to match
        is_critical: Is this a critical field?
        is_important: Is this an important field?

    Returns:
        Tuple of (final_score, match_type, token_score, fuzzy_score, synonym_used)
    """
    header_norm = _normalize_header(column_header)
    keyword_norm = _normalize_header(keyword)

    if not header_norm or not keyword_norm:
        return 0.0, "none", 0.0, 0.0, False

    # Exact match (highest priority)
    if header_norm == keyword_norm:
        # Return as decimal (0-1 scale)
        base = 1.0 if is_critical else (0.97 if is_important else 0.95)
        return base, "exact", 1.0, 1.0, False

    # Tokenize both
    header_tokens = _tokenize(column_header)
    keyword_tokens = _tokenize(keyword)

    # Calculate token-based score
    token_result = _calculate_token_score(keyword_tokens, header_tokens)
    token_score = token_result.score
    synonym_used = len(token_result.synonym_matches) > 0

    # Calculate fuzzy score
    fuzzy_score = fuzz.ratio(header_norm, keyword_norm) / 100.0

    # Substring bonus
    substring_bonus = 0.0
    if len(keyword_norm) >= FUZZY_MATCH_SUBSTRING_MIN_LENGTH and keyword_norm in header_norm:
        substring_bonus = 0.15
    elif len(header_norm) >= FUZZY_MATCH_REVERSE_SUBSTRING_MIN_LENGTH and header_norm in keyword_norm:
        substring_bonus = 0.10

    # Combine scores with weights
    hybrid_score = (
        TOKEN_WEIGHT * token_score +
        FUZZY_WEIGHT * fuzzy_score +
        substring_bonus
    )

    # Cap at 1.0
    hybrid_score = min(hybrid_score, 1.0)

    # Determine match type
    if token_score >= 0.8 and fuzzy_score >= 0.7:
        match_type = "hybrid"
    elif token_score >= 0.8:
        match_type = "token"
    elif fuzzy_score >= 0.75:
        match_type = "fuzzy"
    elif substring_bonus > 0:
        match_type = "substring"
    else:
        match_type = "partial"

    # Apply field priority bonus
    if is_critical and hybrid_score >= HYBRID_SCORE_THRESHOLD:
        hybrid_score = min(hybrid_score + 0.05, 1.0)
    elif is_important and hybrid_score >= HYBRID_SCORE_THRESHOLD:
        hybrid_score = min(hybrid_score + 0.02, 1.0)

    return hybrid_score, match_type, token_score, fuzzy_score, synonym_used


def _calculate_match_score(
    column_header: str,
    keyword: str,
    is_critical: bool = False,
    is_important: bool = False
) -> Tuple[float, str]:
    """
    Calculate match score between column header and keyword.

    Uses hybrid matching combining token-based and fuzzy approaches.

    Returns score (0-100) and match type:
    - exact: Header exactly matches keyword
    - hybrid: Both token and fuzzy match well
    - token: Token-based match (with synonyms)
    - fuzzy: Fuzzy string similarity
    - substring: Substring match
    - partial: Weak match

    Args:
        column_header: Raw column header
        keyword: Keyword to match
        is_critical: Is this a critical field (asset_id, description)?
        is_important: Is this an important field (cost, dates)?

    Returns:
        Tuple of (score 0-100, match_type)
    """
    hybrid_score, match_type, _, _, _ = _calculate_hybrid_score(
        column_header, keyword, is_critical, is_important
    )

    # Convert to 0-100 scale for backward compatibility
    return hybrid_score * 100, match_type


def _find_best_match(
    column_headers: List[str],
    logical_field: str,
    exclude_columns: Set[str] = None
) -> Optional[ColumnMapping]:
    """
    Find best matching column for a logical field using hybrid matching.

    Args:
        column_headers: List of column headers to search
        logical_field: Logical field name (e.g., "asset_id", "cost")
        exclude_columns: Set of already-mapped columns to exclude

    Returns:
        ColumnMapping if found with confidence >= threshold, None otherwise
    """
    if logical_field not in HEADER_KEYS:
        return None

    exclude = exclude_columns or set()
    keywords = HEADER_KEYS[logical_field]

    is_critical = logical_field in CRITICAL_FIELDS
    is_important = logical_field in IMPORTANT_FIELDS

    best_score = 0.0
    best_match = None
    best_type = "none"
    best_token_score = 0.0
    best_fuzzy_score = 0.0
    best_keyword = ""
    best_synonym_used = False

    for col_header in column_headers:
        if col_header in exclude:
            continue

        col_norm = _normalize_header(col_header)
        if not col_norm:
            continue

        for keyword in keywords:
            score, match_type, token_score, fuzzy_score, synonym_used = _calculate_hybrid_score(
                col_header, keyword, is_critical, is_important
            )

            if score > best_score:
                best_score = score
                best_match = col_header
                best_type = match_type
                best_token_score = token_score
                best_fuzzy_score = fuzzy_score
                best_keyword = keyword
                best_synonym_used = synonym_used

    # Use hybrid threshold for matching
    threshold = HYBRID_SCORE_THRESHOLD if best_type in ("hybrid", "token") else FUZZY_MATCH_THRESHOLD / 100.0

    if best_match and best_score >= threshold:
        return ColumnMapping(
            logical_name=logical_field,
            excel_column=best_match,
            match_type=best_type,
            confidence=best_score,
            token_score=best_token_score,
            fuzzy_score=best_fuzzy_score,
            matched_keyword=best_keyword,
            synonym_applied=best_synonym_used
        )

    return None


def detect_columns(
    column_headers: List[str],
    client_mappings: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, str], List[ColumnMapping], List[str]]:
    """
    Detect column mappings from headers.

    Priority order:
    1. Client-specific mappings (if provided)
    2. Critical fields (asset_id, description)
    3. Important fields (dates, cost)
    4. Category/location fields
    5. Optional fields
    6. Transfer fields

    Args:
        column_headers: List of Excel column headers
        client_mappings: Optional client-specific column mappings

    Returns:
        Tuple of (col_map dict, column_mappings list, warnings list)
    """
    col_map = {}
    mappings = []
    warnings = []
    used_columns = set()

    # Apply client-specific mappings first
    if client_mappings:
        for logical_name, excel_col in client_mappings.items():
            if excel_col in column_headers:
                col_map[logical_name] = excel_col
                used_columns.add(excel_col)
                mappings.append(ColumnMapping(
                    logical_name=logical_name,
                    excel_column=excel_col,
                    match_type="client_mapping",
                    confidence=1.0
                ))

    # Process fields in priority order
    all_fields = (
        CRITICAL_FIELDS +
        IMPORTANT_FIELDS +
        CATEGORY_LOCATION_FIELDS +
        OPTIONAL_FIELDS +
        TRANSFER_FIELDS
    )

    for field in all_fields:
        if field in col_map:
            continue  # Already mapped by client config

        match = _find_best_match(column_headers, field, used_columns)
        if match:
            col_map[field] = match.excel_column
            used_columns.add(match.excel_column)
            mappings.append(match)

    # Add warnings for missing critical fields
    for critical in CRITICAL_FIELDS:
        if critical not in col_map:
            warnings.append(f"Missing critical column: {critical}")

    return col_map, mappings, warnings


def get_all_keywords_for_field(field_name: str) -> List[str]:
    """
    Get all keywords associated with a logical field.

    Args:
        field_name: Logical field name

    Returns:
        List of keywords or empty list if field not found
    """
    return HEADER_KEYS.get(field_name, [])


def add_custom_keyword(field_name: str, keyword: str):
    """
    Add a custom keyword to a field's keyword list.

    Useful for extending detection with client-specific terms.

    Args:
        field_name: Logical field name
        keyword: New keyword to add
    """
    if field_name in HEADER_KEYS:
        if keyword.lower() not in [k.lower() for k in HEADER_KEYS[field_name]]:
            HEADER_KEYS[field_name].append(keyword)


def add_custom_synonym(token: str, synonyms: Set[str]):
    """
    Add custom synonyms for a token.

    Useful for client-specific terminology.

    Args:
        token: Base token
        synonyms: Set of synonym tokens
    """
    token_lower = token.lower()
    if token_lower in FA_SYNONYMS:
        FA_SYNONYMS[token_lower].update(synonyms)
    else:
        FA_SYNONYMS[token_lower] = synonyms


# ====================================================================================
# CPA REVIEW & AUDIT FUNCTIONS
# ====================================================================================

def get_mappings_for_review(mappings: List[ColumnMapping]) -> List[ColumnMapping]:
    """
    Filter mappings that need CPA review (low confidence).

    Args:
        mappings: List of column mappings

    Returns:
        List of mappings that need review
    """
    return [m for m in mappings if m.needs_review]


def get_mappings_by_confidence(
    mappings: List[ColumnMapping]
) -> Dict[str, List[ColumnMapping]]:
    """
    Group mappings by confidence level.

    Args:
        mappings: List of column mappings

    Returns:
        Dict with keys "HIGH", "MEDIUM", "LOW" containing mappings
    """
    result = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for m in mappings:
        result[m.confidence_level].append(m)
    return result


def generate_mapping_audit_report(
    mappings: List[ColumnMapping],
    include_all: bool = False
) -> str:
    """
    Generate human-readable audit report of column mappings.

    Args:
        mappings: List of column mappings
        include_all: If True, include all mappings; if False, only low confidence

    Returns:
        Formatted audit report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("COLUMN MAPPING AUDIT REPORT")
    lines.append("=" * 70)

    # Group by confidence
    by_conf = get_mappings_by_confidence(mappings)

    # Summary
    lines.append(f"\nSummary:")
    lines.append(f"  High Confidence (>90%):   {len(by_conf['HIGH'])} mappings")
    lines.append(f"  Medium Confidence (75-90%): {len(by_conf['MEDIUM'])} mappings")
    lines.append(f"  Low Confidence (<75%):    {len(by_conf['LOW'])} mappings [NEEDS REVIEW]")

    # Low confidence (always show)
    if by_conf["LOW"]:
        lines.append("\n" + "-" * 70)
        lines.append("LOW CONFIDENCE MAPPINGS - REQUIRES CPA REVIEW")
        lines.append("-" * 70)
        for m in by_conf["LOW"]:
            lines.append(f"\n  {m.logical_name}:")
            lines.append(f"    Excel Column: {m.excel_column}")
            lines.append(f"    Confidence: {m.confidence:.1%}")
            lines.append(f"    Match Type: {m.match_type}")
            lines.append(f"    Token Score: {m.token_score:.2f}")
            lines.append(f"    Fuzzy Score: {m.fuzzy_score:.2f}")
            lines.append(f"    Matched via: '{m.matched_keyword}'")
            if m.synonym_applied:
                lines.append(f"    Synonym Applied: Yes")

    # Medium confidence (always show)
    if by_conf["MEDIUM"]:
        lines.append("\n" + "-" * 70)
        lines.append("MEDIUM CONFIDENCE MAPPINGS - VERIFY IF NEEDED")
        lines.append("-" * 70)
        for m in by_conf["MEDIUM"]:
            lines.append(f"  {m.logical_name} -> {m.excel_column} ({m.confidence:.1%}, {m.match_type})")

    # High confidence (only if include_all)
    if include_all and by_conf["HIGH"]:
        lines.append("\n" + "-" * 70)
        lines.append("HIGH CONFIDENCE MAPPINGS")
        lines.append("-" * 70)
        for m in by_conf["HIGH"]:
            lines.append(f"  {m.logical_name} -> {m.excel_column} ({m.confidence:.1%})")

    lines.append("\n" + "=" * 70)

    return "\n".join(lines)


def test_hybrid_matching(header: str, target_field: str) -> Dict:
    """
    Test hybrid matching for debugging/tuning.

    Args:
        header: Column header to test
        target_field: Logical field to match against

    Returns:
        Dict with detailed matching results
    """
    if target_field not in HEADER_KEYS:
        return {"error": f"Unknown field: {target_field}"}

    keywords = HEADER_KEYS[target_field]
    results = []

    for keyword in keywords:
        score, match_type, token_score, fuzzy_score, synonym_used = _calculate_hybrid_score(
            header, keyword,
            is_critical=target_field in CRITICAL_FIELDS,
            is_important=target_field in IMPORTANT_FIELDS
        )

        if score > 0:
            results.append({
                "keyword": keyword,
                "hybrid_score": score,
                "match_type": match_type,
                "token_score": token_score,
                "fuzzy_score": fuzzy_score,
                "synonym_used": synonym_used
            })

    # Sort by score
    results.sort(key=lambda x: x["hybrid_score"], reverse=True)

    return {
        "header": header,
        "target_field": target_field,
        "header_tokens": _tokenize(header),
        "matches": results,
        "best_match": results[0] if results else None
    }


# ====================================================================================
# LEGACY COMPATIBILITY
# ====================================================================================

# Keep these exports for backward compatibility
def _header_keys() -> Dict[str, List[str]]:
    """Get header keys dictionary (legacy compatibility)."""
    return HEADER_KEYS


def _fast_match(header: str, keywords: List[str]) -> bool:
    """Check if header matches any keyword (legacy compatibility)."""
    header_norm = _normalize_header(header)
    for kw in keywords:
        kw_norm = _normalize_header(kw)
        if header_norm == kw_norm or kw_norm in header_norm:
            return True
    return False


def _fuzzy_score(header: str, keyword: str) -> float:
    """Get fuzzy match score (legacy compatibility)."""
    return fuzz.ratio(_normalize_header(header), _normalize_header(keyword)) / 100.0


def get_standard_columns() -> List[str]:
    """Get list of standard logical column names."""
    return list(HEADER_KEYS.keys())


class HeaderMatchResult:
    """Legacy result class for backward compatibility."""

    def __init__(self, field: str, column: str, score: float, match_type: str):
        self.field = field
        self.column = column
        self.score = score
        self.match_type = match_type

    def __repr__(self):
        return f"HeaderMatchResult({self.field} -> {self.column}, {self.score:.2f})"
