# fixed_asset_ai/logic/prior_year_reconciler.py
"""
Prior Year Reconciliation Module

Compares current year asset schedule to prior year to detect:
1. Missing assets (in prior year but not current year - should be disposal?)
2. New assets (not disposals but previously existed)
3. Changed values (cost, life, method changed unexpectedly)
4. Verification of disposals against prior year

This is CRITICAL for tax accuracy - most errors come from:
- Forgetting to dispose of sold assets
- Double-counting assets
- Changing depreciation method without proper election
"""

import pandas as pd
from datetime import date
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ReconciliationIssue:
    """Represents a prior year reconciliation issue."""
    severity: str  # CRITICAL, ERROR, WARNING
    asset_id: str
    issue_type: str  # MISSING, CHANGED, DUPLICATE, UNEXPECTED
    message: str
    prior_value: str
    current_value: str
    suggestion: str


def reconcile_to_prior_year(
    current_df: pd.DataFrame,
    prior_df: pd.DataFrame,
    id_column: str = "Asset ID",
    tolerance: float = 0.01
) -> Tuple[List[ReconciliationIssue], Dict]:
    """
    Reconcile current year schedule to prior year.

    Args:
        current_df: Current year asset schedule
        prior_df: Prior year asset schedule (from FA CS export or prior return)
        id_column: Column to use for asset identification
        tolerance: Tolerance for numeric comparisons

    Returns:
        Tuple of (issues list, summary dict)
    """
    issues = []
    summary = {
        "prior_year_count": len(prior_df) if prior_df is not None else 0,
        "current_year_count": len(current_df) if current_df is not None else 0,
        "matched_count": 0,
        "missing_count": 0,
        "new_count": 0,
        "changed_count": 0,
        "reconciled": False,
    }

    if prior_df is None or prior_df.empty:
        summary["reconciled"] = True  # No prior year = nothing to reconcile
        return issues, summary

    if current_df is None or current_df.empty:
        issues.append(ReconciliationIssue(
            severity="CRITICAL",
            asset_id="ALL",
            issue_type="MISSING",
            message="Current year schedule is empty but prior year has assets",
            prior_value=f"{len(prior_df)} assets",
            current_value="0 assets",
            suggestion="Load current year asset schedule"
        ))
        return issues, summary

    # Normalize ID column
    if id_column not in current_df.columns:
        # Try alternatives
        for alt in ["Asset #", "AssetID", "Asset_ID", "Original Asset ID"]:
            if alt in current_df.columns:
                id_column = alt
                break

    if id_column not in prior_df.columns:
        for alt in ["Asset #", "AssetID", "Asset_ID", "Original Asset ID"]:
            if alt in prior_df.columns:
                id_column = alt
                break

    if id_column not in current_df.columns or id_column not in prior_df.columns:
        issues.append(ReconciliationIssue(
            severity="WARNING",
            asset_id="ALL",
            issue_type="SYSTEM",
            message=f"Cannot find matching ID column in both schedules",
            prior_value=str(prior_df.columns.tolist()[:5]),
            current_value=str(current_df.columns.tolist()[:5]),
            suggestion="Ensure both schedules have Asset ID or Asset # column"
        ))
        return issues, summary

    # Get asset IDs from both years (excluding disposed in prior year)
    prior_ids = set()
    for idx, row in prior_df.iterrows():
        asset_id = row.get(id_column)
        trans_type = str(row.get("Transaction Type", "")).lower()
        # Don't include assets that were disposed in prior year
        if "disposal" not in trans_type and pd.notna(asset_id):
            prior_ids.add(str(asset_id).strip())

    current_ids = set()
    current_disposals = set()
    for idx, row in current_df.iterrows():
        asset_id = row.get(id_column)
        trans_type = str(row.get("Transaction Type", "")).lower()
        if pd.notna(asset_id):
            asset_id_str = str(asset_id).strip()
            current_ids.add(asset_id_str)
            if "disposal" in trans_type:
                current_disposals.add(asset_id_str)

    # Find missing assets (in prior, not in current)
    missing_ids = prior_ids - current_ids
    for asset_id in missing_ids:
        prior_row = prior_df[prior_df[id_column].astype(str).str.strip() == asset_id].iloc[0]
        cost = prior_row.get("Cost", prior_row.get("Tax Cost", "N/A"))
        desc = prior_row.get("Description", "N/A")

        issues.append(ReconciliationIssue(
            severity="CRITICAL",
            asset_id=asset_id,
            issue_type="MISSING",
            message=f"Asset in prior year but NOT in current year",
            prior_value=f"Cost: ${float(cost):,.2f}, Desc: {desc}" if pd.notna(cost) else f"Desc: {desc}",
            current_value="NOT FOUND",
            suggestion="Was this asset disposed? Add disposal record. If still owned, add to current year."
        ))
        summary["missing_count"] += 1

    # Find new assets that aren't marked as additions
    matched_ids = prior_ids & current_ids
    summary["matched_count"] = len(matched_ids)

    # Check for changed values on matched assets
    for asset_id in matched_ids:
        prior_row = prior_df[prior_df[id_column].astype(str).str.strip() == asset_id].iloc[0]
        current_row = current_df[current_df[id_column].astype(str).str.strip() == asset_id].iloc[0]

        # Check cost change
        prior_cost = prior_row.get("Cost", prior_row.get("Tax Cost"))
        current_cost = current_row.get("Cost", current_row.get("Tax Cost"))

        if pd.notna(prior_cost) and pd.notna(current_cost):
            try:
                prior_cost_num = float(prior_cost)
                current_cost_num = float(current_cost)

                if abs(prior_cost_num - current_cost_num) > tolerance:
                    issues.append(ReconciliationIssue(
                        severity="ERROR",
                        asset_id=asset_id,
                        issue_type="CHANGED",
                        message="Cost changed from prior year",
                        prior_value=f"${prior_cost_num:,.2f}",
                        current_value=f"${current_cost_num:,.2f}",
                        suggestion="Cost basis should not change. Verify if this is correct or a data error."
                    ))
                    summary["changed_count"] += 1
            except (ValueError, TypeError):
                pass

        # Check MACRS life change
        prior_life = prior_row.get("MACRS Life", prior_row.get("Tax Life"))
        current_life = current_row.get("MACRS Life", current_row.get("Tax Life"))

        if pd.notna(prior_life) and pd.notna(current_life):
            try:
                prior_life_num = float(prior_life)
                current_life_num = float(current_life)

                if prior_life_num != current_life_num:
                    issues.append(ReconciliationIssue(
                        severity="CRITICAL",
                        asset_id=asset_id,
                        issue_type="CHANGED",
                        message="MACRS life changed from prior year",
                        prior_value=f"{prior_life_num} years",
                        current_value=f"{current_life_num} years",
                        suggestion="Cannot change MACRS life after asset is placed in service. Requires Form 3115."
                    ))
                    summary["changed_count"] += 1
            except (ValueError, TypeError):
                pass

        # Check method change
        prior_method = str(prior_row.get("Method", prior_row.get("Tax Method", ""))).upper()
        current_method = str(current_row.get("Method", current_row.get("Tax Method", ""))).upper()

        if prior_method and current_method and prior_method != current_method:
            issues.append(ReconciliationIssue(
                severity="CRITICAL",
                asset_id=asset_id,
                issue_type="CHANGED",
                message="Depreciation method changed from prior year",
                prior_value=prior_method,
                current_value=current_method,
                suggestion="Cannot change depreciation method without Form 3115 (accounting method change)."
            ))
            summary["changed_count"] += 1

    # Verify disposals existed in prior year
    for asset_id in current_disposals:
        if asset_id not in prior_ids:
            current_row = current_df[current_df[id_column].astype(str).str.strip() == asset_id].iloc[0]
            desc = current_row.get("Description", "N/A")

            issues.append(ReconciliationIssue(
                severity="ERROR",
                asset_id=asset_id,
                issue_type="UNEXPECTED",
                message="Disposal for asset that wasn't in prior year",
                prior_value="NOT FOUND",
                current_value=f"Disposal - {desc}",
                suggestion="Verify this is correct. Cannot dispose of asset that wasn't previously on books."
            ))

    # Calculate new assets (in current but not prior, not marked as addition)
    new_ids = current_ids - prior_ids - current_disposals
    for asset_id in new_ids:
        current_row = current_df[current_df[id_column].astype(str).str.strip() == asset_id].iloc[0]
        trans_type = str(current_row.get("Transaction Type", "")).lower()

        if "addition" not in trans_type and "new" not in trans_type:
            desc = current_row.get("Description", "N/A")
            issues.append(ReconciliationIssue(
                severity="WARNING",
                asset_id=asset_id,
                issue_type="NEW",
                message="New asset not marked as addition",
                prior_value="NOT IN PRIOR YEAR",
                current_value=f"{desc}",
                suggestion="Mark as 'Current Year Addition' for proper tracking."
            ))
            summary["new_count"] += 1

    # Determine overall reconciliation status
    critical_count = len([i for i in issues if i.severity == "CRITICAL"])
    summary["reconciled"] = critical_count == 0

    return issues, summary


def reconcile_cost_totals(
    current_df: pd.DataFrame,
    prior_df: pd.DataFrame,
    prior_ending_balance: Optional[float] = None
) -> Tuple[bool, Dict]:
    """
    Reconcile total cost basis between years.

    Formula:
    Prior Ending Balance + Additions - Disposals = Current Ending Balance

    Args:
        current_df: Current year schedule
        prior_df: Prior year schedule
        prior_ending_balance: Optional explicit prior ending balance (if different from prior_df total)

    Returns:
        Tuple of (is_reconciled, details dict)
    """
    details = {
        "prior_ending": 0.0,
        "additions": 0.0,
        "disposals": 0.0,
        "expected_current": 0.0,
        "actual_current": 0.0,
        "variance": 0.0,
        "is_reconciled": False,
    }

    # Calculate prior ending balance
    if prior_ending_balance is not None:
        details["prior_ending"] = prior_ending_balance
    elif prior_df is not None and not prior_df.empty:
        cost_col = "Cost" if "Cost" in prior_df.columns else "Tax Cost"
        if cost_col in prior_df.columns:
            # Exclude disposals from prior year ending balance
            if "Transaction Type" in prior_df.columns:
                non_disposal = ~prior_df["Transaction Type"].astype(str).str.lower().str.contains("disposal", na=False)
                details["prior_ending"] = prior_df.loc[non_disposal, cost_col].sum()
            else:
                details["prior_ending"] = prior_df[cost_col].sum()

    # Calculate current year activity
    if current_df is not None and not current_df.empty:
        cost_col = "Cost" if "Cost" in current_df.columns else "Tax Cost"

        if cost_col in current_df.columns and "Transaction Type" in current_df.columns:
            trans_type = current_df["Transaction Type"].astype(str).str.lower()

            # Additions
            additions_mask = trans_type.str.contains("addition", na=False)
            details["additions"] = current_df.loc[additions_mask, cost_col].sum()

            # Disposals
            disposals_mask = trans_type.str.contains("disposal", na=False)
            details["disposals"] = current_df.loc[disposals_mask, cost_col].sum()

            # Current ending balance (non-disposals)
            non_disposal_mask = ~disposals_mask
            details["actual_current"] = current_df.loc[non_disposal_mask, cost_col].sum()

    # Calculate expected current balance
    details["expected_current"] = details["prior_ending"] + details["additions"] - details["disposals"]

    # Calculate variance
    details["variance"] = abs(details["actual_current"] - details["expected_current"])

    # Check if reconciled (within $1 tolerance for rounding)
    details["is_reconciled"] = details["variance"] <= 1.0

    return details["is_reconciled"], details


def generate_reconciliation_report(
    issues: List[ReconciliationIssue],
    summary: Dict,
    cost_details: Optional[Dict] = None
) -> str:
    """Generate human-readable reconciliation report."""
    lines = []
    lines.append("=" * 70)
    lines.append("PRIOR YEAR RECONCILIATION REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Summary
    lines.append(f"Prior Year Assets: {summary['prior_year_count']}")
    lines.append(f"Current Year Assets: {summary['current_year_count']}")
    lines.append(f"Matched Assets: {summary['matched_count']}")
    lines.append(f"Missing from Current: {summary['missing_count']}")
    lines.append(f"New in Current: {summary['new_count']}")
    lines.append(f"Changed Values: {summary['changed_count']}")
    lines.append("")

    # Cost reconciliation if provided
    if cost_details:
        lines.append("COST BASIS RECONCILIATION:")
        lines.append("-" * 50)
        lines.append(f"  Prior Year Ending:     ${cost_details['prior_ending']:>15,.2f}")
        lines.append(f"  + Additions:           ${cost_details['additions']:>15,.2f}")
        lines.append(f"  - Disposals:           ${cost_details['disposals']:>15,.2f}")
        lines.append(f"  = Expected Current:    ${cost_details['expected_current']:>15,.2f}")
        lines.append(f"  Actual Current:        ${cost_details['actual_current']:>15,.2f}")
        lines.append(f"  Variance:              ${cost_details['variance']:>15,.2f}")
        lines.append("")

        if cost_details['is_reconciled']:
            lines.append("  STATUS: RECONCILED")
        else:
            lines.append("  STATUS: OUT OF BALANCE - INVESTIGATE")
        lines.append("")

    # Issues by severity
    if not issues:
        lines.append("ALL ASSETS RECONCILED - No issues found")
    else:
        critical = [i for i in issues if i.severity == "CRITICAL"]
        errors = [i for i in issues if i.severity == "ERROR"]
        warnings = [i for i in issues if i.severity == "WARNING"]

        if critical:
            lines.append("CRITICAL ISSUES (Must Fix):")
            lines.append("-" * 50)
            for issue in critical:
                lines.append(f"  [{issue.issue_type}] Asset {issue.asset_id}: {issue.message}")
                lines.append(f"    Prior: {issue.prior_value}")
                lines.append(f"    Current: {issue.current_value}")
                lines.append(f"    → {issue.suggestion}")
            lines.append("")

        if errors:
            lines.append("ERRORS (Should Fix):")
            lines.append("-" * 50)
            for issue in errors:
                lines.append(f"  [{issue.issue_type}] Asset {issue.asset_id}: {issue.message}")
                lines.append(f"    Prior: {issue.prior_value} → Current: {issue.current_value}")
            lines.append("")

        if warnings:
            lines.append(f"WARNINGS ({len(warnings)} items):")
            lines.append("-" * 50)
            for issue in warnings[:5]:
                lines.append(f"  Asset {issue.asset_id}: {issue.message}")
            if len(warnings) > 5:
                lines.append(f"  ... and {len(warnings) - 5} more")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)
