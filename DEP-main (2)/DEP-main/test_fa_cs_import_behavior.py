#!/usr/bin/env python3
"""
Test FA CS Import Behavior - Minimal vs Full Export

This script helps determine whether FA CS:
1. Recalculates depreciation when importing (Scenario A)
2. Uses imported calculated values as-is (Scenario B)

Usage:
    python test_fa_cs_import_behavior.py

This will generate TWO Excel files:
- test_minimal_export.xlsx (minimal fields only)
- test_full_export.xlsx (all calculated fields)

Test Procedure:
1. Run this script to generate test files
2. Manually enter TEST-001 in FA CS and note calculated values
3. Import TEST-002 (minimal) from test_minimal_export.xlsx
4. Import TEST-003 (full) from test_full_export.xlsx
5. Compare all three assets in FA CS
6. Report findings to determine FA CS behavior
"""

import pandas as pd
from datetime import date
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from fixed_asset_ai.logic.fa_export import (
    build_fa,
    build_fa_minimal,
    export_fa_excel,
)
from fixed_asset_ai.logic.transaction_classifier import classify_all_transactions


def create_test_assets(tax_year: int = 2024) -> pd.DataFrame:
    """
    Create test assets to verify FA CS import behavior.

    Returns DataFrame with 3 test scenarios:
    1. Current year addition with Section 179
    2. Existing asset (prior year) with accumulated depreciation
    3. Disposal with recapture
    """

    test_data = [
        # Test 1: Current Year Addition (2024) - Section 179 eligible
        {
            "Asset ID": "TEST-001",
            "Description": "Test Computer - Manual Entry",
            "In Service Date": date(2024, 1, 1),
            "Acquisition Date": date(2024, 1, 1),
            "Cost": 5000.0,
            "Final Category": "Office Equipment",
            "Recovery Period": 5,
            "Method": "200DB",
            "MACRS Life": 5,
            "Convention": "HY",
        },
        # Test 2: Current Year Addition (same as TEST-001, for minimal import)
        {
            "Asset ID": "TEST-002",
            "Description": "Test Computer - Minimal Import",
            "In Service Date": date(2024, 1, 1),
            "Acquisition Date": date(2024, 1, 1),
            "Cost": 5000.0,
            "Final Category": "Office Equipment",
            "Recovery Period": 5,
            "Method": "200DB",
            "MACRS Life": 5,
            "Convention": "HY",
        },
        # Test 3: Current Year Addition (same as TEST-001, for full import)
        {
            "Asset ID": "TEST-003",
            "Description": "Test Computer - Full Import",
            "In Service Date": date(2024, 1, 1),
            "Acquisition Date": date(2024, 1, 1),
            "Cost": 5000.0,
            "Final Category": "Office Equipment",
            "Recovery Period": 5,
            "Method": "200DB",
            "MACRS Life": 5,
            "Convention": "HY",
        },
        # Test 4: Existing Asset (prior year)
        {
            "Asset ID": "TEST-004",
            "Description": "Test Desk - Existing Asset",
            "In Service Date": date(2020, 6, 15),
            "Acquisition Date": date(2020, 6, 15),
            "Cost": 3000.0,
            "Final Category": "Office Furniture",
            "Recovery Period": 7,
            "Method": "200DB",
            "MACRS Life": 7,
            "Convention": "HY",
            "Accumulated Depreciation": 2100.0,  # Example accumulated through 2023
        },
    ]

    df = pd.DataFrame(test_data)

    # Convert dates to pandas datetime
    df["In Service Date"] = pd.to_datetime(df["In Service Date"])
    df["Acquisition Date"] = pd.to_datetime(df["Acquisition Date"])

    return df


def main():
    print("=" * 80)
    print("FA CS IMPORT BEHAVIOR TEST")
    print("=" * 80)
    print()
    print("This script generates test files to determine FA CS import behavior.")
    print()

    # Configuration
    tax_year = 2024
    strategy = "Aggressive (179 + Bonus)"
    taxable_income = 100000.0  # High income to avoid 179 limitations

    # Create test assets
    print("Creating test assets...")
    df = create_test_assets(tax_year)

    # Display test assets
    print("\nTest Assets Created:")
    print("-" * 80)
    for idx, row in df.iterrows():
        print(f"{row['Asset ID']}: {row['Description']}")
        print(f"  In Service: {row['In Service Date'].strftime('%Y-%m-%d')}")
        print(f"  Cost: ${row['Cost']:,.2f}")
        print(f"  Life: {row['Recovery Period']} years")
        print()

    # Build FULL export (with all calculated fields)
    print("=" * 80)
    print("GENERATING FULL EXPORT (All Calculated Fields)")
    print("=" * 80)
    fa_full = build_fa(
        df=df.copy(),
        tax_year=tax_year,
        strategy=strategy,
        taxable_income=taxable_income,
        use_acq_if_missing=True,
    )

    # Save full export
    full_export_bytes = export_fa_excel(fa_full)
    full_export_path = "test_full_export.xlsx"
    with open(full_export_path, "wb") as f:
        f.write(full_export_bytes)

    print(f"\n✓ Full export saved: {full_export_path}")
    print(f"  Rows: {len(fa_full)}")
    print(f"  Columns: {len(fa_full.columns)}")
    print(f"  Includes: Section 179, Bonus, Tax Cur Depreciation, etc.")
    print()

    # Show calculated values from full export
    print("\nFull Export Calculated Values (for TEST-003):")
    print("-" * 80)
    test_003 = fa_full[fa_full["Original Asset ID"] == "TEST-003"].iloc[0]
    print(f"Tax Cost: ${test_003['Tax Cost']:,.2f}")
    print(f"Tax Method: {test_003['Tax Method']}")
    print(f"Tax Life: {test_003['Tax Life']}")
    print(f"Convention: {test_003['Convention']}")
    print(f"Tax Sec 179 Expensed: ${test_003.get('Tax Sec 179 Expensed', 0):,.2f}")
    print(f"Bonus Amount: ${test_003.get('Bonus Amount', 0):,.2f}")
    print(f"Tax Cur Depreciation: ${test_003.get('Tax Cur Depreciation', 0):,.2f}")
    print(f"Depreciable Basis: ${test_003.get('Depreciable Basis', 0):,.2f}")
    print()

    # Build MINIMAL export (basic fields only, let FA CS calculate)
    print("=" * 80)
    print("GENERATING MINIMAL EXPORT (Basic Fields Only)")
    print("=" * 80)

    # Classify transactions first (required by build_fa_minimal)
    df_classified = classify_all_transactions(df.copy(), tax_year, verbose=False)

    fa_minimal = build_fa_minimal(
        df=df_classified,
        tax_year=tax_year,
    )

    # Save minimal export
    minimal_export_bytes = export_fa_excel(fa_minimal)
    minimal_export_path = "test_minimal_export.xlsx"
    with open(minimal_export_path, "wb") as f:
        f.write(minimal_export_bytes)

    print(f"\n✓ Minimal export saved: {minimal_export_path}")
    print(f"  Rows: {len(fa_minimal)}")
    print(f"  Columns: {len(fa_minimal.columns)}")
    print(f"  Fields: Asset #, Description, Dates, Cost, Method, Life, Convention only")
    print()

    # Show minimal export fields
    print("\nMinimal Export Fields (for TEST-002):")
    print("-" * 80)
    test_002 = fa_minimal[fa_minimal["Original Asset ID"] == "TEST-002"].iloc[0]
    print(f"Asset #: {test_002['Asset #']}")
    print(f"Description: {test_002['Description']}")
    print(f"Date In Service: {test_002['Date In Service']}")
    print(f"Tax Cost: ${test_002['Tax Cost']:,.2f}")
    print(f"Tax Method: {test_002['Tax Method']}")
    print(f"Tax Life: {test_002['Tax Life']}")
    print(f"Convention: {test_002['Convention']}")
    print(f"Sheet Role: {test_002['Sheet Role']}")
    print()
    print("NOTE: No calculated fields (Sec 179, Bonus, Depreciation) included!")
    print("      FA CS will calculate these internally.")
    print()

    # Testing Instructions
    print("=" * 80)
    print("TESTING INSTRUCTIONS")
    print("=" * 80)
    print()
    print("Follow these steps to determine FA CS import behavior:")
    print()
    print("STEP 1: Manual Entry (Baseline)")
    print("-" * 80)
    print("In FA CS, manually create asset TEST-001:")
    print("  - Asset #: TEST-001")
    print("  - Description: Test Computer - Manual Entry")
    print("  - Date In Service: 1/1/2024")
    print("  - Tax Cost: $5,000")
    print("  - Tax Method: MACRS GDS")
    print("  - Tax Life: 5")
    print("  - Convention: HY")
    print()
    print("Let FA CS calculate Section 179, Bonus, and Depreciation.")
    print("WRITE DOWN the calculated values:")
    print("  [ ] Tax Sec 179 Expensed: $_________")
    print("  [ ] Bonus Amount: $_________")
    print("  [ ] Tax Cur Depreciation: $_________")
    print("  [ ] Depreciable Basis: $_________")
    print()

    print("STEP 2: Import Minimal File")
    print("-" * 80)
    print(f"In FA CS, import: {minimal_export_path}")
    print("This file contains TEST-002 with MINIMAL fields only.")
    print("NO calculated values are included - FA CS must calculate them.")
    print()
    print("After import, check TEST-002 in FA CS:")
    print("  [ ] Tax Sec 179 Expensed: $_________")
    print("  [ ] Bonus Amount: $_________")
    print("  [ ] Tax Cur Depreciation: $_________")
    print("  [ ] Depreciable Basis: $_________")
    print()

    print("STEP 3: Import Full File")
    print("-" * 80)
    print(f"In FA CS, import: {full_export_path}")
    print("This file contains TEST-003 with ALL calculated fields.")
    print()
    print(f"Our tool calculated (for TEST-003):")
    print(f"  - Tax Sec 179 Expensed: ${test_003.get('Tax Sec 179 Expensed', 0):,.2f}")
    print(f"  - Bonus Amount: ${test_003.get('Bonus Amount', 0):,.2f}")
    print(f"  - Tax Cur Depreciation: ${test_003.get('Tax Cur Depreciation', 0):,.2f}")
    print(f"  - Depreciable Basis: ${test_003.get('Depreciable Basis', 0):,.2f}")
    print()
    print("After import, check TEST-003 in FA CS:")
    print("  [ ] Tax Sec 179 Expensed: $_________")
    print("  [ ] Bonus Amount: $_________")
    print("  [ ] Tax Cur Depreciation: $_________")
    print("  [ ] Depreciable Basis: $_________")
    print()

    print("STEP 4: Compare All Three Assets")
    print("-" * 80)
    print("In FA CS, compare TEST-001, TEST-002, and TEST-003:")
    print()
    print("SCENARIO A: FA CS Recalculates (Expected)")
    print("  ✓ TEST-001 (manual) = TEST-002 (minimal) = TEST-003 (full)")
    print("  ✓ All three have SAME calculated values")
    print("  ✓ FA CS ignored our calculations and recalculated")
    print("  ✓ CONCLUSION: Safe to use minimal OR full export")
    print()
    print("SCENARIO B: FA CS Uses Imported Values (Possible)")
    print("  ✗ TEST-001 (manual) = TEST-002 (minimal) ≠ TEST-003 (full)")
    print("  ✗ TEST-003 matches our tool's calculations exactly")
    print("  ✗ FA CS used imported values without recalculating")
    print("  ✗ CONCLUSION: Must verify our calculations are 100% accurate")
    print()

    print("=" * 80)
    print("REPORT RESULTS")
    print("=" * 80)
    print()
    print("After testing, report back:")
    print()
    print("1. Do all three assets have SAME calculated values?")
    print("   YES = FA CS recalculates (Scenario A)")
    print("   NO = FA CS uses imported values (Scenario B)")
    print()
    print("2. If NO, which values differ?")
    print("   - Section 179?")
    print("   - Bonus?")
    print("   - Depreciation?")
    print()
    print("3. Screenshot or copy all calculated values for comparison.")
    print()
    print("=" * 80)
    print()
    print("Test files generated successfully!")
    print(f"  - {minimal_export_path}")
    print(f"  - {full_export_path}")
    print()
    print("Ready to test in FA CS!")
    print("=" * 80)


if __name__ == "__main__":
    main()
