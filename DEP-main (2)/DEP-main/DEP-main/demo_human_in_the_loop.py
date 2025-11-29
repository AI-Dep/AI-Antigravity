"""
Human-in-the-Loop Approval Workflow - Demonstration

Shows how to integrate human approval checkpoints before RPA automation.

CRITICAL: This is the recommended production workflow for tax compliance.
Never run RPA without human approval for tax data.
"""

import pandas as pd
from datetime import date
from fixed_asset_ai.logic.human_approval_workflow import (
    checkpoint_1_quality_review,
    checkpoint_2_tax_review,
    checkpoint_3_pre_rpa_checklist,
    final_approval_and_signoff,
    save_approval_record,
    interactive_approval_workflow,
)


# ==============================================================================
# SCENARIO 1: AUTOMATED WORKFLOW (NON-INTERACTIVE)
# ==============================================================================

def demo_automated_approval():
    """
    Demonstrate automated approval workflow with programmatic sign-off.

    Use this for batch processing where human has pre-approved parameters.
    """
    print("\n" + "=" * 80)
    print("SCENARIO 1: AUTOMATED APPROVAL WORKFLOW")
    print("=" * 80)

    # Sample export data
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

    export_file_path = "demo_export.xlsx"
    tax_year = 2024

    # Checkpoint 1: Quality Review
    quality_approved, validation_summary, approval_status = checkpoint_1_quality_review(
        df, auto_approve_if_perfect=True  # Auto-approve if perfect
    )

    if not quality_approved:
        print("\n❌ Quality review failed - stopping workflow")
        return False

    # Checkpoint 2: Tax Review (with expected totals)
    expected_totals = {
        "total_section_179": 80000.00,
        "total_bonus": 52000.00,
        "year1_total_deduction": 134029.00,
    }

    tax_approved, tax_summary = checkpoint_2_tax_review(
        df, tax_year, expected_totals
    )

    # In automated workflow, programmatic approval
    print("\n✓ Tax calculations reviewed programmatically")

    # Checkpoint 3: Pre-RPA Checklist
    checklist_passed, checklist = checkpoint_3_pre_rpa_checklist(
        df, export_file_path
    )

    if not checklist_passed:
        print("\n❌ Checklist failed - stopping workflow")
        return False

    # Final approval (programmatic sign-off)
    approval_record = final_approval_and_signoff(
        validation_summary=validation_summary,
        tax_summary=tax_summary,
        checklist=checklist,
        approver_name="Tax Manager (Automated)",
        approver_email="taxmanager@company.com",
        notes="Automated approval - parameters pre-verified"
    )

    # Save approval record
    save_approval_record(approval_record, output_dir=".", filename="approval_automated_demo.json")

    print("\n✅ Automated workflow complete - RPA ready")

    return True


# ==============================================================================
# SCENARIO 2: MANUAL REVIEW WORKFLOW
# ==============================================================================

def demo_manual_review():
    """
    Demonstrate manual review workflow with explicit human checkpoints.

    Use this when human must review each checkpoint.
    """
    print("\n" + "=" * 80)
    print("SCENARIO 2: MANUAL REVIEW WORKFLOW")
    print("=" * 80)

    # Sample export with some warnings
    df = pd.DataFrame([
        {
            "Asset ID": "EQ-2024-001",
            "Property Description": "Production Equipment",
            "Date In Service": date(2024, 1, 15),
            "Cost/Basis": 100000.00,
            "Section 179 Amount": 50000.00,
            "Bonus Amount": 40000.00,
            "Depreciable Basis": 10000.00,
            "MACRS Year 1 Depreciation": 1429.00,
            "Section 179 Allowed": 50000.00,
            "Section 179 Carryforward": 0.00,
            "Transaction Type": "Addition",
        },
        {
            "Asset ID": "EQ-2024-002",
            "Property Description": "Large equipment item with very detailed description" * 10,  # Long text (warning)
            "Date In Service": date(2024, 2, 20),
            "Cost/Basis": 75000.00,
            "Section 179 Amount": 50000.00,
            "Bonus Amount": 20000.00,
            "Depreciable Basis": 5000.00,
            "MACRS Year 1 Depreciation": 715.00,
            "Section 179 Allowed": 40000.00,  # Carryforward scenario
            "Section 179 Carryforward": 10000.00,
            "Transaction Type": "Addition",
        }
    ])

    export_file_path = "demo_export_manual.xlsx"
    tax_year = 2024

    # Checkpoint 1: Quality Review (manual approval)
    quality_approved, validation_summary, approval_status = checkpoint_1_quality_review(
        df, auto_approve_if_perfect=False  # Require manual approval
    )

    print("\n⚠️  MANUAL REVIEW POINT:")
    print("    Review validation results above.")
    print("    Decision: APPROVED (for demo purposes)")
    print()

    # Checkpoint 2: Tax Review
    tax_approved, tax_summary = checkpoint_2_tax_review(df, tax_year)

    print("\n⚠️  MANUAL REVIEW POINT:")
    print("    Review tax calculations above.")
    print("    Verify:")
    print("      - Section 179 amounts")
    print("      - Bonus depreciation percentages")
    print("      - MACRS classifications")
    print("      - Carryforward amounts")
    print("    Decision: APPROVED (for demo purposes)")
    print()

    # Checkpoint 3: Pre-RPA Checklist
    checklist_passed, checklist = checkpoint_3_pre_rpa_checklist(df, export_file_path)

    print("\n⚠️  MANUAL REVIEW POINT:")
    print("    Review RPA readiness checklist above.")
    print("    Decision: APPROVED (for demo purposes)")
    print()

    # Final approval
    approval_record = final_approval_and_signoff(
        validation_summary=validation_summary,
        tax_summary=tax_summary,
        checklist=checklist,
        approver_name="John Smith, CPA",
        approver_email="jsmith@accounting.com",
        notes="Manual review completed. Section 179 carryforward verified."
    )

    save_approval_record(approval_record, output_dir=".", filename="approval_manual_demo.json")

    print("\n✅ Manual review workflow complete - RPA ready")

    return True


# ==============================================================================
# SCENARIO 3: INTERACTIVE WORKFLOW (COMMENTED OUT - REQUIRES USER INPUT)
# ==============================================================================

def demo_interactive_workflow():
    """
    Demonstrate interactive workflow with real user input.

    UNCOMMENT to test interactive mode (requires human input).
    """
    print("\n" + "=" * 80)
    print("SCENARIO 3: INTERACTIVE WORKFLOW")
    print("=" * 80)
    print()
    print("NOTE: This scenario is commented out in demo.")
    print("      Uncomment the code below to test interactive mode.")
    print()

    # UNCOMMENT BELOW FOR INTERACTIVE TESTING:
    # ------------------------------------
    # df = pd.DataFrame([...])  # Your export data
    # export_file_path = "export.xlsx"
    # tax_year = 2024
    #
    # approved, approval_record = interactive_approval_workflow(
    #     df=df,
    #     export_file_path=export_file_path,
    #     tax_year=tax_year,
    #     expected_totals=None  # Optional
    # )
    #
    # if approved:
    #     print("✅ RPA AUTHORIZED - Proceed with automation")
    #     # Your RPA code here...
    # else:
    #     print("❌ RPA NOT AUTHORIZED - Do not proceed")
    # ------------------------------------

    return True


# ==============================================================================
# SCENARIO 4: INTEGRATION WITH EXISTING WORKFLOW
# ==============================================================================

def demo_integrated_workflow():
    """
    Demonstrate integration with existing Fixed Asset AI workflow.

    Shows how to add approval checkpoints to build_fa() export.
    """
    print("\n" + "=" * 80)
    print("SCENARIO 4: INTEGRATED WORKFLOW")
    print("=" * 80)
    print()

    # Simulate output from build_fa()
    print("Step 1: Run Fixed Asset AI classification and calculations")
    print("  (This would be your build_fa() call)")
    print()

    # Simulated export dataframe
    df = pd.DataFrame([
        {
            "Asset ID": "A001",
            "Property Description": "Equipment",
            "Date In Service": date(2024, 1, 15),
            "Cost/Basis": 50000.00,
            "Section 179 Amount": 50000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "MACRS Year 1 Depreciation": 0.00,
            "Section 179 Allowed": 50000.00,
            "Section 179 Carryforward": 0.00,
            "Transaction Type": "Addition",
        }
    ])

    print("Step 2: Save export file")
    export_file_path = "FA_Import_2024.xlsx"
    # df.to_excel(export_file_path, index=False)
    print(f"  Export saved: {export_file_path}")
    print()

    print("Step 3: Run approval workflow")
    print("  (Human-in-the-loop checkpoints)")
    print()

    # Run all checkpoints
    quality_approved, validation_summary, _ = checkpoint_1_quality_review(
        df, auto_approve_if_perfect=True
    )

    tax_approved, tax_summary = checkpoint_2_tax_review(df, 2024)

    checklist_passed, checklist = checkpoint_3_pre_rpa_checklist(df, export_file_path)

    # Final approval
    approval_record = final_approval_and_signoff(
        validation_summary=validation_summary,
        tax_summary=tax_summary,
        checklist=checklist,
        approver_name="Integration Test",
        approver_email="test@company.com",
        notes="Integrated workflow test"
    )

    save_approval_record(approval_record, output_dir=".", filename="approval_integrated_demo.json")

    print("\nStep 4: Proceed with RPA automation")
    print("  (Only if approval granted)")
    print()

    if approval_record['rpa_ready']:
        print("✅ RPA AUTHORIZED - Safe to proceed")
        print("   RPA bot can now process the file")
    else:
        print("❌ RPA NOT AUTHORIZED - Do not proceed")

    return True


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("HUMAN-IN-THE-LOOP APPROVAL WORKFLOW - DEMONSTRATION")
    print("=" * 80)
    print()
    print("This demonstration shows how to integrate human approval checkpoints")
    print("before RPA automation of Fixed Asset CS imports.")
    print()

    # Run all scenarios
    print("\n")
    demo_automated_approval()

    print("\n" + "=" * 80)
    input("\nPress Enter to continue to next scenario...")

    demo_manual_review()

    print("\n" + "=" * 80)
    input("\nPress Enter to continue to next scenario...")

    demo_interactive_workflow()

    print("\n" + "=" * 80)
    input("\nPress Enter to continue to final scenario...")

    demo_integrated_workflow()

    # Summary
    print("\n" + "=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()
    print("APPROVAL WORKFLOW BENEFITS:")
    print("  ✓ Human oversight for tax compliance")
    print("  ✓ Multiple checkpoints (Quality, Tax, Pre-RPA)")
    print("  ✓ Audit trail with approval records")
    print("  ✓ Prevents RPA automation errors")
    print("  ✓ Flexible: automated or interactive")
    print()
    print("RECOMMENDED PRODUCTION WORKFLOW:")
    print("  1. Run Fixed Asset AI classification (build_fa)")
    print("  2. Automated quality validation (Checkpoint 1)")
    print("  3. Human tax review (Checkpoint 2)")
    print("  4. Pre-RPA checklist (Checkpoint 3)")
    print("  5. Final sign-off with audit trail")
    print("  6. RPA automation (only if approved)")
    print()
    print("CHECK OUTPUT FILES:")
    print("  - approval_automated_demo.json")
    print("  - approval_manual_demo.json")
    print("  - approval_integrated_demo.json")
    print()
    print("=" * 80)
