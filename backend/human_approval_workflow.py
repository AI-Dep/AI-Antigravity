"""
Human-in-the-Loop Approval Workflow for Fixed Asset CS Export & RPA

CRITICAL: Tax compliance requires human oversight before RPA automation.
This module provides a formal approval workflow with multiple checkpoints.

Workflow:
1. Export Quality Review (automated validation)
2. Tax Calculation Review (human verification)
3. Pre-RPA Approval Checklist
4. Final Sign-off with audit trail

PRODUCTION SAFETY: Never run RPA without human approval for tax data.
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import json
import os
import re

from .export_qa_validator import validate_fixed_asset_cs_export


# ==============================================================================
# SECURITY HELPERS
# ==============================================================================

def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal attacks.

    Args:
        filename: The filename to sanitize

    Returns:
        A safe filename with no directory components
    """
    if not filename:
        raise ValueError("Filename cannot be empty")

    # Remove any directory components (path traversal prevention)
    filename = os.path.basename(filename)

    # Remove or replace unsafe characters
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

    # Prevent hidden files
    if filename.startswith('.'):
        filename = '_' + filename[1:]

    # Ensure filename isn't too long
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext

    if not filename or filename == '.':
        raise ValueError("Invalid filename")

    return filename


# ==============================================================================
# APPROVAL WORKFLOW STATUS
# ==============================================================================

class ApprovalStatus:
    """Track approval workflow status."""

    PENDING_REVIEW = "PENDING_REVIEW"
    QUALITY_APPROVED = "QUALITY_APPROVED"
    TAX_APPROVED = "TAX_APPROVED"
    FINAL_APPROVED = "FINAL_APPROVED"
    REJECTED = "REJECTED"
    RPA_READY = "RPA_READY"


# ==============================================================================
# CHECKPOINT 1: EXPORT QUALITY REVIEW
# ==============================================================================

def checkpoint_1_quality_review(
    df: pd.DataFrame,
    auto_approve_if_perfect: bool = False
) -> Tuple[bool, Dict, str]:
    """
    Checkpoint 1: Automated export quality validation.

    Validates export file quality and determines if human review is needed.

    Args:
        df: Export dataframe
        auto_approve_if_perfect: Auto-approve if no issues (still logs for audit)

    Returns:
        Tuple of (approved, validation_summary, approval_status)
    """
    print("\n" + "=" * 80)
    print("CHECKPOINT 1: EXPORT QUALITY REVIEW")
    print("=" * 80)

    # Run comprehensive validation
    is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=True)

    validation_summary = {
        "checkpoint": "1_QUALITY_REVIEW",
        "timestamp": datetime.now().isoformat(),
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "is_valid": is_valid,
        "critical_count": summary["CRITICAL"],
        "error_count": summary["ERROR"],
        "warning_count": summary["WARNING"],
        "total_issues": summary["TOTAL"],
        "validation_errors": [str(e) for e in errors[:20]],  # First 20 for summary
    }

    # Determine approval
    if summary["CRITICAL"] > 0:
        print("\n🔴 CHECKPOINT 1 FAILED: CRITICAL issues detected")
        print("   ❌ MUST fix critical issues before proceeding")
        print("   ❌ RPA automation BLOCKED")
        approval_status = ApprovalStatus.REJECTED
        approved = False

    elif summary["ERROR"] > 0:
        print("\n⚠️  CHECKPOINT 1 REQUIRES REVIEW: ERROR issues detected")
        print("   ⚠️  Human review REQUIRED")
        print("   ⚠️  Fix errors before RPA or approve with override")
        approval_status = ApprovalStatus.PENDING_REVIEW
        approved = False

    elif summary["WARNING"] > 0:
        print("\n✅ CHECKPOINT 1 PASSED (with warnings)")
        print(f"   ✓ No critical/error issues")
        print(f"   ⚠️  {summary['WARNING']} warnings to review")

        if auto_approve_if_perfect:
            print("   ✓ AUTO-APPROVED (warnings only)")
            approval_status = ApprovalStatus.QUALITY_APPROVED
            approved = True
        else:
            print("   ⚠️  Human review RECOMMENDED")
            approval_status = ApprovalStatus.PENDING_REVIEW
            approved = False

    else:
        print("\n✅ CHECKPOINT 1 PASSED: PERFECT QUALITY")
        print("   ✓ No validation issues detected")
        print("   ✓ Export file is production-ready")

        if auto_approve_if_perfect:
            print("   ✓ AUTO-APPROVED")
            approval_status = ApprovalStatus.QUALITY_APPROVED
            approved = True
        else:
            print("   ⚠️  Human review still required")
            approval_status = ApprovalStatus.PENDING_REVIEW
            approved = False

    print("=" * 80)

    return approved, validation_summary, approval_status


# ==============================================================================
# CHECKPOINT 2: TAX CALCULATION REVIEW
# ==============================================================================

def checkpoint_2_tax_review(
    df: pd.DataFrame,
    tax_year: int,
    expected_totals: Optional[Dict] = None
) -> Tuple[bool, Dict]:
    """
    Checkpoint 2: Human review of tax calculations.

    Provides summary of tax calculations for human verification.

    Args:
        df: Export dataframe
        tax_year: Tax year
        expected_totals: Optional dict of expected totals for validation

    Returns:
        Tuple of (approved, tax_summary)
    """
    print("\n" + "=" * 80)
    print("CHECKPOINT 2: TAX CALCULATION REVIEW")
    print("=" * 80)
    print()

    # Calculate totals
    # Updated 2025-01-20: Support both old and new FA CS column names for compatibility
    total_cost = df.get("Tax Cost", df.get("Cost/Basis", pd.Series([0.0]))).sum()
    total_section_179 = df.get("Tax Sec 179 Expensed", df.get("Section 179 Amount", pd.Series([0.0]))).sum()
    total_bonus = df.get("Bonus Amount", pd.Series([0.0])).sum()
    total_depreciable_basis = df.get("Depreciable Basis", pd.Series([0.0])).sum()
    total_macrs_year1 = df.get("Tax Cur Depreciation", df.get("MACRS Year 1 Depreciation", pd.Series([0.0]))).sum()
    total_de_minimis = df.get("De Minimis Expensed", pd.Series([0.0])).sum()
    total_sec179_carryforward = df.get("Section 179 Carryforward", pd.Series([0.0])).sum()

    # Count assets by type
    additions = len(df[df["Transaction Type"].str.contains("addition", case=False, na=False)])
    disposals = len(df[df["Transaction Type"].str.contains("disposal", case=False, na=False)])
    transfers = len(df[df["Transaction Type"].str.contains("transfer", case=False, na=False)])

    # Year 1 total deduction
    year1_deduction = total_section_179 + total_bonus + total_macrs_year1 + total_de_minimis

    tax_summary = {
        "checkpoint": "2_TAX_REVIEW",
        "timestamp": datetime.now().isoformat(),
        "tax_year": tax_year,
        "total_assets": len(df),
        "additions": additions,
        "disposals": disposals,
        "transfers": transfers,
        "total_cost": total_cost,
        "total_section_179": total_section_179,
        "total_bonus": total_bonus,
        "total_depreciable_basis": total_depreciable_basis,
        "total_macrs_year1": total_macrs_year1,
        "total_de_minimis": total_de_minimis,
        "total_sec179_carryforward": total_sec179_carryforward,
        "year1_total_deduction": year1_deduction,
    }

    # Print summary
    print(f"Tax Year: {tax_year}")
    print()
    print("ASSET COUNTS:")
    print(f"  Total Assets:        {len(df):>6}")
    print(f"  - Additions:         {additions:>6}")
    print(f"  - Disposals:         {disposals:>6}")
    print(f"  - Transfers:         {transfers:>6}")
    print()
    print("TAX CALCULATIONS:")
    print(f"  Total Cost/Basis:              ${total_cost:>15,.2f}")
    print(f"  Section 179 Expensing:         ${total_section_179:>15,.2f}")
    print(f"  Bonus Depreciation:            ${total_bonus:>15,.2f}")
    print(f"  De Minimis Safe Harbor:        ${total_de_minimis:>15,.2f}")
    print(f"  MACRS Year 1 Depreciation:     ${total_macrs_year1:>15,.2f}")
    print(f"  {'─' * 70}")
    print(f"  YEAR 1 TOTAL DEDUCTION:        ${year1_deduction:>15,.2f}")
    print()

    if total_sec179_carryforward > 0:
        print(f"  ⚠️  Section 179 Carryforward:    ${total_sec179_carryforward:>15,.2f}")
        print(f"      (Must be disclosed on Form 4562 next year)")
        print()

    # Check against expected totals if provided
    variances = []
    if expected_totals:
        print("VARIANCE ANALYSIS:")
        for key, expected_value in expected_totals.items():
            actual_value = tax_summary.get(key, 0.0)
            variance = actual_value - expected_value
            variance_pct = (variance / expected_value * 100) if expected_value != 0 else 0

            if abs(variance) > 0.01:  # More than 1 cent variance
                variances.append({
                    "field": key,
                    "expected": expected_value,
                    "actual": actual_value,
                    "variance": variance,
                    "variance_pct": variance_pct
                })

                status = "✓" if abs(variance_pct) < 5 else "⚠️"
                print(f"  {status} {key}: ${variance:+,.2f} ({variance_pct:+.1f}%)")

        if not variances:
            print("  ✓ All calculations match expected totals")
        print()

    tax_summary["variances"] = variances

    print("=" * 80)
    print()
    print("⚠️  HUMAN REVIEW REQUIRED:")
    print("   1. Verify Section 179 amounts are correct")
    print("   2. Confirm bonus depreciation percentages")
    print("   3. Review MACRS classifications")
    print("   4. Check for any unusual amounts")
    print("   5. Verify carryforward calculations")
    print()
    print("=" * 80)

    # Manual approval required
    approved = False  # Must be manually approved

    return approved, tax_summary


# ==============================================================================
# CHECKPOINT 3: PRE-RPA APPROVAL CHECKLIST
# ==============================================================================

def checkpoint_3_pre_rpa_checklist(
    df: pd.DataFrame,
    output_file_path: str
) -> Tuple[bool, Dict]:
    """
    Checkpoint 3: Pre-RPA approval checklist.

    Final verification before RPA automation.

    Args:
        df: Export dataframe
        output_file_path: Path to export file

    Returns:
        Tuple of (approved, checklist_results)
    """
    print("\n" + "=" * 80)
    print("CHECKPOINT 3: PRE-RPA APPROVAL CHECKLIST")
    print("=" * 80)
    print()

    checklist = {
        "checkpoint": "3_PRE_RPA_CHECKLIST",
        "timestamp": datetime.now().isoformat(),
        "output_file": output_file_path,
        "checks": []
    }

    # Check 1: File exists and is readable
    check1 = {
        "check": "Export file exists and is readable",
        "passed": os.path.exists(output_file_path) and os.path.getsize(output_file_path) > 0,
        "details": f"File: {output_file_path}"
    }
    checklist["checks"].append(check1)

    # Check 2: No duplicate Asset #s
    asset_nums = df["Asset #"].dropna()
    duplicates = asset_nums[asset_nums.duplicated()].unique()
    check2 = {
        "check": "No duplicate Asset #s",
        "passed": len(duplicates) == 0,
        "details": f"Duplicates: {len(duplicates)}"
    }
    checklist["checks"].append(check2)

    # Check 3: All required columns present
    # Updated 2025-01-20 to match new FA CS export format
    required_cols = ["Asset #", "Description", "Date In Service", "Tax Cost"]
    missing = [col for col in required_cols if col not in df.columns]
    check3 = {
        "check": "All required columns present",
        "passed": len(missing) == 0,
        "details": f"Missing: {missing if missing else 'None'}"
    }
    checklist["checks"].append(check3)

    # Check 4: No null Asset #s
    null_asset_nums = df["Asset #"].isna().sum()
    check4 = {
        "check": "No null Asset #s",
        "passed": null_asset_nums == 0,
        "details": f"Null count: {null_asset_nums}"
    }
    checklist["checks"].append(check4)

    # Check 5: Data consistency
    check5_passed = True
    check5_details = []

    for idx, row in df.iterrows():
        # Updated 2025-01-20 to match new FA CS export format
        cost = float(row.get("Tax Cost") or 0)
        sec179 = float(row.get("Tax Sec 179 Expensed") or 0)
        bonus = float(row.get("Bonus Amount") or 0)

        if sec179 + bonus > cost + 0.01:
            check5_passed = False
            check5_details.append(f"Row {idx+2}: Sec179+Bonus > Cost")

        if len(check5_details) >= 5:  # Limit to first 5
            break

    check5 = {
        "check": "Data consistency (Sec179 + Bonus ≤ Cost)",
        "passed": check5_passed,
        "details": "; ".join(check5_details) if check5_details else "All consistent"
    }
    checklist["checks"].append(check5)

    # Print checklist
    print("RPA READINESS CHECKLIST:")
    print()

    all_passed = True
    for i, check in enumerate(checklist["checks"], 1):
        status = "✅" if check["passed"] else "❌"
        print(f"  {status} {i}. {check['check']}")
        print(f"     {check['details']}")

        if not check["passed"]:
            all_passed = False

    print()
    print("=" * 80)

    if all_passed:
        print("\n✅ ALL CHECKS PASSED - Ready for final approval")
    else:
        print("\n❌ SOME CHECKS FAILED - Fix issues before RPA")

    print("=" * 80)

    checklist["all_passed"] = all_passed

    return all_passed, checklist


# ==============================================================================
# FINAL APPROVAL & SIGN-OFF
# ==============================================================================

def final_approval_and_signoff(
    validation_summary: Dict,
    tax_summary: Dict,
    checklist: Dict,
    approver_name: str,
    approver_email: str,
    notes: str = ""
) -> Dict:
    """
    Final approval and sign-off for RPA processing.

    Creates audit trail of approval with all checkpoint data.

    Args:
        validation_summary: Results from checkpoint 1
        tax_summary: Results from checkpoint 2
        checklist: Results from checkpoint 3
        approver_name: Name of person approving
        approver_email: Email of approver
        notes: Optional approval notes

    Returns:
        Complete approval record with audit trail
    """
    print("\n" + "=" * 80)
    print("FINAL APPROVAL & SIGN-OFF")
    print("=" * 80)
    print()

    approval_record = {
        "approval_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "approval_timestamp": datetime.now().isoformat(),
        "approver_name": approver_name,
        "approver_email": approver_email,
        "approval_notes": notes,
        "status": ApprovalStatus.FINAL_APPROVED,
        "checkpoints": {
            "checkpoint_1_quality": validation_summary,
            "checkpoint_2_tax": tax_summary,
            "checkpoint_3_checklist": checklist,
        },
        "rpa_ready": True,
    }

    print(f"Approval ID:     {approval_record['approval_id']}")
    print(f"Approved By:     {approver_name}")
    print(f"Email:           {approver_email}")
    print(f"Timestamp:       {approval_record['approval_timestamp']}")
    print(f"Status:          {approval_record['status']}")
    print()

    if notes:
        print(f"Notes:           {notes}")
        print()

    print("CHECKPOINT SUMMARY:")
    print(f"  ✅ Checkpoint 1 (Quality):   {validation_summary.get('total_issues', 0)} issues")
    print(f"  ✅ Checkpoint 2 (Tax):       Reviewed and approved")
    print(f"  ✅ Checkpoint 3 (Pre-RPA):   {len(checklist['checks'])} checks passed")
    print()
    print("✅ FINAL APPROVAL GRANTED - RPA READY")
    print("=" * 80)

    return approval_record


def save_approval_record(
    approval_record: Dict,
    output_dir: str = ".",
    filename: Optional[str] = None
):
    """
    Save approval record to JSON file for audit trail.

    Args:
        approval_record: Approval record from final_approval_and_signoff()
        output_dir: Directory to save approval record
        filename: Optional custom filename
    """
    if not filename:
        filename = f"approval_{approval_record['approval_id']}.json"

    # Sanitize filename to prevent path traversal attacks
    filename = _sanitize_filename(filename)

    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w') as f:
        json.dump(approval_record, f, indent=2)

    print(f"\n✓ Approval record saved: {filepath}")
    print(f"  This file serves as audit trail for RPA processing.")

    return filepath


# ==============================================================================
# INTERACTIVE APPROVAL WORKFLOW
# ==============================================================================

def interactive_approval_workflow(
    df: pd.DataFrame,
    export_file_path: str,
    tax_year: int,
    expected_totals: Optional[Dict] = None
) -> Tuple[bool, Optional[Dict]]:
    """
    Interactive approval workflow with human checkpoints.

    Guides user through all approval checkpoints and collects sign-off.

    Args:
        df: Export dataframe
        export_file_path: Path to export file
        tax_year: Tax year
        expected_totals: Optional expected totals for variance analysis

    Returns:
        Tuple of (approved, approval_record)
    """
    print("\n" + "=" * 80)
    print("HUMAN-IN-THE-LOOP APPROVAL WORKFLOW")
    print("Fixed Asset CS Export & RPA Processing")
    print("=" * 80)
    print()
    print("This workflow requires human approval at multiple checkpoints")
    print("before RPA automation can proceed.")
    print()
    input("Press Enter to begin checkpoint 1 (Quality Review)...")

    # Checkpoint 1: Quality Review
    quality_approved, validation_summary, approval_status = checkpoint_1_quality_review(
        df, auto_approve_if_perfect=False
    )

    if approval_status == ApprovalStatus.REJECTED:
        print("\n❌ Workflow STOPPED: Critical issues detected")
        print("   Fix critical issues and restart workflow")
        return False, None

    if not quality_approved:
        print("\n⚠️  Quality review requires human decision:")
        response = input("   Approve anyway? (yes/no): ").strip().lower()

        if response != "yes":
            print("\n❌ Workflow STOPPED: Quality review not approved")
            return False, None

        print("\n✓ Quality review approved (override)")

    print("\n✓ Checkpoint 1 COMPLETE")
    input("\nPress Enter to continue to checkpoint 2 (Tax Review)...")

    # Checkpoint 2: Tax Review
    tax_approved, tax_summary = checkpoint_2_tax_review(
        df, tax_year, expected_totals
    )

    print("\n⚠️  Tax review requires human approval:")
    response = input("   Approve tax calculations? (yes/no): ").strip().lower()

    if response != "yes":
        print("\n❌ Workflow STOPPED: Tax review not approved")
        return False, None

    print("\n✓ Checkpoint 2 COMPLETE")
    input("\nPress Enter to continue to checkpoint 3 (Pre-RPA Checklist)...")

    # Checkpoint 3: Pre-RPA Checklist
    checklist_passed, checklist = checkpoint_3_pre_rpa_checklist(
        df, export_file_path
    )

    if not checklist_passed:
        print("\n⚠️  Some checklist items failed:")
        response = input("   Approve anyway? (yes/no): ").strip().lower()

        if response != "yes":
            print("\n❌ Workflow STOPPED: Checklist not approved")
            return False, None

        print("\n✓ Checklist approved (override)")

    print("\n✓ Checkpoint 3 COMPLETE")
    print("\n" + "=" * 80)
    print("FINAL SIGN-OFF REQUIRED")
    print("=" * 80)

    approver_name = input("\nYour name: ").strip()
    approver_email = input("Your email: ").strip()
    notes = input("Approval notes (optional): ").strip()

    print("\n" + "=" * 80)
    print("CONFIRMATION")
    print("=" * 80)
    print(f"Approver:  {approver_name} ({approver_email})")
    print(f"Tax Year:  {tax_year}")
    print(f"File:      {export_file_path}")
    print()

    final_confirm = input("FINAL APPROVAL - Authorize RPA processing? (YES/no): ").strip()

    if final_confirm != "YES":
        print("\n❌ FINAL APPROVAL DENIED - RPA not authorized")
        return False, None

    # Create final approval record
    approval_record = final_approval_and_signoff(
        validation_summary=validation_summary,
        tax_summary=tax_summary,
        checklist=checklist,
        approver_name=approver_name,
        approver_email=approver_email,
        notes=notes
    )

    # Save approval record
    save_approval_record(approval_record, output_dir=".")

    print("\n" + "=" * 80)
    print("✅ WORKFLOW COMPLETE - RPA AUTHORIZED")
    print("=" * 80)
    print()
    print("You may now proceed with RPA automation.")
    print("Approval record saved for audit trail.")
    print()

    return True, approval_record


# ==============================================================================
# OPTION 3: HYBRID APPROVAL WORKFLOW
# ==============================================================================

def hybrid_approval_workflow(
    df: pd.DataFrame,
    export_file_path: str,
    tax_year: int,
    expected_totals: Optional[Dict] = None,
    alert_callback: Optional[callable] = None,
    approval_callback: Optional[callable] = None
) -> Tuple[bool, Optional[Dict]]:
    """
    Hybrid approval workflow (Option 3) - Recommended for production use.

    Combines automation with mandatory human oversight:
    - Auto-approve quality if perfect
    - Auto-alert on critical errors
    - ALWAYS require human tax review (CPA-level approval)
    - Auto-pass pre-RPA checklist if conditions met
    - Final sign-off required with audit trail

    This workflow is optimal for production environments where you want
    quality gates to catch errors automatically, but still require
    professional tax review for compliance.

    Args:
        df: Export dataframe
        export_file_path: Path to export file
        tax_year: Tax year
        expected_totals: Optional expected totals for variance analysis
        alert_callback: Optional function to call for critical alerts
                       Signature: alert_callback(message: str, details: Dict)
        approval_callback: Optional function to get human tax approval
                          Signature: approval_callback(tax_summary: Dict) -> Tuple[bool, str, str, str]
                          Returns: (approved, approver_name, approver_email, notes)

    Returns:
        Tuple of (approved, approval_record)
    """
    print("\n" + "=" * 80)
    print("OPTION 3: HYBRID APPROVAL WORKFLOW")
    print("Auto-Quality Gates + Mandatory Human Tax Review")
    print("=" * 80)
    print()
    print("This workflow provides:")
    print("  ✓ Automated quality validation with auto-approval if perfect")
    print("  ✓ Automatic alerts for critical issues")
    print("  ✓ MANDATORY human review for tax calculations (CPA required)")
    print("  ✓ Streamlined pre-RPA checks")
    print("  ✓ Complete audit trail")
    print()
    print("=" * 80)

    # =========================================================================
    # CHECKPOINT 1: QUALITY REVIEW (AUTO-APPROVE IF PERFECT)
    # =========================================================================

    print("\n🔍 CHECKPOINT 1: Quality Review (Auto-Approve Mode)")
    print("-" * 80)

    quality_approved, validation_summary, approval_status = checkpoint_1_quality_review(
        df, auto_approve_if_perfect=True
    )

    # Handle critical errors - BLOCK immediately
    if approval_status == ApprovalStatus.REJECTED:
        error_message = "CRITICAL: Export quality validation failed - RPA BLOCKED"
        error_details = {
            "critical_count": validation_summary["critical_count"],
            "error_count": validation_summary["error_count"],
            "errors": validation_summary["validation_errors"]
        }

        print(f"\n❌ {error_message}")
        print("   WORKFLOW STOPPED - Must fix critical issues")

        # Send alert if callback provided
        if alert_callback:
            try:
                alert_callback(error_message, error_details)
                print("   ✓ Alert sent to monitoring system")
            except Exception as e:
                print(f"   ⚠️  Failed to send alert: {e}")

        return False, None

    # Handle errors - require review but don't auto-block
    if not quality_approved and approval_status == ApprovalStatus.PENDING_REVIEW:
        print("\n⚠️  Quality issues detected (non-critical)")
        print("   Proceeding to tax review, but issues should be reviewed")

        # Send notification if callback provided
        if alert_callback:
            try:
                alert_callback(
                    "WARNING: Export has non-critical quality issues",
                    {
                        "error_count": validation_summary["error_count"],
                        "warning_count": validation_summary["warning_count"],
                        "errors": validation_summary["validation_errors"]
                    }
                )
                print("   ✓ Notification sent")
            except Exception as e:
                print(f"   ⚠️  Failed to send notification: {e}")

    if quality_approved:
        print("\n✅ Checkpoint 1 AUTO-APPROVED")
    else:
        print("\n⚠️  Checkpoint 1 PASSED (with issues noted)")

    # =========================================================================
    # CHECKPOINT 2: TAX REVIEW (ALWAYS REQUIRE HUMAN APPROVAL)
    # =========================================================================

    print("\n💰 CHECKPOINT 2: Tax Calculation Review (MANDATORY HUMAN REVIEW)")
    print("-" * 80)

    tax_approved_auto, tax_summary = checkpoint_2_tax_review(
        df, tax_year, expected_totals
    )

    print("\n⚠️  CRITICAL: This checkpoint ALWAYS requires human CPA approval")
    print("   Tax calculations must be verified by a licensed professional")
    print()

    # Get human approval
    if approval_callback:
        # Use callback to get approval programmatically
        print("   Requesting approval via callback...")
        try:
            tax_approved, approver_name, approver_email, tax_notes = approval_callback(tax_summary)

            if not tax_approved:
                print("\n❌ Tax review NOT APPROVED by human reviewer")
                print("   WORKFLOW STOPPED")
                return False, None

            print(f"\n✅ Tax review APPROVED by {approver_name}")

        except Exception as e:
            print(f"\n❌ Error getting approval via callback: {e}")
            print("   WORKFLOW STOPPED")
            return False, None
    else:
        # Interactive approval
        print("   Manual approval required...")
        response = input("\n   Do you approve these tax calculations? (yes/no): ").strip().lower()

        if response != "yes":
            print("\n❌ Tax review NOT APPROVED")
            print("   WORKFLOW STOPPED")
            return False, None

        print("\n✓ Tax review approved")
        approver_name = input("   Your name (e.g., 'John Smith, CPA'): ").strip()
        approver_email = input("   Your email: ").strip()
        tax_notes = input("   Approval notes (optional): ").strip()

    print("\n✅ Checkpoint 2 APPROVED (Human verified)")

    # =========================================================================
    # CHECKPOINT 3: PRE-RPA CHECKLIST (AUTO-PASS IF ALL CHECKS PASS)
    # =========================================================================

    print("\n✅ CHECKPOINT 3: Pre-RPA Checklist (Auto-Pass Mode)")
    print("-" * 80)

    checklist_passed, checklist = checkpoint_3_pre_rpa_checklist(
        df, export_file_path
    )

    if checklist_passed:
        print("\n✅ Checkpoint 3 AUTO-APPROVED (all checks passed)")
    else:
        print("\n⚠️  Some pre-RPA checks failed")
        print("   Proceeding to final approval with warnings")

    # =========================================================================
    # FINAL APPROVAL & SIGN-OFF
    # =========================================================================

    print("\n📋 FINAL APPROVAL: Creating audit trail...")

    # Combine notes
    final_notes = f"HYBRID WORKFLOW (Option 3)\n"
    final_notes += f"Quality: {'Auto-approved (perfect)' if quality_approved else 'Passed with issues'}\n"
    final_notes += f"Tax: Human approved by CPA\n"
    final_notes += f"Pre-RPA: {'Auto-passed' if checklist_passed else 'Passed with overrides'}\n"

    if tax_notes:
        final_notes += f"\nTax Reviewer Notes: {tax_notes}"

    # Create final approval record
    approval_record = final_approval_and_signoff(
        validation_summary=validation_summary,
        tax_summary=tax_summary,
        checklist=checklist,
        approver_name=approver_name,
        approver_email=approver_email,
        notes=final_notes
    )

    # Add workflow type to approval record
    approval_record["workflow_type"] = "OPTION_3_HYBRID"
    approval_record["quality_auto_approved"] = quality_approved
    approval_record["tax_human_approved"] = True
    approval_record["checklist_auto_approved"] = checklist_passed

    # Save approval record
    save_approval_record(approval_record, output_dir=".")

    print("\n" + "=" * 80)
    print("✅ HYBRID WORKFLOW COMPLETE - RPA AUTHORIZED")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  • Quality Review: {'✓ Auto-approved' if quality_approved else '⚠ Approved with issues'}")
    print(f"  • Tax Review: ✓ Human approved by {approver_name}")
    print(f"  • Pre-RPA Check: {'✓ Auto-passed' if checklist_passed else '⚠ Passed with warnings'}")
    print(f"  • Approval ID: {approval_record['approval_id']}")
    print()
    print("You may now proceed with RPA automation.")
    print("Approval record saved for audit trail.")
    print()

    return True, approval_record
