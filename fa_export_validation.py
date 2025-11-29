"""
Fixed Asset AI - Export Validation Module

Data quality, NBV reconciliation, and materiality scoring functions
extracted from fa_export.py for better maintainability.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import re
import pandas as pd
from typing import Tuple, List, Optional


# ==============================================================================
# DESCRIPTION TYPO CORRECTIONS
# ==============================================================================

# Common description typos found in client data
DESC_TYPOS = {
    # Misspellings
    r"\bcemra\b": "camera",
    r"\bcomupter\b": "computer",
    r"\bcompter\b": "computer",
    r"\bfurntire\b": "furniture",
    r"\bfurniutre\b": "furniture",
    r"\bequipemnt\b": "equipment",
    r"\bequipmet\b": "equipment",
    r"\bvehcile\b": "vehicle",
    r"\bvehilce\b": "vehicle",
    r"\bmachnie\b": "machine",
    r"\bmachinrey\b": "machinery",
    r"\belectornics\b": "electronics",
    r"\belectrnoics\b": "electronics",
    r"\bapplaince\b": "appliance",
    r"\bapplinace\b": "appliance",
    r"\bsoftwrae\b": "software",
    r"\bsotfware\b": "software",
    r"\bprinter\b": "printer",
    r"\bpritner\b": "printer",
    r"\bmoniter\b": "monitor",
    r"\bmontior\b": "monitor",
    r"\bservr\b": "server",
    r"\bserevr\b": "server",
    r"\brouetr\b": "router",
    r"\broouter\b": "router",
    r"\bswtich\b": "switch",
    r"\bswicth\b": "switch",
    # Common abbreviation fixes
    r"\bcomp\.\s*eq\b": "computer equipment",
    r"\boff\.\s*eq\b": "office equipment",
    r"\bfurn\.\s*&\s*fix\b": "furniture and fixtures",
}

# Client category typo fixes
CLIENT_CAT_FIXES = {
    r"compuuter": "computer",
    r"furtniture": "furniture",
    r"vehicel": "vehicle",
    r"equipemtn": "equipment",
    r"machienry": "machinery",
    r"elecetronics": "electronics",
    r"improvemnets": "improvements",
    r"imporvement": "improvement",
}


def _normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, strip)."""
    if not text:
        return ""
    return str(text).lower().strip()


def _fix_description(description: str) -> Tuple[str, bool, str]:
    """
    Fix common description typos.

    Args:
        description: Asset description text

    Returns:
        Tuple of (corrected_text, was_corrected, correction_note)
    """
    if not description:
        return "", False, ""

    original = str(description)
    corrected = original

    corrections_made = []

    for pattern, replacement in DESC_TYPOS.items():
        if re.search(pattern, corrected, re.IGNORECASE):
            corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
            corrections_made.append(f"{pattern} -> {replacement}")

    was_corrected = corrected != original
    note = "; ".join(corrections_made) if corrections_made else ""

    return corrected, was_corrected, note


def _fix_client_category(category: str) -> Tuple[str, bool, str]:
    """
    Fix common client category typos.

    Args:
        category: Client category text

    Returns:
        Tuple of (corrected_text, was_corrected, correction_note)
    """
    if not category:
        return "", False, ""

    original = str(category)
    corrected = original

    corrections_made = []

    for pattern, replacement in CLIENT_CAT_FIXES.items():
        if re.search(pattern, corrected, re.IGNORECASE):
            corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
            corrections_made.append(f"{pattern} -> {replacement}")

    was_corrected = corrected != original
    note = "; ".join(corrections_made) if corrections_made else ""

    return corrected, was_corrected, note


# ==============================================================================
# NBV RECONCILIATION
# ==============================================================================

def _compute_nbv_reco(df: pd.DataFrame, tolerance: float = 5.0) -> pd.DataFrame:
    """
    Compute Net Book Value reconciliation.

    Validates that NBV = Cost - Accumulated Depreciation within tolerance.
    If NBV is missing, computes it from the formula.

    Args:
        df: DataFrame with Tax Cost and Tax Prior Depreciation columns
        tolerance: Dollar tolerance for reconciliation (default $5.00)

    Returns:
        DataFrame with NBV, NBV_Computed, and NBV_Reco columns added
    """
    df = df.copy()

    # Get cost and accumulated depreciation
    cost = pd.to_numeric(df.get("Tax Cost", 0), errors='coerce').fillna(0)
    accum_depr = pd.to_numeric(
        df.get("Tax Prior Depreciation", df.get("Accumulated Depreciation", 0)),
        errors='coerce'
    ).fillna(0)

    # Compute expected NBV
    df["NBV_Computed"] = cost - accum_depr

    # Get existing NBV or use computed
    if "NBV" in df.columns:
        nbv = pd.to_numeric(df["NBV"], errors='coerce')
        # Fill missing NBV with computed
        df["NBV"] = nbv.fillna(df["NBV_Computed"])
    else:
        df["NBV"] = df["NBV_Computed"]

    # Reconciliation check
    df["NBV_Diff"] = abs(df["NBV"] - df["NBV_Computed"])
    df["NBV_Reco"] = df["NBV_Diff"].apply(
        lambda x: "OK" if x <= tolerance else "CHECK"
    )

    return df


# ==============================================================================
# MATERIALITY SCORING
# ==============================================================================

def _compute_materiality(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute materiality scores for CPA review prioritization.

    Assigns a 0-100 score based on relative cost, with review priority:
    - High: Score >= 70 (top 30% by cost)
    - Medium: Score 40-69
    - Low: Score < 40

    Args:
        df: DataFrame with Tax Cost column

    Returns:
        DataFrame with MaterialityScore and ReviewPriority columns added
    """
    df = df.copy()

    cost = pd.to_numeric(df.get("Tax Cost", 0), errors='coerce').fillna(0)

    # Compute materiality score (0-100 based on percentile)
    if cost.max() > 0:
        # Rank-based scoring (higher cost = higher score)
        df["MaterialityScore"] = (cost.rank(pct=True) * 100).round(2)
    else:
        df["MaterialityScore"] = 0.0

    # Assign review priority
    def get_priority(score):
        if score >= 70:
            return "High"
        elif score >= 40:
            return "Medium"
        else:
            return "Low"

    df["ReviewPriority"] = df["MaterialityScore"].apply(get_priority)

    return df


# ==============================================================================
# TRANSACTION TYPE HELPERS
# ==============================================================================

def _is_disposal(row) -> bool:
    """Check if row represents a disposal transaction."""
    trans_type = str(row.get("Transaction Type", "")).lower()
    if "disposal" in trans_type:
        return True

    # Check for disposal date
    disposal_date = row.get("Disposal Date") or row.get("Date Disposed")
    if disposal_date and pd.notna(disposal_date):
        return True

    # Check description keywords
    desc = str(row.get("Description", "")).lower()
    return any(kw in desc for kw in ["disposed", "sold", "retired", "scrapped"])


def _is_transfer(row) -> bool:
    """Check if row represents a transfer/reclassification."""
    trans_type = str(row.get("Transaction Type", "")).lower()
    if "transfer" in trans_type:
        return True

    desc = str(row.get("Description", "")).lower()
    return any(kw in desc for kw in ["transfer", "xfer", "reclass"])


def _is_current_year(in_service_date, tax_year: int) -> bool:
    """Check if asset was placed in service in the current tax year."""
    if in_service_date is None or pd.isna(in_service_date):
        return False

    try:
        if hasattr(in_service_date, 'year'):
            return in_service_date.year == tax_year
        else:
            # Try to parse string date
            from .parse_utils import parse_date
            parsed = parse_date(in_service_date)
            return parsed.year == tax_year if parsed else False
    except Exception:
        return False


# ==============================================================================
# DATE FORMATTING
# ==============================================================================

def _format_date_for_fa_cs(date_series: pd.Series) -> pd.Series:
    """
    Format date series for FA CS import (M/D/YYYY format).

    FA CS expects clean dates like "1/1/2024" not "2024-01-01 00:00:00".
    Uses platform-independent formatting.

    Args:
        date_series: Pandas Series of datetime values

    Returns:
        Series of formatted date strings
    """
    def format_single_date(dt):
        if pd.isna(dt):
            return ""
        try:
            # Platform-independent: use .month, .day, .year directly
            return f"{dt.month}/{dt.day}/{dt.year}"
        except Exception:
            return ""

    return date_series.apply(format_single_date)


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def _pick(*values):
    """Return first non-null, non-empty value from arguments."""
    for v in values:
        if v is not None and v != "" and not (isinstance(v, float) and pd.isna(v)):
            return v
    return None
