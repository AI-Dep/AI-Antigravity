# fixed_asset_ai/logic/smart_column_detector.py
"""
Smart Column Detection Module

Enhances column detection with:
1. Data pattern inference - detect column types from data even when headers are unclear
2. Multi-row header detection - combine adjacent rows to find column names
3. Column mapping confidence scoring - show what was detected and confidence
4. Suggestions for unmapped columns

This module aims to increase the ~70% auto-detection rate to ~85%+
"""

import re
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ColumnInference:
    """Result of inferring a column's type from its data."""
    column_name: str
    inferred_type: str  # "cost", "date", "description", "asset_id", "percentage", "text", "numeric", "unknown"
    confidence: float  # 0.0 to 1.0
    sample_values: List[Any] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)


@dataclass
class ColumnMappingSuggestion:
    """Suggested mapping for a column."""
    excel_column: str
    suggested_logical_field: str
    confidence: float
    source: str  # "header_match", "data_inference", "multi_row_header", "pattern_match"
    evidence: str


@dataclass
class DetectionReport:
    """Full report of column detection results."""
    header_row: int
    detected_mappings: Dict[str, str]  # logical_field -> excel_column
    suggestions: List[ColumnMappingSuggestion]
    unmapped_columns: List[str]
    warnings: List[str]
    overall_confidence: float
    detection_method: str  # "standard", "data_inference", "multi_row_header"


# ============================================================================
# DATA PATTERN ANALYSIS
# ============================================================================

def _is_currency_value(val: Any) -> bool:
    """Check if value looks like currency."""
    if pd.isna(val) or val == "":
        return False
    s = str(val).strip()

    # Must have currency indicator OR be a larger number (>100) OR have decimal
    has_currency_sign = '$' in s or '(' in s  # Accounting format
    has_comma = ',' in s
    has_decimal = '.' in s

    # Simple integers under 100 are likely IDs, not currency
    try:
        num = float(s.replace(',', '').replace('$', '').replace('(', '-').replace(')', ''))
        if abs(num) < 100 and not has_currency_sign and not has_decimal:
            return False
    except:
        pass

    # Matches: $1,234.56, 1234.56, (1,234.56), -1234.56
    if has_currency_sign or has_comma or has_decimal:
        return bool(re.match(r'^[\$\-\(]?[\d,]+\.?\d*[\)]?$', s.replace(',', '')))

    # Plain numbers > 100 might be currency
    try:
        num = float(s)
        return abs(num) >= 100
    except:
        return False


def _is_date_value(val: Any) -> bool:
    """Check if value looks like a date."""
    if pd.isna(val) or val == "":
        return False

    # Already a date type
    if isinstance(val, (datetime, pd.Timestamp)):
        return True

    s = str(val).strip()

    # Common date patterns
    date_patterns = [
        r'^\d{1,2}/\d{1,2}/\d{2,4}$',  # MM/DD/YYYY or M/D/YY
        r'^\d{4}-\d{2}-\d{2}$',         # YYYY-MM-DD
        r'^\d{1,2}-\d{1,2}-\d{2,4}$',   # MM-DD-YYYY
        r'^[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}$',  # January 15, 2024
    ]

    for pattern in date_patterns:
        if re.match(pattern, s):
            return True

    # Try pandas parsing
    try:
        pd.to_datetime(s)
        return True
    except:
        return False


def _is_percentage_value(val: Any) -> bool:
    """Check if value looks like a percentage."""
    if pd.isna(val) or val == "":
        return False
    s = str(val).strip()

    # Must have % sign to be certain, or be a decimal 0.XX
    if '%' in s:
        return True

    try:
        num = float(s)
        # Only decimals between 0 and 1 (exclusive) are likely percentages
        # Integers like 1, 2, 50, 100 could be anything
        if 0 < num < 1:
            return True
        return False
    except:
        return False


def _is_integer_id(val: Any) -> bool:
    """Check if value looks like an integer ID."""
    if pd.isna(val) or val == "":
        return False
    try:
        num = float(val)
        return num == int(num) and num > 0 and num < 1000000
    except:
        return False


def _is_description_value(val: Any) -> bool:
    """Check if value looks like a text description."""
    if pd.isna(val) or val == "":
        return False
    s = str(val).strip()
    # Description should be text, not pure numbers, have some length
    if len(s) < 3:
        return False
    if s.replace(',', '').replace('.', '').replace('-', '').isdigit():
        return False
    return True


def infer_column_type(df: pd.DataFrame, column: str) -> ColumnInference:
    """
    Infer the type of a column based on its data patterns.

    Args:
        df: DataFrame containing the column
        column: Name of the column to analyze

    Returns:
        ColumnInference with detected type and confidence
    """
    if column not in df.columns:
        return ColumnInference(column, "unknown", 0.0, [], ["Column not found"])

    values = df[column].dropna()
    if len(values) == 0:
        return ColumnInference(column, "unknown", 0.0, [], ["Column is empty"])

    sample_values = values.head(5).tolist()
    total = len(values)
    evidence = []

    # Count pattern matches
    currency_count = sum(1 for v in values if _is_currency_value(v))
    date_count = sum(1 for v in values if _is_date_value(v))
    percentage_count = sum(1 for v in values if _is_percentage_value(v))
    integer_id_count = sum(1 for v in values if _is_integer_id(v))
    description_count = sum(1 for v in values if _is_description_value(v))

    # Calculate ratios
    currency_ratio = currency_count / total if total > 0 else 0
    date_ratio = date_count / total if total > 0 else 0
    percentage_ratio = percentage_count / total if total > 0 else 0
    integer_id_ratio = integer_id_count / total if total > 0 else 0
    description_ratio = description_count / total if total > 0 else 0

    # Determine type based on highest ratio
    inferred_type = "unknown"
    confidence = 0.0

    if currency_ratio > 0.7:
        inferred_type = "cost"
        confidence = currency_ratio
        evidence.append(f"{currency_ratio:.0%} of values look like currency")
    elif date_ratio > 0.7:
        inferred_type = "date"
        confidence = date_ratio
        evidence.append(f"{date_ratio:.0%} of values look like dates")
    elif percentage_ratio > 0.7 and all(_is_percentage_value(v) for v in values.head(10)):
        inferred_type = "percentage"
        confidence = percentage_ratio
        evidence.append(f"{percentage_ratio:.0%} of values look like percentages")
    elif integer_id_ratio > 0.8 and values.nunique() == len(values):
        # High ratio of integers + all unique = likely ID
        inferred_type = "asset_id"
        confidence = integer_id_ratio * 0.9  # Slightly lower confidence
        evidence.append(f"Unique integer values suggest Asset ID")
    elif description_ratio > 0.6:
        inferred_type = "description"
        confidence = description_ratio
        evidence.append(f"{description_ratio:.0%} of values are text descriptions")
    else:
        inferred_type = "text"
        confidence = 0.5
        evidence.append("Could not determine specific type")

    return ColumnInference(
        column_name=column,
        inferred_type=inferred_type,
        confidence=confidence,
        sample_values=sample_values,
        evidence=evidence
    )


def infer_all_columns(df: pd.DataFrame) -> Dict[str, ColumnInference]:
    """
    Infer types for all columns in a DataFrame.

    Args:
        df: DataFrame to analyze

    Returns:
        Dict mapping column name to ColumnInference
    """
    inferences = {}
    for col in df.columns:
        inferences[col] = infer_column_type(df, col)
    return inferences


# ============================================================================
# MULTI-ROW HEADER DETECTION
# ============================================================================

def detect_multi_row_headers(
    df_raw: pd.DataFrame,
    max_header_rows: int = 3
) -> Tuple[Optional[int], Optional[List[str]], List[str]]:
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
        Tuple of (header_start_row, combined_headers, warnings)
    """
    warnings = []

    if len(df_raw) < 2:
        return None, None, ["Not enough rows for multi-row header detection"]

    # Known multi-row header patterns
    # These are common split patterns where two rows combine to form a header
    multi_row_patterns = {
        # First row partial -> Full header name
        ("asset", "number"): "asset_id",
        ("asset", "id"): "asset_id",
        ("asset", "#"): "asset_id",
        ("in service", "date"): "in_service_date",
        ("in", "service"): "in_service_date",
        ("placed in", "service"): "in_service_date",
        ("original", "cost"): "cost",
        ("acquisition", "date"): "acquisition_date",
        ("acquisition", "cost"): "cost",
        ("property", "description"): "description",
        ("asset", "description"): "description",
        ("depreciation", "method"): "method",
        ("recovery", "period"): "life",
        ("useful", "life"): "life",
        ("business", "use"): "business_use_pct",
        ("business use", "%"): "business_use_pct",
        ("disposal", "date"): "disposal_date",
        ("sale", "proceeds"): "proceeds",
    }

    # Try combining rows 0+1, 1+2, etc.
    for start_row in range(min(5, len(df_raw) - 1)):
        combined_headers = []
        match_count = 0

        row1 = df_raw.iloc[start_row]
        row2 = df_raw.iloc[start_row + 1]

        for col_idx in range(len(df_raw.columns)):
            val1 = str(row1.iloc[col_idx] if col_idx < len(row1) else "").strip().lower()
            val2 = str(row2.iloc[col_idx] if col_idx < len(row2) else "").strip().lower()

            # Check if this column pair matches a known pattern
            combined = f"{val1} {val2}".strip()

            # Check against patterns
            matched = False
            for (part1, part2), logical_name in multi_row_patterns.items():
                if part1 in val1 and part2 in val2:
                    combined_headers.append(combined)
                    match_count += 1
                    matched = True
                    break

            if not matched:
                # Use the non-empty value or combine
                if val1 and val2:
                    combined_headers.append(combined)
                elif val1:
                    combined_headers.append(val1)
                elif val2:
                    combined_headers.append(val2)
                else:
                    combined_headers.append(f"column_{col_idx}")

        # If we found matches, this is likely a multi-row header
        if match_count >= 2:
            warnings.append(f"Detected multi-row header starting at row {start_row + 1}")
            return start_row, combined_headers, warnings

    return None, None, ["No multi-row header pattern detected"]


# ============================================================================
# SMART COLUMN MAPPING
# ============================================================================

def suggest_column_mappings(
    df: pd.DataFrame,
    existing_mappings: Dict[str, str] = None
) -> List[ColumnMappingSuggestion]:
    """
    Suggest column mappings for unmapped columns based on data patterns.

    Args:
        df: DataFrame to analyze
        existing_mappings: Dict of already-mapped logical_field -> excel_column

    Returns:
        List of ColumnMappingSuggestion for unmapped columns
    """
    existing_mappings = existing_mappings or {}
    mapped_columns = set(existing_mappings.values())

    suggestions = []

    # Infer types for all unmapped columns
    for col in df.columns:
        if col in mapped_columns:
            continue

        inference = infer_column_type(df, col)

        # Map inferred type to logical field
        type_to_field = {
            "cost": "cost",
            "date": "in_service_date",  # Default date to in_service_date
            "percentage": "business_use_pct",
            "asset_id": "asset_id",
            "description": "description",
        }

        if inference.inferred_type in type_to_field:
            logical_field = type_to_field[inference.inferred_type]

            # Don't suggest if this field is already mapped
            if logical_field not in existing_mappings:
                suggestions.append(ColumnMappingSuggestion(
                    excel_column=col,
                    suggested_logical_field=logical_field,
                    confidence=inference.confidence,
                    source="data_inference",
                    evidence="; ".join(inference.evidence)
                ))

        # Special handling for generic "Date" columns
        # If column name is exactly "Date" (case insensitive), suggest as in_service_date
        col_lower = str(col).lower().strip()
        if col_lower in ("date", "dt", "dates") and inference.inferred_type == "date":
            # Boost confidence for exact "Date" column match
            if "in_service_date" not in existing_mappings:
                # Check if we already added a suggestion for this column
                already_suggested = any(s.excel_column == col for s in suggestions)
                if not already_suggested:
                    suggestions.append(ColumnMappingSuggestion(
                        excel_column=col,
                        suggested_logical_field="in_service_date",
                        confidence=0.85,  # Higher confidence for exact "Date" match
                        source="header_match",
                        evidence="Column named 'Date' - likely In-Service Date for CPA purposes"
                    ))

    # Sort by confidence (highest first)
    suggestions.sort(key=lambda x: x.confidence, reverse=True)

    return suggestions


# ============================================================================
# DETECTION REPORT GENERATION
# ============================================================================

def generate_detection_report(
    df_raw: pd.DataFrame,
    detected_mappings: Dict[str, str],
    header_row: int
) -> DetectionReport:
    """
    Generate a comprehensive detection report for user review.

    Args:
        df_raw: Raw DataFrame
        detected_mappings: Dict of logical_field -> excel_column
        header_row: Detected header row number

    Returns:
        DetectionReport with all detection details
    """
    warnings = []

    # Set up DataFrame with detected headers
    if header_row >= 0 and header_row < len(df_raw):
        df = df_raw.iloc[header_row:].copy()
        df.columns = [str(x).strip() for x in df.iloc[0]]
        df = df.iloc[1:].reset_index(drop=True)
    else:
        df = df_raw.copy()

    # Find unmapped columns
    mapped_columns = set(detected_mappings.values())
    unmapped_columns = [col for col in df.columns if col not in mapped_columns]

    # Generate suggestions for unmapped columns
    suggestions = suggest_column_mappings(df, detected_mappings)

    # Check for critical missing mappings
    critical_fields = ["asset_id", "description", "cost", "in_service_date"]
    missing_critical = [f for f in critical_fields if f not in detected_mappings]

    if missing_critical:
        warnings.append(f"Missing critical fields: {', '.join(missing_critical)}")

    # Calculate overall confidence
    if len(detected_mappings) == 0:
        overall_confidence = 0.0
        detection_method = "failed"
    else:
        # Confidence based on critical fields detected
        detected_critical = len([f for f in critical_fields if f in detected_mappings])
        overall_confidence = detected_critical / len(critical_fields)
        detection_method = "standard"

    return DetectionReport(
        header_row=header_row,
        detected_mappings=detected_mappings,
        suggestions=suggestions,
        unmapped_columns=unmapped_columns,
        warnings=warnings,
        overall_confidence=overall_confidence,
        detection_method=detection_method
    )


def format_detection_report(report: DetectionReport) -> str:
    """
    Format detection report as human-readable string.

    Args:
        report: DetectionReport to format

    Returns:
        Formatted string report
    """
    lines = []
    lines.append("=" * 60)
    lines.append("COLUMN DETECTION REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Overall status
    if report.overall_confidence >= 0.75:
        status = "GOOD - Most critical fields detected"
    elif report.overall_confidence >= 0.5:
        status = "PARTIAL - Some fields need manual mapping"
    else:
        status = "NEEDS ATTENTION - Many fields not detected"

    lines.append(f"Status: {status}")
    lines.append(f"Confidence: {report.overall_confidence:.0%}")
    lines.append(f"Header Row: {report.header_row + 1}")
    lines.append(f"Method: {report.detection_method}")
    lines.append("")

    # Detected mappings
    lines.append("DETECTED MAPPINGS:")
    lines.append("-" * 40)
    if report.detected_mappings:
        for logical, excel in sorted(report.detected_mappings.items()):
            lines.append(f"  {logical:25} -> {excel}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Suggestions
    if report.suggestions:
        lines.append("SUGGESTED MAPPINGS (from data patterns):")
        lines.append("-" * 40)
        for sugg in report.suggestions[:5]:  # Top 5
            lines.append(f"  {sugg.suggested_logical_field:25} -> {sugg.excel_column}")
            lines.append(f"    Confidence: {sugg.confidence:.0%}, Evidence: {sugg.evidence[:50]}...")
        lines.append("")

    # Unmapped columns
    if report.unmapped_columns:
        lines.append(f"UNMAPPED COLUMNS ({len(report.unmapped_columns)}):")
        lines.append("-" * 40)
        for col in report.unmapped_columns[:10]:  # First 10
            lines.append(f"  - {col}")
        if len(report.unmapped_columns) > 10:
            lines.append(f"  ... and {len(report.unmapped_columns) - 10} more")
        lines.append("")

    # Warnings
    if report.warnings:
        lines.append("WARNINGS:")
        lines.append("-" * 40)
        for warning in report.warnings:
            lines.append(f"  - {warning}")
        lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


# ============================================================================
# ENHANCED HEADER ROW DETECTION
# ============================================================================

def enhanced_header_detection(
    df_raw: pd.DataFrame,
    max_scan_rows: int = 30,  # Extended from default 20
    try_multi_row: bool = True
) -> Tuple[int, List[str], DetectionReport]:
    """
    Enhanced header detection with extended range and multi-row support.

    Args:
        df_raw: Raw DataFrame without headers set
        max_scan_rows: Maximum rows to scan for headers (default 30, up from 20)
        try_multi_row: Whether to try multi-row header detection

    Returns:
        Tuple of (header_row, column_names, detection_report)
    """
    from .sheet_loader import _detect_header_row, _map_columns_with_validation, _normalize_header

    # First, try standard detection with extended range
    header_idx = _detect_header_row(df_raw, max_scan=max_scan_rows)

    # Extract headers
    df = df_raw.iloc[header_idx:].copy()
    df.columns = [_normalize_header(x) for x in df.iloc[0]]
    df = df.iloc[1:].reset_index(drop=True)

    # Try standard column mapping
    col_map, column_mappings, warnings = _map_columns_with_validation(df, "Sheet")

    # Check if we got critical mappings
    has_description = "description" in col_map
    has_cost = "cost" in col_map

    # If standard detection failed, try multi-row headers
    if try_multi_row and (not has_description or not has_cost):
        multi_start, multi_headers, multi_warnings = detect_multi_row_headers(df_raw)

        if multi_start is not None and multi_headers:
            # Use multi-row headers
            df_multi = df_raw.iloc[multi_start + 2:].copy()  # Skip both header rows
            df_multi.columns = multi_headers

            # Try mapping again with combined headers
            col_map_multi, _, _ = _map_columns_with_validation(df_multi, "Sheet")

            # If multi-row gave better results, use it
            if len(col_map_multi) > len(col_map):
                col_map = col_map_multi
                header_idx = multi_start
                warnings.extend(multi_warnings)
                df = df_multi

    # Generate detection report
    report = generate_detection_report(df_raw, col_map, header_idx)
    report.warnings.extend(warnings)

    # Get column names
    column_names = list(df.columns)

    return header_idx, column_names, report
