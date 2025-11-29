"""
Fixed Asset CS Export Quality Validation - Demonstration

This script demonstrates the comprehensive export quality validation
that ensures Fixed Asset CS import files are perfect quality and
RPA-compatible.

Run with: python demo_export_qa_validation.py
"""

import pandas as pd
from datetime import date
from fixed_asset_ai.logic.export_qa_validator import (
    validate_fixed_asset_cs_export,
    export_validation_report,
)


# ==============================================================================
# SCENARIO 1: PERFECT QUALITY EXPORT
# ==============================================================================

def demo_perfect_export():
    """Demonstrate validation with perfect quality export."""
    print("\n" + "=" * 80)
    print("SCENARIO 1: PERFECT QUALITY EXPORT")
    print("=" * 80)

    df = pd.DataFrame([
        {
            "Asset ID": "A001",
            "Property Description": "Office Equipment - Computer",
            "Date In Service": date(2024, 1, 15),
            "Acquisition Date": date(2024, 1, 10),
            "Cost/Basis": 10000.00,
            "Method": "200DB",
            "Life": 5,
            "Convention": "HY",
            "Section 179 Amount": 10000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "MACRS Year 1 Depreciation": 0.00,
            "Section 179 Allowed": 10000.00,
            "Section 179 Carryforward": 0.00,
            "De Minimis Expensed": 0.00,
            "Sheet Role": "addition",
            "Transaction Type": "Addition",
        },
        {
            "Asset ID": "A002",
            "Property Description": "Machinery - Production Equipment",
            "Date In Service": date(2024, 3, 20),
            "Acquisition Date": date(2024, 3, 15),
            "Cost/Basis": 50000.00,
            "Method": "200DB",
            "Life": 7,
            "Convention": "HY",
            "Section 179 Amount": 0.00,
            "Bonus Amount": 40000.00,
            "Depreciable Basis": 10000.00,
            "MACRS Year 1 Depreciation": 1429.00,
            "Section 179 Allowed": 0.00,
            "Section 179 Carryforward": 0.00,
            "De Minimis Expensed": 0.00,
            "Sheet Role": "addition",
            "Transaction Type": "Addition",
        }
    ])

    is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=True)

    return is_valid


# ==============================================================================
# SCENARIO 2: EXPORT WITH ISSUES (DEMONSTRATES VALIDATION DETECTION)
# ==============================================================================

def demo_export_with_issues():
    """Demonstrate validation detecting common issues."""
    print("\n" + "=" * 80)
    print("SCENARIO 2: EXPORT WITH VALIDATION ISSUES (FOR DEMONSTRATION)")
    print("=" * 80)

    df = pd.DataFrame([
        {
            "Asset ID": "A001",  # OK
            "Property Description": "Computer Equipment",
            "Date In Service": date(2024, 1, 15),
            "Acquisition Date": date(2024, 1, 10),
            "Cost/Basis": 10000.00,
            "Section 179 Amount": 10000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "Section 179 Allowed": 10000.00,
            "Section 179 Carryforward": 0.00,
        },
        {
            "Asset ID": "A001",  # DUPLICATE! (will be caught)
            "Property Description": "Vehicle",
            "Date In Service": date(2024, 2, 20),
            "Acquisition Date": date(2024, 2, 15),
            "Cost/Basis": 40000.00,
            "Section 179 Amount": 0.00,
            "Bonus Amount": 32000.00,
            "Depreciable Basis": 8000.00,
            "Section 179 Allowed": 0.00,
            "Section 179 Carryforward": 0.00,
        },
        {
            "Asset ID": None,  # MISSING ASSET ID! (will be caught)
            "Property Description": "Furniture",
            "Date In Service": date(2024, 3, 10),
            "Cost/Basis": 5000.00,
            "Section 179 Amount": 5000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "Section 179 Allowed": 5000.00,
            "Section 179 Carryforward": 0.00,
        },
        {
            "Asset ID": "A004",
            "Property Description": "Equipment",
            "Date In Service": date(2024, 4, 15),
            "Cost/Basis": 20000.00,
            "Section 179 Amount": 15000.00,
            "Bonus Amount": 10000.00,  # Section 179 + Bonus > Cost! (will be caught)
            "Depreciable Basis": 0.00,
            "Section 179 Allowed": 15000.00,
            "Section 179 Carryforward": 0.00,
        },
        {
            "Asset ID": "A005",
            "Property Description": "Tools",
            "Date In Service": date(2024, 5, 20),
            "Cost/Basis": 8000.00,
            "Section 179 Amount": 8000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "Section 179 Allowed": 6000.00,  # Allowed + Carryforward != Amount! (will be caught)
            "Section 179 Carryforward": 1000.00,  # Should be 2000
        }
    ])

    is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=True)

    # Export detailed validation report
    export_validation_report(df, output_path="export_validation_report_demo.xlsx")

    return is_valid


# ==============================================================================
# SCENARIO 3: RPA COMPATIBILITY CHECKS
# ==============================================================================

def demo_rpa_compatibility():
    """Demonstrate RPA-specific compatibility validation."""
    print("\n" + "=" * 80)
    print("SCENARIO 3: RPA COMPATIBILITY VALIDATION")
    print("=" * 80)

    df = pd.DataFrame([
        {
            "Asset ID": "A-001-2024",  # With dashes (OK)
            "Property Description": "Computer Equipment",
            "Date In Service": date(2024, 1, 15),
            "Cost/Basis": 5000.00,
            "Section 179 Amount": 5000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
        },
        {
            "Asset ID": "A 002",  # With space (WARNING - not recommended for RPA)
            "Property Description": "Office Furniture",
            "Date In Service": date(2024, 2, 10),
            "Cost/Basis": 3000.00,
            "Section 179 Amount": 3000.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
        },
        {
            "Asset ID": "A003",
            "Property Description": "Equipment with very long description" * 10,  # Very long text (WARNING)
            "Date In Service": date(2024, 3, 20),
            "Cost/Basis": 10000.00,
            "Section 179 Amount": 0.00,
            "Bonus Amount": 8000.00,
            "Depreciable Basis": 2000.00,
        }
    ])

    is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=True)

    return is_valid


# ==============================================================================
# SCENARIO 4: COMPREHENSIVE VALIDATION (REAL-WORLD SCENARIO)
# ==============================================================================

def demo_comprehensive_validation():
    """Demonstrate comprehensive validation with mixed transaction types."""
    print("\n" + "=" * 80)
    print("SCENARIO 4: COMPREHENSIVE VALIDATION (REAL-WORLD SCENARIO)")
    print("=" * 80)

    df = pd.DataFrame([
        # Addition
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
            "Uses ADS": False,
            "Sheet Role": "addition",
            "Transaction Type": "Addition",
            "Final Category": "Machinery & Equipment",
        },
        # Addition with carryforward
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
            "Section 179 Allowed": 20000.00,
            "Section 179 Carryforward": 10000.00,
            "De Minimis Expensed": 0.00,
            "Uses ADS": False,
            "Sheet Role": "addition",
            "Transaction Type": "Addition",
            "Final Category": "Trucks & Trailers",
        },
        # Disposal
        {
            "Asset ID": "EQ-2020-005",
            "Property Description": "Old Equipment - Disposed",
            "Date In Service": date(2020, 3, 10),
            "Acquisition Date": date(2020, 3, 5),
            "Cost/Basis": 25000.00,
            "Method": "",  # Empty for disposal
            "Life": "",
            "Convention": "",
            "Section 179 Amount": 0.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "MACRS Year 1 Depreciation": 0.00,
            "§1245 Recapture (Ordinary Income)": 15000.00,
            "Capital Gain": 2000.00,
            "Adjusted Basis at Disposal": 8000.00,
            "Sheet Role": "disposal",
            "Transaction Type": "Disposal",
        },
        # De minimis item
        {
            "Asset ID": "SM-2024-010",
            "Property Description": "Small Tools",
            "Date In Service": date(2024, 4, 5),
            "Acquisition Date": date(2024, 4, 1),
            "Cost/Basis": 0.00,  # Cost zeroed after de minimis
            "Section 179 Amount": 0.00,
            "Bonus Amount": 0.00,
            "Depreciable Basis": 0.00,
            "MACRS Year 1 Depreciation": 0.00,
            "De Minimis Expensed": 2400.00,
            "Sheet Role": "addition",
            "Transaction Type": "Addition",
        }
    ])

    is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=True)

    if is_valid:
        print("\n✅ EXPORT FILE IS PERFECT QUALITY")
        print("   ✓ Ready for Fixed Asset CS import")
        print("   ✓ Ready for RPA automation")
        print("   ✓ All data formats validated")
        print("   ✓ All business logic validated")
        print("   ✓ No compatibility issues detected")

    return is_valid


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("FIXED ASSET CS EXPORT QUALITY VALIDATION - DEMONSTRATION")
    print("=" * 80)
    print()
    print("This demonstration shows comprehensive validation that ensures")
    print("Fixed Asset CS export files are perfect quality and RPA-compatible.")
    print()

    # Run all scenarios
    results = {}

    results["perfect"] = demo_perfect_export()
    results["with_issues"] = demo_export_with_issues()
    results["rpa_compat"] = demo_rpa_compatibility()
    results["comprehensive"] = demo_comprehensive_validation()

    # Summary
    print("\n" + "=" * 80)
    print("VALIDATION DEMONSTRATION SUMMARY")
    print("=" * 80)
    print()
    print("Scenario 1 - Perfect Export:           ", "✅ PASSED" if results["perfect"] else "❌ FAILED")
    print("Scenario 2 - Export with Issues:       ", "✅ PASSED" if results["with_issues"] else "❌ FAILED (expected)")
    print("Scenario 3 - RPA Compatibility:        ", "✅ PASSED" if results["rpa_compat"] else "❌ FAILED")
    print("Scenario 4 - Comprehensive Validation: ", "✅ PASSED" if results["comprehensive"] else "❌ FAILED")
    print()
    print("=" * 80)
    print()

    if results["comprehensive"]:
        print("✅ CONCLUSION: Fixed Asset CS export quality validation is working perfectly!")
        print()
        print("The validation system checks:")
        print("  ✓ Column structure and naming")
        print("  ✓ Date format compliance")
        print("  ✓ Number format validation")
        print("  ✓ Text field compatibility")
        print("  ✓ Data consistency (business logic)")
        print("  ✓ RPA automation compatibility")
        print()
        print("ALL exports are automatically validated before being returned to ensure")
        print("perfect quality for Fixed Asset CS import and RPA automation.")
        print()
        print("=" * 80)
