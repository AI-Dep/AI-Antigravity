#!/usr/bin/env python3
"""
Pre-Deployment Test Runner for Fixed Asset AI

Runs all tests and generates a report.
Use before deploying to production.

Usage:
    python tests/run_all_tests.py           # Run all tests
    python tests/run_all_tests.py --quick   # Run quick smoke tests only
    python tests/run_all_tests.py --report  # Generate HTML report
"""

import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

# Ensure we're in the project root
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_syntax_check():
    """Check all Python files for syntax errors."""
    print_header("SYNTAX CHECK")

    py_files = list(Path("fixed_asset_ai").rglob("*.py"))
    errors = []

    for py_file in py_files:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(py_file)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            errors.append((py_file, result.stderr))
            print(f"  [FAIL] {py_file}")
        else:
            print(f"  [OK]   {py_file.name}")

    if errors:
        print(f"\n  SYNTAX ERRORS FOUND: {len(errors)}")
        for file, error in errors:
            print(f"    {file}: {error}")
        return False

    print(f"\n  All {len(py_files)} files passed syntax check")
    return True


def run_tax_config_validation():
    """Validate tax year configuration."""
    print_header("TAX CONFIGURATION VALIDATION")

    result = subprocess.run(
        [sys.executable, "-m", "fixed_asset_ai.logic.tax_year_config", "--validate"],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    return result.returncode == 0


def generate_test_data():
    """Generate test data files if they don't exist."""
    print_header("TEST DATA GENERATION")

    test_data_dir = Path("tests/data")
    xlsx_files = list(test_data_dir.glob("*.xlsx"))

    if len(xlsx_files) >= 6:
        print(f"  Test data files already exist ({len(xlsx_files)} files)")
        return True

    print("  Generating test data files...")
    result = subprocess.run(
        [sys.executable, "tests/data/generate_test_data.py"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"  [FAIL] {result.stderr}")
        return False

    print(result.stdout)
    return True


def run_unit_tests():
    """Run unit tests."""
    print_header("UNIT TESTS")

    # Check if there are any unit tests
    unit_test_dir = Path("tests/unit")
    test_files = list(unit_test_dir.glob("test_*.py"))

    if not test_files:
        print("  No unit tests found in tests/unit/")
        print("  Skipping unit tests...")
        return True

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit", "-v", "--tb=short"],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    return result.returncode == 0


def run_integration_tests():
    """Run integration tests."""
    print_header("INTEGRATION TESTS")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration", "-v", "--tb=short"],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    return result.returncode == 0


def run_import_checks():
    """Check that all modules can be imported."""
    print_header("IMPORT CHECKS")

    modules_to_check = [
        "fixed_asset_ai.logic.sheet_loader",
        "fixed_asset_ai.logic.fa_export",
        "fixed_asset_ai.logic.validators",
        "fixed_asset_ai.logic.data_validator",
        "fixed_asset_ai.logic.tax_year_config",
        "fixed_asset_ai.logic.macrs_tables",
        "fixed_asset_ai.logic.section_179_carryforward",
    ]

    all_ok = True
    for module in modules_to_check:
        try:
            __import__(module)
            print(f"  [OK]   {module}")
        except Exception as e:
            print(f"  [FAIL] {module}: {e}")
            all_ok = False

    return all_ok


def run_quick_smoke_test():
    """Run a quick smoke test - just imports and basic sanity checks."""
    print_header("QUICK SMOKE TEST")

    success = True

    # 1. Check imports
    try:
        from fixed_asset_ai.logic.sheet_loader import build_unified_dataframe
        from fixed_asset_ai.logic.tax_year_config import get_tax_year_status, TaxYearStatus
        from fixed_asset_ai.logic.validators import validate_assets
        print("  [OK] Core imports successful")
    except Exception as e:
        print(f"  [FAIL] Import error: {e}")
        success = False

    # 2. Check tax config
    try:
        status, msg = get_tax_year_status(2025)
        assert status != TaxYearStatus.UNSUPPORTED, "2025 should be supported"
        print("  [OK] Tax year 2025 is supported")
    except Exception as e:
        print(f"  [FAIL] Tax config error: {e}")
        success = False

    # 3. Check file loading (if test data exists)
    try:
        import pandas as pd
        test_file = Path("tests/data/test_standard_format.xlsx")
        if test_file.exists():
            sheets = pd.read_excel(test_file, sheet_name=None, header=None)
            df = build_unified_dataframe(sheets, target_tax_year=2025, filter_by_date=False)
            assert len(df) > 0, "Should load some data"
            print(f"  [OK] Test file loaded: {len(df)} rows")
        else:
            print("  [SKIP] Test data file not found")
    except Exception as e:
        print(f"  [FAIL] File loading error: {e}")
        success = False

    return success


def generate_report(results):
    """Generate a test report."""
    print_header("TEST REPORT")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n  Timestamp: {timestamp}")
    print(f"  Python: {sys.version.split()[0]}")
    print()

    all_passed = True
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test_name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  " + "=" * 50)
        print("  ALL TESTS PASSED - READY FOR DEPLOYMENT")
        print("  " + "=" * 50)
    else:
        print("  " + "=" * 50)
        print("  TESTS FAILED - DO NOT DEPLOY")
        print("  " + "=" * 50)

    return all_passed


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run pre-deployment tests")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke tests only")
    parser.add_argument("--report", action="store_true", help="Generate detailed report")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  FIXED ASSET AI - PRE-DEPLOYMENT TEST SUITE")
    print("=" * 70)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    if args.quick:
        # Quick smoke test only
        results["Smoke Test"] = run_quick_smoke_test()
    else:
        # Full test suite
        results["Syntax Check"] = run_syntax_check()
        results["Import Checks"] = run_import_checks()
        results["Tax Config Validation"] = run_tax_config_validation()
        results["Test Data Generation"] = generate_test_data()
        results["Integration Tests"] = run_integration_tests()

    all_passed = generate_report(results)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
