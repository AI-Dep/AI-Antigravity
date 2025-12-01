# fixed_asset_ai/logic/classification_verifier.py
"""
Classification Verification System

Verifies MACRS classifications for tax correctness - catches errors that
format validation cannot detect.

Key Verifications:
1. MACRS life matches asset description
2. QIP eligibility (must be post-2017)
3. Listed property rules (IRC §280F)
4. Section 179 eligibility
5. Bonus depreciation eligibility
6. Method consistency (GDS vs ADS)

This module addresses the critical gap: validating TAX CORRECTNESS,
not just data format.
"""

import pandas as pd
from datetime import date, datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from . import tax_year_config


@dataclass
class ClassificationIssue:
    """Represents a classification verification issue."""
    severity: str  # CRITICAL, ERROR, WARNING
    asset_id: str
    field: str
    message: str
    suggestion: str
    rule_reference: str  # IRS publication/code reference


# ============================================================================
# MACRS LIFE VERIFICATION RULES
# ============================================================================

MACRS_LIFE_KEYWORDS = {
    3: ["race horse", "breeding hog", "tractor unit"],
    5: ["car", "automobile", "truck", "computer", "copier", "typewriter",
        "calculator", "office equipment", "research equipment", "aircraft",
        "helicopter", "appliance", "carpet", "furniture used in rental"],
    7: ["furniture", "fixture", "equipment", "machinery", "desk", "chair",
        "filing cabinet", "shelving", "rack", "tool", "die", "mold",
        "agricultural machinery", "railroad track"],
    10: ["vessel", "barge", "tugboat", "water transportation equipment",
         "single purpose agricultural structure", "tree", "vine"],
    15: ["land improvement", "sidewalk", "road", "fence", "landscaping",
         "parking lot", "qualified restaurant property", "retail improvement",
         "qip", "qualified improvement property", "interior improvement"],
    20: ["farm building", "municipal sewer"],
    27.5: ["residential rental", "apartment", "rental house", "duplex"],
    39: ["nonresidential", "commercial building", "office building",
         "warehouse", "factory", "retail building", "store"],
}

# Keywords that indicate potential misclassification
MISCLASSIFICATION_ALERTS = {
    "qip": {"expected_life": 15, "alert": "QIP should be 15-year property (TCJA 2017)"},
    "interior improvement": {"expected_life": 15, "alert": "Interior improvements may qualify as QIP (15-year)"},
    "hvac": {"expected_life": 15, "alert": "HVAC in commercial building may be QIP (15-year)"},
    "roof": {"expected_life": 39, "alert": "Roof is typically 39-year unless QIP eligible"},
    "land improvement": {"expected_life": 15, "alert": "Land improvements are 15-year property"},
    "computer": {"expected_life": 5, "alert": "Computers are 5-year property"},
    "vehicle": {"expected_life": 5, "alert": "Vehicles are 5-year property"},
    "furniture": {"expected_life": 7, "alert": "Furniture is 7-year property"},
    "leasehold": {"expected_life": 15, "alert": "Leasehold improvements may be QIP (15-year)"},
}

# Listed property requiring special handling (IRC §280F)
LISTED_PROPERTY_KEYWORDS = [
    "car", "automobile", "vehicle", "truck", "suv", "van",
    "aircraft", "boat", "yacht",
    "computer", "laptop", "tablet",  # If not used exclusively for business
    "cell phone", "smartphone",
]


def verify_classifications(
    df: pd.DataFrame,
    tax_year: int = None
) -> Tuple[List[ClassificationIssue], Dict]:
    """
    Verify all asset classifications for tax correctness.

    Args:
        df: Asset dataframe with classifications
        tax_year: Tax year for date validations

    Returns:
        Tuple of (issues list, summary dict)
    """
    if tax_year is None:
        tax_year = date.today().year

    issues = []
    summary = {
        "total_verified": 0,
        "critical_count": 0,
        "error_count": 0,
        "warning_count": 0,
        "passed_count": 0,
        "verification_coverage": 0.0,
    }

    if df is None or df.empty:
        return issues, summary

    # Run all verification checks
    issues.extend(_verify_macrs_life_matches_description(df))
    issues.extend(_verify_qip_eligibility(df, tax_year))
    issues.extend(_verify_listed_property(df))
    issues.extend(_verify_section_179_eligibility(df, tax_year))
    issues.extend(_verify_bonus_depreciation_eligibility(df, tax_year))
    issues.extend(_verify_method_consistency(df))
    issues.extend(_verify_convention_consistency(df))

    # Calculate summary
    summary["total_verified"] = len(df)
    summary["critical_count"] = len([i for i in issues if i.severity == "CRITICAL"])
    summary["error_count"] = len([i for i in issues if i.severity == "ERROR"])
    summary["warning_count"] = len([i for i in issues if i.severity == "WARNING"])
    summary["passed_count"] = len(df) - len(set(i.asset_id for i in issues))
    summary["verification_coverage"] = 100.0  # All assets verified

    return issues, summary


def _verify_macrs_life_matches_description(df: pd.DataFrame) -> List[ClassificationIssue]:
    """Verify MACRS life assignment matches asset description."""
    issues = []

    life_col = None
    for col in ["MACRS Life", "Final Life Used", "Tax Life"]:
        if col in df.columns:
            life_col = col
            break

    if life_col is None:
        return issues

    for idx, row in df.iterrows():
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        desc = str(row.get("Description", "")).lower()
        life = row.get(life_col)

        if pd.isna(life) or desc == "":
            continue

        try:
            life_num = float(life)
        except (ValueError, TypeError):
            continue

        # Check for misclassification alerts
        for keyword, alert_info in MISCLASSIFICATION_ALERTS.items():
            if keyword in desc:
                expected_life = alert_info["expected_life"]
                if life_num != expected_life:
                    issues.append(ClassificationIssue(
                        severity="WARNING",
                        asset_id=asset_id,
                        field="MACRS Life",
                        message=f"'{keyword}' in description but life is {life_num}-year (expected {expected_life}-year)",
                        suggestion=alert_info["alert"],
                        rule_reference="IRS Pub 946, Table B-1"
                    ))

        # Check for obvious mismatches
        if "building" in desc and life_num not in [27.5, 39]:
            if "improvement" not in desc and "interior" not in desc:
                issues.append(ClassificationIssue(
                    severity="ERROR",
                    asset_id=asset_id,
                    field="MACRS Life",
                    message=f"Building asset has {life_num}-year life (should be 27.5 or 39)",
                    suggestion="Residential rental = 27.5 years, Commercial = 39 years",
                    rule_reference="IRC §168(c)"
                ))

        if "land" in desc and "improvement" not in desc:
            if life_num > 0:
                issues.append(ClassificationIssue(
                    severity="CRITICAL",
                    asset_id=asset_id,
                    field="MACRS Life",
                    message="Land is NOT depreciable",
                    suggestion="Remove MACRS life - land has unlimited useful life",
                    rule_reference="IRC §167(a)"
                ))

    return issues


def _verify_qip_eligibility(df: pd.DataFrame, tax_year: int) -> List[ClassificationIssue]:
    """Verify QIP (Qualified Improvement Property) eligibility."""
    issues = []

    for idx, row in df.iterrows():
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        desc = str(row.get("Description", "")).lower()
        category = str(row.get("Final Category", row.get("Final Category Used", ""))).lower()

        # Get in-service date
        pis_date = row.get("In Service Date", row.get("Date In Service"))
        if pd.isna(pis_date):
            continue

        try:
            if isinstance(pis_date, str):
                for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                    try:
                        pis_date = datetime.strptime(pis_date, fmt).date()
                        break
                    except ValueError:
                        continue
            elif hasattr(pis_date, 'date'):
                pis_date = pis_date.date()
        except Exception:
            continue

        is_qip_candidate = any(kw in desc or kw in category for kw in [
            "qip", "qualified improvement", "interior improvement",
            "leasehold improvement", "tenant improvement"
        ])

        if is_qip_candidate:
            # QIP only valid for assets placed in service after 12/31/2017
            if pis_date < date(2018, 1, 1):
                issues.append(ClassificationIssue(
                    severity="CRITICAL",
                    asset_id=asset_id,
                    field="QIP Eligibility",
                    message=f"QIP classification invalid - in-service date {pis_date} is before 1/1/2018",
                    suggestion="QIP only applies to improvements placed in service after 12/31/2017. Use 39-year for pre-2018 assets.",
                    rule_reference="TCJA 2017, IRC §168(e)(6)"
                ))

            # Verify 15-year life for QIP
            life = row.get("MACRS Life", row.get("Final Life Used", row.get("Tax Life")))
            if pd.notna(life):
                try:
                    life_num = float(life)
                    if life_num != 15:
                        issues.append(ClassificationIssue(
                            severity="ERROR",
                            asset_id=asset_id,
                            field="MACRS Life",
                            message=f"QIP should be 15-year property (currently {life_num}-year)",
                            suggestion="QIP is 15-year property with 100% bonus depreciation eligible",
                            rule_reference="IRC §168(e)(6)"
                        ))
                except (ValueError, TypeError):
                    pass

    return issues


def _verify_listed_property(df: pd.DataFrame) -> List[ClassificationIssue]:
    """Verify listed property rules (IRC §280F)."""
    issues = []

    for idx, row in df.iterrows():
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        desc = str(row.get("Description", "")).lower()
        category = str(row.get("Final Category", row.get("Final Category Used", ""))).lower()

        # Check if this is listed property
        is_listed = any(kw in desc or kw in category for kw in LISTED_PROPERTY_KEYWORDS)

        if not is_listed:
            continue

        # Check business use percentage
        business_use = row.get("Business Use %", row.get("Business Use Pct"))

        if pd.isna(business_use):
            issues.append(ClassificationIssue(
                severity="WARNING",
                asset_id=asset_id,
                field="Business Use %",
                message="Listed property missing Business Use % - required for IRC §280F compliance",
                suggestion="Document business use percentage. If ≤50%, must use ADS (no Section 179/bonus)",
                rule_reference="IRC §280F"
            ))
            continue

        try:
            if isinstance(business_use, str):
                business_use = float(business_use.strip().rstrip('%'))
            else:
                business_use = float(business_use)

            # Normalize to decimal if needed
            if business_use > 1:
                business_use = business_use / 100.0

            if business_use <= 0.50:
                # Check if ADS is being used
                method = str(row.get("Method", row.get("Tax Method", ""))).upper()

                if "ADS" not in method and "SL" not in method:
                    issues.append(ClassificationIssue(
                        severity="CRITICAL",
                        asset_id=asset_id,
                        field="Depreciation Method",
                        message=f"Listed property with {business_use:.0%} business use MUST use ADS",
                        suggestion="Business use ≤50% requires ADS. No Section 179 or bonus depreciation allowed.",
                        rule_reference="IRC §280F(b)(1)"
                    ))

                # Check for Section 179
                sec179 = row.get("Section 179", row.get("Tax Sec 179 Expensed", 0)) or 0
                if float(sec179) > 0:
                    issues.append(ClassificationIssue(
                        severity="CRITICAL",
                        asset_id=asset_id,
                        field="Section 179",
                        message=f"Section 179 NOT allowed for listed property with {business_use:.0%} business use",
                        suggestion="Remove Section 179 deduction - only allowed if business use >50%",
                        rule_reference="IRC §280F(b)(3)"
                    ))

        except (ValueError, TypeError):
            pass

    return issues


def _verify_section_179_eligibility(df: pd.DataFrame, tax_year: int) -> List[ClassificationIssue]:
    """Verify Section 179 eligibility."""
    issues = []

    # 2024 Section 179 limit (adjust for tax year)
    sec179_limits = {
        2024: 1_220_000,
        2023: 1_160_000,
        2022: 1_080_000,
        2021: 1_050_000,
        2020: 1_040_000,
    }
    annual_limit = sec179_limits.get(tax_year, 1_220_000)

    total_sec179 = 0

    for idx, row in df.iterrows():
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        desc = str(row.get("Description", "")).lower()

        sec179 = row.get("Section 179", row.get("Tax Sec 179 Expensed", 0))
        if pd.isna(sec179) or sec179 == "":
            sec179 = 0
        else:
            try:
                sec179 = float(sec179)
            except (ValueError, TypeError):
                sec179 = 0

        if sec179 <= 0:
            continue

        total_sec179 += sec179

        cost = row.get("Cost", row.get("Tax Cost", 0))
        if pd.notna(cost):
            try:
                cost = float(cost)
                if sec179 > cost:
                    issues.append(ClassificationIssue(
                        severity="CRITICAL",
                        asset_id=asset_id,
                        field="Section 179",
                        message=f"Section 179 (${sec179:,.0f}) exceeds cost (${cost:,.0f})",
                        suggestion="Section 179 cannot exceed asset cost",
                        rule_reference="IRC §179(b)(1)"
                    ))
            except (ValueError, TypeError):
                pass

        # Check for ineligible property
        if any(kw in desc for kw in ["land", "building", "real property", "rental"]):
            if "improvement" not in desc:
                issues.append(ClassificationIssue(
                    severity="CRITICAL",
                    asset_id=asset_id,
                    field="Section 179",
                    message="Real property is NOT eligible for Section 179",
                    suggestion="Remove Section 179 deduction - only tangible personal property qualifies",
                    rule_reference="IRC §179(d)(1)"
                ))

    # Check annual limit
    if total_sec179 > annual_limit:
        issues.append(ClassificationIssue(
            severity="CRITICAL",
            asset_id="ALL",
            field="Section 179 Total",
            message=f"Total Section 179 (${total_sec179:,.0f}) exceeds {tax_year} limit (${annual_limit:,.0f})",
            suggestion=f"Reduce Section 179 elections to stay within ${annual_limit:,.0f} limit",
            rule_reference="IRC §179(b)(1)"
        ))

    return issues


def _verify_bonus_depreciation_eligibility(df: pd.DataFrame, tax_year: int) -> List[ClassificationIssue]:
    """Verify bonus depreciation eligibility."""
    issues = []

    # Get bonus rate from centralized config (OBBBA/TCJA compliant)
    # Note: For verification, we use the max rate (assumes OBBBA eligibility for 2025+)
    max_bonus_rate = tax_year_config.get_bonus_percentage(tax_year)

    for idx, row in df.iterrows():
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        desc = str(row.get("Description", "")).lower()

        bonus = row.get("Bonus", row.get("Bonus Amount", 0))
        if pd.isna(bonus) or bonus == "":
            bonus = 0
        else:
            try:
                bonus = float(bonus)
            except (ValueError, TypeError):
                bonus = 0

        if bonus <= 0:
            continue

        cost = row.get("Cost", row.get("Tax Cost", 0))
        sec179 = row.get("Section 179", row.get("Tax Sec 179 Expensed", 0)) or 0

        if pd.notna(cost):
            try:
                cost = float(cost)
                sec179 = float(sec179) if pd.notna(sec179) else 0
                depreciable_basis = cost - sec179

                max_bonus = depreciable_basis * max_bonus_rate

                if bonus > max_bonus + 0.01:  # Allow 1 cent rounding
                    issues.append(ClassificationIssue(
                        severity="ERROR",
                        asset_id=asset_id,
                        field="Bonus Depreciation",
                        message=f"Bonus (${bonus:,.0f}) exceeds {tax_year} max ({max_bonus_rate:.0%} = ${max_bonus:,.0f})",
                        suggestion=f"Bonus depreciation is {max_bonus_rate:.0%} for {tax_year}. Adjust bonus amount.",
                        rule_reference="IRC §168(k)"
                    ))
            except (ValueError, TypeError):
                pass

        # Check for ineligible property (used property in some cases)
        trans_type = str(row.get("Transaction Type", "")).lower()
        if "used" in desc or "existing" in trans_type:
            # Used property CAN qualify for bonus if certain conditions met (TCJA)
            issues.append(ClassificationIssue(
                severity="WARNING",
                asset_id=asset_id,
                field="Bonus Depreciation",
                message="Used property has bonus - verify acquisition requirements",
                suggestion="Used property qualifies for bonus if: (1) first use by taxpayer, (2) not from related party",
                rule_reference="IRC §168(k)(2)(E)"
            ))

    return issues


def _verify_method_consistency(df: pd.DataFrame) -> List[ClassificationIssue]:
    """Verify depreciation method is appropriate for asset class."""
    issues = []

    method_col = None
    for col in ["Method", "Tax Method", "Final Method Used"]:
        if col in df.columns:
            method_col = col
            break

    if method_col is None:
        return issues

    for idx, row in df.iterrows():
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        desc = str(row.get("Description", "")).lower()
        method = str(row.get(method_col, "")).upper().replace(".", "").strip()

        life = row.get("MACRS Life", row.get("Final Life Used", row.get("Tax Life")))
        if pd.notna(life):
            try:
                life_num = float(life)
            except (ValueError, TypeError):
                life_num = 0
        else:
            life_num = 0

        # Real property should use SL (straight-line)
        if life_num in [27.5, 39]:
            if method not in ["SL", "SLMM", "SLHY"]:
                issues.append(ClassificationIssue(
                    severity="ERROR",
                    asset_id=asset_id,
                    field="Method",
                    message=f"Real property ({life_num}-year) should use Straight-Line method (not {method})",
                    suggestion="Real property must use SL method under MACRS",
                    rule_reference="IRC §168(b)(3)"
                ))

        # Personal property should typically use 200DB or 150DB
        if life_num in [3, 5, 7, 10]:
            if method in ["SL", "SLMM", "SLHY"] and "ADS" not in method:
                issues.append(ClassificationIssue(
                    severity="WARNING",
                    asset_id=asset_id,
                    field="Method",
                    message=f"Personal property ({life_num}-year) using SL - typically uses 200DB (GDS)",
                    suggestion="SL is valid but results in lower deductions. Consider 200DB unless ADS required.",
                    rule_reference="IRC §168(b)(1)"
                ))

    return issues


def _verify_convention_consistency(df: pd.DataFrame) -> List[ClassificationIssue]:
    """Verify convention is appropriate for asset class."""
    issues = []

    conv_col = None
    for col in ["Convention", "Final Conv Used"]:
        if col in df.columns:
            conv_col = col
            break

    if conv_col is None:
        return issues

    for idx, row in df.iterrows():
        asset_id = str(row.get("Asset ID", row.get("Asset #", f"Row {idx+1}")))
        conv = str(row.get(conv_col, "")).upper().strip()

        life = row.get("MACRS Life", row.get("Final Life Used", row.get("Tax Life")))
        if pd.notna(life):
            try:
                life_num = float(life)
            except (ValueError, TypeError):
                life_num = 0
        else:
            life_num = 0

        # Real property should use MM (mid-month)
        if life_num in [27.5, 39]:
            if conv not in ["MM", "MID-MONTH"]:
                issues.append(ClassificationIssue(
                    severity="ERROR",
                    asset_id=asset_id,
                    field="Convention",
                    message=f"Real property ({life_num}-year) should use Mid-Month convention (not {conv})",
                    suggestion="Real property must use Mid-Month (MM) convention",
                    rule_reference="IRC §168(d)(2)"
                ))

        # Personal property typically uses HY or MQ
        if life_num in [3, 5, 7, 10, 15, 20]:
            if conv not in ["HY", "MQ", "HALF-YEAR", "MID-QUARTER"]:
                issues.append(ClassificationIssue(
                    severity="WARNING",
                    asset_id=asset_id,
                    field="Convention",
                    message=f"Personal property using {conv} convention - typically HY or MQ",
                    suggestion="Personal property uses Half-Year unless >40% placed in service in Q4 (then Mid-Quarter)",
                    rule_reference="IRC §168(d)(1)"
                ))

    return issues


def generate_verification_report(issues: List[ClassificationIssue], summary: Dict) -> str:
    """Generate human-readable verification report."""
    lines = []
    lines.append("=" * 70)
    lines.append("CLASSIFICATION VERIFICATION REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Summary
    lines.append(f"Assets Verified: {summary['total_verified']}")
    lines.append(f"Passed: {summary['passed_count']}")
    lines.append(f"Critical Issues: {summary['critical_count']}")
    lines.append(f"Errors: {summary['error_count']}")
    lines.append(f"Warnings: {summary['warning_count']}")
    lines.append("")

    if not issues:
        lines.append("ALL CLASSIFICATIONS VERIFIED - No issues found")
    else:
        # Group by severity
        critical = [i for i in issues if i.severity == "CRITICAL"]
        errors = [i for i in issues if i.severity == "ERROR"]
        warnings = [i for i in issues if i.severity == "WARNING"]

        if critical:
            lines.append("CRITICAL ISSUES (Must Fix):")
            lines.append("-" * 50)
            for issue in critical:
                lines.append(f"  Asset {issue.asset_id}: {issue.message}")
                lines.append(f"    → {issue.suggestion}")
                lines.append(f"    Ref: {issue.rule_reference}")
            lines.append("")

        if errors:
            lines.append("ERRORS (Should Fix):")
            lines.append("-" * 50)
            for issue in errors:
                lines.append(f"  Asset {issue.asset_id}: {issue.message}")
                lines.append(f"    → {issue.suggestion}")
            lines.append("")

        if warnings:
            lines.append("WARNINGS (Review):")
            lines.append("-" * 50)
            for issue in warnings[:10]:  # First 10
                lines.append(f"  Asset {issue.asset_id}: {issue.message}")
            if len(warnings) > 10:
                lines.append(f"  ... and {len(warnings) - 10} more warnings")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)
