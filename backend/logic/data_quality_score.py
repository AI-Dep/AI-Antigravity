# fixed_asset_ai/logic/data_quality_score.py
"""
Data Quality Scoring Module

Provides an objective A-F grade for asset schedule quality.
This gives CPAs and accountants confidence in the data before export.

Scoring is 100% deterministic - no AI judgment, just objective rules.
"""

import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import date, datetime

from .data_validator import AssetDataValidator, ValidationError
from .rollforward_reconciliation import reconcile_rollforward, RollforwardResult


@dataclass
class QualityCheckResult:
    """Result of a single quality check."""
    name: str
    passed: bool
    score: float  # 0-100
    max_score: float
    weight: float  # Relative importance (0-1)
    details: str
    fix_suggestion: Optional[str] = None


@dataclass
class DataQualityScore:
    """Overall data quality assessment."""
    grade: str  # A, B, C, D, F
    score: float  # 0-100
    checks: List[QualityCheckResult] = field(default_factory=list)
    summary: str = ""
    is_export_ready: bool = False
    critical_issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def calculate_data_quality_score(
    df: pd.DataFrame,
    tax_year: int = None,
    include_rollforward: bool = True,
) -> DataQualityScore:
    """
    Calculate comprehensive data quality score with A-F grade.

    Scoring methodology:
    - A (90-100): Excellent - Ready for FA CS export, minimal review needed
    - B (80-89): Good - Ready for export, some items need review
    - C (70-79): Acceptable - Export possible, significant review needed
    - D (60-69): Poor - Export not recommended without fixes
    - F (0-59): Failing - Critical issues must be resolved

    Args:
        df: Asset dataframe
        tax_year: Tax year for validation (defaults to current year)
        include_rollforward: Whether to include rollforward reconciliation

    Returns:
        DataQualityScore with detailed breakdown
    """
    if tax_year is None:
        tax_year = date.today().year

    checks = []
    critical_issues = []
    recommendations = []

    # =========================================================================
    # CHECK 1: Required Fields Completeness (Weight: 25%)
    # =========================================================================
    required_fields_check = _check_required_fields(df)
    checks.append(required_fields_check)
    if not required_fields_check.passed:
        if required_fields_check.score < 70:
            critical_issues.append(required_fields_check.details)
        recommendations.append(required_fields_check.fix_suggestion)

    # =========================================================================
    # CHECK 2: No Duplicate Assets (Weight: 20%)
    # =========================================================================
    duplicate_check = _check_duplicates(df)
    checks.append(duplicate_check)
    if not duplicate_check.passed:
        critical_issues.append(duplicate_check.details)
        recommendations.append(duplicate_check.fix_suggestion)

    # =========================================================================
    # CHECK 3: Date Validity (Weight: 15%)
    # =========================================================================
    date_check = _check_dates(df, tax_year)
    checks.append(date_check)
    if not date_check.passed:
        recommendations.append(date_check.fix_suggestion)

    # =========================================================================
    # CHECK 4: Cost/Value Validity (Weight: 15%)
    # =========================================================================
    cost_check = _check_costs(df)
    checks.append(cost_check)
    if not cost_check.passed:
        if cost_check.score < 70:
            critical_issues.append(cost_check.details)
        recommendations.append(cost_check.fix_suggestion)

    # =========================================================================
    # CHECK 5: Classification Completeness (Weight: 10%)
    # =========================================================================
    classification_check = _check_classification(df)
    checks.append(classification_check)
    if not classification_check.passed:
        recommendations.append(classification_check.fix_suggestion)

    # =========================================================================
    # CHECK 6: Data Consistency (Weight: 10%)
    # =========================================================================
    consistency_check = _check_consistency(df)
    checks.append(consistency_check)
    if not consistency_check.passed:
        recommendations.append(consistency_check.fix_suggestion)

    # =========================================================================
    # CHECK 7: Rollforward Reconciliation (Weight: 5%)
    # =========================================================================
    if include_rollforward:
        rollforward_check = _check_rollforward(df)
        checks.append(rollforward_check)
        if not rollforward_check.passed:
            recommendations.append(rollforward_check.fix_suggestion)

    # =========================================================================
    # Calculate Overall Score
    # =========================================================================
    total_weight = sum(c.weight for c in checks)
    if total_weight > 0:
        weighted_score = sum(c.score * c.weight for c in checks) / total_weight
    else:
        weighted_score = 0

    # Determine grade
    if weighted_score >= 90:
        grade = "A"
    elif weighted_score >= 80:
        grade = "B"
    elif weighted_score >= 70:
        grade = "C"
    elif weighted_score >= 60:
        grade = "D"
    else:
        grade = "F"

    # Determine if export-ready
    is_export_ready = len(critical_issues) == 0 and weighted_score >= 60

    # Generate summary
    summary = _generate_summary(grade, weighted_score, len(df), checks, critical_issues)

    # Filter out None recommendations
    recommendations = [r for r in recommendations if r]

    return DataQualityScore(
        grade=grade,
        score=round(weighted_score, 1),
        checks=checks,
        summary=summary,
        is_export_ready=is_export_ready,
        critical_issues=critical_issues,
        recommendations=recommendations[:5]  # Top 5 recommendations
    )


def _check_required_fields(df: pd.DataFrame) -> QualityCheckResult:
    """Check that all required fields are present and populated."""
    required_fields = ["Asset ID", "Description", "Cost", "In Service Date"]
    optional_important = ["MACRS Life", "Method", "Convention"]

    total_cells = 0
    missing_cells = 0
    missing_fields = []

    for field in required_fields:
        if field not in df.columns:
            missing_fields.append(field)
            missing_cells += len(df)
        else:
            total_cells += len(df)
            missing_count = df[field].isna().sum() + (df[field] == "").sum()
            missing_cells += missing_count

    total_cells = max(total_cells, 1)  # Avoid division by zero
    completeness = ((total_cells - missing_cells) / total_cells) * 100

    passed = completeness >= 90 and len(missing_fields) == 0
    score = min(completeness, 100)

    details = f"Required fields {100-completeness:.0f}% incomplete"
    if missing_fields:
        details = f"Missing columns: {', '.join(missing_fields)}"

    fix_suggestion = None
    if not passed:
        if missing_fields:
            fix_suggestion = f"Add missing columns: {', '.join(missing_fields)}"
        else:
            fix_suggestion = "Fill in blank required fields (Asset ID, Description, Cost, In Service Date)"

    return QualityCheckResult(
        name="Required Fields",
        passed=passed,
        score=score,
        max_score=100,
        weight=0.25,
        details=details,
        fix_suggestion=fix_suggestion
    )


def _check_duplicates(df: pd.DataFrame) -> QualityCheckResult:
    """Check for duplicate Asset IDs."""
    if "Asset ID" not in df.columns:
        return QualityCheckResult(
            name="Duplicate Check",
            passed=True,
            score=100,
            max_score=100,
            weight=0.20,
            details="No Asset ID column to check",
            fix_suggestion=None
        )

    asset_ids = df["Asset ID"].dropna()
    if len(asset_ids) == 0:
        return QualityCheckResult(
            name="Duplicate Check",
            passed=False,
            score=0,
            max_score=100,
            weight=0.20,
            details="No Asset IDs found",
            fix_suggestion="Assign unique Asset IDs to all assets"
        )

    duplicate_count = asset_ids.duplicated().sum()
    total = len(asset_ids)

    if duplicate_count == 0:
        return QualityCheckResult(
            name="Duplicate Check",
            passed=True,
            score=100,
            max_score=100,
            weight=0.20,
            details=f"All {total} Asset IDs are unique",
            fix_suggestion=None
        )

    # Score decreases significantly with duplicates (critical issue)
    score = max(0, 100 - (duplicate_count / total * 200))  # 50% duplicates = 0 score

    duplicate_ids = asset_ids[asset_ids.duplicated()].unique()[:5]

    return QualityCheckResult(
        name="Duplicate Check",
        passed=False,
        score=score,
        max_score=100,
        weight=0.20,
        details=f"{duplicate_count} duplicate Asset IDs found (e.g., {', '.join(str(x) for x in duplicate_ids)})",
        fix_suggestion=f"Remove or reassign {duplicate_count} duplicate Asset IDs to prevent double depreciation"
    )


def _check_dates(df: pd.DataFrame, tax_year: int) -> QualityCheckResult:
    """Check date validity."""
    date_columns = ["In Service Date", "Acquisition Date"]
    issues = 0
    total_dates = 0

    today = date.today()

    for col in date_columns:
        if col not in df.columns:
            continue

        for val in df[col]:
            if pd.isna(val) or val == "":
                continue

            total_dates += 1

            try:
                # Parse date
                if isinstance(val, str):
                    # Try common formats
                    parsed = None
                    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                        try:
                            parsed = datetime.strptime(val, fmt).date()
                            break
                        except ValueError:
                            continue
                    if parsed is None:
                        issues += 1
                        continue
                    val_date = parsed
                elif isinstance(val, (date, datetime, pd.Timestamp)):
                    val_date = val if isinstance(val, date) else val.date()
                else:
                    issues += 1
                    continue

                # Check for invalid dates
                if val_date.year < 1950:
                    issues += 1
                elif val_date > today:
                    issues += 0.5  # Future dates are warnings, not errors

            except Exception:
                issues += 1

    if total_dates == 0:
        return QualityCheckResult(
            name="Date Validity",
            passed=False,
            score=50,
            max_score=100,
            weight=0.15,
            details="No dates found to validate",
            fix_suggestion="Add In Service Date for all assets"
        )

    valid_pct = ((total_dates - issues) / total_dates) * 100
    passed = valid_pct >= 95

    return QualityCheckResult(
        name="Date Validity",
        passed=passed,
        score=min(valid_pct, 100),
        max_score=100,
        weight=0.15,
        details=f"{valid_pct:.0f}% of dates are valid ({int(issues)} issues)",
        fix_suggestion="Fix invalid dates (check format MM/DD/YYYY, year > 1950)" if not passed else None
    )


def _check_costs(df: pd.DataFrame) -> QualityCheckResult:
    """Check cost validity."""
    if "Cost" not in df.columns:
        return QualityCheckResult(
            name="Cost Validity",
            passed=False,
            score=0,
            max_score=100,
            weight=0.15,
            details="No Cost column found",
            fix_suggestion="Add Cost column with asset values"
        )

    issues = 0
    total = 0
    critical_issues = []

    for idx, val in enumerate(df["Cost"]):
        if pd.isna(val) or val == "":
            continue

        total += 1

        try:
            cost = float(val)

            if cost < 0:
                issues += 2  # Negative cost is critical
                critical_issues.append(f"Row {idx+1}: Negative cost ${cost:,.2f}")
            elif cost == 0:
                issues += 0.5  # Zero cost is a warning
            elif cost > 100_000_000:
                issues += 0.5  # Very large cost is a warning

        except (ValueError, TypeError):
            issues += 1

    if total == 0:
        return QualityCheckResult(
            name="Cost Validity",
            passed=False,
            score=0,
            max_score=100,
            weight=0.15,
            details="No cost values found",
            fix_suggestion="Enter cost values for all assets"
        )

    valid_pct = max(0, ((total - issues) / total) * 100)
    passed = valid_pct >= 95 and len(critical_issues) == 0

    details = f"{valid_pct:.0f}% of costs are valid"
    if critical_issues:
        details = f"{len(critical_issues)} negative/invalid costs found"

    return QualityCheckResult(
        name="Cost Validity",
        passed=passed,
        score=min(valid_pct, 100),
        max_score=100,
        weight=0.15,
        details=details,
        fix_suggestion="Fix negative or invalid cost values" if not passed else None
    )


def _check_classification(df: pd.DataFrame) -> QualityCheckResult:
    """Check that assets are properly classified."""
    classification_fields = ["Final Category", "MACRS Life", "Method"]

    has_classification = False
    classified_count = 0
    total = len(df)

    for field in classification_fields:
        if field in df.columns:
            has_classification = True
            non_empty = (~df[field].isna() & (df[field] != "")).sum()
            classified_count = max(classified_count, non_empty)

    if not has_classification or total == 0:
        return QualityCheckResult(
            name="Classification",
            passed=False,
            score=50,
            max_score=100,
            weight=0.10,
            details="No classification columns found",
            fix_suggestion="Run AI classification to assign MACRS categories"
        )

    classified_pct = (classified_count / total) * 100
    passed = classified_pct >= 90

    return QualityCheckResult(
        name="Classification",
        passed=passed,
        score=min(classified_pct, 100),
        max_score=100,
        weight=0.10,
        details=f"{classified_pct:.0f}% of assets are classified",
        fix_suggestion=f"Classify remaining {total - classified_count} assets" if not passed else None
    )


def _check_consistency(df: pd.DataFrame) -> QualityCheckResult:
    """Check data consistency across fields."""
    issues = 0
    total_checks = 0

    # Check 1: Accumulated depreciation <= Cost
    if "Cost" in df.columns and "Tax Prior Depreciation" in df.columns:
        for idx, row in df.iterrows():
            cost = row.get("Cost")
            prior_dep = row.get("Tax Prior Depreciation")

            if pd.notna(cost) and pd.notna(prior_dep):
                total_checks += 1
                try:
                    if float(prior_dep) > float(cost):
                        issues += 1
                except (ValueError, TypeError):
                    pass

    # Check 2: Section 179 + Bonus <= Cost
    if all(col in df.columns for col in ["Cost", "Section 179", "Bonus"]):
        for idx, row in df.iterrows():
            cost = row.get("Cost")
            sec179 = row.get("Section 179", 0) or 0
            bonus = row.get("Bonus", 0) or 0

            if pd.notna(cost):
                total_checks += 1
                try:
                    if float(sec179) + float(bonus) > float(cost):
                        issues += 1
                except (ValueError, TypeError):
                    pass

    if total_checks == 0:
        return QualityCheckResult(
            name="Consistency",
            passed=True,
            score=100,
            max_score=100,
            weight=0.10,
            details="No consistency checks applicable",
            fix_suggestion=None
        )

    consistent_pct = ((total_checks - issues) / total_checks) * 100
    passed = consistent_pct >= 95

    return QualityCheckResult(
        name="Consistency",
        passed=passed,
        score=min(consistent_pct, 100),
        max_score=100,
        weight=0.10,
        details=f"{consistent_pct:.0f}% of records are internally consistent",
        fix_suggestion=f"Fix {issues} records with inconsistent values" if not passed else None
    )


def _check_rollforward(df: pd.DataFrame) -> QualityCheckResult:
    """Check rollforward reconciliation."""
    result = reconcile_rollforward(df)

    if result.is_balanced:
        return QualityCheckResult(
            name="Rollforward",
            passed=True,
            score=100,
            max_score=100,
            weight=0.05,
            details=f"Schedule balances: ${result.expected_ending:,.2f}",
            fix_suggestion=None
        )

    return QualityCheckResult(
        name="Rollforward",
        passed=False,
        score=max(0, 100 - (result.variance / max(result.expected_ending, 1) * 100)),
        max_score=100,
        weight=0.05,
        details=f"Schedule out of balance by ${result.variance:,.2f}",
        fix_suggestion="Review additions and disposals to reconcile rollforward"
    )


def _generate_summary(
    grade: str,
    score: float,
    row_count: int,
    checks: List[QualityCheckResult],
    critical_issues: List[str]
) -> str:
    """Generate human-readable summary."""
    passed_count = sum(1 for c in checks if c.passed)
    total_checks = len(checks)

    if grade == "A":
        status = "EXCELLENT - Ready for FA CS export"
    elif grade == "B":
        status = "GOOD - Ready for export with minor review"
    elif grade == "C":
        status = "ACCEPTABLE - Export possible, review recommended"
    elif grade == "D":
        status = "POOR - Fix issues before export"
    else:
        status = "FAILING - Critical issues must be resolved"

    lines = [
        f"DATA QUALITY GRADE: {grade} ({score:.0f}/100)",
        f"Status: {status}",
        f"Assets: {row_count}",
        f"Checks Passed: {passed_count}/{total_checks}",
    ]

    if critical_issues:
        lines.append(f"CRITICAL ISSUES: {len(critical_issues)}")

    return "\n".join(lines)


def generate_quality_report(score: DataQualityScore) -> str:
    """Generate detailed quality report for display."""
    lines = []
    lines.append("=" * 60)
    lines.append("DATA QUALITY REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(score.summary)
    lines.append("")

    # Check details
    lines.append("QUALITY CHECKS:")
    lines.append("-" * 40)
    for check in score.checks:
        status = "[PASS]" if check.passed else "[FAIL]"
        lines.append(f"  {status} {check.name}: {check.score:.0f}/100")
        lines.append(f"         {check.details}")
    lines.append("")

    # Critical issues
    if score.critical_issues:
        lines.append("CRITICAL ISSUES (Must Fix):")
        for issue in score.critical_issues:
            lines.append(f"  - {issue}")
        lines.append("")

    # Recommendations
    if score.recommendations:
        lines.append("RECOMMENDATIONS:")
        for i, rec in enumerate(score.recommendations, 1):
            lines.append(f"  {i}. {rec}")
        lines.append("")

    # Export readiness
    if score.is_export_ready:
        lines.append("EXPORT STATUS: READY")
    else:
        lines.append("EXPORT STATUS: NOT READY - Fix critical issues first")

    lines.append("=" * 60)

    return "\n".join(lines)


def get_quality_badge(grade: str) -> str:
    """Get a visual badge for the quality grade."""
    badges = {
        "A": "[A] Excellent",
        "B": "[B] Good",
        "C": "[C] Acceptable",
        "D": "[D] Poor",
        "F": "[F] Failing",
    }
    return badges.get(grade, "[?] Unknown")
