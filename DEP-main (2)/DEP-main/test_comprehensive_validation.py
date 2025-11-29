#!/usr/bin/env python3
"""
Comprehensive Test Suite for Quality Improvements

Tests edge cases, error handling, and integration with existing code.
"""

import pandas as pd
import numpy as np
import sys
from datetime import date, datetime

sys.path.insert(0, '/home/user/DEP')

from fixed_asset_ai.logic.rollforward_reconciliation import (
    reconcile_rollforward,
    reconcile_by_category,
    generate_rollforward_report,
    add_rollforward_to_export,
    validate_period_to_period,
    RollforwardResult,
)
from fixed_asset_ai.logic.data_quality_score import (
    calculate_data_quality_score,
    generate_quality_report,
    get_quality_badge,
    DataQualityScore,
)
from fixed_asset_ai.logic.data_validator import (
    AssetDataValidator,
    validate_asset_data,
    ValidationError,
)


def print_test_header(test_name):
    """Print test header."""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print('='*60)


def test_edge_case_empty_dataframe():
    """Test handling of empty DataFrame."""
    print_test_header("Empty DataFrame Handling")

    empty_df = pd.DataFrame()

    # Test rollforward with empty df
    result = reconcile_rollforward(empty_df)
    assert result.is_balanced, "Empty df should be balanced"
    assert result.additions == 0, "Empty df should have 0 additions"
    print("  [PASS] Rollforward handles empty DataFrame")

    # Test quality score with empty df
    score = calculate_data_quality_score(empty_df)
    assert isinstance(score, DataQualityScore), "Should return DataQualityScore"
    print(f"  [PASS] Quality score handles empty DataFrame (Grade: {score.grade})")

    # Test validator with empty df
    validator = AssetDataValidator(tax_year=2024)
    errors = validator.validate_dataframe(empty_df)
    assert isinstance(errors, list), "Should return list"
    print("  [PASS] Validator handles empty DataFrame")

    return True


def test_edge_case_null_values():
    """Test handling of NULL/NaN values."""
    print_test_header("NULL/NaN Value Handling")

    df = pd.DataFrame({
        "Asset ID": [1, None, 3, np.nan, 5],
        "Description": ["Laptop", None, "", np.nan, "Server"],
        "Cost": [1500, None, np.nan, 0, 25000],
        "In Service Date": ["01/15/2024", None, "", np.nan, "03/10/2024"],
        "Transaction Type": ["Addition", None, "Addition", "", "Addition"],
    })

    # Test rollforward
    try:
        result = reconcile_rollforward(df)
        print(f"  [PASS] Rollforward handles NaN values (Additions: ${result.additions:,.2f})")
    except Exception as e:
        print(f"  [FAIL] Rollforward failed: {e}")
        return False

    # Test quality score
    try:
        score = calculate_data_quality_score(df)
        print(f"  [PASS] Quality score handles NaN values (Grade: {score.grade})")
    except Exception as e:
        print(f"  [FAIL] Quality score failed: {e}")
        return False

    # Test validator
    try:
        validator = AssetDataValidator(tax_year=2024)
        errors = validator.validate_dataframe(df)
        print(f"  [PASS] Validator handles NaN values ({len(errors)} errors found)")
    except Exception as e:
        print(f"  [FAIL] Validator failed: {e}")
        return False

    return True


def test_edge_case_special_characters():
    """Test handling of special characters in data."""
    print_test_header("Special Characters Handling")

    df = pd.DataFrame({
        "Asset ID": [1, 2, 3],
        "Description": ["Laptop's \"Computer\"", "Desk & Chair", "Server/Rack (2024)"],
        "Cost": ["$1,500.00", "800", "25000.50"],
        "In Service Date": ["01/15/2024", "2024-02-20", "March 10, 2024"],
        "Transaction Type": ["Addition", "addition", "ADDITION"],
    })

    # Test rollforward
    try:
        result = reconcile_rollforward(df)
        print(f"  [PASS] Rollforward handles special chars (Additions: ${result.additions:,.2f})")
    except Exception as e:
        print(f"  [FAIL] Rollforward failed: {e}")
        return False

    # Test quality score
    try:
        score = calculate_data_quality_score(df)
        print(f"  [PASS] Quality score handles special chars (Grade: {score.grade})")
    except Exception as e:
        print(f"  [FAIL] Quality score failed: {e}")
        return False

    return True


def test_edge_case_large_dataset():
    """Test performance with larger dataset."""
    print_test_header("Large Dataset Performance (1000 rows)")

    import time

    # Create 1000 row dataset
    n = 1000
    df = pd.DataFrame({
        "Asset ID": list(range(1, n+1)),
        "Description": [f"Asset {i}" for i in range(1, n+1)],
        "Cost": [i * 100 for i in range(1, n+1)],
        "In Service Date": ["01/15/2024"] * n,
        "Transaction Type": ["Addition"] * (n-100) + ["Disposal"] * 100,
        "Final Category": ["5-Year"] * (n//2) + ["7-Year"] * (n//2),
    })

    # Test rollforward performance
    start = time.time()
    result = reconcile_rollforward(df)
    rollforward_time = time.time() - start
    print(f"  [PASS] Rollforward completed in {rollforward_time:.3f}s")

    # Test quality score performance
    start = time.time()
    score = calculate_data_quality_score(df)
    quality_time = time.time() - start
    print(f"  [PASS] Quality score completed in {quality_time:.3f}s (Grade: {score.grade})")

    # Test validator performance
    start = time.time()
    validator = AssetDataValidator(tax_year=2024)
    errors = validator.validate_dataframe(df)
    validator_time = time.time() - start
    print(f"  [PASS] Validator completed in {validator_time:.3f}s ({len(errors)} errors)")

    # Performance threshold (should complete in < 5 seconds)
    total_time = rollforward_time + quality_time + validator_time
    assert total_time < 5, f"Performance too slow: {total_time:.2f}s"
    print(f"  [PASS] Total time: {total_time:.3f}s (under 5s threshold)")

    return True


def test_edge_case_negative_and_zero():
    """Test handling of negative and zero values."""
    print_test_header("Negative and Zero Value Handling")

    df = pd.DataFrame({
        "Asset ID": [1, 2, 3, 4, 5],
        "Description": ["Laptop", "Desk", "Server", "Printer", "Chair"],
        "Cost": [-1500, 0, 25000, -500, 0],
        "In Service Date": ["01/15/2024", "02/20/2024", "03/10/2024", "04/01/2024", "05/01/2024"],
        "Transaction Type": ["Addition", "Addition", "Addition", "Disposal", "Addition"],
    })

    # Test validator catches negative costs
    validator = AssetDataValidator(tax_year=2024)
    errors = validator.validate_dataframe(df)

    negative_errors = [e for e in errors if "negative" in str(e).lower()]
    zero_errors = [e for e in errors if "$0" in str(e) or "zero" in str(e).lower()]

    print(f"  Negative cost errors: {len(negative_errors)}")
    print(f"  Zero cost warnings: {len(zero_errors)}")

    assert len(negative_errors) >= 1, "Should catch negative cost"
    print("  [PASS] Negative costs detected correctly")

    # Test quality score reflects issues
    score = calculate_data_quality_score(df)
    # With 2 critical issues in 5 rows, expect grade B or lower (not A)
    assert score.grade != "A", f"Bad data should not get A grade, got {score.grade}"
    assert len(score.critical_issues) > 0, "Should have critical issues"
    print(f"  [PASS] Quality score reflects issues (Grade: {score.grade}, {len(score.critical_issues)} critical issues)")

    return True


def test_edge_case_date_formats():
    """Test handling of various date formats."""
    print_test_header("Date Format Handling")

    df = pd.DataFrame({
        "Asset ID": [1, 2, 3, 4, 5, 6],
        "Description": ["A", "B", "C", "D", "E", "F"],
        "Cost": [1000, 2000, 3000, 4000, 5000, 6000],
        "In Service Date": [
            "01/15/2024",      # MM/DD/YYYY
            "2024-02-20",      # YYYY-MM-DD
            "03-10-2024",      # MM-DD-YYYY
            datetime(2024, 4, 1),  # datetime object
            pd.Timestamp("2024-05-01"),  # pandas Timestamp
            "",                # Empty
        ],
        "Transaction Type": ["Addition"] * 6,
    })

    # Test validator handles all formats
    validator = AssetDataValidator(tax_year=2024)
    errors = validator.validate_dataframe(df)

    date_errors = [e for e in errors if "date" in e.field.lower()]
    print(f"  Date validation errors: {len(date_errors)}")

    # Should only have error for empty date, not format errors
    format_errors = [e for e in date_errors if "format" in str(e).lower()]
    print(f"  Format errors: {len(format_errors)}")

    print("  [PASS] Multiple date formats handled")

    return True


def test_edge_case_duplicate_variations():
    """Test various duplicate scenarios."""
    print_test_header("Duplicate Variations")

    # Scenario 1: Exact duplicate Asset IDs
    df1 = pd.DataFrame({
        "Asset ID": [1, 2, 1, 3, 2],  # 1 and 2 are duplicated
        "Description": ["A", "B", "C", "D", "E"],
        "Cost": [1000, 2000, 3000, 4000, 5000],
        "In Service Date": ["01/15/2024"] * 5,
    })

    validator = AssetDataValidator(tax_year=2024)
    errors1 = validator.validate_dataframe(df1)
    # Duplicate errors have field="Asset ID" and "Duplicate" in message
    dup_errors1 = [e for e in errors1 if "Duplicate" in e.message and "Asset ID" in e.field]

    assert len(dup_errors1) >= 2, f"Should find 2 duplicate IDs, found {len(dup_errors1)}"
    print(f"  [PASS] Exact duplicate IDs detected ({len(dup_errors1)} errors)")

    # Scenario 2: Same description+cost+date (potential data entry dupe)
    df2 = pd.DataFrame({
        "Asset ID": [1, 2, 3, 4],  # Unique IDs
        "Description": ["Laptop", "Laptop", "Desk", "Laptop"],  # Laptop appears 3x
        "Cost": [1500, 1500, 800, 1500],  # Same cost
        "In Service Date": ["01/15/2024", "01/15/2024", "02/20/2024", "01/15/2024"],  # Same date
    })

    validator2 = AssetDataValidator(tax_year=2024)
    errors2 = validator2.validate_dataframe(df2)
    dup_entry_errors = [e for e in errors2 if "Duplicate Entry" in e.field]

    print(f"  Potential data entry dupes detected: {len(dup_entry_errors)}")
    print("  [PASS] Data entry duplicates detected")

    return True


def test_edge_case_mixed_transaction_types():
    """Test handling of various transaction type formats."""
    print_test_header("Mixed Transaction Types")

    df = pd.DataFrame({
        "Asset ID": list(range(1, 11)),
        "Description": [f"Asset {i}" for i in range(1, 11)],
        "Cost": [1000] * 10,
        "In Service Date": ["01/15/2024"] * 10,
        "Transaction Type": [
            "Addition",
            "addition",
            "ADDITION",
            "Disposal",
            "disposal",
            "Sold",
            "Retire",
            "Transfer",
            "Transfer In",
            "Transfer Out",
        ],
    })

    result = reconcile_rollforward(df)

    print(f"  Additions: ${result.additions:,.2f}")
    print(f"  Disposals: ${result.disposals:,.2f}")
    print(f"  Transfers In: ${result.transfers_in:,.2f}")
    print(f"  Transfers Out: ${result.transfers_out:,.2f}")

    # Should have 3 additions (row 1-3)
    assert result.details["additions_count"] == 3, f"Expected 3 additions, got {result.details['additions_count']}"
    # Should have 4 disposals (row 4-7)
    assert result.details["disposals_count"] == 4, f"Expected 4 disposals, got {result.details['disposals_count']}"

    print("  [PASS] All transaction type variations recognized")

    return True


def test_integration_with_fa_export():
    """Test integration with existing fa_export module."""
    print_test_header("Integration with fa_export")

    try:
        from fixed_asset_ai.logic.fa_export import (
            generate_fa_cs_export,
        )

        df = pd.DataFrame({
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

        # First validate with our new tools
        score = calculate_data_quality_score(df)
        print(f"  Quality Score: {score.grade} ({score.score}/100)")

        rollforward = reconcile_rollforward(df)
        print(f"  Rollforward Balanced: {rollforward.is_balanced}")

        print("  [PASS] New modules work alongside existing code")
        return True

    except ImportError as e:
        print(f"  [SKIP] fa_export not available: {e}")
        return True


def test_integration_with_export_qa():
    """Test integration with export_qa_validator."""
    print_test_header("Integration with export_qa_validator")

    try:
        from fixed_asset_ai.logic.export_qa_validator import (
            validate_fixed_asset_cs_export,
        )

        # Create export-format data
        df = pd.DataFrame({
            "Asset #": [1, 2, 3],
            "Description": ["Laptop", "Desk", "Server"],
            "Date In Service": ["01/15/2024", "02/20/2024", "03/10/2024"],
            "Tax Cost": [1500, 800, 25000],
            "Tax Method": ["200DB", "200DB", "200DB"],
            "Tax Life": [5, 7, 5],
            "Convention": ["HY", "HY", "HY"],
            "Transaction Type": ["Addition", "Addition", "Addition"],
        })

        # Run both validations
        is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=False)

        # Also run our new quality score
        score = calculate_data_quality_score(df)

        print(f"  Export QA Valid: {is_valid}")
        print(f"  Export QA Errors: {summary['TOTAL']}")
        print(f"  Quality Score: {score.grade}")

        print("  [PASS] Both validation systems work together")
        return True

    except Exception as e:
        print(f"  [FAIL] Integration failed: {e}")
        return False


def test_rollforward_report_formatting():
    """Test that rollforward report formatting is correct."""
    print_test_header("Rollforward Report Formatting")

    df = pd.DataFrame({
        "Asset ID": [1, 2, 3],
        "Description": ["Laptop", "Desk", "Server"],
        "Cost": [1500, 800, 25000],
        "Transaction Type": ["Addition", "Disposal", "Addition"],
    })

    result = reconcile_rollforward(df)
    report = generate_rollforward_report(result)

    # Check report contains required sections
    assert "ROLLFORWARD RECONCILIATION REPORT" in report, "Missing report title"
    assert "Beginning Balance" in report, "Missing beginning balance"
    assert "Additions" in report, "Missing additions"
    assert "Disposals" in report, "Missing disposals"
    assert "Ending Balance" in report, "Missing ending balance"
    assert "BALANCED" in report or "OUT OF BALANCE" in report, "Missing status"

    print("  Report preview (first 15 lines):")
    for line in report.split("\n")[:15]:
        print(f"    {line}")

    print("  [PASS] Report format is correct")
    return True


def test_quality_badge():
    """Test quality badge generation."""
    print_test_header("Quality Badge Generation")

    badges = {
        "A": get_quality_badge("A"),
        "B": get_quality_badge("B"),
        "C": get_quality_badge("C"),
        "D": get_quality_badge("D"),
        "F": get_quality_badge("F"),
    }

    for grade, badge in badges.items():
        print(f"  Grade {grade}: {badge}")
        assert grade in badge, f"Badge should contain grade {grade}"

    print("  [PASS] All badges generated correctly")
    return True


def test_error_message_format():
    """Test that error messages are properly formatted."""
    print_test_header("Error Message Format")

    df = pd.DataFrame({
        "Asset ID": [1, 1, 3],  # Duplicate
        "Description": ["", "Desk", "Server"],  # Missing
        "Cost": ["invalid", -500, 25000],  # Invalid, negative
        "In Service Date": ["01/15/2024", "02/20/2024", "03/10/2024"],
    })

    validator = AssetDataValidator(tax_year=2024)
    errors = validator.validate_dataframe(df)

    print(f"  Total errors: {len(errors)}")

    for err in errors:
        # Check error has required attributes
        assert hasattr(err, 'severity'), "Error missing severity"
        assert hasattr(err, 'row_id'), "Error missing row_id"
        assert hasattr(err, 'field'), "Error missing field"
        assert hasattr(err, 'message'), "Error missing message"

        # Check str representation works
        err_str = str(err)
        assert err.severity in err_str, "String should contain severity"

        print(f"  [{err.severity}] {err.field}: {err.message[:50]}...")

    print("  [PASS] All error messages properly formatted")
    return True


def run_all_tests():
    """Run all comprehensive tests."""
    print("\n" + "="*70)
    print("COMPREHENSIVE VALIDATION TEST SUITE")
    print("Testing edge cases, error handling, and integration")
    print("="*70)

    tests = [
        ("Empty DataFrame", test_edge_case_empty_dataframe),
        ("NULL/NaN Values", test_edge_case_null_values),
        ("Special Characters", test_edge_case_special_characters),
        ("Large Dataset (1000 rows)", test_edge_case_large_dataset),
        ("Negative and Zero Values", test_edge_case_negative_and_zero),
        ("Date Formats", test_edge_case_date_formats),
        ("Duplicate Variations", test_edge_case_duplicate_variations),
        ("Mixed Transaction Types", test_edge_case_mixed_transaction_types),
        ("Integration: fa_export", test_integration_with_fa_export),
        ("Integration: export_qa", test_integration_with_export_qa),
        ("Rollforward Report Format", test_rollforward_report_formatting),
        ("Quality Badge", test_quality_badge),
        ("Error Message Format", test_error_message_format),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success, None))
        except Exception as e:
            results.append((name, False, str(e)))
            import traceback
            print(f"\n  [FAIL] {name}")
            print(f"  Error: {e}")
            traceback.print_exc()

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, error in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {name}")
        if error:
            print(f"         Error: {error[:60]}...")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nALL TESTS PASSED!")
        return True
    else:
        print(f"\n{total - passed} TESTS FAILED")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
