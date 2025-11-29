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

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import os
import logging
import warnings
from typing import Dict, Optional, List, Tuple, Set, Any
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import re
from rapidfuzz import fuzz

from .parse_utils import parse_date, parse_number
from .typo_engine import typo_engine


# ====================================================================================
# CONFIGURATION & CONSTANTS
# ====================================================================================

# Fuzzy matching thresholds
FUZZY_MATCH_THRESHOLD = 75
FUZZY_MATCH_SUBSTRING_MIN_LENGTH = 4
FUZZY_MATCH_REVERSE_SUBSTRING_MIN_LENGTH = 6

# Header detection constants
HEADER_SCAN_MAX_ROWS = 20
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
OPTIONAL_FIELDS = ["method", "life", "transaction_type", "business_use_pct", "proceeds"]

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
        "macrs method", "convention", "recovery method"
    ],

    "life": [
        "life", "useful life", "recovery period", "class life",
        "macrs life", "years", "depr life", "depreciation life"
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


# ====================================================================================
# SHEET ROLE DETECTION
# ====================================================================================

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
    disposal_keywords = ["dispos", "sold", "retired", "writeoff", "write-off", "sale"]
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
    addition_keywords = ["addition", "add", "new", "purchase", "acquisition"]
    for keyword in addition_keywords:
        if keyword in sheet_lower:
            logger.info(f"Sheet '{sheet_name}' detected as ADDITIONS (keyword: {keyword})")
            return SheetRole.ADDITIONS

    # Check for disposal date column
    result = _find_header_fuzzy(df, "disposal_date")
    if result:
        logger.info(f"Sheet '{sheet_name}' detected as DISPOSALS (has disposal_date column)")
        return SheetRole.DISPOSALS

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
            if any(x in trans_val for x in ["dispos", "sold", "retire", "delete", "sale"]):
                return "disposal"
            # Check for transfer indicators
            if any(x in trans_val for x in ["transfer", "xfer", "reclass", "move", "relocate"]):
                return "transfer"
            # Check for addition indicators
            if any(x in trans_val for x in ["add", "new", "purchase", "acquisition", "acq"]):
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
    }


# ====================================================================================
# COLUMN MAPPING WITH VALIDATION
# ====================================================================================

def _map_columns_with_validation(
    df: pd.DataFrame,
    sheet_name: str,
    overrides: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, str], List[ColumnMapping], List[str]]:
    """
    Map Excel columns to logical fields with validation and warnings

    Args:
        df: DataFrame with normalized column headers
        sheet_name: Name of the sheet (for logging)
        overrides: Optional dictionary of logical_field -> excel_column to force mapping

    Returns:
        Tuple of (col_map dict, column_mappings list, warnings list)
    """
    col_map: Dict[str, str] = {}
    column_mappings: List[ColumnMapping] = []
    warnings_list: List[str] = []
    mapped_cols: Set[str] = set()

    # Apply overrides first
    if overrides:
        for logical, col in overrides.items():
            # Normalize the override column name to match df columns
            col_norm = _normalize_header(col)
            
            # Find the actual column name in df that matches the normalized override
            # (The override might come from UI which might have slightly different casing/spacing if not careful)
            actual_col = None
            for df_col in df.columns:
                if _normalize_header(df_col) == col_norm:
                    actual_col = df_col
                    break
            
            if actual_col:
                col_map[logical] = actual_col
                mapped_cols.add(actual_col)
                column_mappings.append(ColumnMapping(
                    logical_name=logical,
                    excel_column=actual_col,
                    match_type="manual_override",
                    confidence=1.0
                ))
                logger.info(f"[{sheet_name}] Applied override: {logical} -> {actual_col}")
            else:
                warnings_list.append(f"Override column '{col}' not found in sheet")

    # Define priority groups
    priority_groups = [
        CRITICAL_FIELDS,
        IMPORTANT_FIELDS,
        CATEGORY_LOCATION_FIELDS,
        OPTIONAL_FIELDS
    ]

    # Map fields in priority order
    for priority_group in priority_groups:
        for logical in priority_group:
            # Skip if already mapped via override
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

    return col_map, column_mappings, warnings_list


# ====================================================================================
# MAIN SHEET LOADER
# ====================================================================================

def build_unified_dataframe(
    sheets: Dict[str, pd.DataFrame],
    column_mapping_overrides: Optional[Dict[str, Dict[str, str]]] = None
) -> pd.DataFrame:
    """
    Build unified dataframe from multiple Excel sheets

    Handles diverse formats, multiple sheets, various column names with
    intelligent detection and comprehensive validation.

    Args:
        sheets: Dict of sheet_name -> DataFrame (header=None)
        column_mapping_overrides: Optional dict of sheet_name -> {logical_field: excel_column}

    Returns:
        Unified DataFrame with standardized column names

    Raises:
        ValueError: If no valid sheets found or critical errors occur
    """
    if not sheets:
        raise ValueError("No sheets provided")

    all_rows = []
    processed_sheets = 0
    skipped_sheets = 0

    logger.info(f"Processing {len(sheets)} Excel sheets")

    for sheet_name, df_raw in sheets.items():
        logger.info(f"Processing sheet: {sheet_name}")

        if df_raw is None or df_raw.empty:
            logger.warning(f"Skipping empty sheet: {sheet_name}")
            skipped_sheets += 1
            continue

        try:
            # STEP 1: Detect header row
            header_idx = _detect_header_row(df_raw, max_scan=HEADER_SCAN_MAX_ROWS)

            # Extract data starting from header
            df = df_raw.iloc[header_idx:].copy()
            df.columns = [_normalize_header(x) for x in df.iloc[0]]
            df = df.iloc[1:].reset_index(drop=True)

            logger.info(f"[{sheet_name}] Header detected at row {header_idx}, {len(df)} data rows")

            # STEP 2: Map columns with validation
            sheet_overrides = column_mapping_overrides.get(sheet_name) if column_mapping_overrides else None
            col_map, column_mappings, warnings_list = _map_columns_with_validation(df, sheet_name, overrides=sheet_overrides)

            # Log warnings
            for warning in warnings_list:
                logger.warning(f"[{sheet_name}] {warning}")

            # Must have at least description to be useful
            if not col_map.get("description"):
                logger.error(f"Skipping sheet {sheet_name}: No description column found")
                skipped_sheets += 1
                continue

            # STEP 3: Detect sheet role
            sheet_role = _detect_sheet_role(sheet_name, df)

            # STEP 4: Process each row
            rows_processed = 0
            rows_skipped = 0

            for idx, row in df.iterrows():
                cleaned = _clean_row_data(row, col_map)
                if not cleaned:
                    rows_skipped += 1
                    continue

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

    logger.info(f"Final dataframe: {len(df_final)} rows from {processed_sheets} sheets ({skipped_sheets} skipped)")

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
