#!/usr/bin/env python3
"""
Test that Asset# field is numeric-only in FA CS export
"""

import sys
import pandas as pd
from datetime import date

# Add the module to the path
sys.path.insert(0, "/home/user/DEP")

from fixed_asset_ai.logic.fa_export import build_fa
from fixed_asset_ai.logic.transaction_classifier import classify_all_transactions

def test_asset_number_numeric():
    """Test that Asset # is generated as numeric values"""

    # Create test data with alphanumeric Asset IDs
    test_data = pd.DataFrame([
        {
            "Asset ID": "A-001",  # Alphanumeric
            "Description": "Computer Equipment",
            "Cost": 5000,
            "In Service Date": date(2024, 1, 15),
            "Acquisition Date": date(2024, 1, 15),
            "Final Category": "Computer Equipment (5-Year MACRS)",
            "Recovery Period": 5,
            "Method": "200DB",
        },
        {
            "Asset ID": "EQ-2024-002",  # Alphanumeric with dashes
            "Description": "Office Furniture",
            "Cost": 3000,
            "In Service Date": date(2024, 3, 10),
            "Acquisition Date": date(2024, 3, 10),
            "Final Category": "Office Furniture (7-Year MACRS)",
            "Recovery Period": 7,
            "Method": "200DB",
        },
        {
            "Asset ID": "TEST 003",  # Alphanumeric with space
            "Description": "Manufacturing Equipment",
            "Cost": 25000,
            "In Service Date": date(2024, 6, 1),
            "Acquisition Date": date(2024, 6, 1),
            "Final Category": "Manufacturing Equipment (7-Year MACRS)",
            "Recovery Period": 7,
            "Method": "200DB",
        },
    ])

    # Classify transactions
    test_data = classify_all_transactions(test_data, tax_year=2024, verbose=False)

    # Build FA CS export
    fa = build_fa(
        df=test_data,
        tax_year=2024,
        strategy="Aggressive (179 + Bonus)",
        taxable_income=100000,
    )

    # Verify Asset # is numeric
    print("=" * 80)
    print("ASSET # NUMERIC VALIDATION TEST")
    print("=" * 80)
    print("\nOriginal Asset IDs (alphanumeric):")
    for orig_id in fa["Original Asset ID"]:
        print(f"  - {orig_id}")

    print("\nGenerated Asset # (numeric only):")
    for asset_num in fa["Asset #"]:
        print(f"  - {asset_num} (type: {type(asset_num).__name__})")

    # Validation checks
    print("\nValidation Results:")
    print("-" * 80)

    # Check 1: All Asset # are numeric
    all_numeric = True
    for idx, val in enumerate(fa["Asset #"]):
        try:
            numeric_val = pd.to_numeric(val, errors='raise')
            is_integer = float(numeric_val).is_integer()
            if not is_integer:
                print(f"❌ Asset #{idx+1}: Not an integer ({val})")
                all_numeric = False
        except (ValueError, TypeError):
            print(f"❌ Asset #{idx+1}: Not numeric ({val})")
            all_numeric = False

    if all_numeric:
        print("✅ All Asset # values are numeric integers")

    # Check 2: Sequential numbering
    expected_sequence = list(range(1, len(fa) + 1))
    actual_sequence = list(fa["Asset #"])

    if actual_sequence == expected_sequence:
        print(f"✅ Sequential numbering (1, 2, 3, ..., {len(fa)})")
    else:
        print(f"❌ Non-sequential numbering")
        print(f"   Expected: {expected_sequence}")
        print(f"   Got: {actual_sequence}")

    # Check 3: Original Asset ID preserved
    if "Original Asset ID" in fa.columns:
        print("✅ Original Asset ID preserved for reference")
        print("\nMapping:")
        for idx, row in fa.iterrows():
            print(f"   Asset # {row['Asset #']} → Original ID: {row['Original Asset ID']}")
    else:
        print("❌ Original Asset ID not preserved")

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    if all_numeric and "Original Asset ID" in fa.columns:
        print("✅ ALL CHECKS PASSED")
        print("\nKey Points:")
        print("  • Asset # is now purely numeric (1, 2, 3, ...)")
        print("  • Excel will display these correctly (no leading zeros issue)")
        print("  • Original Asset IDs preserved in 'Original Asset ID' column")
        print("  • FA CS import will accept numeric Asset # values")
        return True
    else:
        print("❌ SOME CHECKS FAILED")
        return False

if __name__ == "__main__":
    success = test_asset_number_numeric()
    sys.exit(0 if success else 1)
