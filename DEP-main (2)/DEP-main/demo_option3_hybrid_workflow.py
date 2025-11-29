"""
Option 3: Hybrid Approval Workflow - Demonstration

Demonstrates the recommended production workflow that combines:
- Automated quality gates (auto-approve if perfect)
- Mandatory human tax review (CPA-level approval)
- Streamlined pre-RPA checks
- Complete audit trail

This is the RECOMMENDED approach for most production environments.
"""

import pandas as pd
from datetime import date
from fixed_asset_ai.logic.human_approval_workflow import hybrid_approval_workflow


# ==============================================================================
# SCENARIO 1: HYBRID WORKFLOW WITH PERFECT QUALITY
# ==============================================================================

def demo_hybrid_perfect_quality():
    """
    Demonstrate hybrid workflow with perfect export quality.

    Expected flow:
    - Checkpoint 1: AUTO-APPROVED (no quality issues)
    - Checkpoint 2: HUMAN TAX REVIEW (always required)
    - Checkpoint 3: AUTO-PASSED (all checks pass)
    - Final: APPROVED with audit trail
    """
    print("\n" + "=" * 80)
    print("SCENARIO 1: HYBRID WORKFLOW - PERFECT QUALITY")
    print("=" * 80)
    print()

    # Sample perfect export data
    df = pd.DataFrame([
        {
            "Asset ID": "EQ-2024-001",
            "Property Description": "Production Machinery",
            "Date In Service": date(2024, 1, 15),
            "Acquisition Date": date(2024, 1, 10),
            "Cost/Basis": 100000.00,
            "Method": "200DB",
            "Life": 7,
            "Convention": "HY",
            "Section 179 Amount": 50000.00,
            "Bonus Amount": 40000.00,
            "Depreciable Basis": 10000.00,
            "MACRS Year 1 Depreciation": 1429.00,
            "Section 179 Allowed": 50000.00,
            "Section 179 Carryforward": 0.00,
            "De Minimis Expensed": 0.00,
            "Transaction Type": "Addition",
        },
        {
            "Asset ID": "VEH-2024-002",
            "Property Description": "Delivery Vehicle",
            "Date In Service": date(2024, 2, 20),
            "Acquisition Date": date(2024, 2, 15),
            "Cost/Basis": 45000.00,
            "Method": "200DB",
            "Life": 5,
            "Convention": "HY",
            "Section 179 Amount": 30000.00,
            "Bonus Amount": 12000.00,
            "Depreciable Basis": 3000.00,
            "MACRS Year 1 Depreciation": 600.00,
            "Section 179 Allowed": 30000.00,
            "Section 179 Carryforward": 0.00,
            "De Minimis Expensed": 0.00,
            "Transaction Type": "Addition",
        }
    ])

    export_file_path = "demo_hybrid_perfect.xlsx"
    tax_year = 2024

    # Optional: Define expected totals for variance analysis
    expected_totals = {
        "total_section_179": 80000.00,
        "total_bonus": 52000.00,
        "year1_total_deduction": 134029.00,
    }

    print("Running Option 3: Hybrid Approval Workflow...")
    print()
    print("This workflow will:")
    print("  1. AUTO-approve quality if perfect (Checkpoint 1)")
    print("  2. REQUIRE human tax review (Checkpoint 2)")
    print("  3. AUTO-pass pre-RPA checks if all pass (Checkpoint 3)")
    print("  4. Create complete audit trail")
    print()

    # NOTE: For interactive mode, don't provide approval_callback
    # The workflow will prompt for human input interactively

    approved, approval_record = hybrid_approval_workflow(
        df=df,
        export_file_path=export_file_path,
        tax_year=tax_year,
        expected_totals=expected_totals,
        # alert_callback=None,      # Optional: add email/Slack alerts
        # approval_callback=None,   # Optional: programmatic approval
    )

    if approved:
        print("\n" + "=" * 80)
        print("✅ SUCCESS: RPA AUTHORIZED")
        print("=" * 80)
        print()
        print(f"Approval Record: approval_{approval_record['approval_id']}.json")
        print()
        print("You may now proceed with RPA automation:")
        print("  - run_rpa_bot(export_file_path)")
        print()
    else:
        print("\n" + "=" * 80)
        print("❌ FAILED: RPA NOT AUTHORIZED")
        print("=" * 80)
        print()
        print("Review the issues above and fix before retrying.")
        print()

    return approved


# ==============================================================================
# SCENARIO 2: HYBRID WORKFLOW WITH PROGRAMMATIC APPROVAL
# ==============================================================================

def demo_hybrid_programmatic_approval():
    """
    Demonstrate hybrid workflow with programmatic tax approval.

    This shows how to integrate with automated approval systems
    (e.g., email approval links, web interfaces, etc.)
    """
    print("\n" + "=" * 80)
    print("SCENARIO 2: HYBRID WORKFLOW - PROGRAMMATIC APPROVAL")
    print("=" * 80)
    print()

    # Sample data
    df = pd.DataFrame([
        {
            "Asset ID": "COMP-2024-001",
            "Property Description": "Computer Equipment",
            "Date In Service": date(2024, 3, 1),
            "Acquisition Date": date(2024, 3, 1),
            "Cost/Basis": 25000.00,
            "Method": "200DB",
            "Life": 5,
            "Convention": "HY",
            "Section 179 Amount": 25000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "MACRS Year 1 Depreciation": 0.00,
            "Section 179 Allowed": 25000.00,
            "Section 179 Carryforward": 0.00,
            "De Minimis Expensed": 0.00,
            "Transaction Type": "Addition",
        }
    ])

    export_file_path = "demo_hybrid_programmatic.xlsx"
    tax_year = 2024

    # Define alert callback for critical issues
    def send_alert(message: str, details: dict):
        """Send alert to monitoring system."""
        print(f"\n📧 ALERT SENT: {message}")
        print(f"   Details: {details}")
        # In production: send email, Slack message, PagerDuty alert, etc.

    # Define approval callback for programmatic tax approval
    def get_tax_approval(tax_summary: dict) -> tuple:
        """
        Get tax approval programmatically.

        In production, this could:
        - Send email with approval link
        - Create web form for approval
        - Integrate with approval workflow system
        - Wait for webhook callback

        For demo, we'll auto-approve.
        """
        print("\n📧 TAX APPROVAL REQUEST SENT")
        print("   Sent to: tax_manager@company.com")
        print("   Method: Email with approval link")
        print()
        print("   (For demo: Auto-approving after simulated review)")
        print()

        # In production: wait for actual approval
        # approved = wait_for_approval_webhook()

        # Simulate approval
        approved = True
        approver_name = "Jane Doe, CPA"
        approver_email = "jane.doe@company.com"
        notes = "Reviewed via email. Section 179 amount verified. Approved."

        return approved, approver_name, approver_email, notes

    print("Running Option 3 with callbacks...")
    print()

    approved, approval_record = hybrid_approval_workflow(
        df=df,
        export_file_path=export_file_path,
        tax_year=tax_year,
        expected_totals=None,
        alert_callback=send_alert,
        approval_callback=get_tax_approval
    )

    if approved:
        print("\n✅ RPA AUTHORIZED (programmatic approval)")
        print(f"   Approval ID: {approval_record['approval_id']}")
    else:
        print("\n❌ RPA NOT AUTHORIZED")

    return approved


# ==============================================================================
# SCENARIO 3: HYBRID WORKFLOW WITH CRITICAL ERRORS
# ==============================================================================

def demo_hybrid_with_errors():
    """
    Demonstrate hybrid workflow when critical errors are detected.

    Expected flow:
    - Checkpoint 1: REJECTED (critical errors)
    - Alert sent
    - Workflow STOPPED
    """
    print("\n" + "=" * 80)
    print("SCENARIO 3: HYBRID WORKFLOW - CRITICAL ERRORS")
    print("=" * 80)
    print()

    # Sample data with CRITICAL issues (missing required fields)
    df = pd.DataFrame([
        {
            "Asset ID": None,  # CRITICAL: Missing Asset ID
            "Property Description": "Equipment",
            "Date In Service": "invalid_date",  # CRITICAL: Invalid date
            "Cost/Basis": -1000.00,  # CRITICAL: Negative cost
            "Section 179 Amount": 50000.00,
            "Bonus Amount": 60000.00,  # CRITICAL: Sec179 + Bonus > Cost
            "Transaction Type": "Addition",
        }
    ])

    export_file_path = "demo_hybrid_errors.xlsx"
    tax_year = 2024

    # Alert callback
    critical_alerts = []

    def capture_alert(message: str, details: dict):
        """Capture alerts for demo."""
        critical_alerts.append({"message": message, "details": details})
        print(f"\n🚨 CRITICAL ALERT: {message}")
        print(f"   Critical Count: {details.get('critical_count', 'N/A')}")
        print(f"   Error Count: {details.get('error_count', 'N/A')}")

    print("Running Option 3 with intentional errors...")
    print()

    approved, approval_record = hybrid_approval_workflow(
        df=df,
        export_file_path=export_file_path,
        tax_year=tax_year,
        alert_callback=capture_alert
    )

    print("\n" + "=" * 80)
    print("EXPECTED RESULT: Workflow blocked by critical errors")
    print("=" * 80)
    print()

    if not approved:
        print("✅ CORRECT: RPA blocked due to critical issues")
        print(f"   Alerts sent: {len(critical_alerts)}")
        print()
        print("ACTION REQUIRED:")
        print("  1. Fix critical validation errors")
        print("  2. Re-run export generation")
        print("  3. Re-run approval workflow")
    else:
        print("❌ UNEXPECTED: Should have been blocked")

    return approved


# ==============================================================================
# SCENARIO 4: INTEGRATION WITH EXISTING FA AI WORKFLOW
# ==============================================================================

def demo_integrated_option3_workflow():
    """
    Demonstrate how to integrate Option 3 into existing Fixed Asset AI workflow.

    Shows complete end-to-end flow:
    1. Fixed Asset AI classification (build_fa)
    2. Export to Excel (export_fa_excel)
    3. Option 3 Hybrid Approval Workflow
    4. RPA automation (if approved)
    """
    print("\n" + "=" * 80)
    print("SCENARIO 4: INTEGRATED OPTION 3 WORKFLOW")
    print("=" * 80)
    print()

    print("COMPLETE PRODUCTION WORKFLOW:")
    print("=" * 80)
    print()

    # Step 1: Fixed Asset AI Processing
    print("Step 1: Fixed Asset AI Classification")
    print("  fa_df = build_fa(df, tax_year=2024, strategy='Aggressive', taxable_income=500000)")
    print()

    # Simulated output
    fa_df = pd.DataFrame([
        {
            "Asset ID": "FA-2024-001",
            "Property Description": "Manufacturing Equipment",
            "Date In Service": date(2024, 1, 15),
            "Acquisition Date": date(2024, 1, 15),
            "Cost/Basis": 150000.00,
            "Method": "200DB",
            "Life": 7,
            "Convention": "HY",
            "Section 179 Amount": 100000.00,
            "Bonus Amount": 40000.00,
            "Depreciable Basis": 10000.00,
            "MACRS Year 1 Depreciation": 1429.00,
            "Section 179 Allowed": 100000.00,
            "Section 179 Carryforward": 0.00,
            "De Minimis Expensed": 0.00,
            "Transaction Type": "Addition",
        }
    ])

    # Step 2: Export to Excel
    print("Step 2: Export to Excel")
    export_file_path = "FA_Import_2024_Production.xlsx"
    print(f"  export_fa_excel(fa_df) -> {export_file_path}")
    # In production: excel_bytes = export_fa_excel(fa_df)
    #                with open(export_file_path, 'wb') as f:
    #                    f.write(excel_bytes)
    print()

    # Step 3: Option 3 Hybrid Approval Workflow
    print("Step 3: Option 3 Hybrid Approval Workflow")
    print("  (Auto-quality gates + Human tax review)")
    print()

    def production_alert(message: str, details: dict):
        """Production alert system."""
        print(f"📧 Alert sent to: ops@company.com")
        print(f"   Subject: {message}")
        # In production: send_email() or send_slack_message()

    def production_tax_approval(tax_summary: dict) -> tuple:
        """Production tax approval system."""
        print("📧 Tax review email sent to: cpa@company.com")
        print("   Link: https://approval.company.com/tax-review/12345")

        # Simulate approval
        print("   ⏳ Waiting for CPA approval...")
        print("   ✓ Approved by CPA")

        return True, "Sarah Johnson, CPA", "sarah.johnson@company.com", "All calculations verified."

    approved, approval_record = hybrid_approval_workflow(
        df=fa_df,
        export_file_path=export_file_path,
        tax_year=2024,
        alert_callback=production_alert,
        approval_callback=production_tax_approval
    )

    # Step 4: RPA Automation (only if approved)
    print("\nStep 4: RPA Automation")

    if approved:
        print("  ✅ APPROVAL GRANTED - Proceeding with RPA")
        print(f"     Approval ID: {approval_record['approval_id']}")
        print()
        print("  run_rpa_bot(")
        print(f"      file_path='{export_file_path}',")
        print(f"      approval_id='{approval_record['approval_id']}'")
        print("  )")
        print()
        print("  ✓ RPA automation complete")
        print("  ✓ Data imported to Fixed Asset CS")
        print("  ✓ Audit trail saved")
    else:
        print("  ❌ APPROVAL DENIED - RPA blocked")
        print("     Review issues and retry")

    print()
    print("=" * 80)
    print("WORKFLOW COMPLETE")
    print("=" * 80)

    return approved


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("OPTION 3: HYBRID APPROVAL WORKFLOW - DEMONSTRATION")
    print("=" * 80)
    print()
    print("This demonstrates the RECOMMENDED production workflow that combines:")
    print("  ✓ Automated quality gates (fast)")
    print("  ✓ Mandatory human tax review (compliant)")
    print("  ✓ Streamlined pre-RPA checks (safe)")
    print("  ✓ Complete audit trail (auditable)")
    print()
    print("=" * 80)

    # Run demonstration scenarios
    print("\n\n")
    print("SCENARIO 1: Perfect Quality Export")
    print("=" * 80)
    print("Press Enter to run Scenario 1 (will prompt for tax approval)...")
    input()

    demo_hybrid_perfect_quality()

    print("\n" + "=" * 80)
    print("Press Enter to continue to Scenario 2...")
    input()

    demo_hybrid_programmatic_approval()

    print("\n" + "=" * 80)
    print("Press Enter to continue to Scenario 3...")
    input()

    demo_hybrid_with_errors()

    print("\n" + "=" * 80)
    print("Press Enter to continue to Scenario 4...")
    input()

    demo_integrated_option3_workflow()

    # Summary
    print("\n\n")
    print("=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()
    print("OPTION 3 HYBRID WORKFLOW BENEFITS:")
    print()
    print("✅ FAST: Auto-approve quality if perfect")
    print("   - No manual intervention for clean exports")
    print("   - Instant feedback on quality issues")
    print()
    print("✅ COMPLIANT: Mandatory CPA review for tax")
    print("   - Professional oversight for IRC compliance")
    print("   - Audit defense with documented review")
    print()
    print("✅ SAFE: Automatic critical error blocking")
    print("   - Prevents RPA automation errors")
    print("   - Alerts for immediate attention")
    print()
    print("✅ FLEXIBLE: Interactive or programmatic")
    print("   - Interactive mode for manual approval")
    print("   - Callback mode for automated systems")
    print()
    print("✅ AUDITABLE: Complete audit trail")
    print("   - All checkpoints logged")
    print("   - Timestamped approvals")
    print("   - Named approvers")
    print()
    print("=" * 80)
    print("RECOMMENDED FOR:")
    print("  • Production environments")
    print("  • Batch processing with quality gates")
    print("  • Tax compliance requirements")
    print("  • Environments with CPA oversight")
    print()
    print("INTEGRATION:")
    print("  from fixed_asset_ai.logic.human_approval_workflow import hybrid_approval_workflow")
    print()
    print("  approved, record = hybrid_approval_workflow(")
    print("      df=fa_export_df,")
    print("      export_file_path='FA_Import.xlsx',")
    print("      tax_year=2024,")
    print("      alert_callback=send_alerts,      # Optional")
    print("      approval_callback=get_approval   # Optional")
    print("  )")
    print()
    print("  if approved:")
    print("      run_rpa_automation()")
    print()
    print("=" * 80)
