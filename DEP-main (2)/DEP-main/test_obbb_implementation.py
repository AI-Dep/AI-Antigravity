#!/usr/bin/env python3
"""
Test OBBB Act Implementation

Verifies that the tax engine correctly applies:
1. OBBB Act 100% bonus for property acquired AND placed in service after 1/19/2025
2. TCJA 80% bonus for property not meeting OBBB requirements
3. OBBB Act Section 179 limits ($2.5M max / $4M phase-out)
"""

from datetime import date
from fixed_asset_ai.logic.tax_year_config import (
    get_bonus_percentage,
    get_section_179_limits,
    qualifies_for_obbb_bonus,
    OBBB_BONUS_EFFECTIVE_DATE,
)

def test_bonus_depreciation():
    """Test bonus depreciation percentages under OBBB Act."""

    print("=" * 80)
    print("BONUS DEPRECIATION TEST - OBBB Act vs TCJA Phase-Down")
    print("=" * 80)

    # Test Case 1: 2024 property - should get 80% (TCJA)
    acq_2024 = date(2024, 6, 1)
    pis_2024 = date(2024, 7, 1)
    bonus_2024 = get_bonus_percentage(2024, acq_2024, pis_2024)
    print(f"\n1. 2024 Property (acquired {acq_2024}, in-service {pis_2024})")
    print(f"   Expected: 80% (TCJA)")
    print(f"   Actual: {bonus_2024:.0%}")
    print(f"   ✓ PASS" if bonus_2024 == 0.80 else f"   ✗ FAIL")

    # Test Case 2: 2025 property placed in service BEFORE 1/19/2025 - should get 80% (TCJA)
    acq_early_2025 = date(2025, 1, 5)
    pis_early_2025 = date(2025, 1, 15)
    bonus_early_2025 = get_bonus_percentage(2025, acq_early_2025, pis_early_2025)
    print(f"\n2. Early 2025 Property (acquired {acq_early_2025}, in-service {pis_early_2025})")
    print(f"   Expected: 80% (TCJA - before OBBB effective date)")
    print(f"   Actual: {bonus_early_2025:.0%}")
    print(f"   ✓ PASS" if bonus_early_2025 == 0.80 else f"   ✗ FAIL")

    # Test Case 3: Acquired BEFORE OBBB but placed in service AFTER - should get 80% (doesn't meet BOTH)
    acq_before = date(2025, 1, 10)
    pis_after = date(2025, 2, 1)
    bonus_mixed = get_bonus_percentage(2025, acq_before, pis_after)
    print(f"\n3. Mixed Dates (acquired {acq_before}, in-service {pis_after})")
    print(f"   Expected: 80% (TCJA - acquired before OBBB date)")
    print(f"   Actual: {bonus_mixed:.0%}")
    print(f"   ✓ PASS" if bonus_mixed == 0.80 else f"   ✗ FAIL")

    # Test Case 4: BOTH acquired AND placed in service AFTER 1/19/2025 - should get 100% (OBBB)
    acq_obbb = date(2025, 2, 1)
    pis_obbb = date(2025, 3, 1)
    bonus_obbb = get_bonus_percentage(2025, acq_obbb, pis_obbb)
    qualifies = qualifies_for_obbb_bonus(acq_obbb, pis_obbb)
    print(f"\n4. OBBB Qualifying Property (acquired {acq_obbb}, in-service {pis_obbb})")
    print(f"   Expected: 100% (OBBB Act)")
    print(f"   Actual: {bonus_obbb:.0%}")
    print(f"   Qualifies for OBBB: {qualifies}")
    print(f"   ✓ PASS" if bonus_obbb == 1.00 and qualifies else f"   ✗ FAIL")

    # Test Case 5: No dates provided - should use TCJA schedule
    bonus_no_dates = get_bonus_percentage(2025)
    print(f"\n5. No Dates Provided (tax year 2025)")
    print(f"   Expected: 80% (TCJA default)")
    print(f"   Actual: {bonus_no_dates:.0%}")
    print(f"   ✓ PASS" if bonus_no_dates == 0.80 else f"   ✗ FAIL")

    # Test Case 6: 2026 property without OBBB dates - should get 60% (TCJA phase-down)
    acq_2026 = date(2026, 1, 15)
    pis_2026 = date(2026, 2, 1)
    bonus_2026 = get_bonus_percentage(2026, acq_2026, pis_2026)
    print(f"\n6. 2026 Property (acquired {acq_2026}, in-service {pis_2026})")
    print(f"   Expected: 100% (OBBB Act - acquired after 1/19/2025)")
    print(f"   Actual: {bonus_2026:.0%}")
    print(f"   ✓ PASS" if bonus_2026 == 1.00 else f"   ✗ FAIL")


def test_section_179_limits():
    """Test Section 179 limits under OBBB Act."""

    print("\n" + "=" * 80)
    print("SECTION 179 LIMITS TEST - OBBB Act")
    print("=" * 80)

    # 2024 limits (pre-OBBB)
    limits_2024 = get_section_179_limits(2024)
    print(f"\n2024 Limits (pre-OBBB):")
    print(f"   Max Deduction: ${limits_2024['max_deduction']:,}")
    print(f"   Phase-out Threshold: ${limits_2024['phaseout_threshold']:,}")
    print(f"   Expected: $1,220,000 / $3,050,000")
    pass_2024 = (limits_2024['max_deduction'] == 1220000 and
                 limits_2024['phaseout_threshold'] == 3050000)
    print(f"   ✓ PASS" if pass_2024 else f"   ✗ FAIL")

    # 2025 limits (OBBB Act)
    limits_2025 = get_section_179_limits(2025)
    print(f"\n2025 Limits (OBBB Act - property placed in service after 12/31/2024):")
    print(f"   Max Deduction: ${limits_2025['max_deduction']:,}")
    print(f"   Phase-out Threshold: ${limits_2025['phaseout_threshold']:,}")
    print(f"   Expected: $2,500,000 / $4,000,000")
    pass_2025 = (limits_2025['max_deduction'] == 2500000 and
                 limits_2025['phaseout_threshold'] == 4000000)
    print(f"   ✓ PASS" if pass_2025 else f"   ✗ FAIL")

    # Verify increase from 2024 to 2025
    increase_max = limits_2025['max_deduction'] - limits_2024['max_deduction']
    increase_phaseout = limits_2025['phaseout_threshold'] - limits_2024['phaseout_threshold']
    print(f"\n2024 → 2025 Increases:")
    print(f"   Max Deduction Increase: ${increase_max:,} (+{increase_max/limits_2024['max_deduction']:.1%})")
    print(f"   Phase-out Increase: ${increase_phaseout:,} (+{increase_phaseout/limits_2024['phaseout_threshold']:.1%})")


def test_obbb_effective_dates():
    """Test OBBB effective date constants."""

    print("\n" + "=" * 80)
    print("OBBB EFFECTIVE DATES TEST")
    print("=" * 80)

    print(f"\nOBBB Bonus Effective Date: {OBBB_BONUS_EFFECTIVE_DATE}")
    print(f"Expected: 2025-01-19")
    print(f"✓ PASS" if OBBB_BONUS_EFFECTIVE_DATE == date(2025, 1, 19) else "✗ FAIL")

    from fixed_asset_ai.logic.tax_year_config import OBBB_SECTION_179_EFFECTIVE_DATE
    print(f"\nOBBB Section 179 Effective Date: {OBBB_SECTION_179_EFFECTIVE_DATE}")
    print(f"Expected: 2024-12-31")
    print(f"✓ PASS" if OBBB_SECTION_179_EFFECTIVE_DATE == date(2024, 12, 31) else "✗ FAIL")


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "OBBB ACT IMPLEMENTATION TEST SUITE" + " " * 24 + "║")
    print("║" + " " * 15 + "One Big, Beautiful Bill - Passed July 4, 2025" + " " * 18 + "║")
    print("╚" + "=" * 78 + "╝")

    test_obbb_effective_dates()
    test_bonus_depreciation()
    test_section_179_limits()

    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETE")
    print("=" * 80 + "\n")
