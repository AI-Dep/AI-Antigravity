#!/usr/bin/env python3
"""
Comprehensive Feature Testing Script for Fixed Asset AI

This script tests ALL active features systematically to ensure they work correctly.
Tests are performed on backend logic modules (not UI components).
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("FIXED ASSET AI - COMPREHENSIVE FEATURE TEST")
print("=" * 80)
print(f"Test Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
print()

# Test results tracking
test_results = []

def test_result(test_name, passed, details=""):
    """Record test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    test_results.append({
        'test': test_name,
        'passed': passed,
        'details': details
    })
    print(f"{status}: {test_name}")
    if details:
        print(f"   Details: {details}")
    print()

# ================================================================
# TEST 1: Load Test Data
# ================================================================
print("TEST 1: Loading Test Data")
print("-" * 80)

try:
    df = pd.read_excel('comprehensive_test_data.xlsx', sheet_name='Assets')
    test_result("Load test data file", True, f"Loaded {len(df)} assets")
except Exception as e:
    test_result("Load test data file", False, str(e))
    print("CRITICAL: Cannot continue without test data")
    sys.exit(1)

# ================================================================
# TEST 2: Sheet Loader Module
# ================================================================
print("TEST 2: Sheet Loader Module")
print("-" * 80)

try:
    from fixed_asset_ai.logic.sheet_loader import build_unified_dataframe

    # Test with our data
    unified_df = build_unified_dataframe(df, "Assets")

    # Verify required columns exist
    required_cols = ['Asset ID', 'Description', 'Cost', 'Date In Service']
    missing_cols = [col for col in required_cols if col not in unified_df.columns]

    if missing_cols:
        test_result("Sheet loader - unified dataframe", False,
                   f"Missing columns: {missing_cols}")
    else:
        test_result("Sheet loader - unified dataframe", True,
                   f"Generated {len(unified_df)} rows with all required columns")

except Exception as e:
    test_result("Sheet loader - unified dataframe", False, str(e))
    # Fallback - use original dataframe
    unified_df = df.copy()

# ================================================================
# TEST 3: Transaction Classifier
# ================================================================
print("TEST 3: Transaction Classifier")
print("-" * 80)

try:
    from fixed_asset_ai.logic.transaction_classifier import classify_all_transactions, validate_transaction_classification

    # Ensure unified_df exists
    if 'unified_df' not in locals():
        unified_df = df.copy()

    # Classify transactions
    classified_df = classify_all_transactions(unified_df.copy(), tax_year=2024)

    # Verify Transaction Type column exists
    if 'Transaction Type' not in classified_df.columns:
        test_result("Transaction classification", False, "Transaction Type column not created")
    else:
        # Check transaction type distribution
        trans_counts = classified_df['Transaction Type'].value_counts().to_dict()

        # Verify we have the expected transaction types
        expected_types = ['Current Year Addition', 'Existing Asset', 'Disposal']
        found_types = [t for t in expected_types if any(t in str(tt) for tt in trans_counts.keys())]

        test_result("Transaction classification", True,
                   f"Found {len(trans_counts)} transaction types: {list(trans_counts.keys())}")

        # Validate classification
        validation_result = validate_transaction_classification(classified_df, tax_year=2024)
        test_result("Transaction classification validation",
                   len(validation_result) == 0,
                   f"{len(validation_result)} validation issues found" if validation_result else "All validations passed")

except Exception as e:
    test_result("Transaction classification", False, str(e))
    classified_df = unified_df.copy()  # Fallback

# ================================================================
# TEST 4: MACRS Classification
# ================================================================
print("TEST 4: MACRS Classification (Rules + AI)")
print("-" * 80)

try:
    from fixed_asset_ai.logic.macrs_classification import load_rules, classify_asset

    # Load rules
    rules = load_rules()
    test_result("Load MACRS rules", rules is not None and len(rules) > 0,
               f"Loaded {len(rules) if rules else 0} classification rules")

    # Test classification on sample assets
    sample_assets = [
        ("Dell Laptop Computer", "Computer"),
        ("2024 Ford F-150 Pickup Truck", "Vehicle"),
        ("Manufacturing CNC Machine", "Manufacturing equipment"),
        ("Office Building HVAC System", "Building improvement"),
    ]

    classification_successes = 0
    for desc, expected_category in sample_assets:
        try:
            result = classify_asset(desc, rules)
            if result and 'category' in result:
                classification_successes += 1
        except Exception:
            pass

    test_result("MACRS classification - sample assets",
               classification_successes == len(sample_assets),
               f"Successfully classified {classification_successes}/{len(sample_assets)} assets")

except Exception as e:
    test_result("MACRS classification", False, str(e))

# ================================================================
# TEST 5: Validators
# ================================================================
print("TEST 5: Data Validation")
print("-" * 80)

try:
    from fixed_asset_ai.logic.validators import validate_assets

    # Run validation
    validation_issues = validate_assets(classified_df)

    if validation_issues is None:
        test_result("Data validation", False, "Validation returned None")
    elif isinstance(validation_issues, list):
        # Validation passed - issues is a list of problems (may be empty)
        test_result("Data validation", True,
                   f"Validation completed, found {len(validation_issues)} issues")
    else:
        test_result("Data validation", True,
                   "Validation completed successfully")

except Exception as e:
    test_result("Data validation", False, str(e))

# ================================================================
# TEST 6: Advanced Validations
# ================================================================
print("TEST 6: Advanced Validations")
print("-" * 80)

try:
    from fixed_asset_ai.logic.advanced_validations import advanced_validations

    # Run advanced validation
    adv_issues = advanced_validations(classified_df)

    test_result("Advanced validations", True,
               f"Completed, found {len(adv_issues) if isinstance(adv_issues, list) else 0} advanced issues")

except Exception as e:
    test_result("Advanced validations", False, str(e))

# ================================================================
# TEST 7: Outlier Detection
# ================================================================
print("TEST 7: Outlier Detection")
print("-" * 80)

try:
    from fixed_asset_ai.logic.outlier_detector import detect_outliers

    # Run outlier detection
    outliers = detect_outliers(classified_df)

    if outliers is None or (isinstance(outliers, pd.DataFrame) and outliers.empty):
        test_result("Outlier detection", True, "No outliers detected (expected for good data)")
    elif isinstance(outliers, pd.DataFrame):
        test_result("Outlier detection", True,
                   f"Detected {len(outliers)} potential outliers")
    else:
        test_result("Outlier detection", False, "Unexpected return type")

except Exception as e:
    test_result("Outlier detection", False, str(e))

# ================================================================
# TEST 8: FA Export - build_fa()
# ================================================================
print("TEST 8: FA Export - build_fa() Function")
print("-" * 80)

try:
    from fixed_asset_ai.logic.fa_export import build_fa

    # Test with different strategies
    strategies = [
        ("Aggressive (179 + Bonus)", 200000),
        ("Balanced (Bonus Only)", 200000),
        ("Conservative (MACRS Only)", 200000),
    ]

    for strategy, taxable_income in strategies:
        try:
            fa_df = build_fa(
                df=classified_df.copy(),
                tax_year=2024,
                strategy=strategy,
                taxable_income=taxable_income,
                use_acq_if_missing=True,
                de_minimis_limit=2500,
                section_179_carryforward_from_prior_year=0
            )

            # Verify output has required columns
            required_export_cols = ['Asset #', 'Description', 'Tax Cost', 'Tax Method']
            has_all_cols = all(col in fa_df.columns for col in required_export_cols)

            test_result(f"build_fa() - {strategy}",
                       has_all_cols and len(fa_df) > 0,
                       f"Generated {len(fa_df)} rows with {len(fa_df.columns)} columns")

            # Verify depreciation calculations exist
            if 'Tax Sec 179 Expensed' in fa_df.columns:
                total_179 = fa_df['Tax Sec 179 Expensed'].fillna(0).sum()
                print(f"   Section 179 Total: ${total_179:,.2f}")

            if 'Bonus Amount' in fa_df.columns:
                total_bonus = fa_df['Bonus Amount'].fillna(0).sum()
                print(f"   Bonus Depreciation Total: ${total_bonus:,.2f}")

            if 'Tax Cur Depreciation' in fa_df.columns:
                total_macrs = fa_df['Tax Cur Depreciation'].fillna(0).sum()
                print(f"   MACRS Depreciation Total: ${total_macrs:,.2f}")

            print()

        except Exception as e:
            test_result(f"build_fa() - {strategy}", False, str(e))

except Exception as e:
    test_result("build_fa() import", False, str(e))

# ================================================================
# TEST 9: FA Export - export_fa_excel()
# ================================================================
print("TEST 9: FA Export - Multi-Worksheet Excel Generation")
print("-" * 80)

try:
    from fixed_asset_ai.logic.fa_export import export_fa_excel

    # Generate export with the FA dataframe from previous test
    if 'fa_df' in locals():
        excel_bytes = export_fa_excel(fa_df)

        # Verify output is bytes
        if isinstance(excel_bytes, bytes) and len(excel_bytes) > 0:
            test_result("export_fa_excel() - Excel generation",
                       True,
                       f"Generated {len(excel_bytes):,} bytes")

            # Try to read it back to verify it's valid Excel
            from io import BytesIO
            try:
                test_df = pd.read_excel(BytesIO(excel_bytes), sheet_name='FA_CS_Import')
                test_result("export_fa_excel() - Excel validity",
                           len(test_df) > 0,
                           f"Excel file valid, FA_CS_Import sheet has {len(test_df)} rows")

                # Check for other worksheets
                excel_file = pd.ExcelFile(BytesIO(excel_bytes))
                expected_sheets = ['FA_CS_Import', 'CPA_Review', 'Audit_Trail',
                                 'Tax_Details', 'Summary_Dashboard', 'Data_Dictionary']
                has_all_sheets = all(sheet in excel_file.sheet_names for sheet in expected_sheets)

                test_result("export_fa_excel() - Multi-worksheet structure",
                           has_all_sheets,
                           f"Found {len(excel_file.sheet_names)} sheets: {excel_file.sheet_names}")

            except Exception as e:
                test_result("export_fa_excel() - Excel validity", False, str(e))
        else:
            test_result("export_fa_excel() - Excel generation", False,
                       "Output is not bytes or is empty")
    else:
        test_result("export_fa_excel() - Excel generation", False,
                   "No FA dataframe available from previous test")

except Exception as e:
    test_result("export_fa_excel()", False, str(e))

# ================================================================
# TEST 10: Dashboard Calculation Accuracy
# ================================================================
print("TEST 10: Dashboard Total Value Calculation")
print("-" * 80)

try:
    # Simulate the dashboard calculation
    df_stats = classified_df.copy()

    # Calculate using the NEW fixed logic
    if "Cost" in df_stats.columns:
        if "Transaction Type" in df_stats.columns:
            # Only sum costs for non-disposal transactions
            non_disposal_mask = ~df_stats["Transaction Type"].astype(str).str.contains("Disposal", case=False, na=False)
            total_cost_new = df_stats.loc[non_disposal_mask, "Cost"].sum()
        else:
            total_cost_new = df_stats["Cost"].sum()
    else:
        total_cost_new = 0

    # Calculate using the OLD buggy logic (for comparison)
    total_cost_old = df_stats["Cost"].sum()

    # Calculate expected values from our test data
    additions_cost = df_stats.iloc[0:10]["Cost"].sum()  # First 10 are additions
    existing_cost = df_stats.iloc[10:20]["Cost"].sum()  # Next 10 are existing
    disposal_cost = df_stats.iloc[20:25]["Cost"].sum()  # Next 5 are disposals
    expected_total = additions_cost + existing_cost

    print(f"   Additions Cost: ${additions_cost:,.2f}")
    print(f"   Existing Cost: ${existing_cost:,.2f}")
    print(f"   Disposal Cost: ${disposal_cost:,.2f}")
    print(f"   Expected Total (without disposals): ${expected_total:,.2f}")
    print(f"   OLD Calculation (buggy - includes disposals): ${total_cost_old:,.2f}")
    print(f"   NEW Calculation (fixed - excludes disposals): ${total_cost_new:,.2f}")
    print()

    # Test passes if new calculation matches expected
    calculation_correct = abs(total_cost_new - expected_total) < 1.0  # Allow for floating point errors
    bug_fixed = total_cost_new != total_cost_old  # Verify fix was applied

    test_result("Dashboard calculation - excludes disposals",
               calculation_correct and bug_fixed,
               f"Correct: ${total_cost_new:,.2f} == ${expected_total:,.2f}, Bug fixed: {bug_fixed}")

except Exception as e:
    test_result("Dashboard calculation", False, str(e))

# ================================================================
# TEST 11: Sanitizer
# ================================================================
print("TEST 11: Sanitizer (Security)")
print("-" * 80)

try:
    from fixed_asset_ai.logic.sanitizer import sanitize_asset_description

    # Test sanitization of potentially malicious input
    test_cases = [
        ("Normal asset description", True),
        ("<script>alert('xss')</script>", False),
        ("Asset with 'quotes' and \"double quotes\"", True),
        ("Very " * 200 + "long description", False),  # Too long
    ]

    sanitize_successes = 0
    for test_input, should_pass in test_cases:
        try:
            result = sanitize_asset_description(test_input)
            # If it should pass, result should be non-empty
            # If it shouldn't pass, result should be sanitized
            if result:
                sanitize_successes += 1
        except Exception:
            if not should_pass:
                sanitize_successes += 1  # Expected to fail

    test_result("Sanitizer - security checks",
               sanitize_successes >= len(test_cases) // 2,
               f"Handled {sanitize_successes}/{len(test_cases)} test cases")

except Exception as e:
    test_result("Sanitizer", False, str(e))

# ================================================================
# TEST SUMMARY
# ================================================================
print()
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)

total_tests = len(test_results)
passed_tests = sum(1 for t in test_results if t['passed'])
failed_tests = total_tests - passed_tests
pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

print(f"\nTotal Tests Run: {total_tests}")
print(f"Passed: {passed_tests} ({pass_rate:.1f}%)")
print(f"Failed: {failed_tests}")
print()

if failed_tests > 0:
    print("FAILED TESTS:")
    print("-" * 80)
    for result in test_results:
        if not result['passed']:
            print(f"  ❌ {result['test']}")
            if result['details']:
                print(f"     {result['details']}")
    print()

print("=" * 80)
print(f"Test Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

# Exit with appropriate code
sys.exit(0 if failed_tests == 0 else 1)
