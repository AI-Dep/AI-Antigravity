#!/usr/bin/env python3
"""
TIER 2 Implementation Test Suite

Tests high-risk production-readiness features:
1. Listed Property Business Use % Tracking (IRC §280F)
2. ADS (Alternative Depreciation System) Detection and Enforcement (IRC §168(g))
3. Depreciation Recapture Calculations (IRC §1245 / §1250)
"""

from datetime import date
from fixed_asset_ai.logic.listed_property import (
    is_listed_property,
    get_business_use_percentage,
    validate_business_use_for_incentives,
    requires_ads,
)
from fixed_asset_ai.logic.ads_system import (
    get_ads_recovery_period,
    should_use_ads,
)
from fixed_asset_ai.logic.recapture import (
    calculate_section_1245_recapture,
    calculate_section_1250_recapture,
    determine_recapture_type,
)


def test_listed_property_detection():
    """Test detection of listed property per IRC §280F."""

    print("=" * 80)
    print("LISTED PROPERTY DETECTION TEST (IRC §280F)")
    print("=" * 80)

    # Test Case 1: Passenger automobile
    asset1 = {
        "Final Category": "Passenger Automobile",
        "Description": "2024 Toyota Camry",
    }
    is_listed, reason = is_listed_property(asset1)
    print(f"\n1. Passenger Automobile")
    print(f"   Description: {asset1['Description']}")
    print(f"   Expected: Listed property")
    print(f"   Actual: {'Listed' if is_listed else 'Not listed'}")
    print(f"   Reason: {reason}")
    print(f"   ✓ PASS" if is_listed else "   ✗ FAIL")

    # Test Case 2: Computer
    asset2 = {
        "Final Category": "Office Equipment",
        "Description": "Dell Laptop Computer",
    }
    is_listed, reason = is_listed_property(asset2)
    print(f"\n2. Computer")
    print(f"   Description: {asset2['Description']}")
    print(f"   Expected: Listed property")
    print(f"   Actual: {'Listed' if is_listed else 'Not listed'}")
    print(f"   Reason: {reason}")
    print(f"   ✓ PASS" if is_listed else "   ✗ FAIL")

    # Test Case 3: Non-listed property (machinery)
    asset3 = {
        "Final Category": "Machinery & Equipment",
        "Description": "CNC Milling Machine",
    }
    is_listed, reason = is_listed_property(asset3)
    print(f"\n3. Machinery (non-listed)")
    print(f"   Description: {asset3['Description']}")
    print(f"   Expected: Not listed property")
    print(f"   Actual: {'Listed' if is_listed else 'Not listed'}")
    print(f"   ✓ PASS" if not is_listed else "   ✗ FAIL")


def test_business_use_percentage():
    """Test business use percentage extraction and validation."""

    print("\n" + "=" * 80)
    print("BUSINESS USE PERCENTAGE TEST")
    print("=" * 80)

    # Test Case 1: 100% business use (decimal format)
    asset1 = {"Business Use %": 1.0}
    pct1 = get_business_use_percentage(asset1)
    print(f"\n1. 100% Business Use (decimal: 1.0)")
    print(f"   Expected: 1.0")
    print(f"   Actual: {pct1}")
    print(f"   ✓ PASS" if pct1 == 1.0 else "   ✗ FAIL")

    # Test Case 2: 75% business use (percentage format)
    asset2 = {"Business Use %": "75%"}
    pct2 = get_business_use_percentage(asset2)
    print(f"\n2. 75% Business Use (string: '75%')")
    print(f"   Expected: 0.75")
    print(f"   Actual: {pct2}")
    print(f"   ✓ PASS" if pct2 == 0.75 else "   ✗ FAIL")

    # Test Case 3: 50% business use (integer format)
    asset3 = {"Business Use %": 50}
    pct3 = get_business_use_percentage(asset3)
    print(f"\n3. 50% Business Use (integer: 50)")
    print(f"   Expected: 0.50")
    print(f"   Actual: {pct3}")
    print(f"   ✓ PASS" if pct3 == 0.50 else "   ✗ FAIL")

    # Test Case 4: No business use specified (defaults to None)
    asset4 = {"Description": "Test asset"}
    pct4 = get_business_use_percentage(asset4)
    print(f"\n4. No Business Use Specified")
    print(f"   Expected: None")
    print(f"   Actual: {pct4}")
    print(f"   ✓ PASS" if pct4 is None else "   ✗ FAIL")


def test_business_use_validation():
    """Test business use validation for Section 179/bonus eligibility."""

    print("\n" + "=" * 80)
    print("BUSINESS USE VALIDATION TEST (>50% requirement)")
    print("=" * 80)

    # Test Case 1: Listed property with 60% business use (PASSES >50%)
    asset1 = {
        "Final Category": "Passenger Automobile",
        "Description": "2024 Honda Accord",
        "Business Use %": 0.60,
    }
    s179_ok, bonus_ok, warnings = validate_business_use_for_incentives(
        asset1, allow_section_179=True, allow_bonus=True
    )
    print(f"\n1. Listed Property - 60% Business Use")
    print(f"   Expected: Section 179 ✓, Bonus ✓ (>50% test met)")
    print(f"   Actual: Section 179 {'✓' if s179_ok else '✗'}, Bonus {'✓' if bonus_ok else '✗'}")
    print(f"   Warnings: {len(warnings)}")
    for w in warnings:
        print(f"     - {w}")
    print(f"   ✓ PASS" if (s179_ok and bonus_ok) else "   ✗ FAIL")

    # Test Case 2: Listed property with 50% business use (FAILS ≤50%)
    asset2 = {
        "Final Category": "Passenger Automobile",
        "Description": "2024 BMW X5",
        "Business Use %": 0.50,
    }
    s179_ok, bonus_ok, warnings = validate_business_use_for_incentives(
        asset2, allow_section_179=True, allow_bonus=True
    )
    print(f"\n2. Listed Property - 50% Business Use (FAILS)")
    print(f"   Expected: Section 179 ✗, Bonus ✗ (≤50% = ADS required)")
    print(f"   Actual: Section 179 {'✓' if s179_ok else '✗'}, Bonus {'✓' if bonus_ok else '✗'}")
    print(f"   Warnings: {len(warnings)}")
    for w in warnings:
        print(f"     - {w}")
    print(f"   ✓ PASS" if (not s179_ok and not bonus_ok) else "   ✗ FAIL")

    # Test Case 3: Listed property with 30% business use (FAILS)
    asset3 = {
        "Final Category": "Passenger Automobile",
        "Description": "2024 Tesla Model 3",
        "Business Use %": 0.30,
    }
    s179_ok, bonus_ok, warnings = validate_business_use_for_incentives(
        asset3, allow_section_179=True, allow_bonus=True
    )
    print(f"\n3. Listed Property - 30% Business Use (FAILS)")
    print(f"   Expected: Section 179 ✗, Bonus ✗ (≤50%)")
    print(f"   Actual: Section 179 {'✓' if s179_ok else '✗'}, Bonus {'✓' if bonus_ok else '✗'}")
    print(f"   Warnings: {len(warnings)}")
    for w in warnings:
        print(f"     - {w}")
    print(f"   ✓ PASS" if (not s179_ok and not bonus_ok) else "   ✗ FAIL")


def test_ads_detection():
    """Test ADS (Alternative Depreciation System) detection."""

    print("\n" + "=" * 80)
    print("ADS DETECTION TEST (IRC §168(g))")
    print("=" * 80)

    # Test Case 1: Listed property with 40% business use → ADS required
    asset1 = {
        "Final Category": "Passenger Automobile",
        "Description": "2024 Mercedes C-Class",
        "Business Use %": 0.40,
    }
    needs_ads, reason = should_use_ads(asset1)
    print(f"\n1. Listed Property - 40% Business Use")
    print(f"   Expected: ADS REQUIRED (≤50% business use)")
    print(f"   Actual: {'ADS REQUIRED' if needs_ads else 'MACRS allowed'}")
    print(f"   Reason: {reason}")
    print(f"   ✓ PASS" if needs_ads else "   ✗ FAIL")

    # Test Case 2: Listed property with 70% business use → MACRS allowed
    asset2 = {
        "Final Category": "Passenger Automobile",
        "Description": "2024 Ford F-150",
        "Business Use %": 0.70,
    }
    needs_ads, reason = should_use_ads(asset2)
    print(f"\n2. Listed Property - 70% Business Use")
    print(f"   Expected: MACRS allowed (>50% business use)")
    print(f"   Actual: {'ADS REQUIRED' if needs_ads else 'MACRS allowed'}")
    print(f"   ✓ PASS" if not needs_ads else "   ✗ FAIL")

    # Test Case 3: Non-listed property → MACRS allowed
    asset3 = {
        "Final Category": "Machinery & Equipment",
        "Description": "Industrial Lathe",
    }
    needs_ads, reason = should_use_ads(asset3)
    print(f"\n3. Non-Listed Property (Machinery)")
    print(f"   Expected: MACRS allowed (not listed property)")
    print(f"   Actual: {'ADS REQUIRED' if needs_ads else 'MACRS allowed'}")
    print(f"   ✓ PASS" if not needs_ads else "   ✗ FAIL")


def test_ads_recovery_periods():
    """Test ADS recovery period determination."""

    print("\n" + "=" * 80)
    print("ADS RECOVERY PERIODS TEST")
    print("=" * 80)

    # Test Case 1: Passenger automobile (5-year under ADS)
    ads_life1 = get_ads_recovery_period(category="Passenger Automobile")
    print(f"\n1. Passenger Automobile")
    print(f"   MACRS Life: 5 years")
    print(f"   Expected ADS Life: 5 years")
    print(f"   Actual ADS Life: {ads_life1} years")
    print(f"   ✓ PASS" if ads_life1 == 5 else "   ✗ FAIL")

    # Test Case 2: Office Furniture (7-year MACRS → 12-year ADS)
    ads_life2 = get_ads_recovery_period(macrs_life=7)
    print(f"\n2. Office Furniture")
    print(f"   MACRS Life: 7 years")
    print(f"   Expected ADS Life: 12 years")
    print(f"   Actual ADS Life: {ads_life2} years")
    print(f"   ✓ PASS" if ads_life2 == 12 else "   ✗ FAIL")

    # Test Case 3: Nonresidential Real Property (39-year MACRS → 40-year ADS)
    ads_life3 = get_ads_recovery_period(macrs_life=39)
    print(f"\n3. Nonresidential Real Property")
    print(f"   MACRS Life: 39 years")
    print(f"   Expected ADS Life: 40 years")
    print(f"   Actual ADS Life: {ads_life3} years")
    print(f"   ✓ PASS" if ads_life3 == 40 else "   ✗ FAIL")


def test_section_1245_recapture():
    """Test Section 1245 recapture calculations for personal property."""

    print("\n" + "=" * 80)
    print("SECTION 1245 RECAPTURE TEST (IRC §1245 - Personal Property)")
    print("=" * 80)

    # Test Case 1: Gain on sale with depreciation
    result1 = calculate_section_1245_recapture(
        cost=100000,
        accumulated_depreciation=30000,
        proceeds=90000,
        section_179_taken=10000,
        bonus_taken=20000
    )
    print(f"\n1. Equipment Sale with Gain")
    print(f"   Cost: $100,000")
    print(f"   Depreciation: $30,000 (MACRS) + $10,000 (§179) + $20,000 (Bonus) = $60,000")
    print(f"   Adjusted Basis: ${result1['adjusted_basis']:,.0f}")
    print(f"   Proceeds: $90,000")
    print(f"   Gain on Sale: ${result1['gain_on_sale']:,.0f}")
    print(f"   §1245 Recapture (Ordinary Income): ${result1['section_1245_recapture']:,.0f}")
    print(f"   Capital Gain: ${result1['capital_gain']:,.0f}")
    print(f"   Expected: $50,000 gain, all recaptured as ordinary income")
    pass_1 = (result1['gain_on_sale'] == 50000 and
              result1['section_1245_recapture'] == 50000 and
              result1['capital_gain'] == 0)
    print(f"   ✓ PASS" if pass_1 else "   ✗ FAIL")

    # Test Case 2: Loss on sale (no recapture)
    result2 = calculate_section_1245_recapture(
        cost=100000,
        accumulated_depreciation=60000,
        proceeds=30000,
    )
    print(f"\n2. Equipment Sale with Loss")
    print(f"   Cost: $100,000")
    print(f"   Depreciation: $60,000")
    print(f"   Adjusted Basis: ${result2['adjusted_basis']:,.0f}")
    print(f"   Proceeds: $30,000")
    print(f"   Loss on Sale: ${result2['capital_loss']:,.0f}")
    print(f"   §1245 Recapture: ${result2['section_1245_recapture']:,.0f}")
    print(f"   Expected: $10,000 loss, no recapture")
    pass_2 = (result2['capital_loss'] == 10000 and
              result2['section_1245_recapture'] == 0)
    print(f"   ✓ PASS" if pass_2 else "   ✗ FAIL")


def test_section_1250_recapture():
    """Test Section 1250 recapture calculations for real property."""

    print("\n" + "=" * 80)
    print("SECTION 1250 RECAPTURE TEST (IRC §1250 - Real Property)")
    print("=" * 80)

    # Test Case 1: Building sale with unrecaptured §1250 gain
    result1 = calculate_section_1250_recapture(
        cost=500000,
        accumulated_depreciation=100000,
        proceeds=550000,
        accelerated_depreciation=0  # Post-1986: SL only
    )
    print(f"\n1. Building Sale with Gain")
    print(f"   Cost: $500,000")
    print(f"   Straight-Line Depreciation: $100,000")
    print(f"   Adjusted Basis: ${result1['adjusted_basis']:,.0f}")
    print(f"   Proceeds: $550,000")
    print(f"   Gain on Sale: ${result1['gain_on_sale']:,.0f}")
    print(f"   §1250 Recapture (Ordinary): ${result1['section_1250_recapture']:,.0f}")
    print(f"   Unrecaptured §1250 Gain (25% rate): ${result1['unrecaptured_1250_gain']:,.0f}")
    print(f"   Capital Gain (0/15/20% rates): ${result1['capital_gain']:,.0f}")
    print(f"   Expected: $150,000 gain → $100,000 unrecaptured @25%, $50,000 cap gain")
    pass_1 = (result1['gain_on_sale'] == 150000 and
              result1['section_1250_recapture'] == 0 and  # No accelerated for post-1986
              result1['unrecaptured_1250_gain'] == 100000 and
              result1['capital_gain'] == 50000)
    print(f"   ✓ PASS" if pass_1 else "   ✗ FAIL")


def test_recapture_type_determination():
    """Test determination of recapture type (§1245 vs §1250)."""

    print("\n" + "=" * 80)
    print("RECAPTURE TYPE DETERMINATION TEST")
    print("=" * 80)

    # Test Case 1: Machinery & Equipment → §1245
    type1 = determine_recapture_type("Machinery & Equipment")
    print(f"\n1. Machinery & Equipment")
    print(f"   Expected: §1245 (personal property)")
    print(f"   Actual: §{type1}")
    print(f"   ✓ PASS" if type1 == "1245" else "   ✗ FAIL")

    # Test Case 2: Nonresidential Real Property → §1250
    type2 = determine_recapture_type("Nonresidential Real Property")
    print(f"\n2. Nonresidential Real Property")
    print(f"   Expected: §1250 (real property)")
    print(f"   Actual: §{type2}")
    print(f"   ✓ PASS" if type2 == "1250" else "   ✗ FAIL")

    # Test Case 3: Land → none
    type3 = determine_recapture_type("Land")
    print(f"\n3. Land")
    print(f"   Expected: none (not depreciable)")
    print(f"   Actual: {type3}")
    print(f"   ✓ PASS" if type3 == "none" else "   ✗ FAIL")


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 25 + "TIER 2 TEST SUITE" + " " * 36 + "║")
    print("║" + " " * 18 + "High-Risk Production Readiness Features" + " " * 21 + "║")
    print("╚" + "=" * 78 + "╝")

    # Listed Property Tests
    test_listed_property_detection()
    test_business_use_percentage()
    test_business_use_validation()

    # ADS Tests
    test_ads_detection()
    test_ads_recovery_periods()

    # Recapture Tests
    test_section_1245_recapture()
    test_section_1250_recapture()
    test_recapture_type_determination()

    print("\n" + "=" * 80)
    print("TIER 2 TEST SUITE COMPLETE")
    print("=" * 80 + "\n")
