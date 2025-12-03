# fixed_asset_ai/logic/smart_tab_analyzer.py
"""
Smart Tab Analyzer for Fixed Asset Schedules

This module provides intelligent analysis of Excel tab/sheet names to:
1. Detect tab roles (summary, detail, disposals, prior year)
2. Recommend which tabs to process vs skip
3. Detect data anomalies (e.g., summary has data but details are empty)
4. Provide user-friendly UI data for tab selection

Key Features:
- Pattern-based tab role detection
- Summary vs detail tab differentiation
- Prior year tab identification
- Data validation across tabs (detect missing detail data)
- Fiscal year extraction from tab names

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

logger = logging.getLogger(__name__)


# ====================================================================================
# TAB ROLE DEFINITIONS
# ====================================================================================

class TabRole(Enum):
    """Classification of Excel tab types in fixed asset schedules"""
    SUMMARY = "summary"           # Roll-up/total tabs (FY 2024 2025)
    DETAIL = "detail"             # Category detail tabs (Office Equip, F&F)
    DISPOSALS = "disposals"       # Disposal tracking tabs
    ADDITIONS = "additions"       # New additions tabs
    TRANSFERS = "transfers"       # Asset transfer tabs
    PRIOR_YEAR = "prior_year"     # Historical/prior year tabs
    WORKING = "working"           # Draft/working tabs
    UNKNOWN = "unknown"           # Unclassified tabs


@dataclass
class TabAnalysis:
    """Analysis results for a single Excel tab"""
    tab_name: str
    role: TabRole
    fiscal_year: Optional[int]  # Extracted fiscal year (ending year for FY ranges)
    row_count: int              # Number of data rows (excluding header)
    data_row_count: int         # Rows with actual data (non-empty description)
    has_cost_data: bool         # Has cost column with values
    has_date_data: bool         # Has date column with values
    should_process: bool        # Recommended: should this tab be processed?
    skip_reason: Optional[str]  # Why it should be skipped
    confidence: float           # Confidence in role detection (0.0-1.0)
    detection_notes: List[str] = field(default_factory=list)

    @property
    def icon(self) -> str:
        """Return appropriate icon for this tab role"""
        icons = {
            TabRole.SUMMARY: "📊",
            TabRole.DETAIL: "📋",
            TabRole.DISPOSALS: "🗑️",
            TabRole.ADDITIONS: "➕",
            TabRole.TRANSFERS: "🔄",
            TabRole.PRIOR_YEAR: "📅",
            TabRole.WORKING: "📝",
            TabRole.UNKNOWN: "❓",
        }
        return icons.get(self.role, "❓")

    @property
    def role_label(self) -> str:
        """Human-readable role label"""
        labels = {
            TabRole.SUMMARY: "Summary (skip)",
            TabRole.DETAIL: "Detail → Process",
            TabRole.DISPOSALS: "Disposals → Track",
            TabRole.ADDITIONS: "Additions → Process",
            TabRole.TRANSFERS: "Transfers → Track",
            TabRole.PRIOR_YEAR: "Prior Year (skip)",
            TabRole.WORKING: "Working/Draft (skip)",
            TabRole.UNKNOWN: "Unknown",
        }
        return labels.get(self.role, "Unknown")


@dataclass
class TabAnalysisResult:
    """Complete analysis results for all tabs in a workbook"""
    tabs: List[TabAnalysis]
    target_fiscal_year: Optional[int]
    detected_fy_start_month: Optional[int] = None  # Auto-detected fiscal year start month (1=Jan, 4=Apr, etc.)
    fy_detection_source: Optional[str] = None  # Where we detected the FY from (e.g., "FY 2024 2025 tab header: Beg Balance 4/1/2024")
    warnings: List[str] = field(default_factory=list)
    summary_tabs: List[str] = field(default_factory=list)
    detail_tabs: List[str] = field(default_factory=list)
    disposal_tabs: List[str] = field(default_factory=list)
    prior_year_tabs: List[str] = field(default_factory=list)

    @property
    def tabs_to_process(self) -> List[TabAnalysis]:
        """Get tabs recommended for processing"""
        return [t for t in self.tabs if t.should_process]

    @property
    def tabs_to_skip(self) -> List[TabAnalysis]:
        """Get tabs recommended to skip"""
        return [t for t in self.tabs if not t.should_process]

    @property
    def total_process_rows(self) -> int:
        """Total data rows in tabs to process"""
        return sum(t.data_row_count for t in self.tabs_to_process)

    @property
    def total_skip_rows(self) -> int:
        """Total data rows in tabs to skip"""
        return sum(t.data_row_count for t in self.tabs_to_skip)

    def get_efficiency_stats(self) -> Dict[str, Any]:
        """Calculate efficiency improvement from smart tab filtering"""
        total_rows = sum(t.data_row_count for t in self.tabs)
        process_rows = self.total_process_rows
        skip_rows = self.total_skip_rows

        if total_rows == 0:
            reduction_pct = 0
        else:
            reduction_pct = (skip_rows / total_rows) * 100

        return {
            "total_tabs": len(self.tabs),
            "process_tabs": len(self.tabs_to_process),
            "skip_tabs": len(self.tabs_to_skip),
            "total_rows": total_rows,
            "process_rows": process_rows,
            "skip_rows": skip_rows,
            "reduction_percent": reduction_pct,
        }


# ====================================================================================
# PATTERN DEFINITIONS
# ====================================================================================

# Summary tab patterns - tabs that aggregate data from other tabs
SUMMARY_TAB_PATTERNS = [
    # Fiscal year roll-up patterns (most common)
    r"^fy\s*\d{4}\s*\d{4}$",           # "FY 2024 2025"
    r"^fy\s*\d{4}\s*-\s*\d{4}$",       # "FY 2024-2025"
    r"^fy\s*\d{4}/\d{4}$",             # "FY 2024/2025"
    r"^fiscal\s*year\s*\d{4}",          # "Fiscal Year 2024..."

    # Summary/Total patterns
    r"^summary$", r"^totals?$", r"^roll\s*-?\s*forward$",
    r"^consolidated$", r"^master\s*list$",
    r"schedule\s*summary", r"asset\s*summary",
]

# Detail tab patterns - tabs with actual asset data by category
DETAIL_TAB_PATTERNS = [
    # Equipment categories
    r"office\s*(&|and)?\s*computer",    # "Office & Computer Equip"
    r"computer\s*(equip|equipment)?",
    r"office\s*(equip|equipment)?",
    r"furniture\s*(&|and)?\s*fixtures?", r"^f\s*&\s*f$", r"^ff&e$",
    r"plant\s*(equip|equipment)?",
    r"machinery",
    r"vehicles?",

    # Improvement categories
    r"leasehold\s*improv",  r"^lhi$", r"^lh\s*improvement",
    r"building\s*improv",
    r"land\s*improv",

    # Other categories
    r"software", r"intangible", r"construction",
    r"capital\s*lease", r"^cip$",  # Construction in progress
]

# Disposal tab patterns
DISPOSAL_TAB_PATTERNS = [
    r"disposal", r"disposed", r"retire", r"retired",
    r"write\s*-?\s*off", r"scrap", r"sold",
]

# Addition tab patterns
ADDITION_TAB_PATTERNS = [
    r"^addition", r"new\s*asset", r"new\s*purchase",
    r"acquisition", r"current\s*year\s*add",
]

# Transfer tab patterns
TRANSFER_TAB_PATTERNS = [
    r"transfer", r"xfer", r"reclass", r"reclassification",
]

# Prior year patterns
PRIOR_YEAR_TAB_PATTERNS = [
    r"prior\s*year", r"historical", r"archive",
    r"old\s*data", r"legacy",
]

# Working/Draft tab patterns
WORKING_TAB_PATTERNS = [
    r"working", r"draft", r"temp", r"scratch",
    r"reconciliation", r"recon$",
    r"pivot", r"chart", r"graph",
    r"table\s*of\s*contents", r"^toc$", r"^cover$", r"instructions",
]


# ====================================================================================
# CORE ANALYSIS FUNCTIONS
# ====================================================================================

def _extract_fiscal_year(tab_name: str) -> Optional[int]:
    """
    Extract fiscal year from tab name.

    For FY ranges like "FY 2024 2025", returns the ENDING year (2025).
    This is the tax year the data applies to.

    Args:
        tab_name: Name of the Excel tab

    Returns:
        Fiscal year as integer, or None if not found
    """
    tab_lower = tab_name.lower().strip()

    # Pattern 1: "FY 2024 2025" or "FY2024-2025" -> return ENDING year
    match = re.search(r'fy\s*(\d{4})\s*[-/]?\s*(\d{4})', tab_lower)
    if match:
        return int(match.group(2))  # Return ending year

    # Pattern 2: "FY 2024" or "FY2024"
    match = re.search(r'fy\s*(\d{4})', tab_lower)
    if match:
        return int(match.group(1))

    # Pattern 3: Just a year like "2024 additions"
    match = re.search(r'(20\d{2})', tab_lower)
    if match:
        return int(match.group(1))

    return None


def _detect_fiscal_year_from_headers(df: pd.DataFrame, tab_name: str = "") -> Tuple[Optional[int], Optional[str]]:
    """
    Detect fiscal year START MONTH from column headers in rollforward schedules.

    Looks for patterns like:
    - "Beg Balance 4/1/2024" in same cell -> April start (month 4)
    - Header "Beg Balance" with "4/1/2024" in cell below -> April start
    - "End Balance 3/31/2025" -> March end (confirms Apr-Mar FY)

    Args:
        df: DataFrame to analyze (first few rows contain headers)
        tab_name: Tab name for logging

    Returns:
        Tuple of (fy_start_month, detection_source)
        - fy_start_month: 1=Jan (calendar), 4=Apr, 7=Jul, 10=Oct, or None
        - detection_source: Description of where we found the info
    """
    if df is None or df.empty:
        return None, None

    # Date pattern to find standalone dates
    date_pattern = r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})'

    detected_start_month = None
    source = None

    # Check first 15 rows for header information
    rows_to_check = min(15, len(df))

    # Strategy 1: Look for header row with "Beg Balance" and date row below
    for row_idx in range(rows_to_check - 1):  # -1 to allow checking row below
        row = df.iloc[row_idx]
        for col_idx, cell in enumerate(row):
            if cell is None or pd.isna(cell):
                continue

            cell_str = str(cell).lower().strip()

            # Check if this cell is a "Beg Balance" header (without date)
            if any(x in cell_str for x in ['beg bal', 'beg. bal', 'beginning bal', 'beg balance', 'beginning balance']):
                # Look at the cell BELOW for a date
                if row_idx + 1 < len(df):
                    below_cell = df.iloc[row_idx + 1, col_idx] if col_idx < len(df.columns) else None
                    if below_cell is not None and not pd.isna(below_cell):
                        month, day, year = None, None, None

                        # Handle datetime objects directly (Excel often stores dates as datetime)
                        if hasattr(below_cell, 'month') and hasattr(below_cell, 'day'):
                            month = below_cell.month
                            day = below_cell.day
                            year = below_cell.year
                            logger.info(f"[FY Detection] Found datetime object: {below_cell} -> month={month}, day={day}")
                        else:
                            # Try parsing as string (format: "4/1/2024" or "2024-04-01")
                            below_str = str(below_cell).strip()
                            # Try MM/DD/YYYY or MM-DD-YYYY format
                            date_match = re.search(date_pattern, below_str)
                            if date_match:
                                month = int(date_match.group(1))
                                day = int(date_match.group(2))
                                year = int(date_match.group(3))
                            else:
                                # Try YYYY-MM-DD format (ISO format from datetime str)
                                iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', below_str)
                                if iso_match:
                                    year = int(iso_match.group(1))
                                    month = int(iso_match.group(2))
                                    day = int(iso_match.group(3))
                                    logger.info(f"[FY Detection] Parsed ISO date from string: {below_str}")

                        if month and day and year:
                            if year < 100:
                                year += 2000
                            # Beginning balance on 1st of month = fiscal year start
                            if day == 1 and 1 <= month <= 12:
                                detected_start_month = month
                                source = f"'{tab_name}' header row: 'Beg Balance' with date {month}/1/{year} below"
                                logger.info(f"[FY Detection] Found start month {month} from header+date pattern: {cell_str}")
                                break

            # Check if this cell is an "End Balance" header (without date)
            if any(x in cell_str for x in ['end bal', 'end. bal', 'ending bal', 'end balance', 'ending balance']):
                # Look at the cell BELOW for a date
                if row_idx + 1 < len(df):
                    below_cell = df.iloc[row_idx + 1, col_idx] if col_idx < len(df.columns) else None
                    if below_cell is not None and not pd.isna(below_cell):
                        month, day, year = None, None, None

                        # Handle datetime objects directly (Excel often stores dates as datetime)
                        if hasattr(below_cell, 'month') and hasattr(below_cell, 'day'):
                            month = below_cell.month
                            day = below_cell.day
                            year = below_cell.year
                            logger.info(f"[FY Detection] Found end balance datetime: {below_cell}")
                        else:
                            # Try parsing as string
                            below_str = str(below_cell).strip()
                            date_match = re.search(date_pattern, below_str)
                            if date_match:
                                month = int(date_match.group(1))
                                day = int(date_match.group(2))
                                year = int(date_match.group(3))
                            else:
                                # Try YYYY-MM-DD format
                                iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', below_str)
                                if iso_match:
                                    year = int(iso_match.group(1))
                                    month = int(iso_match.group(2))
                                    day = int(iso_match.group(3))

                        if month and day and year:
                            if year < 100:
                                year += 2000
                            # End of fiscal year - infer start month
                            # End 3/31 -> start month is 4 (April)
                            # End 12/31 -> start month is 1 (January/calendar)
                            # End 6/30 -> start month is 7 (July)
                            # End 9/30 -> start month is 10 (October)
                            if not detected_start_month:
                                inferred_start = (month % 12) + 1
                                detected_start_month = inferred_start
                                source = f"'{tab_name}' header row: 'End Balance' with date {month}/{day}/{year} below -> start month {inferred_start}"
                                logger.info(f"[FY Detection] Inferred start month {inferred_start} from end balance: month={month}, day={day}")

            # Strategy 2: Look for "Beg Balance 4/1/2024" pattern in same cell
            beg_with_date = re.search(r'(?:beg(?:inning)?\.?\s*(?:bal(?:ance)?\.?)?|opening)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', cell_str)
            if beg_with_date and not detected_start_month:
                month = int(beg_with_date.group(1))
                day = int(beg_with_date.group(2))
                year = int(beg_with_date.group(3))
                if year < 100:
                    year += 2000

                if day == 1 and 1 <= month <= 12:
                    detected_start_month = month
                    source = f"'{tab_name}' cell: Beg Balance {month}/1/{year}"
                    logger.info(f"[FY Detection] Found start month {month} from combined cell: {cell_str}")

        if detected_start_month:
            break

    # Map detected start month to standard options (1, 4, 7, 10)
    if detected_start_month:
        # Round to nearest standard fiscal year start
        standard_starts = [1, 4, 7, 10]
        closest = min(standard_starts, key=lambda x: min(abs(x - detected_start_month), 12 - abs(x - detected_start_month)))
        if closest != detected_start_month:
            logger.info(f"[FY Detection] Rounding month {detected_start_month} to standard start {closest}")
            source = f"{source} (rounded to {closest})"
            detected_start_month = closest

        return detected_start_month, source

    return None, None


def _detect_tab_role(tab_name: str, target_year: Optional[int] = None) -> Tuple[TabRole, float, List[str]]:
    """
    Detect the role of a tab based on its name.

    Args:
        tab_name: Name of the Excel tab
        target_year: Target tax year (e.g., 2025)

    Returns:
        Tuple of (TabRole, confidence, detection_notes)
    """
    tab_lower = tab_name.lower().strip()
    notes = []

    logger.debug(f"[TabRole] Detecting role for '{tab_name}' (lower: '{tab_lower}')")

    # 1. Check for Working/Draft tabs first (highest priority skip)
    for pattern in WORKING_TAB_PATTERNS:
        if re.search(pattern, tab_lower):
            notes.append(f"Matched working pattern: {pattern}")
            return TabRole.WORKING, 0.95, notes

    # 2. Check for explicit prior year patterns
    for pattern in PRIOR_YEAR_TAB_PATTERNS:
        if re.search(pattern, tab_lower):
            notes.append(f"Matched prior year pattern: {pattern}")
            return TabRole.PRIOR_YEAR, 0.95, notes

    # 3. Check for disposal patterns
    # NOTE: Disposal sheets ARE year-specific - prior year disposals are already processed
    # So we DO mark prior year disposal sheets for skipping (unlike regular asset tabs)
    for pattern in DISPOSAL_TAB_PATTERNS:
        if re.search(pattern, tab_lower):
            notes.append(f"Matched disposal pattern: {pattern}")
            tab_year = _extract_fiscal_year(tab_name)
            if tab_year and target_year and tab_year < target_year:
                notes.append(f"Prior year disposal sheet (FY {tab_year}) - skip, already processed")
                return TabRole.PRIOR_YEAR, 0.90, notes
            return TabRole.DISPOSALS, 0.90, notes

    # 4. Check for transfer patterns
    for pattern in TRANSFER_TAB_PATTERNS:
        if re.search(pattern, tab_lower):
            notes.append(f"Matched transfer pattern: {pattern}")
            return TabRole.TRANSFERS, 0.85, notes

    # 5. Check for addition patterns
    for pattern in ADDITION_TAB_PATTERNS:
        if re.search(pattern, tab_lower):
            notes.append(f"Matched addition pattern: {pattern}")
            return TabRole.ADDITIONS, 0.85, notes

    # 6. Check for SUMMARY patterns (FY roll-ups)
    for pattern in SUMMARY_TAB_PATTERNS:
        if re.search(pattern, tab_lower):
            notes.append(f"Matched summary pattern: {pattern}")
            tab_year = _extract_fiscal_year(tab_name)
            # Mark prior year summaries but DON'T skip - let row-level filtering handle it
            if tab_year and target_year and tab_year < target_year:
                notes.append(f"Year {tab_year} < target {target_year} - will filter at row level")
            return TabRole.SUMMARY, 0.90, notes

    # 7. Check for DETAIL patterns (category-specific tabs)
    for pattern in DETAIL_TAB_PATTERNS:
        if re.search(pattern, tab_lower):
            notes.append(f"Matched detail pattern: {pattern}")
            return TabRole.DETAIL, 0.85, notes

    # 8. Check for year-based tabs - treat as DETAIL for row-level filtering
    # Don't skip based on year - the row-level date filter will handle prior year rows
    tab_year = _extract_fiscal_year(tab_name)
    if tab_year and target_year:
        if tab_year < target_year:
            notes.append(f"Year {tab_year} < target {target_year} - will process and filter at row level")
            # Return DETAIL instead of PRIOR_YEAR - let row filtering decide
            return TabRole.DETAIL, 0.70, notes
        elif tab_year == target_year:
            # Current year tab without specific role - might be summary
            # Check if it looks like just "FY XXXX XXXX"
            if re.match(r'^fy\s*\d{4}\s*[-/]?\s*\d{4}\s*$', tab_lower):
                notes.append(f"Plain FY range tab - likely summary")
                return TabRole.SUMMARY, 0.75, notes

    # Default: Unknown
    notes.append("No pattern matched - unknown role")
    logger.debug(f"[TabRole] '{tab_name}' -> UNKNOWN (no pattern matched)")
    return TabRole.UNKNOWN, 0.50, notes


def _count_data_rows(df: pd.DataFrame) -> Tuple[int, bool, bool]:
    """
    Count actual data rows and check for cost/date data.

    Args:
        df: Raw DataFrame (header=None)

    Returns:
        Tuple of (data_row_count, has_cost_data, has_date_data)
    """
    if df is None or df.empty:
        return 0, False, False

    # Try to find header row and count non-empty data rows
    data_rows = 0
    has_cost = False
    has_date = False

    # Skip first few rows that might be headers
    # Count rows where at least some cells have non-null values
    for idx, row in df.iterrows():
        # Skip first 2 rows (likely headers/titles)
        if idx < 2:
            continue

        # Count non-null, non-empty cells
        non_empty = sum(1 for val in row if pd.notna(val) and str(val).strip())
        if non_empty >= 2:  # At least 2 non-empty cells = data row
            data_rows += 1

            # Check for cost-like values (numbers > 100)
            for val in row:
                if pd.notna(val):
                    try:
                        num = float(str(val).replace(',', '').replace('$', ''))
                        if num > 100:
                            has_cost = True
                    except (ValueError, TypeError):
                        pass

                    # Check for date-like values
                    str_val = str(val).lower()
                    if any(x in str_val for x in ['/', '-', '20']) and len(str_val) >= 6:
                        try:
                            pd.to_datetime(val, errors='raise')
                            has_date = True
                        except (ValueError, TypeError, Exception):
                            pass

    return data_rows, has_cost, has_date


def _has_individual_asset_records(df: pd.DataFrame) -> Tuple[bool, int, str]:
    """
    CRITICAL: Check if a tab contains individual asset records vs. summary totals.

    This prevents skipping tabs that look like summaries but actually contain
    individual asset data that must be processed.

    Individual asset records typically have:
    - Unique Asset IDs (FA-001, 10001, etc.) or serial numbers
    - Individual descriptions (not category names like "Total Computer Equipment")
    - Individual costs (not aggregated totals)
    - Many rows with similar structure

    Summary/rollup tabs typically have:
    - Category names only ("Computer Equipment", "Furniture", etc.)
    - Aggregated totals (large round numbers)
    - Few rows (one per category)
    - "Total" keywords

    Args:
        df: Raw DataFrame (header=None)

    Returns:
        Tuple of (has_individual_records, unique_id_count, detection_reason)
    """
    if df is None or df.empty:
        return False, 0, "Empty dataframe"

    # Patterns that indicate individual Asset IDs
    asset_id_patterns = [
        r'^[A-Z]{1,3}[-_]?\d{3,}$',      # FA-001, FA001, AST-12345
        r'^\d{4,}$',                       # 10001, 123456
        r'^[A-Z]{2,}\d{2,}$',              # FA01, AST123
        r'^[A-Z]-\d+$',                    # A-1, B-123
        r'^\d{1,3}[-/.]\d+$',              # 1-001, 1.001
    ]

    # Patterns that indicate summary/total rows (NOT individual records)
    summary_keywords = [
        'total', 'subtotal', 'sub-total', 'grand total',
        'sum', 'balance', 'net', 'accumulated',
        'category total', 'department total',
    ]

    unique_ids = set()
    individual_descriptions = 0
    summary_rows = 0
    total_data_rows = 0

    # Scan rows for patterns
    for idx, row in df.iterrows():
        if idx < 2:  # Skip header rows
            continue

        row_values = [str(v).strip() for v in row if pd.notna(v) and str(v).strip()]
        if len(row_values) < 2:
            continue

        total_data_rows += 1

        # Check for summary keywords in this row
        row_text = ' '.join(row_values).lower()
        is_summary_row = any(kw in row_text for kw in summary_keywords)
        if is_summary_row:
            summary_rows += 1
            continue

        # Look for Asset ID patterns in first few columns
        for val in row_values[:3]:  # Check first 3 columns
            val_upper = val.upper().strip()
            for pattern in asset_id_patterns:
                if re.match(pattern, val_upper):
                    unique_ids.add(val_upper)
                    break

        # Check if description looks individual (longer, specific)
        for val in row_values:
            # Individual descriptions are typically 10+ chars and specific
            if len(val) >= 10 and not any(kw in val.lower() for kw in summary_keywords):
                # Check it's not a category name (usually short, capitalized)
                if not re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+$', val):  # Not "Computer Equipment"
                    individual_descriptions += 1
                    break

    # Decision logic
    unique_id_count = len(unique_ids)

    # Strong indicator: Many unique Asset IDs
    if unique_id_count >= 5:
        return True, unique_id_count, f"Found {unique_id_count} unique Asset IDs"

    # Strong indicator: Mostly individual descriptions, few summary rows
    if total_data_rows > 0:
        summary_ratio = summary_rows / total_data_rows
        if summary_ratio < 0.3 and individual_descriptions >= 5:
            return True, unique_id_count, f"Found {individual_descriptions} individual descriptions, only {summary_ratio:.0%} summary rows"

    # Many rows with cost/date data suggests individual records
    if total_data_rows >= 10 and summary_rows < 3:
        return True, unique_id_count, f"Found {total_data_rows} data rows with minimal summary rows"

    # Few rows = likely a summary
    if total_data_rows < 5:
        return False, unique_id_count, f"Only {total_data_rows} rows - likely summary"

    # High summary ratio = definitely a summary
    if total_data_rows > 0 and summary_rows / total_data_rows > 0.5:
        return False, unique_id_count, f"High summary row ratio ({summary_rows}/{total_data_rows})"

    # Default: If in doubt and has decent data, assume individual records (SAFE)
    if total_data_rows >= 5:
        return True, unique_id_count, f"Uncertain but has {total_data_rows} rows - treating as individual data for safety"

    return False, unique_id_count, "Insufficient data to determine"


def analyze_tabs(
    sheets: Dict[str, pd.DataFrame],
    target_tax_year: Optional[int] = None,
    fy_start_month: int = 1
) -> TabAnalysisResult:
    """
    Analyze all tabs in an Excel workbook and recommend which to process.

    This is the main entry point for smart tab analysis.

    Args:
        sheets: Dict of sheet_name -> DataFrame (header=None)
        target_tax_year: Target tax year (e.g., 2025)
        fy_start_month: First month of fiscal year (1=Jan, 4=Apr)

    Returns:
        TabAnalysisResult with complete analysis
    """
    logger.info(f"Analyzing {len(sheets)} tabs for target year {target_tax_year}")

    result = TabAnalysisResult(
        tabs=[],
        target_fiscal_year=target_tax_year,
    )

    # Track detected fiscal year start month (from rollforward headers)
    detected_fy_start_month = None
    fy_detection_source = None

    # Analyze each tab
    for tab_name, df in sheets.items():
        role, confidence, notes = _detect_tab_role(tab_name, target_tax_year)
        fiscal_year = _extract_fiscal_year(tab_name)

        # CRITICAL: Try to detect fiscal year start month from SUMMARY/rollforward tabs
        # Look for headers like "Beg Balance 4/1/2024" to auto-detect April fiscal year
        if role == TabRole.SUMMARY and df is not None and not df.empty:
            fy_month, fy_source = _detect_fiscal_year_from_headers(df, tab_name)
            if fy_month and not detected_fy_start_month:
                detected_fy_start_month = fy_month
                fy_detection_source = fy_source
                logger.info(f"[FY Auto-Detection] Detected fiscal year start month {fy_month} from: {fy_source}")

        # Count rows and check for data
        row_count = len(df) if df is not None else 0
        data_row_count, has_cost, has_date = _count_data_rows(df)

        # CRITICAL: Content-based validation
        # Check if tab actually has individual asset records (not just name-based)
        has_individual_records, unique_id_count, content_reason = _has_individual_asset_records(df)

        # Determine if should process
        # PHILOSOPHY: Process ANY tab with asset-like data, regardless of name
        should_process = True
        skip_reason = None

        logger.info(f"Tab '{tab_name}': role={role.value}, data_rows={data_row_count}, has_records={has_individual_records}, reason={content_reason}")

        # PRIORITY ORDER: Prior year check comes FIRST (never process prior year data)
        if role == TabRole.PRIOR_YEAR:
            # Prior year tabs are NEVER processed, regardless of content
            # EXCEPTION: If tab has individual records, maybe it's miscategorized
            if has_individual_records and data_row_count >= 5:
                notes.append(f"OVERRIDE: Prior year tab has individual records ({content_reason}) - will process")
                role = TabRole.DETAIL
                confidence = 0.75
                logger.info(f"Tab '{tab_name}' reclassified from PRIOR_YEAR to DETAIL: {content_reason}")
            else:
                should_process = False
                skip_reason = f"Prior year data (year: {fiscal_year}, target: {target_tax_year})"
        elif role == TabRole.WORKING:
            # Working tabs can still have real data
            if has_individual_records and data_row_count >= 5:
                notes.append(f"OVERRIDE: Working tab has individual records ({content_reason}) - will process")
                role = TabRole.DETAIL
                confidence = 0.70
                logger.info(f"Tab '{tab_name}' reclassified from WORKING to DETAIL: {content_reason}")
            else:
                should_process = False
                skip_reason = "Working/draft tab - not final data"
        elif data_row_count == 0:
            should_process = False
            skip_reason = "Empty tab - no data rows found"
        elif role == TabRole.SUMMARY:
            # Summary tabs might actually have individual records
            if has_individual_records:
                # Override! This tab has individual asset data, must process it
                notes.append(f"OVERRIDE: Summary tab has individual records ({content_reason})")
                role = TabRole.DETAIL  # Reclassify as detail
                confidence = 0.85
                should_process = True
                skip_reason = None
                logger.info(f"Tab '{tab_name}' reclassified from SUMMARY to DETAIL: {content_reason}")
            else:
                should_process = False
                skip_reason = "Summary tab - contains roll-up totals, not detail data"
        elif role == TabRole.UNKNOWN:
            # CRITICAL: For unknown tabs, ALWAYS check content
            # If content has asset data, process it!
            if has_individual_records or data_row_count >= 5:
                notes.append(f"UNKNOWN tab with data - processing ({content_reason})")
                role = TabRole.DETAIL  # Reclassify as detail
                confidence = 0.70
                logger.info(f"Tab '{tab_name}' reclassified from UNKNOWN to DETAIL: has data")
            elif data_row_count > 0:
                # Even if we're not sure, try processing tabs with some data
                notes.append(f"UNKNOWN tab with {data_row_count} rows - processing to be safe")
                role = TabRole.DETAIL
                confidence = 0.50
                logger.info(f"Tab '{tab_name}' treated as DETAIL: {data_row_count} rows present")

        # Add content analysis to notes
        if unique_id_count > 0:
            notes.append(f"Content check: {unique_id_count} unique Asset IDs found")

        # Flag low confidence for manual review
        low_confidence = confidence < 0.80

        # Create analysis object
        analysis = TabAnalysis(
            tab_name=tab_name,
            role=role,
            fiscal_year=fiscal_year,
            row_count=row_count,
            data_row_count=data_row_count,
            has_cost_data=has_cost,
            has_date_data=has_date,
            should_process=should_process,
            skip_reason=skip_reason,
            confidence=confidence,
            detection_notes=notes,
        )

        result.tabs.append(analysis)

        # Categorize into lists
        if role == TabRole.SUMMARY:
            result.summary_tabs.append(tab_name)
        elif role in (TabRole.DETAIL, TabRole.ADDITIONS, TabRole.UNKNOWN):
            if should_process:
                result.detail_tabs.append(tab_name)
        elif role == TabRole.DISPOSALS:
            result.disposal_tabs.append(tab_name)
        elif role == TabRole.PRIOR_YEAR:
            result.prior_year_tabs.append(tab_name)

    # CRITICAL: Check for data anomalies
    result.warnings = _detect_data_anomalies(result, sheets)

    # Set detected fiscal year start month
    result.detected_fy_start_month = detected_fy_start_month
    result.fy_detection_source = fy_detection_source

    if detected_fy_start_month:
        month_names = {1: "January (Calendar Year)", 4: "April", 7: "July", 10: "October"}
        logger.info(f"[FY Auto-Detection] RESULT: Fiscal year starts in {month_names.get(detected_fy_start_month, f'Month {detected_fy_start_month}')}")
        if detected_fy_start_month != 1:
            result.warnings.insert(0, f"Auto-detected fiscal year: {month_names.get(detected_fy_start_month, f'Month {detected_fy_start_month}')} start from '{fy_detection_source}'")

    logger.info(f"Tab analysis complete: {len(result.tabs_to_process)} to process, {len(result.tabs_to_skip)} to skip")

    return result


def _detect_data_anomalies(result: TabAnalysisResult, sheets: Dict[str, pd.DataFrame]) -> List[str]:
    """
    Detect data anomalies that might indicate misconfigured tabs.

    Critical check: If a "summary" tab has data but detail tabs are empty or missing,
    the user might have put all data in the summary tab by mistake.

    IMPORTANT: This function also AUTO-SELECTS summary tabs when detail tabs are empty,
    to prevent missing data. The user can still deselect if needed.

    Args:
        result: TabAnalysisResult from initial analysis
        sheets: Original sheets dict

    Returns:
        List of warning messages
    """
    warnings = []

    # Get summary and detail tabs
    # NOTE: For anomaly detection, we need ALL detail-role tabs (regardless of should_process)
    # so we can detect cases like "detail tabs exist but are all empty"
    summary_tabs = [t for t in result.tabs if t.role == TabRole.SUMMARY]
    all_detail_tabs = [t for t in result.tabs if t.role in (TabRole.DETAIL, TabRole.ADDITIONS, TabRole.UNKNOWN)]
    processable_detail_tabs = [t for t in all_detail_tabs if t.should_process]

    # Check 1: Summary has data but no detail tabs exist (or none are processable)
    # AUTO-SELECT the summary tab to prevent missing data
    if summary_tabs and not processable_detail_tabs:
        for summary_tab in summary_tabs:
            if summary_tab.data_row_count > 0:
                # AUTO-SELECT: Enable the summary tab since there are no detail tabs
                summary_tab.should_process = True
                summary_tab.skip_reason = None
                summary_tab.detection_notes.append("AUTO-SELECTED: No detail tabs found, summary has data")
                warnings.append(
                    f"✅ AUTO-ENABLED SUMMARY TAB: '{summary_tab.tab_name}' has "
                    f"{summary_tab.data_row_count} rows and no detail tabs were found. "
                    f"Processing this tab to ensure no data is missed."
                )
                logger.info(f"Auto-enabled summary tab '{summary_tab.tab_name}' - no detail tabs found")

    # Check 2: Summary has MORE data than all detail tabs combined
    if summary_tabs and processable_detail_tabs:
        total_detail_rows = sum(t.data_row_count for t in processable_detail_tabs)
        for summary_tab in summary_tabs:
            if summary_tab.data_row_count >= total_detail_rows * 1.5:  # 50% or more
                warnings.append(
                    f"⚠️ SUMMARY TAB HAS MORE DATA: '{summary_tab.tab_name}' has "
                    f"{summary_tab.data_row_count} rows but detail tabs only have "
                    f"{total_detail_rows} rows total. Check if data is missing from detail tabs."
                )

    # Check 3: Detail tabs EXIST but are all empty, but summary has data
    # This catches the case where detail tabs are present but have no data
    # AUTO-SELECT the summary tab
    if all_detail_tabs and summary_tabs:
        non_empty_details = [t for t in all_detail_tabs if t.data_row_count > 0]
        if not non_empty_details:
            for summary_tab in summary_tabs:
                if summary_tab.data_row_count > 0:
                    # AUTO-SELECT: Enable the summary tab since detail tabs are empty
                    summary_tab.should_process = True
                    summary_tab.skip_reason = None
                    summary_tab.detection_notes.append("AUTO-SELECTED: Detail tabs are empty, summary has data")
                    warnings.append(
                        f"✅ AUTO-ENABLED SUMMARY TAB: All detail tabs are empty but "
                        f"'{summary_tab.tab_name}' has {summary_tab.data_row_count} rows. "
                        f"Processing this tab to ensure no data is missed."
                    )
                    logger.info(f"Auto-enabled summary tab '{summary_tab.tab_name}' - detail tabs are empty")

    # Check 4: Only disposal tabs with data but no detail tabs
    disposal_tabs = [t for t in result.tabs if t.role == TabRole.DISPOSALS and t.data_row_count > 0]
    if disposal_tabs and not any(t.data_row_count > 0 for t in all_detail_tabs):
        warnings.append(
            f"ℹ️ DISPOSALS ONLY: Only disposal tabs have data. "
            f"If you expect additions, check that detail tabs have data."
        )

    # Check 5: Low confidence detections that need manual review
    low_confidence_tabs = [t for t in result.tabs if t.confidence < 0.80 and t.data_row_count > 0]
    if low_confidence_tabs:
        tab_names = [t.tab_name for t in low_confidence_tabs[:3]]  # Show first 3
        warnings.append(
            f"🔍 MANUAL REVIEW SUGGESTED: {len(low_confidence_tabs)} tab(s) have low detection confidence: "
            f"{', '.join(tab_names)}{'...' if len(low_confidence_tabs) > 3 else ''}. "
            f"Please verify these are correctly categorized."
        )

    return warnings


def validate_tab_selection(
    result: TabAnalysisResult,
    selected_tabs: List[str],
    sheets: Dict[str, pd.DataFrame]
) -> List[str]:
    """
    Validate user's tab selection and provide warnings if needed.

    Args:
        result: Original TabAnalysisResult
        selected_tabs: User's selected tabs to process
        sheets: Original sheets dict

    Returns:
        List of validation warnings
    """
    warnings = []

    # Check if user is skipping tabs with data
    for tab in result.tabs:
        if tab.tab_name not in selected_tabs and tab.data_row_count > 10:
            warnings.append(
                f"ℹ️ Skipping '{tab.tab_name}' which has {tab.data_row_count} data rows"
            )

    # Check if user selected a summary tab
    for tab in result.tabs:
        if tab.tab_name in selected_tabs and tab.role == TabRole.SUMMARY:
            warnings.append(
                f"⚠️ '{tab.tab_name}' appears to be a summary tab. "
                f"Make sure it contains individual asset records, not just totals."
            )

    return warnings


def format_tab_tree(result: TabAnalysisResult) -> str:
    """
    Format tab analysis as a visual tree for display.

    Args:
        result: TabAnalysisResult

    Returns:
        Formatted string for display
    """
    lines = ["Detected Tabs:"]

    for i, tab in enumerate(result.tabs):
        is_last = i == len(result.tabs) - 1
        prefix = "└──" if is_last else "├──"

        status = "✓ PROCESS" if tab.should_process else "✗ SKIP"
        line = f"{prefix} {tab.icon} {tab.tab_name} ─── [{tab.role_label}] ({tab.data_row_count} rows)"
        lines.append(line)

        if tab.skip_reason:
            indent = "    " if is_last else "│   "
            lines.append(f"{indent}  └─ {tab.skip_reason}")

    return "\n".join(lines)


def get_processing_recommendation(result: TabAnalysisResult) -> Dict[str, Any]:
    """
    Get a processing recommendation summary.

    Args:
        result: TabAnalysisResult

    Returns:
        Dict with recommendation details
    """
    stats = result.get_efficiency_stats()

    return {
        "process_tabs": [t.tab_name for t in result.tabs_to_process],
        "skip_tabs": [t.tab_name for t in result.tabs_to_skip],
        "disposal_tabs": result.disposal_tabs,
        "total_rows_to_process": stats["process_rows"],
        "rows_saved": stats["skip_rows"],
        "efficiency_gain": f"{stats['reduction_percent']:.0f}%",
        "warnings": result.warnings,
        "recommendation": (
            f"Process {stats['process_tabs']} tabs ({stats['process_rows']} rows), "
            f"skip {stats['skip_tabs']} tabs ({stats['skip_rows']} rows). "
            f"Efficiency gain: {stats['reduction_percent']:.0f}% fewer rows to classify."
        )
    }
