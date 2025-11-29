# fixed_asset_ai/logic/spot_checker.py
"""
Sampling/Spot Check System

Provides random sampling of assets for manual verification before export.
This is a critical quality control step - even perfect automation needs human verification.

Features:
1. Random sample selection (configurable %)
2. Stratified sampling (by category, transaction type, risk level)
3. High-value asset inclusion (always sample above threshold)
4. Risk-based sampling (prioritize high-risk assets)
5. Verification checklist generation
"""

import pandas as pd
import numpy as np
from datetime import date
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class SpotCheckItem:
    """Represents an asset selected for spot checking."""
    asset_id: str
    description: str
    cost: float
    category: str
    life: str
    method: str
    convention: str
    transaction_type: str
    selection_reason: str
    verification_checklist: List[str]
    verified: bool = False
    verification_notes: str = ""


@dataclass
class SpotCheckResult:
    """Result of spot check session."""
    total_assets: int
    sample_size: int
    sample_percentage: float
    items: List[SpotCheckItem]
    verified_count: int
    issues_found: int
    approval_status: str  # PENDING, APPROVED, REJECTED


def select_spot_check_sample(
    df: pd.DataFrame,
    sample_percentage: float = 10.0,
    min_sample: int = 5,
    max_sample: int = 50,
    high_value_threshold: float = 100_000,
    include_all_high_risk: bool = True,
    stratify_by: Optional[str] = "Transaction Type"
) -> SpotCheckResult:
    """
    Select a sample of assets for manual spot checking.

    Sampling Strategy:
    1. Always include assets above high_value_threshold
    2. Always include high-risk assets (if risk score available)
    3. Random sample from remaining to meet sample_percentage
    4. Stratify by category or transaction type for coverage

    Args:
        df: Asset dataframe
        sample_percentage: Percentage of assets to sample (default 10%)
        min_sample: Minimum number of assets to sample
        max_sample: Maximum number of assets to sample
        high_value_threshold: Always sample assets above this cost
        include_all_high_risk: Include all assets with risk score > 70
        stratify_by: Column to stratify sample by (ensures coverage)

    Returns:
        SpotCheckResult with selected items
    """
    if df is None or df.empty:
        return SpotCheckResult(
            total_assets=0,
            sample_size=0,
            sample_percentage=0.0,
            items=[],
            verified_count=0,
            issues_found=0,
            approval_status="PENDING"
        )

    total_assets = len(df)
    selected_indices = set()
    selection_reasons = {}

    # 1. Always include high-value assets
    cost_col = "Cost" if "Cost" in df.columns else "Tax Cost"
    if cost_col in df.columns:
        high_value_mask = pd.to_numeric(df[cost_col], errors='coerce') >= high_value_threshold
        high_value_indices = df[high_value_mask].index.tolist()
        for idx in high_value_indices:
            selected_indices.add(idx)
            selection_reasons[idx] = f"High value (>= ${high_value_threshold:,.0f})"

    # 2. Include high-risk assets (if risk score available)
    if include_all_high_risk and "RiskScore" in df.columns:
        high_risk_mask = pd.to_numeric(df["RiskScore"], errors='coerce') < 70  # Lower score = higher risk
        high_risk_indices = df[high_risk_mask].index.tolist()
        for idx in high_risk_indices:
            if idx not in selected_indices:
                selected_indices.add(idx)
                selection_reasons[idx] = "High risk score"

    # 3. Include assets with low classification confidence
    for conf_col in ["Rule Confidence", "Confidence", "Classification Confidence"]:
        if conf_col in df.columns:
            low_conf_mask = pd.to_numeric(df[conf_col], errors='coerce') < 0.7
            low_conf_indices = df[low_conf_mask].index.tolist()
            for idx in low_conf_indices[:10]:  # Limit to 10 low-confidence
                if idx not in selected_indices:
                    selected_indices.add(idx)
                    selection_reasons[idx] = f"Low classification confidence (<70%)"
            break

    # 4. Calculate remaining sample size
    target_sample = max(min_sample, min(max_sample, int(total_assets * sample_percentage / 100)))
    remaining_sample = max(0, target_sample - len(selected_indices))

    # 5. Stratified random sample from remaining
    if remaining_sample > 0:
        remaining_df = df.drop(index=list(selected_indices))

        if stratify_by and stratify_by in remaining_df.columns:
            # Stratified sampling
            groups = remaining_df.groupby(stratify_by)
            samples_per_group = max(1, remaining_sample // len(groups))

            for group_name, group_df in groups:
                n_to_sample = min(samples_per_group, len(group_df))
                if n_to_sample > 0:
                    sampled = group_df.sample(n=n_to_sample, random_state=42)
                    for idx in sampled.index:
                        selected_indices.add(idx)
                        selection_reasons[idx] = f"Random sample ({group_name})"
        else:
            # Simple random sample
            if len(remaining_df) > 0:
                n_to_sample = min(remaining_sample, len(remaining_df))
                sampled = remaining_df.sample(n=n_to_sample, random_state=42)
                for idx in sampled.index:
                    selected_indices.add(idx)
                    selection_reasons[idx] = "Random sample"

    # 6. Build SpotCheckItem list
    items = []
    for idx in selected_indices:
        row = df.loc[idx]
        item = _build_spot_check_item(row, idx, selection_reasons.get(idx, "Selected"))
        items.append(item)

    # Sort by cost (highest first)
    items.sort(key=lambda x: x.cost, reverse=True)

    return SpotCheckResult(
        total_assets=total_assets,
        sample_size=len(items),
        sample_percentage=round(len(items) / total_assets * 100, 1) if total_assets > 0 else 0,
        items=items,
        verified_count=0,
        issues_found=0,
        approval_status="PENDING"
    )


def _build_spot_check_item(row: pd.Series, idx: int, reason: str) -> SpotCheckItem:
    """Build a SpotCheckItem from a dataframe row."""
    asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
    description = str(row.get("Description", "N/A"))

    cost = 0.0
    for cost_col in ["Cost", "Tax Cost"]:
        if cost_col in row.index and pd.notna(row.get(cost_col)):
            try:
                cost = float(row.get(cost_col))
                break
            except (ValueError, TypeError):
                pass

    category = str(row.get("Final Category", row.get("Final Category Used", "N/A")))

    life = "N/A"
    for life_col in ["MACRS Life", "Final Life Used", "Tax Life"]:
        if life_col in row.index and pd.notna(row.get(life_col)):
            life = str(row.get(life_col))
            break

    method = str(row.get("Method", row.get("Tax Method", row.get("Final Method Used", "N/A"))))
    convention = str(row.get("Convention", row.get("Final Conv Used", "N/A")))
    trans_type = str(row.get("Transaction Type", "N/A"))

    # Generate verification checklist based on asset type
    checklist = _generate_verification_checklist(row, category, trans_type)

    return SpotCheckItem(
        asset_id=asset_id,
        description=description,
        cost=cost,
        category=category,
        life=life,
        method=method,
        convention=convention,
        transaction_type=trans_type,
        selection_reason=reason,
        verification_checklist=checklist,
        verified=False,
        verification_notes=""
    )


def _generate_verification_checklist(row: pd.Series, category: str, trans_type: str) -> List[str]:
    """Generate context-specific verification checklist."""
    checklist = [
        "[ ] Description accurately represents the asset",
        "[ ] Cost matches source documentation",
        "[ ] In-service date is correct",
    ]

    # Add category-specific checks
    category_lower = category.lower()

    if "building" in category_lower or "real" in category_lower:
        checklist.extend([
            "[ ] Verify residential (27.5yr) vs commercial (39yr) classification",
            "[ ] Confirm land cost is excluded",
            "[ ] Check for QIP eligibility if interior improvement",
        ])
    elif "vehicle" in category_lower or "auto" in category_lower:
        checklist.extend([
            "[ ] Verify business use percentage documentation",
            "[ ] Check luxury auto limits if applicable",
            "[ ] Confirm 5-year life is appropriate",
        ])
    elif "furniture" in category_lower or "equipment" in category_lower:
        checklist.extend([
            "[ ] Verify 7-year life is appropriate",
            "[ ] Check if could be 5-year (office equipment, computers)",
        ])
    elif "qip" in category_lower or "improvement" in category_lower:
        checklist.extend([
            "[ ] Confirm placed in service after 12/31/2017",
            "[ ] Verify qualifies as interior improvement to nonresidential",
            "[ ] 15-year life is correct",
        ])
    elif "land" in category_lower:
        checklist.extend([
            "[ ] CRITICAL: Land is NOT depreciable",
            "[ ] If land improvement, verify 15-year classification",
        ])

    # Add transaction-specific checks
    trans_lower = trans_type.lower()

    if "addition" in trans_lower:
        checklist.extend([
            "[ ] Verify this is a NEW asset (not previously on books)",
            "[ ] Section 179 election documented if applicable",
            "[ ] Bonus depreciation calculation correct",
        ])
    elif "disposal" in trans_lower:
        checklist.extend([
            "[ ] Verify asset was on prior year books",
            "[ ] Disposal date is correct",
            "[ ] Gain/loss calculation reviewed",
            "[ ] Proceeds amount documented",
        ])
    elif "transfer" in trans_lower:
        checklist.extend([
            "[ ] Verify transfer is between related entities",
            "[ ] Historical cost basis maintained",
            "[ ] Accumulated depreciation carried over",
        ])

    # Add Section 179/Bonus checks if applicable
    sec179 = row.get("Section 179", row.get("Tax Sec 179 Expensed", 0))
    if pd.notna(sec179) and float(sec179 or 0) > 0:
        checklist.append("[ ] Section 179 eligibility verified")
        checklist.append(f"[ ] Section 179 amount (${float(sec179):,.0f}) within annual limit")

    bonus = row.get("Bonus", row.get("Bonus Amount", 0))
    if pd.notna(bonus) and float(bonus or 0) > 0:
        checklist.append("[ ] Bonus depreciation rate correct for tax year")
        checklist.append(f"[ ] Bonus amount (${float(bonus):,.0f}) calculation verified")

    return checklist


def generate_spot_check_report(result: SpotCheckResult) -> str:
    """Generate printable spot check report."""
    lines = []
    lines.append("=" * 70)
    lines.append("SPOT CHECK VERIFICATION REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Total Assets: {result.total_assets}")
    lines.append(f"Sample Size: {result.sample_size} ({result.sample_percentage}%)")
    lines.append(f"Status: {result.approval_status}")
    lines.append("")

    for i, item in enumerate(result.items, 1):
        lines.append(f"--- Asset {i} of {len(result.items)} ---")
        lines.append(f"Asset ID: {item.asset_id}")
        lines.append(f"Description: {item.description}")
        lines.append(f"Cost: ${item.cost:,.2f}")
        lines.append(f"Category: {item.category}")
        lines.append(f"Life: {item.life} | Method: {item.method} | Convention: {item.convention}")
        lines.append(f"Transaction: {item.transaction_type}")
        lines.append(f"Selection Reason: {item.selection_reason}")
        lines.append("")
        lines.append("Verification Checklist:")
        for check in item.verification_checklist:
            lines.append(f"  {check}")
        lines.append("")
        lines.append("Verification Notes: ___________________________________")
        lines.append("")
        lines.append("Verified by: _______________ Date: ___________")
        lines.append("")

    lines.append("=" * 70)
    lines.append("FINAL APPROVAL")
    lines.append("")
    lines.append("[ ] All sampled assets verified and approved")
    lines.append("[ ] Issues found have been documented and resolved")
    lines.append("")
    lines.append("Approved by: _______________ Date: ___________")
    lines.append("=" * 70)

    return "\n".join(lines)


def calculate_sample_size_recommendation(
    total_assets: int,
    risk_level: str = "medium"
) -> Dict:
    """
    Calculate recommended sample size based on total assets and risk level.

    Based on audit sampling standards:
    - Low risk: 5-10%
    - Medium risk: 10-15%
    - High risk: 15-25%
    """
    recommendations = {
        "low": {"percentage": 7.5, "min": 3, "max": 30},
        "medium": {"percentage": 12.5, "min": 5, "max": 50},
        "high": {"percentage": 20.0, "min": 10, "max": 100},
    }

    risk_config = recommendations.get(risk_level.lower(), recommendations["medium"])

    raw_sample = int(total_assets * risk_config["percentage"] / 100)
    recommended_sample = max(risk_config["min"], min(risk_config["max"], raw_sample))

    return {
        "total_assets": total_assets,
        "risk_level": risk_level,
        "recommended_sample": recommended_sample,
        "recommended_percentage": round(risk_config["percentage"], 1),
        "min_sample": risk_config["min"],
        "max_sample": risk_config["max"],
    }
