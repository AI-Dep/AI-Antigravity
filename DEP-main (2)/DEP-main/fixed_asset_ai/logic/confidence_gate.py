# fixed_asset_ai/logic/confidence_gate.py
"""
Classification Confidence Gate

Blocks export when classification confidence is too low.
This prevents RPA from entering potentially incorrect data.

Key Features:
1. Average confidence threshold (default 70%)
2. Individual asset confidence minimum (default 50%)
3. Manual override with acknowledgment
4. Detailed report of low-confidence items

This addresses the critical gap: automated systems should NOT proceed
when they're uncertain about their outputs.
"""

import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class LowConfidenceAsset:
    """Represents an asset with low classification confidence."""
    asset_id: str
    description: str
    category: str
    confidence: float
    source: str  # "rule", "gpt", "fallback"
    reason: str


@dataclass
class ConfidenceGateResult:
    """Result of confidence gate check."""
    passed: bool
    average_confidence: float
    min_confidence: float
    total_assets: int
    low_confidence_count: int
    low_confidence_assets: List[LowConfidenceAsset]
    blocking_reason: Optional[str]
    requires_override: bool
    override_acknowledged: bool = False


# Confidence thresholds
DEFAULT_AVERAGE_THRESHOLD = 0.70  # 70% average required
DEFAULT_MINIMUM_THRESHOLD = 0.50  # No asset below 50%
HIGH_VALUE_THRESHOLD = 50_000     # Extra scrutiny for expensive assets


def check_confidence_gate(
    df: pd.DataFrame,
    average_threshold: float = DEFAULT_AVERAGE_THRESHOLD,
    minimum_threshold: float = DEFAULT_MINIMUM_THRESHOLD,
    high_value_minimum: float = 0.60
) -> ConfidenceGateResult:
    """
    Check if classification confidence meets thresholds for export.

    Args:
        df: Asset dataframe with confidence scores
        average_threshold: Required average confidence (default 70%)
        minimum_threshold: No asset below this (default 50%)
        high_value_minimum: Higher minimum for expensive assets (default 60%)

    Returns:
        ConfidenceGateResult with pass/fail and details
    """
    if df is None or df.empty:
        return ConfidenceGateResult(
            passed=True,
            average_confidence=0.0,
            min_confidence=0.0,
            total_assets=0,
            low_confidence_count=0,
            low_confidence_assets=[],
            blocking_reason=None,
            requires_override=False
        )

    # Find confidence column
    confidence_col = None
    for col in ["Rule Confidence", "Confidence", "Classification Confidence", "GPT Confidence"]:
        if col in df.columns:
            confidence_col = col
            break

    if confidence_col is None:
        # No confidence column - can't gate, assume OK
        return ConfidenceGateResult(
            passed=True,
            average_confidence=1.0,
            min_confidence=1.0,
            total_assets=len(df),
            low_confidence_count=0,
            low_confidence_assets=[],
            blocking_reason=None,
            requires_override=False
        )

    # Find source column
    source_col = None
    for col in ["Source", "Classification Source", "source"]:
        if col in df.columns:
            source_col = col
            break

    # Collect low-confidence assets
    low_confidence_assets = []
    confidences = []
    blocking_reasons = []
    skipped_disposals = 0

    for idx, row in df.iterrows():
        # SKIP DISPOSALS - they don't need classification
        # Disposals are being removed from books, so classification confidence is irrelevant
        trans_type = str(row.get("Transaction Type", "")).lower()
        source = str(row.get(source_col, "unknown")).lower() if source_col else "unknown"

        is_disposal = (
            "disposal" in trans_type or
            "disposed" in trans_type or
            "skipped_disposal" in source or
            "disposal" in source
        )

        if is_disposal:
            skipped_disposals += 1
            continue  # Skip disposals from confidence calculation

        conf = row.get(confidence_col)

        if pd.isna(conf):
            # Missing confidence - treat as 0 (safest assumption)
            conf = 0.0
        else:
            try:
                conf = float(conf)
                # Normalize if stored as percentage
                if conf > 1:
                    conf = conf / 100.0
            except (ValueError, TypeError):
                conf = 0.0

        confidences.append(conf)

        # Check if this asset needs review
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        description = str(row.get("Description", "N/A"))
        category = str(row.get("Final Category", row.get("Final Category Used", "Unknown")))
        # Note: source already defined above for disposal check

        # Determine applicable threshold
        cost = 0.0
        for cost_col in ["Cost", "Tax Cost"]:
            if cost_col in row.index and pd.notna(row.get(cost_col)):
                try:
                    cost = float(row.get(cost_col))
                    break
                except (ValueError, TypeError):
                    pass

        applicable_threshold = minimum_threshold
        if cost >= HIGH_VALUE_THRESHOLD:
            applicable_threshold = max(minimum_threshold, high_value_minimum)

        # Check if below threshold
        if conf < applicable_threshold:
            reason = _determine_low_confidence_reason(conf, cost, source, applicable_threshold)
            low_confidence_assets.append(LowConfidenceAsset(
                asset_id=asset_id,
                description=description[:50] + "..." if len(description) > 50 else description,
                category=category,
                confidence=conf,
                source=source,
                reason=reason
            ))

            if conf < minimum_threshold:
                blocking_reasons.append(f"Asset {asset_id}: {conf:.0%} confidence < {minimum_threshold:.0%} minimum")

    # Calculate statistics (excluding disposals)
    total_assets = len(df) - skipped_disposals
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    min_confidence = min(confidences) if confidences else 0.0
    low_confidence_count = len(low_confidence_assets)

    # Determine if passed
    passed = True
    blocking_reason = None

    if average_confidence < average_threshold:
        passed = False
        blocking_reason = f"Average confidence ({average_confidence:.0%}) is below {average_threshold:.0%} threshold"

    if min_confidence < minimum_threshold:
        passed = False
        if blocking_reason:
            blocking_reason += f"; {low_confidence_count} assets below {minimum_threshold:.0%} minimum"
        else:
            blocking_reason = f"{low_confidence_count} assets have confidence below {minimum_threshold:.0%} minimum"

    return ConfidenceGateResult(
        passed=passed,
        average_confidence=average_confidence,
        min_confidence=min_confidence,
        total_assets=total_assets,
        low_confidence_count=low_confidence_count,
        low_confidence_assets=low_confidence_assets,
        blocking_reason=blocking_reason,
        requires_override=not passed
    )


def _determine_low_confidence_reason(
    confidence: float,
    cost: float,
    source: str,
    threshold: float
) -> str:
    """Generate explanation for why confidence is low."""
    reasons = []

    if confidence < 0.30:
        reasons.append("Very low confidence - likely fallback classification")
    elif confidence < 0.50:
        reasons.append("Low confidence - AI uncertain about category")
    else:
        reasons.append(f"Below {threshold:.0%} threshold")

    if source == "fallback":
        reasons.append("Used fallback (neither rule nor AI matched)")
    elif source == "gpt":
        reasons.append("AI classification (no rule match)")

    if cost >= HIGH_VALUE_THRESHOLD:
        reasons.append(f"High-value asset (${cost:,.0f}) requires extra scrutiny")

    return "; ".join(reasons)


def get_confidence_summary(df: pd.DataFrame) -> Dict:
    """Get summary statistics about classification confidence."""
    result = check_confidence_gate(df)

    return {
        "total_assets": result.total_assets,
        "average_confidence": f"{result.average_confidence:.1%}",
        "min_confidence": f"{result.min_confidence:.1%}",
        "low_confidence_count": result.low_confidence_count,
        "gate_passed": result.passed,
        "blocking_reason": result.blocking_reason,
    }


def generate_confidence_report(result: ConfidenceGateResult) -> str:
    """Generate detailed confidence report."""
    lines = []
    lines.append("=" * 70)
    lines.append("CLASSIFICATION CONFIDENCE REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Status
    if result.passed:
        lines.append("STATUS: PASSED - Confidence thresholds met")
    else:
        lines.append("STATUS: BLOCKED - Confidence thresholds NOT met")
        lines.append(f"REASON: {result.blocking_reason}")
    lines.append("")

    # Statistics
    lines.append("CONFIDENCE STATISTICS:")
    lines.append("-" * 50)
    lines.append(f"  Total Assets:        {result.total_assets}")
    lines.append(f"  Average Confidence:  {result.average_confidence:.1%}")
    lines.append(f"  Minimum Confidence:  {result.min_confidence:.1%}")
    lines.append(f"  Low Confidence:      {result.low_confidence_count} assets")
    lines.append("")

    # Thresholds
    lines.append("THRESHOLDS:")
    lines.append(f"  Average Required:    {DEFAULT_AVERAGE_THRESHOLD:.0%}")
    lines.append(f"  Minimum Required:    {DEFAULT_MINIMUM_THRESHOLD:.0%}")
    lines.append(f"  High-Value Minimum:  {0.60:.0%} (assets >= ${HIGH_VALUE_THRESHOLD:,.0f})")
    lines.append("")

    # Low confidence assets
    if result.low_confidence_assets:
        lines.append(f"LOW CONFIDENCE ASSETS ({len(result.low_confidence_assets)}):")
        lines.append("-" * 50)

        for asset in result.low_confidence_assets[:20]:  # First 20
            lines.append(f"  Asset {asset.asset_id}: {asset.confidence:.0%}")
            lines.append(f"    Category: {asset.category}")
            lines.append(f"    Source: {asset.source}")
            lines.append(f"    Reason: {asset.reason}")
            lines.append("")

        if len(result.low_confidence_assets) > 20:
            lines.append(f"  ... and {len(result.low_confidence_assets) - 20} more")
            lines.append("")

    # Override section
    if result.requires_override:
        lines.append("OVERRIDE REQUIRED:")
        lines.append("-" * 50)
        lines.append("  To proceed with export, you must:")
        lines.append("  [ ] Review all low-confidence assets")
        lines.append("  [ ] Manually verify or correct classifications")
        lines.append("  [ ] Acknowledge risk by checking 'Override confidence gate'")
        lines.append("")
        lines.append("  WARNING: Proceeding without review may result in")
        lines.append("  incorrect tax classifications being entered via RPA.")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def get_assets_requiring_review(df: pd.DataFrame, threshold: float = 0.60) -> pd.DataFrame:
    """
    Get DataFrame of assets that require manual review due to low confidence.

    Args:
        df: Asset dataframe
        threshold: Confidence threshold below which review is required

    Returns:
        DataFrame of assets needing review with relevant columns
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # Find confidence column
    confidence_col = None
    for col in ["Rule Confidence", "Confidence", "Classification Confidence"]:
        if col in df.columns:
            confidence_col = col
            break

    if confidence_col is None:
        return pd.DataFrame()

    # Filter to low confidence
    df_copy = df.copy()
    df_copy["_confidence"] = pd.to_numeric(df_copy[confidence_col], errors='coerce').fillna(0)

    # Normalize if needed
    if df_copy["_confidence"].max() > 1:
        df_copy["_confidence"] = df_copy["_confidence"] / 100.0

    low_conf_mask = df_copy["_confidence"] < threshold

    # Select relevant columns
    display_cols = []
    for col in ["Asset ID", "Asset #", "Description", "Cost", "Tax Cost",
                "Final Category", "Final Category Used", confidence_col,
                "Source", "Transaction Type"]:
        if col in df_copy.columns:
            display_cols.append(col)

    if not display_cols:
        return pd.DataFrame()

    result = df_copy.loc[low_conf_mask, display_cols].copy()
    result = result.drop(columns=["_confidence"], errors="ignore")

    return result
