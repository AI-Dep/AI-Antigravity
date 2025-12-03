"""
Fixed Asset AI - Sheet Analysis Module

Sheet skip detection, role detection, and fiscal year logic
extracted from sheet_loader.py for better maintainability.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import re
from datetime import datetime, date
from typing import Tuple, Optional, List
from enum import Enum

import pandas as pd


# ====================================================================================
# SHEET ROLE ENUMERATION
# ====================================================================================

class SheetRole(Enum):
    """Enumeration of sheet roles for CPA workflow categorization"""
    MAIN = "main"
    ADDITIONS = "additions"      # Current year new acquisitions
    DISPOSALS = "disposals"      # Current year disposals/retirements
    TRANSFERS = "transfers"      # Location/dept transfers or reclassifications
    EXISTING = "existing"        # Prior year assets already in FA CS
    SUMMARY = "summary"          # Summary/totals sheet (skip for asset extraction)


# ====================================================================================
# SHEET SKIP PATTERNS
# ====================================================================================

# Patterns for sheets that should typically be skipped
SHEET_SKIP_PATTERNS = [
    # Summary/overview sheets
    "summary", "overview", "totals", "total", "recap",
    # Working/draft sheets
    "reconciliation", "recon", "reclass", "reclassification",
    "draft", "temp", "scratch", "working", "work",
    # Analysis sheets
    "pivot", "chart", "graph", "analysis",
    # Metadata sheets
    "table of contents", "toc", "cover", "instructions",
    "notes", "readme",
    # Historical/archive sheets
    "prior year", "prior years", "historical", "archive", "archived",
    "old", "backup",
]

# Regex patterns for prior year detection
PRIOR_YEAR_PATTERNS = [
    r"fy\s*20[0-1]\d",           # FY 2019 and earlier
    r"fy\s*202[0-3](?!\s*202)",  # FY 2020-2023 (not "FY 2023 2024")
    r"20[0-1]\d\s*-\s*20[0-1]\d", # 2010-2019 ranges
    r"20[0-1]\d\s+asset",         # "2019 assets"
    r"^20[0-1]\d$",              # Just "2019"
    r"\b19\d\d\b",               # 1900s years
]


# ====================================================================================
# SHEET SKIP DETECTION
# ====================================================================================

def _should_skip_sheet(sheet_name: str, custom_skip_patterns: List[str] = None) -> Tuple[bool, str]:
    """
    Determine if a sheet should be skipped based on naming patterns.

    Args:
        sheet_name: Name of the Excel sheet
        custom_skip_patterns: Additional patterns to skip (client-specific)

    Returns:
        Tuple of (should_skip: bool, reason: str)
    """
    if not sheet_name:
        return True, "Empty sheet name"

    name_lower = sheet_name.lower().strip()

    # Check standard skip patterns
    for pattern in SHEET_SKIP_PATTERNS:
        if pattern in name_lower:
            return True, f"Matches skip pattern: {pattern}"

    # Check custom skip patterns
    if custom_skip_patterns:
        for pattern in custom_skip_patterns:
            if pattern.lower() in name_lower:
                return True, f"Matches custom skip pattern: {pattern}"

    # Check prior year patterns
    for pattern in PRIOR_YEAR_PATTERNS:
        if re.search(pattern, name_lower):
            return True, f"Prior year sheet: {pattern}"

    return False, ""


def _is_prior_year_sheet(sheet_name: str, target_year: int) -> bool:
    """
    Check if sheet appears to be from a prior year.

    Args:
        sheet_name: Sheet name to check
        target_year: Current/target tax year

    Returns:
        True if sheet appears to be prior year data
    """
    name_lower = sheet_name.lower()

    # Extract year mentions from sheet name
    year_matches = re.findall(r'20\d\d', name_lower)

    for year_str in year_matches:
        year = int(year_str)
        # If year is before target year, it's prior year
        if year < target_year:
            return True

    # Check for "prior" keywords
    if any(kw in name_lower for kw in ["prior", "historical", "archive", "old"]):
        return True

    return False


# ====================================================================================
# SHEET ROLE DETECTION
# ====================================================================================

def _detect_sheet_role(sheet_name: str) -> SheetRole:
    """
    Detect the role of a sheet based on its name.

    Args:
        sheet_name: Name of the Excel sheet

    Returns:
        SheetRole enum value
    """
    name_lower = sheet_name.lower().strip()

    # Disposal sheets
    disposal_keywords = ["dispos", "retired", "writeoff", "write-off", "scrap", "sold", "sale"]
    if any(kw in name_lower for kw in disposal_keywords):
        return SheetRole.DISPOSALS

    # Transfer sheets
    transfer_keywords = ["transfer", "xfer", "reclass", "reclassification", "move"]
    if any(kw in name_lower for kw in transfer_keywords):
        return SheetRole.TRANSFERS

    # Addition sheets
    addition_keywords = ["addition", "new asset", "new purchase", "acquisition", "purchase", "add"]
    if any(kw in name_lower for kw in addition_keywords):
        return SheetRole.ADDITIONS

    # Default to main
    return SheetRole.MAIN


# ====================================================================================
# FISCAL YEAR UTILITIES
# ====================================================================================

def _extract_fiscal_year_from_sheet(sheet_name: str) -> Optional[int]:
    """
    Extract fiscal year from sheet name if present.

    Examples:
    - "FY 2024" -> 2024
    - "FY 2024 2025" -> 2025 (end year)
    - "Assets 2024" -> 2024

    Args:
        sheet_name: Sheet name to parse

    Returns:
        Extracted year or None
    """
    name_lower = sheet_name.lower()

    # FY YYYY YYYY format (fiscal year spanning two years)
    match = re.search(r'fy\s*(\d{4})\s*(\d{4})', name_lower)
    if match:
        return int(match.group(2))  # Return end year

    # FY YYYY format
    match = re.search(r'fy\s*(\d{4})', name_lower)
    if match:
        return int(match.group(1))

    # Just a year
    match = re.search(r'\b(20\d{2})\b', name_lower)
    if match:
        return int(match.group(1))

    return None


def _is_date_in_fiscal_year(
    check_date,
    target_tax_year: int,
    fy_start_month: int = 1
) -> bool:
    """
    Check if a date falls within a fiscal year.

    Supports both calendar year (Jan-Dec) and fiscal year (e.g., Apr-Mar).

    Args:
        check_date: Date to check (datetime, date, or parseable string)
        target_tax_year: Tax year to check against
        fy_start_month: First month of fiscal year (1=Jan, 4=Apr, 7=Jul, etc.)

    Returns:
        True if date is within the fiscal year
    """
    if check_date is None or pd.isna(check_date):
        return True  # Allow missing dates through

    # Parse date if string
    if isinstance(check_date, str):
        try:
            from .parse_utils import parse_date
            check_date = parse_date(check_date)
        except Exception:
            return True  # Allow unparseable dates

    # Convert to date object
    if hasattr(check_date, 'date'):
        check_date = check_date.date()

    if not isinstance(check_date, date):
        return True  # Allow non-date types

    # Calculate fiscal year boundaries
    if fy_start_month == 1:
        # Calendar year
        fy_start = date(target_tax_year, 1, 1)
        fy_end = date(target_tax_year, 12, 31)
    else:
        # Fiscal year (e.g., Apr 2024 - Mar 2025 for tax year 2025)
        fy_start = date(target_tax_year - 1, fy_start_month, 1)

        # Calculate end month
        if fy_start_month == 1:
            fy_end_month = 12
            fy_end_year = target_tax_year
        else:
            fy_end_month = fy_start_month - 1
            fy_end_year = target_tax_year

        # Last day of end month
        if fy_end_month == 12:
            fy_end = date(fy_end_year, 12, 31)
        elif fy_end_month in [4, 6, 9, 11]:
            fy_end = date(fy_end_year, fy_end_month, 30)
        elif fy_end_month == 2:
            # Handle leap year
            if fy_end_year % 4 == 0 and (fy_end_year % 100 != 0 or fy_end_year % 400 == 0):
                fy_end = date(fy_end_year, 2, 29)
            else:
                fy_end = date(fy_end_year, 2, 28)
        else:
            fy_end = date(fy_end_year, fy_end_month, 31)

    return fy_start <= check_date <= fy_end


def get_fiscal_year_range(
    target_tax_year: int,
    fy_start_month: int = 1
) -> Tuple[date, date]:
    """
    Get the date range for a fiscal year.

    Args:
        target_tax_year: Tax year
        fy_start_month: First month of fiscal year

    Returns:
        Tuple of (start_date, end_date)
    """
    if fy_start_month == 1:
        return date(target_tax_year, 1, 1), date(target_tax_year, 12, 31)

    fy_start = date(target_tax_year - 1, fy_start_month, 1)
    fy_end_month = fy_start_month - 1 if fy_start_month > 1 else 12
    fy_end_year = target_tax_year

    # Calculate last day of end month
    if fy_end_month == 12:
        fy_end = date(fy_end_year, 12, 31)
    elif fy_end_month in [4, 6, 9, 11]:
        fy_end = date(fy_end_year, fy_end_month, 30)
    elif fy_end_month == 2:
        if fy_end_year % 4 == 0 and (fy_end_year % 100 != 0 or fy_end_year % 400 == 0):
            fy_end = date(fy_end_year, 2, 29)
        else:
            fy_end = date(fy_end_year, 2, 28)
    else:
        fy_end = date(fy_end_year, fy_end_month, 31)

    return fy_start, fy_end


# ====================================================================================
# TRANSACTION TYPE DETECTION
# ====================================================================================

def _detect_transaction_type(
    row: dict,
    sheet_role: SheetRole,
    col_map: dict
) -> str:
    """
    Detect transaction type from row data and sheet context.

    Priority:
    1. Explicit transaction type column
    2. Disposal date populated
    3. Description keywords
    4. Sheet role
    5. Default to addition

    Args:
        row: Row data dictionary
        sheet_role: Role of the sheet this row is from
        col_map: Column mapping dictionary

    Returns:
        Transaction type string
    """
    # Check explicit transaction type column
    if "transaction_type" in col_map:
        trans_val = row.get(col_map["transaction_type"], "")
        if trans_val and pd.notna(trans_val):
            trans_lower = str(trans_val).lower()
            if "dispos" in trans_lower or "sold" in trans_lower or "retired" in trans_lower:
                return "disposal"
            if "transfer" in trans_lower or "reclass" in trans_lower:
                return "transfer"
            if "add" in trans_lower or "new" in trans_lower:
                return "addition"

    # Check disposal date
    if "disposal_date" in col_map:
        disposal_date = row.get(col_map["disposal_date"])
        if disposal_date and pd.notna(disposal_date):
            return "disposal"

    # Check description keywords
    desc_col = col_map.get("description", "")
    if desc_col:
        desc = str(row.get(desc_col, "")).lower()
        if any(kw in desc for kw in ["disposed", "sold", "retired", "scrapped"]):
            return "disposal"
        if any(kw in desc for kw in ["transfer", "xfer", "reclass"]):
            return "transfer"

    # Check for negative cost (sometimes indicates disposal)
    cost_col = col_map.get("cost", "")
    if cost_col:
        cost = row.get(cost_col)
        if cost and pd.notna(cost):
            try:
                if float(str(cost).replace(",", "").replace("$", "")) < 0:
                    return "disposal"
            except ValueError:
                pass

    # Use sheet role
    if sheet_role == SheetRole.DISPOSALS:
        return "disposal"
    if sheet_role == SheetRole.TRANSFERS:
        return "transfer"
    if sheet_role == SheetRole.ADDITIONS:
        return "addition"

    # Default
    return "addition"
