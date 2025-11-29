# fixed_asset_ai/logic/parse_utils.py
"""
Parsing Utilities Module

Handles safe parsing of numbers, dates, and text from various input formats.
Includes proper error handling and logging for debugging data quality issues.
"""

import re
import pandas as pd
from datetime import datetime, date
from typing import Optional, Tuple, Union, List

from .logging_utils import get_logger
from .constants import (
    EXCEL_SERIAL_DATE_BASE,
    MIN_EXCEL_SERIAL_DATE,
    EARLIEST_REASONABLE_DATE,
    MAX_FUTURE_YEARS,
)

logger = get_logger(__name__)


# ==============================================================================
# NUMBER PARSING
# ==============================================================================

def parse_number(v, default: Optional[float] = None) -> Optional[float]:
    """
    Parse a numeric value from various formats.

    Handles:
    - String numbers with commas: "1,234.56" -> 1234.56
    - String numbers with currency: "$1,234.56" -> 1234.56
    - Accounting format negatives: "(1,234.56)" -> -1234.56
    - Already numeric values

    Args:
        v: Value to parse
        default: Default value if parsing fails

    Returns:
        Parsed float or default value
    """
    if pd.isna(v) or v == "" or v is None:
        return default

    try:
        # Already a number
        if isinstance(v, (int, float)):
            return float(v)

        # Convert to string and clean
        s = str(v).strip()

        # Handle accounting format negatives: (1,234.56)
        is_negative = False
        if s.startswith("(") and s.endswith(")"):
            is_negative = True
            s = s[1:-1]

        # Remove currency symbols and commas
        s = re.sub(r"[$,€£¥]", "", s)

        # Handle leading minus sign
        if s.startswith("-"):
            is_negative = True
            s = s[1:]

        # Parse
        result = float(s)

        if is_negative:
            result = -result

        return result

    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Failed to parse number from '{v}': {e}")
        return default


def parse_percentage(v, default: Optional[float] = None) -> Optional[float]:
    """
    Parse a percentage value.

    Handles:
    - "50%" -> 0.50
    - "0.50" -> 0.50
    - 50 -> 0.50 (if > 1, assumes percentage)

    Args:
        v: Value to parse
        default: Default value if parsing fails

    Returns:
        Parsed percentage as decimal (0.0 to 1.0) or default
    """
    if pd.isna(v) or v == "" or v is None:
        return default

    try:
        s = str(v).strip()

        # Remove percentage sign
        if "%" in s:
            s = s.replace("%", "")
            result = float(s) / 100.0
        else:
            result = float(s)
            # If > 1, assume it's a percentage that needs conversion
            if result > 1.0:
                result = result / 100.0

        # Clamp to [0, 1]
        return max(0.0, min(1.0, result))

    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Failed to parse percentage from '{v}': {e}")
        return default


# ==============================================================================
# DATE PARSING
# ==============================================================================

class DateParseResult:
    """Result of date parsing with optional warning message."""

    def __init__(
        self,
        value: Optional[pd.Timestamp],
        success: bool = True,
        warning: Optional[str] = None,
        original_value: str = ""
    ):
        self.value = value
        self.success = success
        self.warning = warning
        self.original_value = original_value

    def __bool__(self):
        return self.value is not None


def parse_date(
    v,
    warn_on_failure: bool = False,
    context: str = ""
) -> Optional[pd.Timestamp]:
    """
    Parse a date value from various formats.

    Handles:
    - Excel serial dates (e.g., 45000 -> 2023-03-14)
    - ISO format: "2023-03-14"
    - US format: "03/14/2023", "3/14/2023"
    - European format: "14/03/2023" (with dayfirst=True fallback)
    - Embedded dates in text: "Acquired on 03/14/2023"

    Args:
        v: Value to parse
        warn_on_failure: If True, log warning when parsing fails
        context: Context string for better error messages (e.g., "Asset ID 123")

    Returns:
        Parsed pandas Timestamp or None if parsing fails

    Note:
        To get full parse result with warnings, use parse_date_with_warning()
    """
    result = parse_date_with_warning(v, context)

    if warn_on_failure and result.warning:
        logger.warning(result.warning)

    return result.value


def parse_date_with_warning(v, context: str = "") -> DateParseResult:
    """
    Parse a date with detailed result including any warnings.

    This is the comprehensive date parser that returns both the parsed
    value and any warnings that occurred during parsing.

    Args:
        v: Value to parse
        context: Context string for error messages

    Returns:
        DateParseResult with value, success flag, and optional warning
    """
    original = str(v) if v is not None else ""

    # Handle empty/null values
    if pd.isna(v) or v == "" or v is None:
        return DateParseResult(None, True, None, original)

    # Excel serial dates (integer values > 30000)
    if isinstance(v, (int, float)) and v > MIN_EXCEL_SERIAL_DATE:
        try:
            base = pd.to_datetime(EXCEL_SERIAL_DATE_BASE)
            result = base + pd.to_timedelta(int(v), unit="D")

            # Sanity check
            if result.year < EARLIEST_REASONABLE_DATE.year:
                warning = f"Excel serial date {v} parsed to unreasonably old date {result.strftime('%Y-%m-%d')}"
                if context:
                    warning = f"{context}: {warning}"
                return DateParseResult(None, False, warning, original)

            return DateParseResult(result, True, None, original)
        except (ValueError, TypeError, OverflowError) as e:
            warning = f"Failed to parse Excel serial date {v}: {e}"
            if context:
                warning = f"{context}: {warning}"
            logger.debug(warning)

    # Already a datetime-like object
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return DateParseResult(pd.Timestamp(v), True, None, original)

    # String parsing
    try:
        dt = pd.to_datetime(v)

        # Future date check
        max_year = datetime.now().year + MAX_FUTURE_YEARS
        if dt.year > max_year:
            warning = f"Date '{v}' is too far in the future (year {dt.year})"
            if context:
                warning = f"{context}: {warning}"
            return DateParseResult(None, False, warning, original)

        # Very old date check
        if dt.year < EARLIEST_REASONABLE_DATE.year:
            warning = f"Date '{v}' is unreasonably old (year {dt.year})"
            if context:
                warning = f"{context}: {warning}"
            return DateParseResult(None, False, warning, original)

        return DateParseResult(dt, True, None, original)

    except (ValueError, TypeError, pd.errors.OutOfBoundsDatetime):
        pass

    # Try to extract date from text (e.g., "Acquired on 03/14/2023")
    m = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", str(v))
    if m:
        try:
            dt = pd.to_datetime(m.group(0))
            return DateParseResult(dt, True, None, original)
        except (ValueError, TypeError, pd.errors.OutOfBoundsDatetime):
            pass

    # Try European format (day first)
    try:
        dt = pd.to_datetime(v, dayfirst=True)
        return DateParseResult(dt, True, None, original)
    except (ValueError, TypeError, pd.errors.OutOfBoundsDatetime):
        pass

    # Parsing failed
    warning = f"Could not parse date from value '{v}'"
    if context:
        warning = f"{context}: {warning}"

    return DateParseResult(None, False, warning, original)


def validate_date_chronology(
    acquisition_date: Optional[pd.Timestamp],
    in_service_date: Optional[pd.Timestamp],
    disposal_date: Optional[pd.Timestamp] = None
) -> Tuple[bool, List[str]]:
    """
    Validate that dates are in chronological order.

    Expected order: Acquisition Date <= In-Service Date <= Disposal Date

    Args:
        acquisition_date: Date asset was acquired
        in_service_date: Date asset was placed in service
        disposal_date: Date asset was disposed (optional)

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check acquisition <= in-service
    if acquisition_date and in_service_date:
        if acquisition_date > in_service_date:
            errors.append(
                f"Acquisition Date ({acquisition_date.strftime('%Y-%m-%d')}) "
                f"is after In-Service Date ({in_service_date.strftime('%Y-%m-%d')})"
            )

    # Check in-service <= disposal
    if in_service_date and disposal_date:
        if in_service_date > disposal_date:
            errors.append(
                f"In-Service Date ({in_service_date.strftime('%Y-%m-%d')}) "
                f"is after Disposal Date ({disposal_date.strftime('%Y-%m-%d')})"
            )

    # Check acquisition <= disposal
    if acquisition_date and disposal_date:
        if acquisition_date > disposal_date:
            errors.append(
                f"Acquisition Date ({acquisition_date.strftime('%Y-%m-%d')}) "
                f"is after Disposal Date ({disposal_date.strftime('%Y-%m-%d')})"
            )

    return len(errors) == 0, errors


# ==============================================================================
# TEXT SANITIZATION
# ==============================================================================

def sanitize_asset_description(text: str) -> str:
    """
    Sanitize asset description for logging/display.

    Removes potentially sensitive information like long alphanumeric IDs
    that might be serial numbers, account numbers, etc.

    Args:
        text: Raw description text

    Returns:
        Sanitized description
    """
    if not isinstance(text, str):
        return ""

    # Redact long alphanumeric sequences (likely serial numbers, IDs)
    sanitized = re.sub(r"[A-Z0-9]{8,}", "[REDACTED ID]", text)

    return sanitized.strip()


def normalize_string(s: str) -> str:
    """
    Normalize a string for comparison.

    - Strips whitespace
    - Converts to lowercase
    - Removes extra internal whitespace

    Args:
        s: String to normalize

    Returns:
        Normalized string
    """
    if not s:
        return ""

    return " ".join(str(s).strip().lower().split())


# ==============================================================================
# SAFE COLUMN ACCESS
# ==============================================================================

def safe_get(d, keys: Union[str, List[str]], default=""):
    """
    Safely get value from dict or pandas Series using multiple possible keys.

    Args:
        d: Dictionary or pandas Series
        keys: Single key or list of possible keys to try
        default: Default value if no key found

    Returns:
        Value from first matching key, or default
    """
    if isinstance(keys, str):
        keys = [keys]

    if not hasattr(d, 'get') and not hasattr(d, '__getitem__'):
        return default

    for k in keys:
        try:
            if hasattr(d, 'get'):
                val = d.get(k)
            else:
                val = d[k] if k in d else None

            if val is not None and val != "":
                return val
        except (KeyError, AttributeError):
            continue

    return default
