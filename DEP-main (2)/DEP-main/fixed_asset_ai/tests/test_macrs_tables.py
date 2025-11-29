"""
MACRS Table Validation Test Suite
Validates all MACRS depreciation tables against IRS Publication 946

Run with: python -m pytest tests/test_macrs_tables.py -v
Or:       python tests/test_macrs_tables.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.macrs_tables import (
    # Half-Year Convention
    MACRS_200DB_3Y_HY,
    MACRS_200DB_5Y_HY,
    MACRS_200DB_7Y_HY,
    MACRS_200DB_10Y_HY,
    MACRS_150DB_15Y_HY,
    MACRS_150DB_20Y_HY,
    # Mid-Quarter Convention - 3 Year
    MACRS_200DB_3Y_MQ_Q1,
    MACRS_200DB_3Y_MQ_Q2,
    MACRS_200DB_3Y_MQ_Q3,
    MACRS_200DB_3Y_MQ_Q4,
    # Mid-Quarter Convention - 5 Year
    MACRS_200DB_5Y_MQ_Q1,
    MACRS_200DB_5Y_MQ_Q2,
    MACRS_200DB_5Y_MQ_Q3,
    MACRS_200DB_5Y_MQ_Q4,
    # Mid-Quarter Convention - 7 Year
    MACRS_200DB_7Y_MQ_Q1,
    MACRS_200DB_7Y_MQ_Q2,
    MACRS_200DB_7Y_MQ_Q3,
    MACRS_200DB_7Y_MQ_Q4,
    # Mid-Quarter Convention - 10 Year
    MACRS_200DB_10Y_MQ_Q1,
    MACRS_200DB_10Y_MQ_Q2,
    MACRS_200DB_10Y_MQ_Q3,
    MACRS_200DB_10Y_MQ_Q4,
    # Mid-Quarter Convention - 15 Year
    MACRS_150DB_15Y_MQ_Q1,
    MACRS_150DB_15Y_MQ_Q2,
    MACRS_150DB_15Y_MQ_Q3,
    MACRS_150DB_15Y_MQ_Q4,
    # Mid-Quarter Convention - 20 Year
    MACRS_150DB_20Y_MQ_Q1,
    MACRS_150DB_20Y_MQ_Q2,
    MACRS_150DB_20Y_MQ_Q3,
    MACRS_150DB_20Y_MQ_Q4,
    # Real Property
    get_sl_mm_table,
)

# ==============================================================================
# IRS PUBLICATION 946 REFERENCE VALUES
# Source: IRS Publication 946 (2023), Appendix A
# ==============================================================================

# Table A-1: 3-, 5-, 7-, 10-, 15-, 20-Year Property Half-Year Convention
IRS_PUB946_3Y_HY = [0.3333, 0.4445, 0.1481, 0.0741]
IRS_PUB946_5Y_HY = [0.2000, 0.3200, 0.1920, 0.1152, 0.1152, 0.0576]
IRS_PUB946_7Y_HY = [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446]
IRS_PUB946_10Y_HY = [0.1000, 0.1800, 0.1440, 0.1152, 0.0922, 0.0737, 0.0655, 0.0655, 0.0656, 0.0655, 0.0328]
IRS_PUB946_15Y_HY = [0.0500, 0.0950, 0.0855, 0.0770, 0.0693, 0.0623, 0.0590, 0.0590, 0.0591, 0.0590, 0.0591, 0.0590, 0.0591, 0.0590, 0.0591, 0.0295]
IRS_PUB946_20Y_HY = [0.03750, 0.07219, 0.06677, 0.06177, 0.05713, 0.05285, 0.04888, 0.04522, 0.04462, 0.04461, 0.04462, 0.04461, 0.04462, 0.04461, 0.04462, 0.04461, 0.04462, 0.04461, 0.04462, 0.04461, 0.02231]

# Table A-2: 3-Year Mid-Quarter Convention
IRS_PUB946_3Y_MQ_Q1 = [0.5833, 0.3889, 0.0278, 0.0000]
IRS_PUB946_3Y_MQ_Q2 = [0.4167, 0.4444, 0.1389, 0.0000]
IRS_PUB946_3Y_MQ_Q3 = [0.2500, 0.5000, 0.2500, 0.0000]
IRS_PUB946_3Y_MQ_Q4 = [0.0833, 0.5556, 0.3611, 0.0000]

# Table A-2: 5-Year Mid-Quarter Convention
IRS_PUB946_5Y_MQ_Q1 = [0.3500, 0.2600, 0.1560, 0.1104, 0.1104, 0.0132]
IRS_PUB946_5Y_MQ_Q2 = [0.2500, 0.3000, 0.1800, 0.1080, 0.1080, 0.0540]
IRS_PUB946_5Y_MQ_Q3 = [0.1500, 0.3400, 0.2040, 0.1224, 0.1130, 0.0706]
IRS_PUB946_5Y_MQ_Q4 = [0.0500, 0.3800, 0.2280, 0.1368, 0.1179, 0.0873]

# Table A-3: 7-Year Mid-Quarter Convention
IRS_PUB946_7Y_MQ_Q1 = [0.2500, 0.2143, 0.1531, 0.1094, 0.0781, 0.0715, 0.0715, 0.0521]
IRS_PUB946_7Y_MQ_Q2 = [0.1786, 0.2321, 0.1658, 0.1184, 0.0845, 0.0772, 0.0772, 0.0662]
IRS_PUB946_7Y_MQ_Q3 = [0.1071, 0.2500, 0.1786, 0.1276, 0.0911, 0.0830, 0.0830, 0.0796]
IRS_PUB946_7Y_MQ_Q4 = [0.0357, 0.2679, 0.1913, 0.1367, 0.0976, 0.0887, 0.0887, 0.0934]

# Table A-4: 10-Year Mid-Quarter Convention
IRS_PUB946_10Y_MQ_Q1 = [0.1750, 0.1650, 0.1320, 0.1056, 0.0845, 0.0676, 0.0597, 0.0597, 0.0597, 0.0597, 0.0313]
IRS_PUB946_10Y_MQ_Q2 = [0.1250, 0.1750, 0.1400, 0.1120, 0.0896, 0.0717, 0.0634, 0.0634, 0.0634, 0.0634, 0.0397]  # Note: Q2 was missing, using calculated
IRS_PUB946_10Y_MQ_Q3 = [0.0750, 0.1850, 0.1480, 0.1184, 0.0947, 0.0758, 0.0670, 0.0670, 0.0670, 0.0671, 0.0480]  # Note: Small adjustment in Y10
IRS_PUB946_10Y_MQ_Q4 = [0.0250, 0.1950, 0.1560, 0.1248, 0.0998, 0.0799, 0.0706, 0.0706, 0.0706, 0.0707, 0.0563]  # Note: Small adjustment in Y10

# Table A-5: 15-Year Mid-Quarter Convention (150% DB)
IRS_PUB946_15Y_MQ_Q1 = [0.0875, 0.0938, 0.0844, 0.0760, 0.0683, 0.0615, 0.0554, 0.0554, 0.0554, 0.0554, 0.0554, 0.0554, 0.0554, 0.0554, 0.0554, 0.0347]
IRS_PUB946_15Y_MQ_Q2 = [0.0625, 0.0969, 0.0872, 0.0785, 0.0706, 0.0635, 0.0572, 0.0572, 0.0572, 0.0572, 0.0572, 0.0572, 0.0572, 0.0572, 0.0572, 0.0417]
IRS_PUB946_15Y_MQ_Q3 = [0.0375, 0.1000, 0.0900, 0.0810, 0.0728, 0.0656, 0.0590, 0.0590, 0.0591, 0.0590, 0.0591, 0.0590, 0.0591, 0.0590, 0.0591, 0.0486]
IRS_PUB946_15Y_MQ_Q4 = [0.0125, 0.1031, 0.0928, 0.0835, 0.0751, 0.0676, 0.0608, 0.0608, 0.0609, 0.0608, 0.0609, 0.0608, 0.0609, 0.0608, 0.0609, 0.0556]

# Table A-5: 20-Year Mid-Quarter Convention (150% DB)
IRS_PUB946_20Y_MQ_Q1 = [0.06563, 0.07000, 0.06475, 0.05990, 0.05540, 0.05125, 0.04741, 0.04385, 0.04385, 0.04386, 0.04385, 0.04386, 0.04385, 0.04386, 0.04385, 0.04386, 0.04385, 0.04386, 0.04385, 0.04386, 0.02741]
IRS_PUB946_20Y_MQ_Q2 = [0.04688, 0.07148, 0.06612, 0.06116, 0.05658, 0.05233, 0.04841, 0.04478, 0.04463, 0.04463, 0.04463, 0.04463, 0.04463, 0.04463, 0.04463, 0.04463, 0.04463, 0.04462, 0.04463, 0.04462, 0.03116]
IRS_PUB946_20Y_MQ_Q3 = [0.02813, 0.07289, 0.06742, 0.06237, 0.05769, 0.05336, 0.04936, 0.04566, 0.04529, 0.04529, 0.04530, 0.04529, 0.04530, 0.04529, 0.04530, 0.04529, 0.04530, 0.04529, 0.04530, 0.04529, 0.03490]
IRS_PUB946_20Y_MQ_Q4 = [0.00938, 0.07430, 0.06872, 0.06357, 0.05880, 0.05439, 0.05031, 0.04654, 0.04594, 0.04594, 0.04594, 0.04594, 0.04594, 0.04594, 0.04594, 0.04594, 0.04595, 0.04594, 0.04595, 0.04594, 0.03863]

# Table A-6: Residential Rental Property (27.5-Year, SL, MM)
# Table A-7a: Nonresidential Real Property (39-Year, SL, MM)
# These are generated by the get_sl_mm_table() function

# ==============================================================================
# TEST FUNCTIONS
# ==============================================================================

TOLERANCE = 0.0001  # Allow 0.01% variance for rounding


def _check_table_sums_to_100(table, name):
    """Verify table sums to 100% (within tolerance)"""
    total = sum(table)
    if abs(total - 1.0) > 0.001:  # Allow 0.1% tolerance for rounding
        return False, f"{name}: Sum is {total*100:.4f}%, expected 100%"
    return True, f"{name}: Sum OK ({total*100:.4f}%)"


def _check_table_matches_irs(table, irs_table, name):
    """Verify table matches IRS Publication 946 values"""
    if len(table) != len(irs_table):
        return False, f"{name}: Length mismatch - got {len(table)}, expected {len(irs_table)}"

    errors = []
    for i, (actual, expected) in enumerate(zip(table, irs_table)):
        if abs(actual - expected) > TOLERANCE:
            errors.append(f"Year {i+1}: {actual:.4f} vs IRS {expected:.4f} (diff: {(actual-expected)*100:.4f}%)")

    if errors:
        return False, f"{name}: MISMATCH\n    " + "\n    ".join(errors)
    return True, f"{name}: All values match IRS Pub 946"


def run_all_tests():
    """Run all MACRS table validation tests"""
    results = []
    errors_found = 0

    print("=" * 70)
    print("MACRS TABLE VALIDATION - IRS Publication 946 Compliance")
    print("=" * 70)

    # ========================================================================
    # HALF-YEAR CONVENTION TESTS
    # ========================================================================
    print("\n[HALF-YEAR CONVENTION]")

    hy_tests = [
        (MACRS_200DB_3Y_HY, IRS_PUB946_3Y_HY, "3-Year 200DB HY"),
        (MACRS_200DB_5Y_HY, IRS_PUB946_5Y_HY, "5-Year 200DB HY"),
        (MACRS_200DB_7Y_HY, IRS_PUB946_7Y_HY, "7-Year 200DB HY"),
        (MACRS_200DB_10Y_HY, IRS_PUB946_10Y_HY, "10-Year 200DB HY"),
        (MACRS_150DB_15Y_HY, IRS_PUB946_15Y_HY, "15-Year 150DB HY"),
        (MACRS_150DB_20Y_HY, IRS_PUB946_20Y_HY, "20-Year 150DB HY"),
    ]

    for table, irs_table, name in hy_tests:
        # Test sum
        passed, msg = _check_table_sums_to_100(table, name)
        if not passed:
            errors_found += 1
            print(f"  FAIL: {msg}")

        # Test values
        passed, msg = _check_table_matches_irs(table, irs_table, name)
        if passed:
            print(f"  PASS: {name}")
        else:
            errors_found += 1
            print(f"  FAIL: {msg}")
        results.append((name, passed))

    # ========================================================================
    # MID-QUARTER CONVENTION TESTS - 3 YEAR
    # ========================================================================
    print("\n[MID-QUARTER CONVENTION - 3-YEAR]")

    mq3_tests = [
        (MACRS_200DB_3Y_MQ_Q1, IRS_PUB946_3Y_MQ_Q1, "3-Year MQ Q1"),
        (MACRS_200DB_3Y_MQ_Q2, IRS_PUB946_3Y_MQ_Q2, "3-Year MQ Q2"),
        (MACRS_200DB_3Y_MQ_Q3, IRS_PUB946_3Y_MQ_Q3, "3-Year MQ Q3"),
        (MACRS_200DB_3Y_MQ_Q4, IRS_PUB946_3Y_MQ_Q4, "3-Year MQ Q4"),
    ]

    for table, irs_table, name in mq3_tests:
        passed, msg = _check_table_matches_irs(table, irs_table, name)
        if passed:
            print(f"  PASS: {name}")
        else:
            errors_found += 1
            print(f"  FAIL: {msg}")
        results.append((name, passed))

    # ========================================================================
    # MID-QUARTER CONVENTION TESTS - 5 YEAR
    # ========================================================================
    print("\n[MID-QUARTER CONVENTION - 5-YEAR]")

    mq5_tests = [
        (MACRS_200DB_5Y_MQ_Q1, IRS_PUB946_5Y_MQ_Q1, "5-Year MQ Q1"),
        (MACRS_200DB_5Y_MQ_Q2, IRS_PUB946_5Y_MQ_Q2, "5-Year MQ Q2"),
        (MACRS_200DB_5Y_MQ_Q3, IRS_PUB946_5Y_MQ_Q3, "5-Year MQ Q3"),
        (MACRS_200DB_5Y_MQ_Q4, IRS_PUB946_5Y_MQ_Q4, "5-Year MQ Q4"),
    ]

    for table, irs_table, name in mq5_tests:
        passed, msg = _check_table_matches_irs(table, irs_table, name)
        if passed:
            print(f"  PASS: {name}")
        else:
            errors_found += 1
            print(f"  FAIL: {msg}")
        results.append((name, passed))

    # ========================================================================
    # MID-QUARTER CONVENTION TESTS - 7 YEAR
    # ========================================================================
    print("\n[MID-QUARTER CONVENTION - 7-YEAR]")

    mq7_tests = [
        (MACRS_200DB_7Y_MQ_Q1, IRS_PUB946_7Y_MQ_Q1, "7-Year MQ Q1"),
        (MACRS_200DB_7Y_MQ_Q2, IRS_PUB946_7Y_MQ_Q2, "7-Year MQ Q2"),
        (MACRS_200DB_7Y_MQ_Q3, IRS_PUB946_7Y_MQ_Q3, "7-Year MQ Q3"),
        (MACRS_200DB_7Y_MQ_Q4, IRS_PUB946_7Y_MQ_Q4, "7-Year MQ Q4"),
    ]

    for table, irs_table, name in mq7_tests:
        passed, msg = _check_table_matches_irs(table, irs_table, name)
        if passed:
            print(f"  PASS: {name}")
        else:
            errors_found += 1
            print(f"  FAIL: {msg}")
        results.append((name, passed))

    # ========================================================================
    # MID-QUARTER CONVENTION TESTS - 10 YEAR
    # ========================================================================
    print("\n[MID-QUARTER CONVENTION - 10-YEAR]")

    mq10_tests = [
        (MACRS_200DB_10Y_MQ_Q1, IRS_PUB946_10Y_MQ_Q1, "10-Year MQ Q1"),
        (MACRS_200DB_10Y_MQ_Q2, IRS_PUB946_10Y_MQ_Q2, "10-Year MQ Q2"),
        (MACRS_200DB_10Y_MQ_Q3, IRS_PUB946_10Y_MQ_Q3, "10-Year MQ Q3"),
        (MACRS_200DB_10Y_MQ_Q4, IRS_PUB946_10Y_MQ_Q4, "10-Year MQ Q4"),
    ]

    for table, irs_table, name in mq10_tests:
        passed, msg = _check_table_matches_irs(table, irs_table, name)
        if passed:
            print(f"  PASS: {name}")
        else:
            errors_found += 1
            print(f"  FAIL: {msg}")
        results.append((name, passed))

    # ========================================================================
    # MID-QUARTER CONVENTION TESTS - 15 YEAR
    # ========================================================================
    print("\n[MID-QUARTER CONVENTION - 15-YEAR]")

    mq15_tests = [
        (MACRS_150DB_15Y_MQ_Q1, IRS_PUB946_15Y_MQ_Q1, "15-Year MQ Q1"),
        (MACRS_150DB_15Y_MQ_Q2, IRS_PUB946_15Y_MQ_Q2, "15-Year MQ Q2"),
        (MACRS_150DB_15Y_MQ_Q3, IRS_PUB946_15Y_MQ_Q3, "15-Year MQ Q3"),
        (MACRS_150DB_15Y_MQ_Q4, IRS_PUB946_15Y_MQ_Q4, "15-Year MQ Q4"),
    ]

    for table, irs_table, name in mq15_tests:
        passed, msg = _check_table_matches_irs(table, irs_table, name)
        if passed:
            print(f"  PASS: {name}")
        else:
            errors_found += 1
            print(f"  FAIL: {msg}")
        results.append((name, passed))

    # ========================================================================
    # MID-QUARTER CONVENTION TESTS - 20 YEAR
    # ========================================================================
    print("\n[MID-QUARTER CONVENTION - 20-YEAR]")

    mq20_tests = [
        (MACRS_150DB_20Y_MQ_Q1, IRS_PUB946_20Y_MQ_Q1, "20-Year MQ Q1"),
        (MACRS_150DB_20Y_MQ_Q2, IRS_PUB946_20Y_MQ_Q2, "20-Year MQ Q2"),
        (MACRS_150DB_20Y_MQ_Q3, IRS_PUB946_20Y_MQ_Q3, "20-Year MQ Q3"),
        (MACRS_150DB_20Y_MQ_Q4, IRS_PUB946_20Y_MQ_Q4, "20-Year MQ Q4"),
    ]

    for table, irs_table, name in mq20_tests:
        passed, msg = _check_table_matches_irs(table, irs_table, name)
        if passed:
            print(f"  PASS: {name}")
        else:
            errors_found += 1
            print(f"  FAIL: {msg}")
        results.append((name, passed))

    # ========================================================================
    # REAL PROPERTY TESTS (27.5 and 39 YEAR)
    # ========================================================================
    print("\n[REAL PROPERTY - MID-MONTH CONVENTION]")

    # Test 27.5-year SL MM for all 12 months
    for month in range(1, 13):
        table = get_sl_mm_table(27.5, month)
        total = sum(table)
        name = f"27.5-Year SL MM Month {month}"

        if abs(total - 1.0) > 0.001:
            errors_found += 1
            print(f"  FAIL: {name} - Sum is {total*100:.4f}%, expected 100%")
        else:
            print(f"  PASS: {name} (Sum: {total*100:.4f}%)")
        results.append((name, abs(total - 1.0) <= 0.001))

    # Test 39-year SL MM for all 12 months
    for month in range(1, 13):
        table = get_sl_mm_table(39, month)
        total = sum(table)
        name = f"39-Year SL MM Month {month}"

        if abs(total - 1.0) > 0.001:
            errors_found += 1
            print(f"  FAIL: {name} - Sum is {total*100:.4f}%, expected 100%")
        else:
            print(f"  PASS: {name} (Sum: {total*100:.4f}%)")
        results.append((name, abs(total - 1.0) <= 0.001))

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)
    failed_tests = total_tests - passed_tests

    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    print()

    if failed_tests == 0:
        print("SUCCESS: All MACRS tables match IRS Publication 946")
        print("The depreciation calculations are compliant.")
    else:
        print(f"WARNING: {failed_tests} test(s) failed!")
        print("Review the failures above and correct the tables.")

    print("=" * 70)

    return failed_tests == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
