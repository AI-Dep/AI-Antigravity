# fixed_asset_ai/logic/sheet_loader.py
"""
Advanced Excel Parser for Fixed Asset Schedules

This module provides robust Excel parsing capabilities for fixed asset schedules
with intelligent column detection, header identification, and data validation.

Key Features:
- Fuzzy column name matching with priority-based mapping
- Automatic header row detection
- Sheet role detection (additions, disposals, transfers)
- Transaction type inference
- Comprehensive error handling and validation
- Debug logging support

Refactored Modules:
- column_detector.py: Header keys, fuzzy matching, column detection
- sheet_analyzer.py: Sheet skip, role detection, fiscal year logic

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import os
import logging
import warnings
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Set, Any
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import re
from rapidfuzz import fuzz

from .parse_utils import parse_date, parse_number
from .typo_engine import typo_engine
from . import client_mapping_manager

# Import from refactored column detector module (provides HEADER_KEYS, fuzzy matching)
from .column_detector import (
    ColumnMapping as BaseColumnMapping,
    HEADER_KEYS,
    CRITICAL_FIELDS as COL_CRITICAL_FIELDS,
    IMPORTANT_FIELDS as COL_IMPORTANT_FIELDS,
    FUZZY_MATCH_THRESHOLD as COL_FUZZY_THRESHOLD,
    _normalize_header,
    _find_best_match as find_column_match,
)

# Import from refactored sheet analyzer module (provides skip/role detection)
# Note: _should_skip_sheet is NOT imported - using local version with less aggressive patterns
from .sheet_analyzer import (
    SheetRole,
    _is_prior_year_sheet,
    _detect_sheet_role,
    _extract_fiscal_year_from_sheet,
    _is_date_in_fiscal_year,
    _detect_transaction_type,
)

# Smart tab analyzer is optional - graceful fallback if import fails
try:
    from . import smart_tab_analyzer
    SMART_TAB_ANALYZER_AVAILABLE = True
except ImportError as e:
    smart_tab_analyzer = None
    SMART_TAB_ANALYZER_AVAILABLE = False
    logging.getLogger(__name__).warning(f"Smart tab analyzer not available: {e}")


# ====================================================================================
# CONFIGURATION & CONSTANTS
# ====================================================================================

# Fuzzy matching thresholds
FUZZY_MATCH_THRESHOLD = 75
FUZZY_MATCH_SUBSTRING_MIN_LENGTH = 4
FUZZY_MATCH_REVERSE_SUBSTRING_MIN_LENGTH = 6

# Header detection constants
# Increased from 20 to 50 to handle files with titles/blanks above headers
# Can be overridden per-client via client_mapping_manager
HEADER_SCAN_MAX_ROWS = 100  # Increased from 50 to handle extreme cases
HEADER_NUMERIC_PENALTY_THRESHOLD = 0.4
HEADER_REPETITION_MAX_LENGTH = 30

# Scoring weights for header detection
class HeaderScore:
    """Scoring weights for header row detection"""
    EXACT_MATCH_CRITICAL = 10    # asset_id, description
    EXACT_MATCH_IMPORTANT = 7    # cost, dates
    EXACT_MATCH_NORMAL = 5       # other fields

    SUBSTRING_MATCH_CRITICAL = 6
    SUBSTRING_MATCH_IMPORTANT = 4
    SUBSTRING_MATCH_NORMAL = 2

    REVERSE_SUBSTRING_LONG = 2
    REVERSE_SUBSTRING_SHORT = 1

    EARLY_ROW_BONUS_TOP3 = 2
    EARLY_ROW_BONUS_TOP6 = 1

# Column mapping priorities
CRITICAL_FIELDS = ["asset_id", "description"]
IMPORTANT_FIELDS = ["acquisition_date", "in_service_date", "disposal_date", "cost"]
CATEGORY_LOCATION_FIELDS = ["category", "location", "department"]
OPTIONAL_FIELDS = ["method", "life", "transaction_type", "business_use_pct", "proceeds", "accumulated_depreciation", "section_179_taken", "bonus_taken", "net_book_value", "tax_life", "book_life", "tax_method", "book_method"]
TRANSFER_FIELDS = ["transfer_date", "from_location", "to_location", "from_department", "to_department", "transfer_type", "old_category"]

# Logging
logger = logging.getLogger(__name__)


# ====================================================================================
# DATA CLASSES
# ====================================================================================

@dataclass
class ColumnMapping:
    """Represents a column mapping with confidence score"""
    logical_name: str
    excel_column: str
    match_type: str  # "exact", "substring", "substring_reverse", "fuzzy"
    confidence: float

    def __repr__(self) -> str:
        return f"{self.logical_name} -> {self.excel_column} ({self.match_type}, {self.confidence:.2f})"


@dataclass
class SheetAnalysis:
    """Analysis results for a single Excel sheet"""
    sheet_name: str
    header_row: int  # Excel row number (1-indexed)
    total_rows: int
    detected_columns: Dict[str, str]
    column_mappings: List[ColumnMapping]
    all_columns: List[str]
    sheet_role: str
    warnings: List[str]

    @property
    def has_critical_columns(self) -> bool:
        """Check if critical columns (asset_id or description) were found"""
        return bool(self.detected_columns.get("asset_id") or self.detected_columns.get("description"))

    @property
    def has_dates(self) -> bool:
        """Check if any date columns were found"""
        return bool(
            self.detected_columns.get("acquisition_date") or
            self.detected_columns.get("in_service_date")
        )


class SheetRole(Enum):
    """Enumeration of sheet roles"""
    MAIN = "main"
    ADDITIONS = "additions"
    DISPOSALS = "disposals"
    TRANSFERS = "transfers"


# ====================================================================================
# HEADER DETECTION - Comprehensive mappings for all possible column names
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
        "asset details", "name", "title",
        # Specific
        "make/model", "make and model", "model", "type/description"
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
        "placed in service", "place in service", "pis date",
        "in service", "date in service", "date placed in service",
        # Variations
        "start date", "begin date", "commencement date",
        "depreciation start", "depreciation start date",
        # Specific
        "original in service date", "original service date",
        "date of service", "service"
    ],

    "location": [
        # Standard
        "location", "site", "facility", "plant", "branch",
        # Specific - REMOVED department/dept to avoid conflicts with Department column
        # "department", "dept", "division", "cost center",  # These should NOT be location
        "room", "building", "floor", "area",
        # Alternate
        "physical location", "asset location", "where located"
    ],

    # ADDED: Separate field for department (not location)
    "department": [
        "department", "dept", "division", "cost center",
        "business unit", "bu", "functional area"
    ],

    "disposal_date": [
        "disposal date", "dispose date", "date disposed",
        "sale date", "sold date", "date sold",
        "retirement date", "retired date", "date retired",
        "writeoff date", "date written off"
    ],

    "proceeds": [
        "proceeds", "sale proceeds", "sales price", "selling price",
        "disposal proceeds", "amount received"
    ],

    "method": [
        "method", "depreciation method", "depr method",
        "macrs method", "convention", "recovery method",
        # Variations with "deprec" spelling
        "deprec method", "tax deprec method", "book deprec method"
    ],

    "life": [
        "life", "useful life", "recovery period", "class life",
        "macrs life", "years", "depr life", "depreciation life",
        # Variations with years/yrs qualifiers (e.g., "Useful Life (Yrs) - Tax")
        "useful life yrs", "life yrs", "life years"
    ],

    # ==========================================================================
    # BOOK VS TAX SPECIFIC COLUMNS
    # ==========================================================================
    # Many client files have separate Book and Tax columns for life/method

    "tax_life": [
        "tax life", "useful life tax", "useful life yrs tax",
        "life tax", "tax useful life", "tax recovery period",
        "macrs life", "tax depreciation life", "tax depr life"
    ],

    "book_life": [
        "book life", "useful life book", "useful life yrs book",
        "life book", "book useful life", "book recovery period",
        "gaap life", "book depreciation life", "book depr life"
    ],

    "tax_method": [
        "tax method", "tax depreciation method", "tax depr method",
        "tax deprec method", "macrs method", "tax recovery method"
    ],

    "book_method": [
        "book method", "book depreciation method", "book depr method",
        "book deprec method", "gaap method", "book recovery method",
        "financial method"
    ],

    "transaction_type": [
        "transaction type", "trans type", "transaction", "type",
        "status", "action", "change type", "activity",
        "add/dispose", "a/d", "transaction code"
    ],

    "business_use_pct": [
        # Percentage formats
        "business use %", "business use percent", "business use percentage",
        "business %", "business pct", "business percent",
        # Usage formats
        "business use", "business usage", "% business use",
        "business use ratio", "business portion",
        # Tax specific
        "qualified business use", "qbu", "qbu %",
        "trade or business use", "business use test",
        # Listed property specific
        "listed property %", "listed property use",
        "personal use %", "business vs personal"
    ],

    "accumulated_depreciation": [
        "accumulated depreciation", "accum depreciation", "accum depr",
        "total depreciation", "depreciation taken", "depr taken",
        "accumulated depr", "acc depreciation", "acc depr",
        "total depr taken", "cumulative depreciation",
        # Common variations with Book/Tax qualifiers (e.g., "Accum. Deprec. (Book)")
        "accum deprec", "accum deprec book", "accum deprec tax",
        "accumulated deprec", "deprec book", "deprec tax"
    ],

    "section_179_taken": [
        "section 179 taken", "179 taken", "sec 179 taken",
        "section 179 deduction", "179 deduction",
        "historical 179", "prior 179"
    ],

    "bonus_taken": [
        "bonus taken", "bonus depreciation taken",
        "bonus depr taken", "historical bonus",
        "prior bonus", "bonus deduction"
    ],

    "net_book_value": [
        "net book value", "nbv", "book value", "net value",
        "carrying value", "carrying amount", "book amount",
        "net asset value", "current book value", "remaining value",
        "undepreciated value", "undepreciated cost",
        # Common variations with Book/Tax qualifiers (e.g., "NBV (Book)", "NBV (Tax)")
        "nbv book", "nbv tax", "book nbv", "tax nbv",
        "net book", "book net value"
    ],

    # ==========================================================================
    # TRANSFER-SPECIFIC COLUMNS
    # ==========================================================================

    "transfer_date": [
        "transfer date", "date transferred", "date of transfer",
        "xfer date", "relocation date", "reclass date",
        "reclassification date", "move date", "effective date"
    ],

    "from_location": [
        "from location", "source location", "old location",
        "prior location", "previous location", "transfer from",
        "from site", "from facility", "from plant", "from building"
    ],

    "to_location": [
        "to location", "destination location", "new location",
        "target location", "transfer to", "to site",
        "to facility", "to plant", "to building"
    ],

    "from_department": [
        "from department", "from dept", "source department",
        "old department", "prior department", "previous department",
        "from cost center", "from division", "from business unit"
    ],

    "to_department": [
        "to department", "to dept", "destination department",
        "new department", "target department", "to cost center",
        "to division", "to business unit"
    ],

    "transfer_type": [
        "transfer type", "type of transfer", "transfer reason",
        "reason for transfer", "transfer category", "reclass type",
        "reclassification type", "movement type"
    ],

    "old_category": [
        "old category", "prior category", "previous category",
        "from category", "source category", "old classification",
        "prior classification", "old asset class", "from class"
    ]
}


# ====================================================================================
# FUZZY HEADER MATCHING
# ====================================================================================

def _normalize_header(s: object) -> str:
    """
    Normalize header string for comparison

    Args:
        s: Header value (can be string, number, or any type)

    Returns:
        Normalized lowercase string with special chars removed
    """
    if pd.isna(s):
        return ""
    text = str(s).strip().lower()
    # Remove special characters but keep spaces
    text = re.sub(r'[^\w\s]', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _calculate_match_score(
    col_norm: str,
    keyword: str,
    logical: str
) -> Tuple[Optional[int], Optional[str]]:
    """
    Calculate match score for a column against a keyword

    Args:
        col_norm: Normalized column name
        keyword: Keyword to match against
        logical: Logical field name (for priority weighting)

    Returns:
        (score, match_type) tuple or (None, None) if no match
    """
    # PRIORITY 1: Exact match (after normalization)
    if keyword == col_norm:
        if logical in CRITICAL_FIELDS:
            return 100, "exact"
        elif logical in IMPORTANT_FIELDS:
            return 97, "exact"
        else:
            return 95, "exact"

    # PRIORITY 2: Substring match (keyword in column name)
    # Only allow if the keyword is meaningful (4+ chars)
    if len(keyword) >= FUZZY_MATCH_SUBSTRING_MIN_LENGTH:
        if keyword in col_norm:
            if logical in CRITICAL_FIELDS:
                return 90, "substring"
            elif logical in IMPORTANT_FIELDS:
                return 87, "substring"
            else:
                return 85, "substring"

        # Reverse substring (column name in keyword)
        # Be very careful - this can match "plant" in "plant"
        if col_norm in keyword:
            if len(col_norm) >= FUZZY_MATCH_REVERSE_SUBSTRING_MIN_LENGTH:
                return 80, "substring_reverse"
            else:
                return 70, "substring_reverse"

    # PRIORITY 3: Fuzzy match (using rapidfuzz)
    fuzzy_score = fuzz.ratio(keyword, col_norm)
    if fuzzy_score >= FUZZY_MATCH_THRESHOLD:
        return fuzzy_score, "fuzzy"

    return None, None


def _find_header_fuzzy(
    df: pd.DataFrame,
    logical: str,
    threshold: int = FUZZY_MATCH_THRESHOLD,
    exclude_cols: Optional[Set[str]] = None
) -> Optional[Tuple[str, ColumnMapping]]:
    """
    Find header column using fuzzy matching with confidence scoring

    Args:
        df: DataFrame with column headers
        logical: Logical field name (e.g., "asset_id", "description")
        threshold: Minimum fuzzy match score (default from config)
        exclude_cols: Set of columns to exclude from matching (already mapped)

    Returns:
        (column_name, ColumnMapping) tuple or None if no match found
    """
    keys = HEADER_KEYS.get(logical, [])
    if not keys:
        logger.warning(f"No keywords defined for logical field: {logical}")
        return None

    exclude_cols = exclude_cols or set()
    best_col = None
    best_score = 0
    best_match_type = None

    for col in df.columns:
        # Skip already mapped columns
        if col in exclude_cols:
            continue

        col_norm = _normalize_header(col)
        if not col_norm:
            continue

        # Try matching against all keywords for this logical field
        for keyword in keys:
            score, match_type = _calculate_match_score(col_norm, keyword, logical)

            if score is None:
                continue

            # Update if this is the best score so far
            if score > best_score:
                best_score = score
                best_col = col
                best_match_type = match_type

    if best_col is None or best_score < threshold:
        return None

    # Create ColumnMapping with confidence
    confidence = best_score / 100.0
    mapping = ColumnMapping(
        logical_name=logical,
        excel_column=best_col,
        match_type=best_match_type,
        confidence=confidence
    )

    return best_col, mapping


# ====================================================================================
# HEADER ROW DETECTION
# ====================================================================================

def _is_likely_data_row(row: pd.Series) -> bool:
    """
    Check if a row is likely a data row (not a header row)

    Args:
        row: DataFrame row to check

    Returns:
        True if row appears to be data (many numbers), False if likely header
    """
    numeric_count = 0
    text_count = 0

    for val in row:
        if pd.isna(val):
            continue

        # Check if value is numeric
        try:
            float(val)
            numeric_count += 1
        except (ValueError, TypeError):
            text_count += 1

    total = numeric_count + text_count
    if total == 0:
        return False  # Empty row

    # If more than 40% numeric, likely a data row
    return (numeric_count / total) > HEADER_NUMERIC_PENALTY_THRESHOLD


def _score_potential_header_row(row: pd.Series, row_index: int) -> float:
    """
    Score a row based on how likely it is to be a header row

    Args:
        row: DataFrame row to score
        row_index: 0-based index of the row

    Returns:
        Score (higher is better)
    """
    score = 0.0
    text_count = 0

    for val in row:
        if pd.isna(val):
            continue

        # Skip numeric values (headers are usually text)
        try:
            float(val)
            continue
        except (ValueError, TypeError):
            pass

        val_norm = _normalize_header(val)
        if not val_norm:
            continue

        text_count += 1
        matched = False

        # Check against all possible header keywords
        for logical, keywords in HEADER_KEYS.items():
            if matched:
                break

            for keyword in keywords:
                # Exact match (best)
                if keyword == val_norm:
                    if logical in CRITICAL_FIELDS:
                        score += HeaderScore.EXACT_MATCH_CRITICAL
                    elif logical in IMPORTANT_FIELDS:
                        score += HeaderScore.EXACT_MATCH_IMPORTANT
                    else:
                        score += HeaderScore.EXACT_MATCH_NORMAL
                    matched = True
                    break

                # Good substring match (keyword in value)
                # But only if keyword is meaningful (4+ chars)
                elif len(keyword) >= FUZZY_MATCH_SUBSTRING_MIN_LENGTH and keyword in val_norm:
                    if logical in CRITICAL_FIELDS:
                        score += HeaderScore.SUBSTRING_MATCH_CRITICAL
                    elif logical in IMPORTANT_FIELDS:
                        score += HeaderScore.SUBSTRING_MATCH_IMPORTANT
                    else:
                        score += HeaderScore.SUBSTRING_MATCH_NORMAL
                    matched = True
                    break

                # Reverse substring (value in keyword) - lower priority
                elif len(val_norm) >= FUZZY_MATCH_SUBSTRING_MIN_LENGTH and val_norm in keyword:
                    # Only give points if it's a strong match
                    if len(val_norm) >= FUZZY_MATCH_REVERSE_SUBSTRING_MIN_LENGTH:
                        score += HeaderScore.REVERSE_SUBSTRING_LONG
                    else:
                        score += HeaderScore.REVERSE_SUBSTRING_SHORT
                    matched = True
                    break

    # Penalize if row looks like data (many numbers)
    if _is_likely_data_row(row):
        score *= 0.3  # Heavy penalty

    # Slight preference for earlier rows (headers usually at top)
    if row_index <= 2:
        score += HeaderScore.EARLY_ROW_BONUS_TOP3
    elif row_index <= 5:
        score += HeaderScore.EARLY_ROW_BONUS_TOP6

    return score


def _detect_header_row(df_raw: pd.DataFrame, max_scan: int = HEADER_SCAN_MAX_ROWS) -> int:
    """
    Detect which row contains the headers using intelligent scoring

    Strategy:
    - Exact/near-exact keyword matches get high scores
    - Rows with many numeric values are penalized (likely data rows)
    - Earlier rows get slight preference (headers usually at top)

    Args:
        df_raw: Raw DataFrame (no headers set)
        max_scan: Maximum number of rows to scan (default 20)

    Returns:
        0-based index of the header row
    """
    best_idx = 0
    best_score = -1.0

    rows_to_scan = min(len(df_raw), max_scan)

    for i in range(rows_to_scan):
        row = df_raw.iloc[i]
        score = _score_potential_header_row(row, i)

        if score > best_score:
            best_score = score
            best_idx = i
            logger.debug(f"Row {i}: score={score:.2f} (new best)")
        else:
            logger.debug(f"Row {i}: score={score:.2f}")

    logger.info(f"Selected row {best_idx} as header (score={best_score:.2f})")
    return best_idx


def _detect_multi_row_headers(
    df_raw: pd.DataFrame,
    max_header_rows: int = 3
) -> Tuple[Optional[int], Optional[List[str]], bool]:
    """
    Detect if headers span multiple rows and combine them.

    Some Excel files have headers like:
        Row 1: "Asset"     "In Service"   "Original"
        Row 2: "Number"    "Date"         "Cost"

    This should be combined to: "Asset Number", "In Service Date", "Original Cost"

    Args:
        df_raw: Raw DataFrame without headers set
        max_header_rows: Maximum number of rows to consider as headers

    Returns:
        Tuple of (header_start_row, combined_headers, is_multi_row)
    """
    if len(df_raw) < 2:
        return None, None, False

    # Known multi-row header patterns (common in CPA Excel files)
    # These are patterns where two rows combine to form a complete header
    multi_row_patterns = {
        # (first_row_partial, second_row_partial) -> indicates valid multi-row
        ("asset", "number"): True,
        ("asset", "id"): True,
        ("asset", "#"): True,
        ("property", "number"): True,
        ("property", "id"): True,
        ("in service", "date"): True,
        ("in", "service"): True,
        ("placed in", "service"): True,
        ("placed", "in service"): True,
        ("original", "cost"): True,
        ("acquisition", "date"): True,
        ("acquisition", "cost"): True,
        ("property", "description"): True,
        ("asset", "description"): True,
        ("depreciation", "method"): True,
        ("recovery", "period"): True,
        ("useful", "life"): True,
        ("business", "use"): True,
        ("business use", "%"): True,
        ("disposal", "date"): True,
        ("sale", "proceeds"): True,
        ("net book", "value"): True,
        ("accumulated", "depreciation"): True,
        ("prior", "depreciation"): True,
        ("current", "depreciation"): True,
        ("tax", "life"): True,
        ("book", "life"): True,
    }

    # Try combining rows 0+1, 1+2, etc.
    for start_row in range(min(10, len(df_raw) - 1)):
        combined_headers = []
        match_count = 0

        row1 = df_raw.iloc[start_row]
        row2 = df_raw.iloc[start_row + 1]

        for col_idx in range(len(df_raw.columns)):
            val1 = str(row1.iloc[col_idx] if col_idx < len(row1) else "").strip().lower()
            val2 = str(row2.iloc[col_idx] if col_idx < len(row2) else "").strip().lower()

            # Skip if both are numeric (likely data rows)
            try:
                float(val1.replace(',', '').replace('$', ''))
                float(val2.replace(',', '').replace('$', ''))
                # Both are numeric - not header rows
                combined_headers.append(f"column_{col_idx}")
                continue
            except ValueError:
                pass

            # Combine the values
            combined = f"{val1} {val2}".strip()

            # Check against patterns
            for (part1, part2) in multi_row_patterns.keys():
                if part1 in val1 and part2 in val2:
                    match_count += 1
                    break

            # Use the non-empty value or combine
            if val1 and val2 and val1 != val2:
                combined_headers.append(combined)
            elif val1:
                combined_headers.append(val1)
            elif val2:
                combined_headers.append(val2)
            else:
                combined_headers.append(f"column_{col_idx}")

        # If we found 2+ pattern matches, this is likely a multi-row header
        if match_count >= 2:
            logger.info(f"Detected multi-row header at rows {start_row + 1}-{start_row + 2} ({match_count} patterns matched)")
            return start_row, combined_headers, True

    return None, None, False


# ====================================================================================
# SHEET ROLE DETECTION
# ====================================================================================

def _detect_sheet_role_from_name(sheet_name: str) -> Optional[SheetRole]:
    """
    Quick sheet role detection based on sheet name only.

    Used for early detection before column mapping to enable
    contextual column mapping (e.g., disposal sheets map cost → proceeds).

    Args:
        sheet_name: Name of the Excel sheet

    Returns:
        SheetRole enum or None if can't be determined from name alone
    """
    sheet_lower = sheet_name.lower()

    # Disposal indicators
    if any(kw in sheet_lower for kw in ["disposal", "disposed", "retire", "sold", "sale", "writeoff", "write-off"]):
        return SheetRole.DISPOSALS

    # Transfer indicators
    if any(kw in sheet_lower for kw in ["transfer", "xfer", "reclass", "reclassification"]):
        return SheetRole.TRANSFERS

    # Addition indicators
    if any(kw in sheet_lower for kw in ["addition", "purchase", "acquisition", "new"]):
        return SheetRole.ADDITIONS

    # Summary indicators
    if any(kw in sheet_lower for kw in ["summary", "totals", "rollforward", "roll-forward", "master"]):
        return SheetRole.SUMMARY

    return None


# ====================================================================================
# ====================================================================================

# ====================================================================================
# SHEET SKIP DETECTION - Skip Summary and Prior Year tabs
# ====================================================================================

# Patterns for sheets that should be SKIPPED
# NOTE: Be careful not to skip useful sheets like "FY 2024 2025" which contains roll-forward data
SHEET_SKIP_PATTERNS = [
    # Working/draft sheets only - NOT summary (too broad, matches useful roll-forward sheets)
    "reconciliation", "recon", "working", "draft", "temp", "scratch",
    "pivot", "chart", "graph",

    # Clear non-data sheets
    "table of contents", "toc", "cover", "instructions",

    # Historical archives
    "prior year", "prior years", "historical", "archive", "archived",
    "old data", "legacy",
]

# Fiscal year patterns that indicate PRIOR years (not current)
# These get matched against sheet names to detect prior year data
PRIOR_YEAR_PATTERNS = [
    r"fy\s*20[0-1]\d",           # FY 2019 and earlier
    r"fy\s*202[0-3](?!\s*202)",  # FY 2020-2023 (but not "FY 2023 2024")
    r"20[0-1]\d\s*-\s*20[0-1]\d", # 2010-2019 ranges
    r"20[0-1]\d\s+asset",        # "2019 assets"
    r"^20[0-1]\d$",              # Just "2019" as sheet name
    r"^20[0-2][0-3]$",           # Just "2020", "2021", "2022", "2023"
]


def _should_skip_sheet(sheet_name: str, target_tax_year: Optional[int] = None) -> Tuple[bool, str]:
    """
    Determine if a sheet should be skipped entirely.

    Skips:
    - Summary/overview sheets (contain totals, not asset data)
    - Prior year sheets (historical data)
    - Working/draft sheets

    Args:
        sheet_name: Name of the Excel sheet
        target_tax_year: The tax year being processed (e.g., 2024)

    Returns:
        Tuple of (should_skip, reason)
    """
    sheet_lower = sheet_name.lower().strip()

    # Check against skip patterns
    for pattern in SHEET_SKIP_PATTERNS:
        if pattern in sheet_lower:
            return True, f"Matches skip pattern: '{pattern}'"

    # Check for prior year patterns using regex
    for pattern in PRIOR_YEAR_PATTERNS:
        if re.search(pattern, sheet_lower):
            return True, f"Matches prior year pattern: '{pattern}'"

    # If we have a target tax year, check if sheet name contains older years
    if target_tax_year:
        # Look for year numbers in sheet name
        years_in_name = re.findall(r'20\d{2}', sheet_lower)
        if years_in_name:
            years = [int(y) for y in years_in_name]
            max_year = max(years)

            # If the highest year in the sheet name is older than target-1, skip it
            # (e.g., if target is 2025, skip sheets with only 2023 or earlier)
            if max_year < target_tax_year - 1:
                return True, f"Sheet year ({max_year}) is older than target year ({target_tax_year})"

    return False, ""


def _extract_fiscal_year_from_sheet(sheet_name: str) -> Optional[int]:
    """
    Extract fiscal year from sheet name.

    Handles patterns like:
    - "FY 2024 2025" -> 2025 (the ending year)
    - "FY 2024" -> 2024
    - "2024 Additions" -> 2024
    - "Disposals FY 2024 2025" -> 2025

    Args:
        sheet_name: Name of the Excel sheet

    Returns:
        Fiscal year as integer, or None if not found
    """
    sheet_lower = sheet_name.lower()

    # Pattern 1: "FY 2024 2025" or "FY2024-2025" -> return the ENDING year (2025)
    match = re.search(r'fy\s*(\d{4})\s*[-/]?\s*(\d{4})', sheet_lower)
    if match:
        return int(match.group(2))  # Return ending year

    # Pattern 2: "FY 2024" or "FY2024"
    match = re.search(r'fy\s*(\d{4})', sheet_lower)
    if match:
        return int(match.group(1))

    # Pattern 3: Just a year like "2024 additions" or "disposals 2024"
    match = re.search(r'(20\d{2})', sheet_lower)
    if match:
        return int(match.group(1))

    return None


def _is_date_in_fiscal_year(
    date_val,
    target_tax_year: int,
    fy_start_month: int = 1
) -> bool:
    """
    Check if a date falls within the target fiscal year.

    Handles both calendar year (Jan-Dec) and fiscal year (e.g., Apr-Mar).

    Args:
        date_val: Date value to check (can be string, datetime, or None)
        target_tax_year: The tax year (e.g., 2025)
        fy_start_month: First month of fiscal year (1=Jan/calendar, 4=Apr, 7=Jul, 10=Oct)

    Returns:
        True if date is within target fiscal year, False otherwise

    Examples:
        Calendar year (fy_start_month=1):
            target_tax_year=2025 -> Jan 1, 2025 to Dec 31, 2025

        Fiscal year Apr-Mar (fy_start_month=4):
            target_tax_year=2025 -> Apr 1, 2024 to Mar 31, 2025
            (FY 2024-2025 ends in calendar 2025)
    """
    if date_val is None or pd.isna(date_val):
        return False

    try:
        # Parse the date
        if isinstance(date_val, str):
            dt = pd.to_datetime(date_val, errors='coerce')
        else:
            dt = pd.to_datetime(date_val, errors='coerce')

        if pd.isna(dt):
            return False

        # Calculate fiscal year boundaries
        if fy_start_month == 1:
            # Calendar year: Jan 1 to Dec 31
            fy_start = pd.Timestamp(year=target_tax_year, month=1, day=1)
            fy_end = pd.Timestamp(year=target_tax_year, month=12, day=31)
        else:
            # Fiscal year: e.g., Apr 1, 2024 to Mar 31, 2025 for FY 2025
            # The fiscal year ENDS in the target_tax_year
            fy_start = pd.Timestamp(year=target_tax_year - 1, month=fy_start_month, day=1)
            # End is last day of month before fy_start_month in target_tax_year
            end_month = fy_start_month - 1 if fy_start_month > 1 else 12
            end_year = target_tax_year if fy_start_month > 1 else target_tax_year
            # Get last day of end month
            fy_end = pd.Timestamp(year=end_year, month=end_month, day=1) + pd.offsets.MonthEnd(0)

        return fy_start <= dt <= fy_end

    except Exception:
        return False


def _detect_sheet_role(sheet_name: str, df: pd.DataFrame) -> SheetRole:
    """
    Detect if sheet contains additions, disposals, or transfers

    Args:
        sheet_name: Name of the Excel sheet
        df: DataFrame with normalized columns

    Returns:
        SheetRole enum value
    """
    sheet_lower = sheet_name.lower()

    # Disposal patterns
    # NOTE: Removed "sale" and "sold" - too broad, matches "Sales", "Sales Rep", etc.
    # These caused FALSE POSITIVES where entire sheets of assets were marked as disposals
    # Individual row disposal detection still happens in transaction_classifier.py
    disposal_keywords = ["dispos", "retired", "writeoff", "write-off", "scrap"]
    for keyword in disposal_keywords:
        if keyword in sheet_lower:
            logger.info(f"Sheet '{sheet_name}' detected as DISPOSALS (keyword: {keyword})")
            return SheetRole.DISPOSALS

    # Transfer patterns
    transfer_keywords = ["transfer", "xfer", "reclass", "reclassification"]
    for keyword in transfer_keywords:
        if keyword in sheet_lower:
            logger.info(f"Sheet '{sheet_name}' detected as TRANSFERS (keyword: {keyword})")
            return SheetRole.TRANSFERS

    # Addition patterns
    # NOTE: Removed "add" - too broad, matches "address", "additional"
    # Use specific patterns to avoid false positives
    addition_keywords = ["additions", "new asset", "new purchase", "acquisitions"]
    for keyword in addition_keywords:
        if keyword in sheet_lower:
            logger.info(f"Sheet '{sheet_name}' detected as ADDITIONS (keyword: {keyword})")
            return SheetRole.ADDITIONS

    # NOTE: REMOVED the check for disposal_date column existence
    # Having a disposal_date column does NOT mean all rows are disposals
    # Many systems have this column for ALL assets (empty for non-disposed)
    # Individual row disposal detection happens in transaction_classifier.py based on:
    # - Disposal Date being POPULATED (not just column existing)
    # - Transaction Type column value
    # - Description keywords

    # Default to main
    logger.info(f"Sheet '{sheet_name}' detected as MAIN (default)")
    return SheetRole.MAIN


# ====================================================================================
# TRANSACTION TYPE DETECTION
# ====================================================================================

def _detect_transaction_type(
    row: pd.Series,
    description_col: Optional[str],
    cost_col: Optional[str],
    transaction_type_col: Optional[str] = None,
    disposal_date_col: Optional[str] = None
) -> str:
    """
    Detect transaction type from row data

    Args:
        row: DataFrame row
        description_col: Name of description column
        cost_col: Name of cost column
        transaction_type_col: Name of transaction type column (if present)
        disposal_date_col: Name of disposal date column (if present)

    Returns:
        Transaction type: "addition", "disposal", "transfer"
    """
    # First, check explicit transaction type column if present
    if transaction_type_col:
        trans_val = str(row.get(transaction_type_col, "")).lower().strip()
        if trans_val:
            # Check for disposal indicators
            # NOTE: Removed "delete" (matches "delete key"), "sale" (matches "sales")
            if any(x in trans_val for x in ["dispos", "sold", "retire", "scrap", "writeoff"]):
                return "disposal"
            # Check for transfer indicators
            # NOTE: Removed "move" (matches "removal", "movement"), "relocate" (too broad)
            if any(x in trans_val for x in ["transfer", "xfer", "reclass"]):
                return "transfer"
            # Check for addition indicators
            # NOTE: Removed "add" (matches "address", "additional")
            if any(x in trans_val for x in ["addition", "new asset", "purchase", "acquisition"]):
                return "addition"

    # Check if disposal date is present (strong indicator of disposal)
    if disposal_date_col:
        disposal_val = row.get(disposal_date_col)
        if disposal_val and not pd.isna(disposal_val):
            return "disposal"

    # Check description for transaction type indicators
    if description_col:
        desc = str(row.get(description_col, "")).lower()

        # Check for disposal indicators
        disposal_words = ["disposed", "sold", "retired", "scrapped", "writeoff", "write-off", "disposal"]
        for word in disposal_words:
            if word in desc:
                return "disposal"

        # Check for transfer indicators
        transfer_words = ["transfer", "xfer", "reclass", "reclassify", "reclassification", "moved", "relocated"]
        for word in transfer_words:
            if word in desc:
                return "transfer"

    # Check for negative cost (disposal)
    if cost_col:
        try:
            cost = parse_number(row.get(cost_col))
            if cost and cost < 0:
                return "disposal"
        except (ValueError, TypeError) as e:
            logger.debug(f"Error parsing cost for transaction type detection: {e}")

    # Default to addition
    return "addition"


# ====================================================================================
# DATA CLEANING & VALIDATION
# ====================================================================================

def _is_header_repetition(desc: str) -> bool:
    """
    Check if a description value is actually a repeated header

    Args:
        desc: Description string to check

    Returns:
        True if this appears to be a header row that slipped through
    """
    desc_lower = desc.lower()
    header_keywords = ["description", "asset description", "property", "item", "equipment"]

    if any(keyword in desc_lower for keyword in header_keywords):
        if len(desc) < HEADER_REPETITION_MAX_LENGTH:
            return True

    return False


# Keywords that indicate a totals/summary row (not actual asset data)
TOTALS_ROW_KEYWORDS = [
    "total", "subtotal", "sub-total", "sub total",
    "grand total", "balance", "net", "sum",
    "category total", "class total", "group total",
    "carried forward", "brought forward", "b/f", "c/f",
    "ending balance", "beginning balance",
    "summary", "totals", "accumulated"
]


def _is_totals_row(desc: str, asset_id: str = "") -> bool:
    """
    Check if a row is a totals/summary row that should be skipped.

    Many Excel files have totals rows that should not be imported as assets.
    These rows typically have keywords like "Total", "Subtotal", "Balance" etc.

    Args:
        desc: Description string to check
        asset_id: Asset ID to check (totals rows often have empty or special IDs)

    Returns:
        True if this appears to be a totals row
    """
    if not desc:
        return False

    desc_lower = desc.lower().strip()

    # Check for exact matches or keyword presence
    for keyword in TOTALS_ROW_KEYWORDS:
        # Check if description starts with or contains the totals keyword
        if desc_lower.startswith(keyword) or f" {keyword}" in f" {desc_lower}":
            # Additional check: totals rows are usually short-to-medium length
            # Increased from 50 to 80 to catch "Total for Manufacturing Equipment Department"
            if len(desc) < 80:
                logger.debug(f"Skipping totals row: {desc}")
                return True

    # Check for pattern like "Total - Category Name" or "Total: Equipment"
    if re.match(r'^(total|subtotal|sum)\s*[-:]\s*', desc_lower):
        return True

    # Check for pattern like "*** TOTAL ***" or "=== SUBTOTAL ==="
    if re.match(r'^[\*\=\-\s]*(total|subtotal)[\*\=\-\s]*$', desc_lower):
        return True

    return False


def _clean_row_data(row: pd.Series, col_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Clean and validate a single row

    Args:
        row: DataFrame row
        col_map: Dictionary mapping logical field names to Excel column names

    Returns:
        Dictionary with cleaned data or None if row should be skipped
    """
    asset_id = str(row.get(col_map.get("asset_id"), "")).strip() if col_map.get("asset_id") else ""
    desc_raw = str(row.get(col_map.get("description"), "")).strip() if col_map.get("description") else ""

    # Skip completely empty rows
    if not asset_id and not desc_raw:
        return None

    # Skip header repetitions (Excel sometimes repeats headers)
    if _is_header_repetition(desc_raw):
        logger.debug(f"Skipping header repetition: {desc_raw}")
        return None

    # Skip totals/summary rows (not actual asset data)
    if _is_totals_row(desc_raw, asset_id):
        return None

    # Fix typos in description
    description = typo_engine.correct_description(desc_raw) if desc_raw else ""

    # Category
    category = ""
    if col_map.get("category"):
        cat_raw = row.get(col_map["category"], "")
        if pd.notna(cat_raw):
            category = typo_engine.correct_category(str(cat_raw))

    # Cost
    cost = None
    if col_map.get("cost"):
        try:
            cost = parse_number(row[col_map["cost"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing cost: {e}")

    # Dates
    acq_date = None
    if col_map.get("acquisition_date"):
        try:
            acq_date = parse_date(row[col_map["acquisition_date"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing acquisition date: {e}")

    pis_date = None
    if col_map.get("in_service_date"):
        try:
            pis_date = parse_date(row[col_map["in_service_date"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing in-service date: {e}")

    disposal_date = None
    if col_map.get("disposal_date"):
        try:
            disposal_date = parse_date(row[col_map["disposal_date"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing disposal date: {e}")

    # Location
    location = ""
    if col_map.get("location"):
        loc_val = row.get(col_map["location"], "")
        if pd.notna(loc_val):
            location = str(loc_val).strip()

    # Department (NEW - was missing from output!)
    department = ""
    if col_map.get("department"):
        dept_val = row.get(col_map["department"], "")
        if pd.notna(dept_val):
            department = str(dept_val).strip()

    # Business use percentage
    business_use_pct = None
    if col_map.get("business_use_pct"):
        try:
            pct_val = parse_number(row[col_map["business_use_pct"]])
            if pct_val is not None:
                # Convert to decimal if percentage (e.g., 100 -> 1.0)
                if pct_val > 1:
                    pct_val = pct_val / 100.0
                business_use_pct = pct_val
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing business use %: {e}")

    # Proceeds
    proceeds = None
    if col_map.get("proceeds"):
        try:
            proceeds = parse_number(row[col_map["proceeds"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing proceeds: {e}")

    # Accumulated Depreciation (for disposals)
    accumulated_depreciation = None
    if col_map.get("accumulated_depreciation"):
        try:
            accumulated_depreciation = parse_number(row[col_map["accumulated_depreciation"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing accumulated depreciation: {e}")

    # Section 179 Taken (Historical, for disposals)
    section_179_taken = None
    if col_map.get("section_179_taken"):
        try:
            section_179_taken = parse_number(row[col_map["section_179_taken"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing section 179 taken: {e}")

    # Bonus Taken (Historical, for disposals)
    bonus_taken = None
    if col_map.get("bonus_taken"):
        try:
            bonus_taken = parse_number(row[col_map["bonus_taken"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing bonus taken: {e}")

    # Net Book Value
    net_book_value = None
    if col_map.get("net_book_value"):
        try:
            net_book_value = parse_number(row[col_map["net_book_value"]])
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing net book value: {e}")

    # ==========================================================================
    # BOOK VS TAX SPECIFIC COLUMNS
    # ==========================================================================
    # Extract Tax Life (prefer tax_life, fallback to generic life)
    tax_life = None
    if col_map.get("tax_life"):
        try:
            val = row.get(col_map["tax_life"], "")
            if pd.notna(val) and str(val).strip():
                tax_life = parse_number(str(val))
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing tax life: {e}")
    elif col_map.get("life"):
        # Fallback to generic life column
        try:
            val = row.get(col_map["life"], "")
            if pd.notna(val) and str(val).strip():
                tax_life = parse_number(str(val))
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing life: {e}")

    # Extract Book Life
    book_life = None
    if col_map.get("book_life"):
        try:
            val = row.get(col_map["book_life"], "")
            if pd.notna(val) and str(val).strip():
                book_life = parse_number(str(val))
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Error parsing book life: {e}")

    # Extract Tax Method (prefer tax_method, fallback to generic method)
    tax_method = None
    if col_map.get("tax_method"):
        val = row.get(col_map["tax_method"], "")
        if pd.notna(val) and str(val).strip():
            tax_method = str(val).strip()
    elif col_map.get("method"):
        # Fallback to generic method column
        val = row.get(col_map["method"], "")
        if pd.notna(val) and str(val).strip():
            tax_method = str(val).strip()

    # Extract Book Method
    book_method = None
    if col_map.get("book_method"):
        val = row.get(col_map["book_method"], "")
        if pd.notna(val) and str(val).strip():
            book_method = str(val).strip()

    return {
        "asset_id": asset_id,
        "description": description,
        "client_category": category,
        "cost": cost,
        "acquisition_date": acq_date,
        "in_service_date": pis_date,
        "disposal_date": disposal_date,
        "location": location,
        "department": department,  # NOW INCLUDED!
        "business_use_pct": business_use_pct,
        "proceeds": proceeds,
        "accumulated_depreciation": accumulated_depreciation,
        "section_179_taken": section_179_taken,
        "bonus_taken": bonus_taken,
        "net_book_value": net_book_value,
        # Book vs Tax specific
        "tax_life": tax_life,
        "book_life": book_life,
        "tax_method": tax_method,
        "book_method": book_method,
    }


# ====================================================================================
# COLUMN MAPPING WITH VALIDATION
# ====================================================================================

def _map_columns_with_validation(
    df: pd.DataFrame,
    sheet_name: str,
    client_mappings: Optional[Dict[str, str]] = None,
    additional_keywords: Optional[Dict[str, List[str]]] = None,
    sheet_role: Optional[str] = None
) -> Tuple[Dict[str, str], List[ColumnMapping], List[str]]:
    """
    Map Excel columns to logical fields with validation and warnings.

    Includes contextual matching based on sheet role:
    - DISPOSALS sheets: Unmapped cost-like columns map to 'proceeds'
    - TRANSFERS sheets: Location columns get special handling for from/to
    - ADDITIONS sheets: Standard processing

    Args:
        df: DataFrame with normalized column headers
        sheet_name: Name of the sheet (for logging)
        client_mappings: Optional dict of logical_field -> excel_column from client config
        additional_keywords: Optional dict of logical_field -> [keywords] to extend detection
        sheet_role: Optional sheet role (DISPOSALS, ADDITIONS, TRANSFERS, etc.) for contextual mapping

    Returns:
        Tuple of (col_map dict, column_mappings list, warnings list)
    """
    col_map: Dict[str, str] = {}
    column_mappings: List[ColumnMapping] = []
    warnings_list: List[str] = []
    mapped_cols: Set[str] = set()

    # STEP 1: Apply client-specific mappings first (highest priority)
    if client_mappings:
        for logical, excel_col in client_mappings.items():
            excel_col_norm = _normalize_header(excel_col)
            # Check if this column exists in the dataframe
            if excel_col_norm in [_normalize_header(c) for c in df.columns]:
                # Find the actual column name (preserving original casing)
                for col in df.columns:
                    if _normalize_header(col) == excel_col_norm:
                        col_map[logical] = col
                        mapped_cols.add(col)
                        column_mappings.append(ColumnMapping(
                            logical_name=logical,
                            excel_column=col,
                            match_type="client_override",
                            confidence=1.0
                        ))
                        logger.info(f"[{sheet_name}] Client mapping: {logical} -> {col}")
                        break

    # STEP 2: Extend HEADER_KEYS with additional keywords if provided
    extended_header_keys = dict(HEADER_KEYS)
    if additional_keywords:
        for field, keywords in additional_keywords.items():
            if field in extended_header_keys:
                # Add new keywords without duplicates
                existing = set(extended_header_keys[field])
                for kw in keywords:
                    if kw.lower() not in existing:
                        extended_header_keys[field] = list(extended_header_keys[field]) + [kw.lower()]

    # Define priority groups
    priority_groups = [
        CRITICAL_FIELDS,
        IMPORTANT_FIELDS,
        CATEGORY_LOCATION_FIELDS,
        OPTIONAL_FIELDS,
        TRANSFER_FIELDS
    ]

    # STEP 3: Auto-detect remaining fields in priority order
    for priority_group in priority_groups:
        for logical in priority_group:
            # Skip if already mapped by client config
            if logical in col_map:
                continue

            result = _find_header_fuzzy(df, logical, exclude_cols=mapped_cols)
            if result:
                col, mapping = result
                col_map[logical] = col
                column_mappings.append(mapping)
                mapped_cols.add(col)

                # Debug logging
                if os.getenv("DEBUG_COLUMN_MAPPING"):
                    logger.debug(f"[{sheet_name}] {mapping}")

    # Validation: Check for critical columns
    if not col_map.get("description"):
        # Try even more lenient matching for description
        for col in df.columns:
            if col in mapped_cols:
                continue
            col_text = str(col).lower()
            if any(keyword in col_text for keyword in ["desc", "property", "item", "equipment"]):
                # Avoid matching "department" as description
                if "depart" not in col_text and "dept" not in col_text:
                    col_map["description"] = col
                    mapped_cols.add(col)
                    warnings_list.append(f"Description column found with lenient matching: {col}")
                    logger.warning(f"[{sheet_name}] Description found with lenient matching: {col}")
                    break

    # Check for missing critical columns
    if not col_map.get("asset_id"):
        warnings_list.append("Asset ID column not found - row numbers may be used")
        logger.warning(f"[{sheet_name}] No Asset ID column found")

    if not col_map.get("description"):
        warnings_list.append("CRITICAL: Description column not found - sheet may be skipped")
        logger.error(f"[{sheet_name}] No Description column found")

    # Check for missing important columns
    if not col_map.get("cost"):
        warnings_list.append("Cost column not found - cost data will be missing")
        logger.warning(f"[{sheet_name}] No Cost column found")

    if not col_map.get("in_service_date"):
        warnings_list.append("In-Service Date column not found - transaction classification may fail")
        logger.warning(f"[{sheet_name}] No In-Service Date column found")

    # =========================================================================
    # FALLBACK: Generic "Date" column detection
    # =========================================================================
    # CPAs often receive client schedules with just "Date" column instead of
    # specific "In Service Date" or "Acquisition Date". If no date columns
    # were detected, try to find a generic "Date" column and use it.
    # Priority: in_service_date > acquisition_date (most common CPA use case)
    if not col_map.get("in_service_date") and not col_map.get("acquisition_date"):
        for col in df.columns:
            if col in mapped_cols:
                continue
            col_text = str(col).lower().strip()
            # Match columns that are exactly "date" or very close
            # Avoid matching "disposal date", "update date", etc.
            if col_text == "date" or col_text == "dt" or col_text == "dates":
                # Verify it contains date-like data
                sample_values = df[col].dropna().head(5)
                if len(sample_values) > 0:
                    date_count = 0
                    for val in sample_values:
                        if pd.notna(val):
                            # Check if value is date-like
                            if isinstance(val, (pd.Timestamp, datetime)):
                                date_count += 1
                            else:
                                try:
                                    pd.to_datetime(val)
                                    date_count += 1
                                except:
                                    pass
                    # If most values are dates, use this column
                    if date_count >= len(sample_values) * 0.5:
                        col_map["in_service_date"] = col
                        mapped_cols.add(col)
                        column_mappings.append(ColumnMapping(
                            logical_name="in_service_date",
                            excel_column=col,
                            match_type="fallback_generic_date",
                            confidence=0.7
                        ))
                        # Remove the warning we just added
                        warnings_list = [w for w in warnings_list if "In-Service Date column not found" not in w]
                        warnings_list.append(f"Using generic 'Date' column as In-Service Date: {col}")
                        logger.info(f"[{sheet_name}] Fallback: Using '{col}' as In-Service Date")
                        break

    # =========================================================================
    # CONTEXTUAL MATCHING: Sheet-role-aware column mapping
    # =========================================================================
    # This is critical for CPA workflows where disposal sheets have "Amount" or
    # "Cost" columns that should map to "proceeds", not "cost"

    if sheet_role:
        sheet_role_lower = str(sheet_role).lower()

        # DISPOSAL SHEETS: Map unmapped amount columns to 'proceeds'
        if "disposal" in sheet_role_lower or "retired" in sheet_role_lower or "sold" in sheet_role_lower:
            # If we have cost but not proceeds, look for another amount-like column
            if col_map.get("cost") and not col_map.get("proceeds"):
                proceeds_keywords = ["amount", "value", "price", "proceeds", "sale", "sold"]
                for col in df.columns:
                    if col in mapped_cols:
                        continue
                    col_lower = str(col).lower()
                    # Check for proceeds-like column names (excluding the one mapped to cost)
                    if any(kw in col_lower for kw in proceeds_keywords):
                        # Verify it contains numeric data
                        sample = df[col].dropna().head(5)
                        numeric_count = sum(1 for v in sample if _is_numeric_value(v))
                        if numeric_count >= len(sample) * 0.5:
                            col_map["proceeds"] = col
                            mapped_cols.add(col)
                            column_mappings.append(ColumnMapping(
                                logical_name="proceeds",
                                excel_column=col,
                                match_type="contextual_disposal",
                                confidence=0.75
                            ))
                            logger.info(f"[{sheet_name}] Contextual: Disposal sheet - '{col}' mapped to proceeds")
                            break

            # If we don't have cost but have a numeric column, in disposal context it's likely proceeds
            elif not col_map.get("cost") and not col_map.get("proceeds"):
                for col in df.columns:
                    if col in mapped_cols:
                        continue
                    col_lower = str(col).lower()
                    # Skip clearly non-monetary columns
                    if any(skip in col_lower for skip in ["date", "life", "year", "method", "id", "number"]):
                        continue
                    # Check for numeric data
                    sample = df[col].dropna().head(5)
                    if len(sample) == 0:
                        continue
                    numeric_count = sum(1 for v in sample if _is_numeric_value(v))
                    if numeric_count >= len(sample) * 0.6:
                        # In disposal context, map to proceeds rather than cost
                        col_map["proceeds"] = col
                        mapped_cols.add(col)
                        column_mappings.append(ColumnMapping(
                            logical_name="proceeds",
                            excel_column=col,
                            match_type="contextual_disposal_inference",
                            confidence=0.65
                        ))
                        logger.info(f"[{sheet_name}] Contextual: Disposal sheet inferred '{col}' as proceeds")
                        break

        # TRANSFER SHEETS: Handle from/to location columns
        elif "transfer" in sheet_role_lower or "reclass" in sheet_role_lower:
            location_cols = []
            for col in df.columns:
                if col in mapped_cols:
                    continue
                col_lower = str(col).lower()
                if any(kw in col_lower for kw in ["location", "from", "to", "old", "new", "dept", "department"]):
                    location_cols.append(col)

            # If we have exactly 2 location-like columns, assign from/to
            if len(location_cols) >= 2:
                # Try to identify which is "from" and which is "to"
                from_col = None
                to_col = None
                for col in location_cols:
                    col_lower = str(col).lower()
                    if "from" in col_lower or "old" in col_lower or "prior" in col_lower:
                        from_col = col
                    elif "to" in col_lower or "new" in col_lower:
                        to_col = col

                if from_col and not col_map.get("from_location"):
                    col_map["from_location"] = from_col
                    mapped_cols.add(from_col)
                    column_mappings.append(ColumnMapping(
                        logical_name="from_location",
                        excel_column=from_col,
                        match_type="contextual_transfer",
                        confidence=0.75
                    ))
                    logger.info(f"[{sheet_name}] Contextual: Transfer sheet - '{from_col}' mapped to from_location")

                if to_col and not col_map.get("to_location"):
                    col_map["to_location"] = to_col
                    mapped_cols.add(to_col)
                    column_mappings.append(ColumnMapping(
                        logical_name="to_location",
                        excel_column=to_col,
                        match_type="contextual_transfer",
                        confidence=0.75
                    ))
                    logger.info(f"[{sheet_name}] Contextual: Transfer sheet - '{to_col}' mapped to to_location")

    # =========================================================================
    # DATA-TYPE INFERENCE FALLBACK: For critical unmapped columns
    # =========================================================================
    # If description is still missing, try to find a text column with asset-like data

    if not col_map.get("description"):
        for col in df.columns:
            if col in mapped_cols:
                continue
            sample = df[col].dropna().head(10)
            if len(sample) == 0:
                continue

            # Check if column contains text descriptions (not pure numbers, has length)
            text_count = 0
            for val in sample:
                if pd.notna(val):
                    s = str(val).strip()
                    # Description: not pure numbers, has some length, contains letters
                    if len(s) >= 5 and not s.replace(',', '').replace('.', '').replace('-', '').isdigit():
                        if any(c.isalpha() for c in s):
                            text_count += 1

            if text_count >= len(sample) * 0.6:
                col_map["description"] = col
                mapped_cols.add(col)
                column_mappings.append(ColumnMapping(
                    logical_name="description",
                    excel_column=col,
                    match_type="data_inference",
                    confidence=0.60
                ))
                # Remove critical warning
                warnings_list = [w for w in warnings_list if "CRITICAL: Description column not found" not in w]
                warnings_list.append(f"Description inferred from data patterns: {col}")
                logger.info(f"[{sheet_name}] Data inference: '{col}' inferred as description")
                break

    # If cost is still missing, try to find a currency column
    if not col_map.get("cost"):
        for col in df.columns:
            if col in mapped_cols:
                continue
            sample = df[col].dropna().head(10)
            if len(sample) == 0:
                continue

            currency_count = 0
            for val in sample:
                if _is_numeric_value(val):
                    # Check if it looks like currency (has $ or large number)
                    s = str(val).strip()
                    if '$' in s or ',' in s:
                        currency_count += 1
                    else:
                        try:
                            num = float(s.replace(',', ''))
                            if abs(num) >= 100:  # Large numbers likely cost
                                currency_count += 1
                        except:
                            pass

            if currency_count >= len(sample) * 0.5:
                col_map["cost"] = col
                mapped_cols.add(col)
                column_mappings.append(ColumnMapping(
                    logical_name="cost",
                    excel_column=col,
                    match_type="data_inference",
                    confidence=0.60
                ))
                # Remove warning
                warnings_list = [w for w in warnings_list if "Cost column not found" not in w]
                warnings_list.append(f"Cost inferred from data patterns: {col}")
                logger.info(f"[{sheet_name}] Data inference: '{col}' inferred as cost")
                break

    return col_map, column_mappings, warnings_list


def _is_numeric_value(val) -> bool:
    """Check if a value is numeric (for data-type inference)."""
    if pd.isna(val) or val == "":
        return False
    try:
        s = str(val).strip()
        # Remove currency symbols and commas
        s = s.replace('$', '').replace(',', '').replace('(', '-').replace(')', '')
        float(s)
        return True
    except (ValueError, TypeError):
        return False


# ====================================================================================
# MAIN SHEET LOADER
# ====================================================================================

def build_unified_dataframe(
    sheets: Dict[str, pd.DataFrame],
    target_tax_year: Optional[int] = None,
    fy_start_month: int = 1,
    filter_by_date: bool = True,
    client_id: Optional[str] = None
) -> pd.DataFrame:
    """
    Build unified dataframe from multiple Excel sheets

    Handles diverse formats, multiple sheets, various column names with
    intelligent detection and comprehensive validation.

    SMART FILTERING:
    1. Sheet-level: Skips working/draft sheets, prior year archives
    2. Row-level: Only includes rows with dates in the target fiscal year
       (dramatically reduces data when category tabs have years of history)

    CLIENT-SPECIFIC MAPPINGS:
    When client_id is provided, the function will:
    1. Load client-specific column mappings from config
    2. Apply these mappings before auto-detection (highest priority)
    3. Use any additional keywords defined for this client

    Args:
        sheets: Dict of sheet_name -> DataFrame (header=None)
        target_tax_year: The tax year being processed (e.g., 2025). Used for
                        both sheet-level and row-level filtering.
        fy_start_month: First month of fiscal year (1=Jan/calendar, 4=Apr, 7=Jul, 10=Oct)
                       For "FY 2024 2025" (Apr-Mar), use fy_start_month=4
        filter_by_date: If True, only include rows with dates in target fiscal year.
                       Set to False to load all rows regardless of date.
        client_id: Optional client identifier for client-specific column mappings.
                  If provided, mappings from client_input_mappings.json will be used.

    Returns:
        Unified DataFrame with standardized column names

    Raises:
        ValueError: If no valid sheets found or critical errors occur

    Example:
        For a client with FY Apr-Mar and tax year 2025:
        - fy_start_month=4, target_tax_year=2025
        - Includes: Apr 1, 2024 to Mar 31, 2025
        - Filters out: All rows with dates before Apr 2024 or after Mar 2025
    """
    if not sheets:
        raise ValueError("No sheets provided")

    all_rows = []
    processed_sheets = 0
    skipped_sheets = 0
    skipped_sheet_reasons = []
    rows_filtered_by_date = 0  # Track how many rows filtered out by date

    # Load client-specific mappings if client_id provided
    client_col_mappings: Dict[str, str] = {}
    additional_keywords: Dict[str, List[str]] = {}
    client_skip_sheets: List[str] = []
    client_header_row: Optional[int] = None

    if client_id:
        manager = client_mapping_manager.get_manager()
        client_col_mappings = manager.get_column_mapping(client_id)
        additional_keywords = manager.get_additional_keywords()
        client_skip_sheets = manager.get_skip_sheets(client_id)
        client_header_row = manager.get_header_row(client_id)

        if client_col_mappings:
            logger.info(f"Using client '{client_id}' mappings: {len(client_col_mappings)} column overrides")
        if client_header_row:
            logger.info(f"Using client '{client_id}' header row: {client_header_row}")
    else:
        # Still load additional keywords from default config
        manager = client_mapping_manager.get_manager()
        additional_keywords = manager.get_additional_keywords()

    # Log fiscal year info
    if fy_start_month == 1:
        fy_desc = f"Calendar Year {target_tax_year}"
    else:
        month_names = {1: 'Jan', 4: 'Apr', 7: 'Jul', 10: 'Oct'}
        fy_desc = f"FY {target_tax_year - 1}-{target_tax_year} ({month_names.get(fy_start_month, str(fy_start_month))}-{month_names.get((fy_start_month - 1) % 12 or 12, '')})"

    logger.info(f"Processing {len(sheets)} Excel sheets")
    logger.info(f"Target: {fy_desc}, Date filtering: {'ON' if filter_by_date else 'OFF'}")

    for sheet_name, df_raw in sheets.items():
        logger.info(f"Processing sheet: {sheet_name}")

        # SMART SKIP: Check if sheet should be skipped entirely
        should_skip, skip_reason = _should_skip_sheet(sheet_name, target_tax_year)
        if should_skip:
            logger.info(f"⏭️  Skipping sheet '{sheet_name}': {skip_reason}")
            skipped_sheet_reasons.append(f"'{sheet_name}': {skip_reason}")
            skipped_sheets += 1
            continue

        # CLIENT-SPECIFIC SKIP: Check client's skip_sheets patterns
        if client_skip_sheets:
            import fnmatch
            sheet_lower = sheet_name.lower()
            skip_this_sheet = False
            for pattern in client_skip_sheets:
                if fnmatch.fnmatch(sheet_lower, pattern.lower()):
                    logger.info(f"⏭️  Skipping sheet '{sheet_name}': Client skip pattern '{pattern}'")
                    skipped_sheet_reasons.append(f"'{sheet_name}': Client skip pattern")
                    skipped_sheets += 1
                    skip_this_sheet = True
                    break
            if skip_this_sheet:
                continue

        if df_raw is None or df_raw.empty:
            logger.warning(f"Skipping empty sheet: {sheet_name}")
            skipped_sheets += 1
            continue

        try:
            # STEP 1: Detect sheet role FIRST (for contextual column mapping)
            # Pre-detect role from sheet name before we have column data
            sheet_role = _detect_sheet_role_from_name(sheet_name)
            logger.debug(f"[{sheet_name}] Initial sheet role from name: {sheet_role}")

            # STEP 2: Detect header row (use client override if provided)
            if client_header_row is not None:
                header_idx = client_header_row - 1  # Convert to 0-indexed
                logger.info(f"[{sheet_name}] Using client-specified header row: {client_header_row}")
                use_multi_row = False
            else:
                header_idx = _detect_header_row(df_raw, max_scan=HEADER_SCAN_MAX_ROWS)
                use_multi_row = False

            # Extract data starting from header
            df = df_raw.iloc[header_idx:].copy()

            # SAFETY: Check for empty DataFrame after header extraction
            if df.empty or len(df) < 1:
                logger.warning(f"[{sheet_name}] No data rows after header detection at row {header_idx}")
                skipped_sheets += 1
                skipped_sheet_reasons.append(f"'{sheet_name}': No data rows after header")
                continue

            # Set column names from header row
            df.columns = [_normalize_header(x) for x in df.iloc[0]]

            # Handle duplicate column names from merged cells (NaN → "" → duplicates)
            # Pandas will auto-rename duplicates to "col", "col.1", "col.2" etc.
            seen_cols = {}
            new_cols = []
            for col in df.columns:
                if col in seen_cols:
                    seen_cols[col] += 1
                    new_cols.append(f"{col}_{seen_cols[col]}" if col else f"unnamed_{seen_cols[col]}")
                else:
                    seen_cols[col] = 0
                    new_cols.append(col if col else "unnamed_0")
            df.columns = new_cols

            df = df.iloc[1:].reset_index(drop=True)

            logger.info(f"[{sheet_name}] Header detected at row {header_idx}, {len(df)} data rows")

            # STEP 3: Map columns with validation (using client mappings and sheet role)
            col_map, column_mappings, warnings_list = _map_columns_with_validation(
                df, sheet_name,
                client_mappings=client_col_mappings,
                additional_keywords=additional_keywords,
                sheet_role=sheet_role.value if sheet_role else None
            )

            # STEP 3b: MULTI-ROW HEADER FALLBACK
            # If critical columns not found, try multi-row header detection
            if not col_map.get("description") or not col_map.get("cost"):
                multi_start, multi_headers, is_multi = _detect_multi_row_headers(df_raw)

                if is_multi and multi_headers:
                    logger.info(f"[{sheet_name}] Trying multi-row header detection...")
                    # Rebuild DataFrame with combined headers
                    df_multi = df_raw.iloc[multi_start + 2:].copy()  # Skip both header rows
                    df_multi.columns = [_normalize_header(h) for h in multi_headers]
                    df_multi = df_multi.reset_index(drop=True)

                    # Re-run column mapping with combined headers
                    col_map_multi, mappings_multi, warnings_multi = _map_columns_with_validation(
                        df_multi, sheet_name,
                        client_mappings=client_col_mappings,
                        additional_keywords=additional_keywords,
                        sheet_role=sheet_role.value if sheet_role else None
                    )

                    # Use multi-row results if better
                    multi_critical = sum(1 for f in ["description", "cost", "in_service_date"]
                                        if col_map_multi.get(f))
                    orig_critical = sum(1 for f in ["description", "cost", "in_service_date"]
                                       if col_map.get(f))

                    if multi_critical > orig_critical:
                        logger.info(f"[{sheet_name}] Multi-row headers improved detection: {orig_critical} -> {multi_critical} critical fields")
                        col_map = col_map_multi
                        column_mappings = mappings_multi
                        warnings_list = warnings_multi
                        df = df_multi
                        header_idx = multi_start
                        use_multi_row = True
                        warnings_list.append("Multi-row header detection applied")

            # Log warnings
            for warning in warnings_list:
                logger.warning(f"[{sheet_name}] {warning}")

            # Must have at least description to be useful
            if not col_map.get("description"):
                logger.error(f"Skipping sheet {sheet_name}: No description column found")
                skipped_sheets += 1
                continue

            # STEP 4: Refine sheet role with column data
            sheet_role = _detect_sheet_role(sheet_name, df)

            # STEP 4: Process each row
            rows_processed = 0
            rows_skipped = 0
            rows_filtered_date_sheet = 0  # Date-filtered rows for this sheet

            for idx, row in df.iterrows():
                cleaned = _clean_row_data(row, col_map)
                if not cleaned:
                    rows_skipped += 1
                    continue

                # ROW-LEVEL DATE FILTERING
                # Only include rows with dates in the target fiscal year
                # This dramatically reduces data when category tabs have years of history
                if filter_by_date and target_tax_year:
                    # Check in_service_date first, then acquisition_date
                    row_date = cleaned.get("in_service_date") or cleaned.get("acquisition_date")

                    if row_date and not _is_date_in_fiscal_year(row_date, target_tax_year, fy_start_month):
                        rows_filtered_date_sheet += 1
                        rows_filtered_by_date += 1
                        continue  # Skip this row - not in target fiscal year

                # Detect transaction type
                trans_type = _detect_transaction_type(
                    row,
                    col_map.get("description"),
                    col_map.get("cost"),
                    col_map.get("transaction_type"),
                    col_map.get("disposal_date")
                )

                # Override with sheet role if it's more specific
                if sheet_role == SheetRole.DISPOSALS:
                    trans_type = "disposal"
                elif sheet_role == SheetRole.TRANSFERS:
                    trans_type = "transfer"

                all_rows.append({
                    "sheet_name": sheet_name,
                    "sheet_role": sheet_role.value,
                    "source_row": header_idx + idx + 2,  # Excel row number (1-indexed)
                    "transaction_type": trans_type,
                    **cleaned
                })

                rows_processed += 1

            # Log with date filtering info
            if rows_filtered_date_sheet > 0:
                logger.info(f"[{sheet_name}] Processed {rows_processed} rows, skipped {rows_skipped} empty, filtered {rows_filtered_date_sheet} by date (prior years)")
            else:
                logger.info(f"[{sheet_name}] Processed {rows_processed} rows, skipped {rows_skipped} rows")
            processed_sheets += 1

        except Exception as e:
            logger.error(f"Error processing sheet {sheet_name}: {e}", exc_info=True)
            skipped_sheets += 1
            continue

    # Build final dataframe
    if not all_rows:
        logger.error("No data rows found in any sheet")
        return pd.DataFrame()

    logger.info(f"Building final dataframe from {len(all_rows)} rows")
    df_final = pd.DataFrame(all_rows)

    # Filter out any rows that slipped through with no asset_id AND no description
    before_filter = len(df_final)
    df_final = df_final[
        ~(
            df_final["asset_id"].astype(str).str.strip().eq("") &
            df_final["description"].astype(str).str.strip().eq("")
        )
    ]
    after_filter = len(df_final)

    if before_filter != after_filter:
        logger.info(f"Filtered out {before_filter - after_filter} empty rows")

    # Sort by sheet, then row number for consistency
    df_final = df_final.sort_values(["sheet_name", "source_row"]).reset_index(drop=True)

    # Final summary with date filtering stats
    if rows_filtered_by_date > 0:
        logger.info(f"Final dataframe: {len(df_final)} current-year rows from {processed_sheets} sheets")
        logger.info(f"  📅 Filtered out {rows_filtered_by_date} prior-year rows (date filtering)")
        logger.info(f"  ⏭️  Skipped {skipped_sheets} sheets entirely")
    else:
        logger.info(f"Final dataframe: {len(df_final)} rows from {processed_sheets} sheets ({skipped_sheets} skipped)")

    # Log skipped sheets summary for user visibility
    if skipped_sheet_reasons:
        logger.info(f"Sheets skipped (smart filtering): {len(skipped_sheet_reasons)}")
        for reason in skipped_sheet_reasons[:5]:  # Show first 5
            logger.info(f"  - {reason}")
        if len(skipped_sheet_reasons) > 5:
            logger.info(f"  - ... and {len(skipped_sheet_reasons) - 5} more")

    # Store filtering stats in dataframe attrs for UI display
    df_final.attrs['rows_filtered_by_date'] = rows_filtered_by_date
    df_final.attrs['sheets_skipped'] = skipped_sheets
    df_final.attrs['sheets_processed'] = processed_sheets
    df_final.attrs['client_id'] = client_id  # Store client_id for reference

    return df_final


# ====================================================================================
# DIAGNOSTIC FUNCTIONS
# ====================================================================================

def analyze_excel_structure(sheets: Dict[str, pd.DataFrame]) -> Dict[str, SheetAnalysis]:
    """
    Analyze Excel file structure for debugging

    Args:
        sheets: Dict of sheet_name -> DataFrame (header=None)

    Returns:
        Dictionary of sheet_name -> SheetAnalysis objects
    """
    analysis = {}

    for sheet_name, df_raw in sheets.items():
        if df_raw is None or df_raw.empty:
            continue

        try:
            # Detect header row
            header_idx = _detect_header_row(df_raw, max_scan=HEADER_SCAN_MAX_ROWS)

            # Extract data
            df = df_raw.iloc[header_idx:].copy()
            if df.empty or len(df) < 1:
                logger.warning(f"Sheet '{sheet_name}' has no data after header row {header_idx}")
                continue
            df.columns = [_normalize_header(x) for x in df.iloc[0]]
            df = df.iloc[1:].reset_index(drop=True)

            # Map columns
            col_map, column_mappings, warnings_list = _map_columns_with_validation(df, sheet_name)

            # Detect sheet role
            sheet_role = _detect_sheet_role(sheet_name, df)

            # Create analysis object
            sheet_analysis = SheetAnalysis(
                sheet_name=sheet_name,
                header_row=header_idx + 1,  # Excel row number (1-indexed)
                total_rows=len(df),
                detected_columns=col_map,
                column_mappings=column_mappings,
                all_columns=df.columns.tolist(),
                sheet_role=sheet_role.value,
                warnings=warnings_list
            )

            analysis[sheet_name] = sheet_analysis

        except Exception as e:
            logger.error(f"Error analyzing sheet {sheet_name}: {e}", exc_info=True)
            continue

    return analysis


# ====================================================================================
# SMART TAB ANALYSIS - CPA-Style File Structure Detection
# ====================================================================================

def analyze_tabs_smart(
    sheets: Dict[str, pd.DataFrame],
    target_tax_year: Optional[int] = None,
    fy_start_month: int = 1
):
    """
    Analyze Excel tabs like a CPA would - detecting summaries, details, disposals, prior years.

    This is the main entry point for smart tab analysis. Call this BEFORE processing
    to understand file structure and get recommendations.

    Args:
        sheets: Dict of sheet_name -> DataFrame (header=None)
        target_tax_year: Target tax year (e.g., 2025)
        fy_start_month: First month of fiscal year (1=Jan, 4=Apr)

    Returns:
        TabAnalysisResult with complete analysis and recommendations, or None if not available

    Example:
        # Analyze tabs first
        result = analyze_tabs_smart(sheets, target_tax_year=2025)

        # Show user the analysis
        print(result.format_tab_tree())

        # Check for warnings (e.g., summary tab has data but detail tabs empty)
        for warning in result.warnings:
            print(warning)

        # Get recommended tabs to process
        tabs_to_process = [t.tab_name for t in result.tabs_to_process]
    """
    if not SMART_TAB_ANALYZER_AVAILABLE:
        logger.warning("Smart tab analyzer not available - returning None")
        return None
    return smart_tab_analyzer.analyze_tabs(sheets, target_tax_year, fy_start_month)


def build_unified_dataframe_smart(
    sheets: Dict[str, pd.DataFrame],
    target_tax_year: Optional[int] = None,
    fy_start_month: int = 1,
    filter_by_date: bool = True,
    client_id: Optional[str] = None,
    selected_tabs: Optional[List[str]] = None,
    tab_analysis: Optional[Any] = None
) -> Tuple[pd.DataFrame, Any]:
    """
    Build unified dataframe with smart tab filtering.

    This is an enhanced version of build_unified_dataframe that:
    1. Analyzes tabs first (if not provided)
    2. Uses smart tab selection (summary/prior year filtering)
    3. Returns both the dataframe and analysis results

    Args:
        sheets: Dict of sheet_name -> DataFrame (header=None)
        target_tax_year: Target tax year (e.g., 2025)
        fy_start_month: First month of fiscal year (1=Jan, 4=Apr)
        filter_by_date: If True, filter rows by fiscal year date
        client_id: Optional client identifier for column mappings
        selected_tabs: Optional list of tab names to process (overrides auto-detection)
        tab_analysis: Optional pre-computed TabAnalysisResult

    Returns:
        Tuple of (DataFrame, TabAnalysisResult) or (DataFrame, None) if analyzer unavailable

    Example:
        # Let smart analyzer decide which tabs to process
        df, analysis = build_unified_dataframe_smart(sheets, target_tax_year=2025)

        # Or specify tabs manually after reviewing analysis
        analysis = analyze_tabs_smart(sheets, target_tax_year=2025)
        selected = ['Office & Computer Equip', 'F&F', 'Disposals FY 2024 2025']
        df, _ = build_unified_dataframe_smart(sheets, target_tax_year=2025, selected_tabs=selected)
    """
    # Check if smart tab analyzer is available
    if not SMART_TAB_ANALYZER_AVAILABLE:
        logger.warning("Smart tab analyzer not available - using standard processing")
        df = build_unified_dataframe(
            sheets,
            target_tax_year=target_tax_year,
            fy_start_month=fy_start_month,
            filter_by_date=filter_by_date,
            client_id=client_id
        )
        return df, None

    # Step 1: Analyze tabs if not provided
    if tab_analysis is None:
        tab_analysis = smart_tab_analyzer.analyze_tabs(sheets, target_tax_year, fy_start_month)

    # Step 2: Determine which tabs to process
    if selected_tabs is not None:
        # User specified tabs - use their selection
        tabs_to_process = selected_tabs
        logger.info(f"Using user-selected tabs: {tabs_to_process}")
    else:
        # Use smart recommendation
        tabs_to_process = [t.tab_name for t in tab_analysis.tabs_to_process]
        logger.info(f"Using smart-recommended tabs: {tabs_to_process}")

    # Step 3: Filter sheets to only process selected tabs
    filtered_sheets = {name: df for name, df in sheets.items() if name in tabs_to_process}

    if not filtered_sheets:
        logger.warning("No tabs selected for processing - using all sheets")
        filtered_sheets = sheets

    # Step 4: Log efficiency stats
    stats = tab_analysis.get_efficiency_stats()
    logger.info(f"Smart tab filtering: Processing {stats['process_tabs']}/{stats['total_tabs']} tabs")
    logger.info(f"  Expected reduction: {stats['reduction_percent']:.0f}% fewer rows")

    # Step 5: Process with standard function
    df = build_unified_dataframe(
        filtered_sheets,
        target_tax_year=target_tax_year,
        fy_start_month=fy_start_month,
        filter_by_date=filter_by_date,
        client_id=client_id
    )

    # Step 6: Store smart analysis stats in dataframe attrs
    df.attrs['tab_analysis'] = tab_analysis
    df.attrs['tabs_processed'] = tabs_to_process
    df.attrs['tabs_skipped'] = [t.tab_name for t in tab_analysis.tabs_to_skip]
    df.attrs['smart_filtering_enabled'] = True

    return df, tab_analysis


def format_tab_analysis_for_display(analysis) -> str:
    """
    Format tab analysis as a visual tree for UI display.

    Args:
        analysis: TabAnalysisResult from analyze_tabs_smart()

    Returns:
        Formatted string suitable for display in UI, or empty string if unavailable
    """
    if not SMART_TAB_ANALYZER_AVAILABLE or analysis is None:
        return ""
    return smart_tab_analyzer.format_tab_tree(analysis)
