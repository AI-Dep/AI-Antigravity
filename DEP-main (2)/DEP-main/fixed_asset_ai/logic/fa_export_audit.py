"""
Fixed Asset AI - Export Audit Trail Module

Classification explanations, audit trail generation, and confidence scoring
extracted from fa_export.py for better maintainability.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, Any, Optional

import pandas as pd


# ==============================================================================
# CLASSIFICATION EXPLANATIONS
# ==============================================================================

def _classification_explanation(row) -> str:
    """
    Generate human-readable explanation of classification decision.

    Explains the IRS logic behind the MACRS classification for each asset.

    Args:
        row: DataFrame row with classification data

    Returns:
        Explanation string
    """
    category = str(row.get("Final Category", "")).strip()
    life = row.get("Tax Life") or row.get("Recovery Period") or row.get("MACRS Life")
    trans_type = str(row.get("Transaction Type", ""))

    # Handle disposals/transfers
    if "Disposal" in trans_type:
        return "Disposed asset - recapture rules may apply"
    if "Transfer" in trans_type:
        return "Transferred asset - no depreciation change"

    # Build explanation based on category
    explanations = {
        "Computer": f"5-year property under Rev. Proc. 87-56 (computers and peripheral equipment)",
        "Vehicle": f"5-year property under IRC §168(e)(3)(B) (automobiles and light trucks)",
        "Office Furniture": f"7-year property under Rev. Proc. 87-56 (furniture and fixtures)",
        "Machinery": f"7-year property under Rev. Proc. 87-56 (machinery and equipment)",
        "Land Improvement": f"15-year property under IRC §168(e)(3)(C) (land improvements)",
        "QIP": f"15-year property under IRC §168(e)(6) as amended by CARES Act (qualified improvement property)",
        "Qualified Improvement Property": f"15-year property under IRC §168(e)(6) (qualified improvement property)",
        "Residential": f"27.5-year property under IRC §168(c)(1) (residential rental property)",
        "Nonresidential": f"39-year property under IRC §168(c)(1) (nonresidential real property)",
        "Land": f"Non-depreciable property - land has indefinite useful life",
        "Intangible": f"Section 197 intangible - 15-year amortization under IRC §197",
    }

    # Find matching explanation
    for key, explanation in explanations.items():
        if key.lower() in category.lower():
            return explanation

    # Default explanation
    if life:
        return f"{life}-year MACRS property based on asset classification"

    return "Classification based on asset description and category"


def _macrs_reason_code(row) -> str:
    """
    Generate compact MACRS reason code for audit trail.

    Codes:
    - L0: Land (non-depreciable)
    - LI15: Land Improvement (15-year)
    - QIP15: Qualified Improvement Property (15-year)
    - RP39: Real Property - Nonresidential (39-year)
    - RR27: Residential Rental (27.5-year)
    - V5: Vehicle (5-year)
    - C5: Computer (5-year)
    - F7: Furniture (7-year)
    - M7: Machinery (7-year)
    - I15: Intangible (Section 197)
    - DSP: Disposal
    - XFR: Transfer

    Args:
        row: DataFrame row with classification data

    Returns:
        Reason code string
    """
    category = str(row.get("Final Category", "")).lower()
    trans_type = str(row.get("Transaction Type", ""))

    # Transaction-based codes
    if "Disposal" in trans_type:
        return "DSP"
    if "Transfer" in trans_type:
        return "XFR"

    # Category-based codes
    if "land" in category and "improvement" not in category:
        return "L0"
    if "land improvement" in category:
        return "LI15"
    if "qip" in category or "qualified improvement" in category:
        return "QIP15"
    if "nonresidential" in category or "39" in str(row.get("Tax Life", "")):
        return "RP39"
    if "residential" in category or "27.5" in str(row.get("Tax Life", "")):
        return "RR27"
    if "vehicle" in category or "auto" in category:
        return "V5"
    if "computer" in category:
        return "C5"
    if "furniture" in category:
        return "F7"
    if "machinery" in category or "equipment" in category:
        return "M7"
    if "intangible" in category:
        return "I15"

    # Default based on life
    life = row.get("Tax Life") or row.get("Recovery Period")
    if life:
        return f"Y{int(float(life))}"

    return "UNK"


def _confidence_grade(row) -> str:
    """
    Convert confidence score to letter grade for CPA review.

    Grades:
    - A: 90%+ confidence (high)
    - B: 75-89% confidence (medium)
    - C: 60-74% confidence (low)
    - D: <60% confidence (needs manual review)

    Args:
        row: DataFrame row with confidence data

    Returns:
        Letter grade (A, B, C, or D)
    """
    confidence = row.get("Confidence") or row.get("confidence")

    if confidence is None or pd.isna(confidence):
        return "D"  # No confidence = needs review

    try:
        conf_float = float(confidence)
        if conf_float >= 0.90:
            return "A"
        elif conf_float >= 0.75:
            return "B"
        elif conf_float >= 0.60:
            return "C"
        else:
            return "D"
    except (ValueError, TypeError):
        return "D"


# ==============================================================================
# AUDIT TRAIL GENERATION
# ==============================================================================

def _audit_fields(row) -> Dict[str, Any]:
    """
    Generate comprehensive audit trail fields.

    Creates audit fields including:
    - Source (Rule Engine, GPT, Manual)
    - Rule triggers
    - Warnings
    - Classification hash (SHA256 for integrity)
    - Timestamp

    Args:
        row: DataFrame row with asset data

    Returns:
        Dict with audit field names and values
    """
    audit = {}

    # Source tracking
    source = row.get("Source", row.get("source", ""))
    if "gpt" in str(source).lower():
        audit["AuditSource"] = "GPT Classifier"
    elif "rule" in str(source).lower():
        audit["AuditSource"] = "Rule Engine"
    elif "override" in str(source).lower():
        audit["AuditSource"] = "Manual Override"
    else:
        audit["AuditSource"] = "Client/Fallback"

    # Rule triggers (if from rule engine)
    rule_trigger = row.get("RuleTrigger", row.get("rule_trigger", ""))
    audit["AuditRuleTriggers"] = str(rule_trigger) if rule_trigger else ""

    # Warnings collection
    warnings = []

    # Check NBV reconciliation
    if row.get("NBV_Reco") == "CHECK":
        warnings.append("NBV out of balance")

    # Check for ADS requirement
    if row.get("Uses ADS"):
        warnings.append("ADS required")

    # Check for luxury auto limits
    auto_note = row.get("Auto Limit Notes", "")
    if "§280F" in str(auto_note):
        warnings.append("Luxury auto limits applied")

    # Check confidence
    grade = row.get("ConfidenceGrade", _confidence_grade(row))
    if grade in ("C", "D"):
        warnings.append(f"Low confidence ({grade}) - review recommended")

    audit["AuditWarnings"] = "; ".join(warnings) if warnings else ""

    # Classification hash for integrity verification
    hash_input = "|".join([
        str(row.get("Asset #", "")),
        str(row.get("Final Category", "")),
        str(row.get("Tax Life", "")),
        str(row.get("Tax Method", "")),
        str(row.get("Convention", "")),
    ])
    audit["ClassificationHash"] = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    # Timestamp
    audit["AuditTimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return audit


# ==============================================================================
# EXPORT VALIDATION SUMMARY
# ==============================================================================

def generate_audit_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate audit summary statistics for export.

    Args:
        df: DataFrame with audit fields

    Returns:
        Dict with summary statistics
    """
    summary = {
        "total_assets": len(df),
        "timestamp": datetime.now().isoformat(),
    }

    # Confidence breakdown
    if "ConfidenceGrade" in df.columns:
        summary["confidence_grades"] = df["ConfidenceGrade"].value_counts().to_dict()

    # Review priority breakdown
    if "ReviewPriority" in df.columns:
        summary["review_priorities"] = df["ReviewPriority"].value_counts().to_dict()

    # Source breakdown
    if "AuditSource" in df.columns:
        summary["classification_sources"] = df["AuditSource"].value_counts().to_dict()

    # Warning count
    if "AuditWarnings" in df.columns:
        warnings_with_content = df[df["AuditWarnings"].astype(str).str.len() > 0]
        summary["assets_with_warnings"] = len(warnings_with_content)

    # NBV issues
    if "NBV_Reco" in df.columns:
        summary["nbv_check_count"] = (df["NBV_Reco"] == "CHECK").sum()

    return summary


def format_audit_trail_for_display(row: Dict) -> str:
    """
    Format audit trail fields for human-readable display.

    Args:
        row: Dict with audit field values

    Returns:
        Formatted string for display
    """
    lines = [
        f"Source: {row.get('AuditSource', 'Unknown')}",
        f"Confidence: {row.get('ConfidenceGrade', 'N/A')}",
    ]

    if row.get("AuditRuleTriggers"):
        lines.append(f"Rule: {row['AuditRuleTriggers']}")

    if row.get("AuditWarnings"):
        lines.append(f"Warnings: {row['AuditWarnings']}")

    lines.append(f"Hash: {row.get('ClassificationHash', 'N/A')[:8]}...")
    lines.append(f"Time: {row.get('AuditTimestamp', 'N/A')}")

    return "\n".join(lines)
