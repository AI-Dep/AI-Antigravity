#!/usr/bin/env python3
"""
Test suite for Quality Improvements:
1. Rollforward Reconciliation
2. Duplicate Detection
3. Data Quality Score (A-F)
4. Enhanced Error Messages

These features are 100% deterministic and should achieve perfect accuracy.
"""

import pandas as pd
import sys
from datetime import date

# Add the project to path
sys.path.insert(0, '/home/user/DEP')

from fixed_asset_ai.logic.rollforward_reconciliation import (
    reconcile_rollforward,
    reconcile_by_category,
    generate_rollforward_report,
    add_rollforward_to_export,
)
from fixed_asset_ai.logic.data_quality_score import (
    calculate_data_quality_score,
    generate_quality_report,
    get_quality_badge,
)
from fixed_asset_ai.logic.data_validator import (
    AssetDataValidator,
    validate_asset_data,
)


def test_rollforward_reconciliation():
    """Test rollforward reconciliation with various scenarios."""
    print("\n" + "=" * 60)
    print("TEST 1: ROLLFORWARD RECONCILIATION")
    print("=" * 60)

    # Create test data with additions and disposals
    df = pd.DataFrame({
        "Asset ID": [1, 2, 3, 4, 5],
        "Description": ["Laptop", "Desk", "Server", "Old Printer", "Vehicle"],
        "Cost": [1500, 800, 25000, 500, 35000],
        "Transaction Type": ["Addition", "Addition", "Addition", "Disposal", "Addition"],
        "In Service Date": ["01/15/2024", "02/20/2024", "03/10/2024", "01/01/2020", "04/01/2024"],
    })

    result = reconcile_rollforward(df)

    print(f"\nResults:")
    print(f"  Is Balanced: {result.is_balanced}")
    print(f"  Additions: ${result.additions:,.2f}")
    print(f"  Disposals: ${result.disposals:,.2f}")
    print(f"  Expected Ending: ${result.expected_ending:,.2f}")
    print(f"  Variance: ${result.variance:,.2f}")

    # Verify calculations
    expected_additions = 1500 + 800 + 25000 + 35000  # 62,300
    expected_disposals = 500
    expected_ending = expected_additions - expected_disposals  # 61,800

    assert result.additions == expected_additions, f"Additions mismatch: {result.additions} != {expected_additions}"
    assert result.disposals == expected_disposals, f"Disposals mismatch: {result.disposals} != {expected_disposals}"
    assert result.expected_ending == expected_ending, f"Ending mismatch: {result.expected_ending} != {expected_ending}"
    assert result.is_balanced, "Should be balanced"

    print("\n  [PASS] Rollforward calculations are correct!")

    # Test report generation
    report = generate_rollforward_report(result)
    print("\n  Generated Report Preview:")
    print("  " + "\n  ".join(report.split("\n")[:10]))

    return True


def test_duplicate_detection():
    """Test duplicate asset detection."""
    print("\n" + "=" * 60)
    print("TEST 2: DUPLICATE DETECTION")
    print("=" * 60)

    # Create test data with duplicates
    df = pd.DataFrame({
        "Asset ID": [1, 2, 3, 2, 4, 3],  # 2 and 3 are duplicated
        "Description": ["Laptop", "Desk", "Server", "Desk Copy", "Chair", "Server Copy"],
        "Cost": [1500, 800, 25000, 800, 500, 25000],
        "In Service Date": ["01/15/2024", "02/20/2024", "03/10/2024", "02/20/2024", "04/01/2024", "03/10/2024"],
    })

    validator = AssetDataValidator(tax_year=2024)
    errors = validator.validate_dataframe(df)

    # Check for duplicate errors
    duplicate_errors = [e for e in errors if "Duplicate" in e.field or "Duplicate" in e.message]

    print(f"\nDuplicate errors found: {len(duplicate_errors)}")
    for err in duplicate_errors:
        print(f"  - {err}")

    assert len(duplicate_errors) >= 2, "Should detect at least 2 duplicate Asset IDs"
    print("\n  [PASS] Duplicate detection working!")

    return True


def test_data_quality_score():
    """Test data quality scoring with different quality levels."""
    print("\n" + "=" * 60)
    print("TEST 3: DATA QUALITY SCORE (A-F GRADING)")
    print("=" * 60)

    # Test Case A: Perfect data (should get A)
    print("\n  Test Case A: Perfect Data")
    perfect_df = pd.DataFrame({
        "Asset ID": [1, 2, 3],
        "Description": ["Laptop Computer", "Office Desk", "Server Rack"],
        "Cost": [1500, 800, 25000],
        "In Service Date": ["01/15/2024", "02/20/2024", "03/10/2024"],
        "Transaction Type": ["Addition", "Addition", "Addition"],
        "Final Category": ["5-Year Property", "7-Year Property", "5-Year Property"],
        "MACRS Life": [5, 7, 5],
        "Method": ["200DB", "200DB", "200DB"],
        "Convention": ["HY", "HY", "HY"],
    })

    score_a = calculate_data_quality_score(perfect_df, tax_year=2024)
    print(f"    Grade: {score_a.grade} ({score_a.score}/100)")
    print(f"    Export Ready: {score_a.is_export_ready}")
    assert score_a.grade in ["A", "B"], f"Perfect data should get A or B, got {score_a.grade}"
    print("    [PASS] Perfect data gets good grade!")

    # Test Case B: Data with issues (should get lower grade)
    print("\n  Test Case B: Data with Issues")
    bad_df = pd.DataFrame({
        "Asset ID": [1, 1, 3],  # Duplicate
        "Description": ["", "Desk", "Server"],  # Missing description
        "Cost": [-1500, 800, 25000],  # Negative cost
        "In Service Date": ["", "02/20/2024", "03/10/2024"],  # Missing date
        "Transaction Type": ["Addition", "Addition", "Addition"],
    })

    score_b = calculate_data_quality_score(bad_df, tax_year=2024)
    print(f"    Grade: {score_b.grade} ({score_b.score}/100)")
    print(f"    Critical Issues: {len(score_b.critical_issues)}")
    for issue in score_b.critical_issues[:3]:
        print(f"      - {issue}")
    print(f"    Export Ready: {score_b.is_export_ready}")
    assert score_b.grade in ["D", "F"], f"Bad data should get D or F, got {score_b.grade}"
    assert not score_b.is_export_ready, "Bad data should not be export ready"
    print("    [PASS] Bad data gets appropriate low grade!")

    # Test detailed report
    print("\n  Quality Report Preview:")
    report = generate_quality_report(score_a)
    print("  " + "\n  ".join(report.split("\n")[:15]))

    return True


def test_error_messages_with_fixes():
    """Test that error messages include FIX suggestions."""
    print("\n" + "=" * 60)
    print("TEST 4: ERROR MESSAGES WITH FIX SUGGESTIONS")
    print("=" * 60)

    # Create data with various issues
    df = pd.DataFrame({
        "Asset ID": [1, 2, 3],
        "Description": ["Laptop", "Desk", "Server"],
        "Cost": ["invalid", -500, 25000],  # Invalid and negative
        "In Service Date": ["01/15/2024", "02/20/2024", "03/10/2024"],
        "Transaction Type": ["Addition", "Addition", "Addition"],
    })

    validator = AssetDataValidator(tax_year=2024)
    errors = validator.validate_dataframe(df)

    print(f"\nErrors found: {len(errors)}")
    fix_count = 0
    for err in errors:
        has_fix = "FIX:" in str(err) or "fix" in str(err).lower()
        if has_fix:
            fix_count += 1
        print(f"  [{err.severity}] {err.field}: {err.message[:80]}...")
        if has_fix:
            print(f"         ^ Contains FIX suggestion")

    print(f"\n  Errors with FIX suggestions: {fix_count}/{len(errors)}")
    assert fix_count > 0, "Should have at least some errors with FIX suggestions"
    print("  [PASS] Error messages include actionable FIX suggestions!")

    return True


def test_rollforward_by_category():
    """Test rollforward reconciliation grouped by category."""
    print("\n" + "=" * 60)
    print("TEST 5: ROLLFORWARD BY CATEGORY")
    print("=" * 60)

    df = pd.DataFrame({
        "Asset ID": [1, 2, 3, 4, 5],
        "Description": ["Laptop", "Desk", "Server", "Chair", "Vehicle"],
        "Cost": [1500, 800, 25000, 500, 35000],
        "Transaction Type": ["Addition", "Addition", "Addition", "Addition", "Addition"],
        "Final Category": ["5-Year", "7-Year", "5-Year", "7-Year", "5-Year"],
    })

    results = reconcile_by_category(df)

    print(f"\nCategories found: {list(results.keys())}")
    for category, result in results.items():
        print(f"\n  {category}:")
        print(f"    Additions: ${result.additions:,.2f}")
        print(f"    Count: {result.details.get('additions_count', 0)}")

    assert len(results) == 2, f"Should have 2 categories, got {len(results)}"
    assert "5-Year" in results, "Should have 5-Year category"
    assert "7-Year" in results, "Should have 7-Year category"

    # Verify 5-Year totals
    five_year = results["5-Year"]
    expected_5yr = 1500 + 25000 + 35000
    assert five_year.additions == expected_5yr, f"5-Year total mismatch: {five_year.additions} != {expected_5yr}"

    print("\n  [PASS] Category-level rollforward working!")

    return True


def test_rollforward_export_sheet():
    """Test adding rollforward summary to export."""
    print("\n" + "=" * 60)
    print("TEST 6: ROLLFORWARD EXPORT SHEET")
    print("=" * 60)

    df = pd.DataFrame({
        "Asset ID": [1, 2, 3],
        "Description": ["Laptop", "Desk", "Server"],
        "Cost": [1500, 800, 25000],
        "Transaction Type": ["Addition", "Addition", "Disposal"],
    })

    summary_df = add_rollforward_to_export(df)

    print(f"\nRollforward Summary Sheet:")
    print(summary_df.to_string(index=False))

    assert len(summary_df) >= 6, "Summary should have at least 6 rows"
    assert "Line Item" in summary_df.columns, "Should have Line Item column"
    assert "Amount" in summary_df.columns, "Should have Amount column"

    print("\n  [PASS] Rollforward export sheet generated!")

    return True


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("QUALITY IMPROVEMENTS TEST SUITE")
    print("Testing: Rollforward, Duplicates, Quality Score, Error Messages")
    print("=" * 70)

    tests = [
        ("Rollforward Reconciliation", test_rollforward_reconciliation),
        ("Duplicate Detection", test_duplicate_detection),
        ("Data Quality Score", test_data_quality_score),
        ("Error Messages with Fixes", test_error_messages_with_fixes),
        ("Rollforward by Category", test_rollforward_by_category),
        ("Rollforward Export Sheet", test_rollforward_export_sheet),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success, None))
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"\n  [FAIL] {name}: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, error in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {name}")
        if error:
            print(f"         Error: {error}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nALL TESTS PASSED - Quality improvements are working correctly!")
        return True
    else:
        print(f"\n{total - passed} TESTS FAILED - Please review errors above")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
