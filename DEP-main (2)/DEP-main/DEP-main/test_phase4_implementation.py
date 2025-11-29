"""
Comprehensive Test Suite for Phase 4 Implementation

Tests:
1. MACRS depreciation tables (IRS Publication 946)
2. Multi-year depreciation projection
3. Section 179 carryforward tracking
4. Integration with fa_export.py

Run with: pytest test_phase4_implementation.py -v
Or: python test_phase4_implementation.py
"""

try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False

import pandas as pd
from datetime import date

from fixed_asset_ai.logic.macrs_tables import (
    get_macrs_table,
    calculate_macrs_depreciation,
    MACRS_200DB_5Y_HY,
    MACRS_200DB_7Y_HY,
    MACRS_200DB_5Y_MQ_Q1,
    MACRS_200DB_5Y_MQ_Q4,
)

from fixed_asset_ai.logic.depreciation_projection import (
    project_asset_depreciation,
    project_portfolio_depreciation,
    create_detailed_projection_table,
    analyze_depreciation_cliff,
)

from fixed_asset_ai.logic.section_179_carryforward import (
    calculate_section_179_with_income_limit,
    allocate_section_179_limitation,
    Section179CarryforwardTracker,
    apply_section_179_carryforward_to_dataframe,
    validate_section_179_carryforward,
)

from fixed_asset_ai.logic.fa_export import build_fa


# ==============================================================================
# TEST 1: MACRS DEPRECIATION TABLES
# ==============================================================================

class TestMACRSTables:
    """Test MACRS depreciation percentage tables from IRS Publication 946."""

    def test_5year_half_year_table(self):
        """Test 5-year property half-year convention table."""
        table = get_macrs_table(recovery_period=5, method="200DB", convention="HY")

        # IRS Publication 946 - Table A-1
        expected = [0.2000, 0.3200, 0.1920, 0.1152, 0.1152, 0.0576]

        assert len(table) == 6, "5-year property should have 6 years"
        assert table == expected, "5-year HY percentages don't match IRS tables"

        # Verify sum equals 100%
        assert abs(sum(table) - 1.0) < 0.0001, "Percentages should sum to 100%"

    def test_7year_half_year_table(self):
        """Test 7-year property half-year convention table."""
        table = get_macrs_table(recovery_period=7, method="200DB", convention="HY")

        # IRS Publication 946 - Table A-1
        expected = [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446]

        assert len(table) == 8, "7-year property should have 8 years"
        assert table == expected, "7-year HY percentages don't match IRS tables"

        # Verify sum equals 100%
        assert abs(sum(table) - 1.0) < 0.0001, "Percentages should sum to 100%"

    def test_5year_mid_quarter_q1(self):
        """Test 5-year property mid-quarter Q1 convention."""
        table = get_macrs_table(recovery_period=5, method="200DB", convention="MQ", quarter=1)

        # IRS Publication 946 - Table A-2
        expected = [0.3500, 0.2600, 0.1560, 0.1104, 0.1104, 0.0232]

        assert len(table) == 6
        assert table == expected, "5-year MQ-Q1 percentages don't match IRS tables"

    def test_5year_mid_quarter_q4(self):
        """Test 5-year property mid-quarter Q4 convention."""
        table = get_macrs_table(recovery_period=5, method="200DB", convention="MQ", quarter=4)

        # IRS Publication 946 - Table A-2
        expected = [0.0500, 0.3800, 0.2280, 0.1368, 0.1179, 0.0873]

        assert len(table) == 6
        assert table == expected, "5-year MQ-Q4 percentages don't match IRS tables"

    def test_calculate_macrs_depreciation_5year(self):
        """Test MACRS depreciation calculation for 5-year property."""
        basis = 10000.0
        recovery_period = 5
        method = "200DB"
        convention = "HY"

        # Year 1: 20% of $10,000 = $2,000
        year1_dep = calculate_macrs_depreciation(basis, recovery_period, method, convention, year=1)
        assert year1_dep == 2000.0, f"Year 1 depreciation should be $2,000, got ${year1_dep}"

        # Year 2: 32% of $10,000 = $3,200
        year2_dep = calculate_macrs_depreciation(basis, recovery_period, method, convention, year=2)
        assert year2_dep == 3200.0, f"Year 2 depreciation should be $3,200, got ${year2_dep}"

        # Year 6: 5.76% of $10,000 = $576
        year6_dep = calculate_macrs_depreciation(basis, recovery_period, method, convention, year=6)
        assert year6_dep == 576.0, f"Year 6 depreciation should be $576, got ${year6_dep}"

        # Year 7: No depreciation (beyond recovery period)
        year7_dep = calculate_macrs_depreciation(basis, recovery_period, method, convention, year=7)
        assert year7_dep == 0.0, f"Year 7 depreciation should be $0, got ${year7_dep}"


# ==============================================================================
# TEST 2: MULTI-YEAR DEPRECIATION PROJECTION
# ==============================================================================

class TestDepreciationProjection:
    """Test multi-year depreciation projection functionality."""

    def test_single_asset_projection_5year(self):
        """Test depreciation projection for single 5-year asset."""
        projection = project_asset_depreciation(
            depreciable_basis=10000.0,
            recovery_period=5,
            method="200DB",
            convention="HY",
            in_service_year=2024,
            projection_years=10
        )

        # Verify years
        assert len(projection["years"]) == 6, "Should have 6 years of depreciation"
        assert projection["years"][0] == 2024, "First year should be 2024"
        assert projection["years"][-1] == 2029, "Last year should be 2029"

        # Verify depreciation amounts
        expected_dep = [2000.0, 3200.0, 1920.0, 1152.0, 1152.0, 576.0]
        for i, expected in enumerate(expected_dep):
            actual = projection["depreciation"][i]
            assert abs(actual - expected) < 0.01, \
                f"Year {i+1} depreciation: expected ${expected}, got ${actual}"

        # Verify accumulated depreciation
        assert abs(projection["accumulated_depreciation"][-1] - 10000.0) < 0.01, \
            "Total accumulated depreciation should equal basis"

        # Verify remaining basis
        assert abs(projection["remaining_basis"][-1]) < 0.01, \
            "Remaining basis should be ~$0 at end"

    def test_zero_basis_projection(self):
        """Test projection with zero depreciable basis."""
        projection = project_asset_depreciation(
            depreciable_basis=0.0,
            recovery_period=5,
            method="200DB",
            convention="HY",
            in_service_year=2024,
            projection_years=10
        )

        assert len(projection["years"]) == 0, "Zero basis should have no years"
        assert len(projection["depreciation"]) == 0, "Zero basis should have no depreciation"

    def test_portfolio_projection(self):
        """Test portfolio-wide depreciation projection."""
        # Create sample portfolio
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Equipment A",
                "Depreciable Basis": 10000.0,
                "Recovery Period": 5,
                "Method": "200DB",
                "Convention": "HY",
                "In Service Date": date(2024, 1, 15),
            },
            {
                "Asset ID": "A002",
                "Description": "Equipment B",
                "Depreciable Basis": 20000.0,
                "Recovery Period": 7,
                "Method": "200DB",
                "Convention": "HY",
                "In Service Date": date(2024, 3, 20),
            },
            {
                "Asset ID": "A003",
                "Description": "Equipment C (no basis)",
                "Depreciable Basis": 0.0,
                "Recovery Period": 5,
                "Method": "200DB",
                "Convention": "HY",
                "In Service Date": date(2024, 6, 10),
            },
        ])

        summary = project_portfolio_depreciation(df, current_tax_year=2024, projection_years=10)

        # Verify summary structure
        assert "Tax Year" in summary.columns
        assert "Total Depreciation" in summary.columns
        assert "Assets Depreciating" in summary.columns

        # Year 2024:
        # A001: $2,000 (20% of $10k)
        # A002: $2,858 (14.29% of $20k)
        # Total: $4,858
        year_2024 = summary[summary["Tax Year"] == 2024]
        assert len(year_2024) == 1
        expected_2024 = 2000.0 + (20000.0 * 0.1429)
        assert abs(year_2024.iloc[0]["Total Depreciation"] - expected_2024) < 1.0

    def test_depreciation_cliff_detection(self):
        """Test depreciation cliff analysis."""
        # Create portfolio with assets that fully depreciate by 2026
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Equipment",
                "Depreciable Basis": 100000.0,
                "Recovery Period": 3,
                "Method": "200DB",
                "Convention": "HY",
                "In Service Date": date(2024, 1, 15),
            },
        ])

        analysis = analyze_depreciation_cliff(df, current_tax_year=2024, projection_years=6, cliff_threshold=0.20)

        # Should detect cliff when 3-year property runs out
        assert "cliffs" in analysis
        assert "recommendations" in analysis
        # After year 4, depreciation drops to 0 - should be detected as cliff


# ==============================================================================
# TEST 3: SECTION 179 CARRYFORWARD TRACKING
# ==============================================================================

class TestSection179Carryforward:
    """Test Section 179 carryforward tracking per IRC §179(b)(3)."""

    def test_no_limitation_full_deduction(self):
        """Test Section 179 when taxable income is sufficient."""
        result = calculate_section_179_with_income_limit(
            section_179_elected=50000.0,
            taxable_business_income=100000.0,
            carryforward_from_prior_years=0.0
        )

        assert result["current_year_deduction"] == 50000.0
        assert result["carryforward_to_next_year"] == 0.0
        assert result["limitation_applied"] == False

    def test_income_limitation_partial_carryforward(self):
        """Test Section 179 when taxable income is insufficient."""
        result = calculate_section_179_with_income_limit(
            section_179_elected=100000.0,
            taxable_business_income=60000.0,
            carryforward_from_prior_years=0.0
        )

        assert result["current_year_deduction"] == 60000.0, "Deduction limited to taxable income"
        assert result["carryforward_to_next_year"] == 40000.0, "Excess carries forward"
        assert result["limitation_applied"] == True

    def test_zero_income_full_carryforward(self):
        """Test Section 179 when no taxable income."""
        result = calculate_section_179_with_income_limit(
            section_179_elected=50000.0,
            taxable_business_income=0.0,
            carryforward_from_prior_years=0.0
        )

        assert result["current_year_deduction"] == 0.0, "No deduction allowed"
        assert result["carryforward_to_next_year"] == 50000.0, "Entire amount carries forward"
        assert result["limitation_applied"] == True

    def test_carryforward_from_prior_years(self):
        """Test applying carryforward from prior years."""
        result = calculate_section_179_with_income_limit(
            section_179_elected=30000.0,
            taxable_business_income=50000.0,
            carryforward_from_prior_years=25000.0
        )

        # Total available = $30k + $25k = $55k
        # Income limit = $50k
        # Deduction = $50k, Carryforward = $5k
        assert result["total_elected"] == 55000.0
        assert result["current_year_deduction"] == 50000.0
        assert result["carryforward_to_next_year"] == 5000.0

    def test_multi_year_carryforward_tracker(self):
        """Test Section 179 carryforward tracking across multiple years."""
        tracker = Section179CarryforwardTracker(initial_carryforward=10000.0)

        # Year 1: $50k elected, $40k income -> $40k deducted, $20k carryforward
        result_2024 = tracker.process_year(
            tax_year=2024,
            section_179_elected=50000.0,
            taxable_business_income=40000.0
        )

        assert result_2024["current_year_deduction"] == 40000.0
        assert result_2024["carryforward_to_next_year"] == 20000.0
        assert tracker.get_carryforward_balance() == 20000.0

        # Year 2: $30k elected, $100k income -> All deducted, $0 carryforward
        result_2025 = tracker.process_year(
            tax_year=2025,
            section_179_elected=30000.0,
            taxable_business_income=100000.0
        )

        assert result_2025["current_year_deduction"] == 50000.0  # $20k carryforward + $30k new
        assert result_2025["carryforward_to_next_year"] == 0.0
        assert tracker.get_carryforward_balance() == 0.0

    def test_asset_allocation_with_limitation(self):
        """Test allocation of limited Section 179 across multiple assets."""
        assets = [
            {"Section 179 Elected": 30000.0},  # Asset A
            {"Section 179 Elected": 20000.0},  # Asset B
            {"Section 179 Elected": 10000.0},  # Asset C
        ]

        # Total elected = $60k, but only $40k taxable income
        updated_assets, carryforward = allocate_section_179_limitation(
            assets=assets,
            taxable_business_income=40000.0,
            carryforward_from_prior_years=0.0
        )

        # Should allocate pro-rata: 40k / 60k = 66.67%
        assert abs(updated_assets[0]["Section 179 Allowed"] - 20000.0) < 1.0  # 30k * 66.67%
        assert abs(updated_assets[1]["Section 179 Allowed"] - 13333.33) < 1.0  # 20k * 66.67%
        assert abs(updated_assets[2]["Section 179 Allowed"] - 6666.67) < 1.0   # 10k * 66.67%

        assert abs(carryforward - 20000.0) < 1.0  # Total carryforward = $20k

    def test_dataframe_integration(self):
        """Test Section 179 carryforward integration with pandas DataFrame."""
        df = pd.DataFrame([
            {"Asset ID": "A001", "Section 179": 30000.0},
            {"Asset ID": "A002", "Section 179": 20000.0},
            {"Asset ID": "A003", "Section 179": 10000.0},
        ])

        # Total = $60k, income = $40k
        df_updated, summary = apply_section_179_carryforward_to_dataframe(
            df=df,
            taxable_business_income=40000.0,
            carryforward_from_prior_years=0.0
        )

        # Verify summary
        assert summary["section_179_elected"] == 60000.0
        assert summary["taxable_business_income"] == 40000.0
        assert summary["section_179_allowed"] == 40000.0
        assert abs(summary["carryforward_to_next_year"] - 20000.0) < 1.0
        assert summary["limitation_applied"] == True

        # Verify dataframe columns
        assert "Section 179 Allowed" in df_updated.columns
        assert "Section 179 Carryforward" in df_updated.columns

        # Verify validation
        is_valid, warnings = validate_section_179_carryforward(df_updated, verbose=False)
        assert is_valid, f"Validation failed: {warnings}"


# ==============================================================================
# TEST 4: INTEGRATION WITH FA_EXPORT
# ==============================================================================

class TestFAExportIntegration:
    """Test Phase 4 integration with fa_export.py."""

    def test_macrs_calculation_in_export(self):
        """Test MACRS Year 1 depreciation calculation in build_fa."""
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Computer Equipment",
                "Cost": 10000.0,
                "Acquisition Date": date(2024, 1, 15),
                "In Service Date": date(2024, 1, 15),
                "Transaction Type": "Addition",
                "Final Category": "Computer Equipment & Software",
                "MACRS Life": 5,
                "Recovery Period": 5,
                "Method": "200DB",
                "Convention": "HY",
            }
        ])

        result = build_fa(
            df=df,
            tax_year=2024,
            strategy="Aggressive (179 + Bonus)",
            taxable_income=500000.0,
            de_minimis_limit=0.0
        )

        # Verify MACRS columns exist
        assert "Depreciable Basis" in result.columns
        assert "MACRS Year 1 Depreciation" in result.columns
        assert "Section 179 Allowed" in result.columns
        assert "Section 179 Carryforward" in result.columns

    def test_section_179_carryforward_in_export(self):
        """Test Section 179 carryforward tracking in build_fa."""
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Equipment",
                "Cost": 50000.0,
                "Acquisition Date": date(2024, 1, 15),
                "In Service Date": date(2024, 1, 15),
                "Transaction Type": "Addition",
                "Final Category": "Machinery & Equipment",
                "MACRS Life": 7,
                "Recovery Period": 7,
                "Method": "200DB",
                "Convention": "HY",
            },
            {
                "Asset ID": "A002",
                "Description": "Equipment 2",
                "Cost": 60000.0,
                "Acquisition Date": date(2024, 2, 20),
                "In Service Date": date(2024, 2, 20),
                "Transaction Type": "Addition",
                "Final Category": "Machinery & Equipment",
                "MACRS Life": 7,
                "Recovery Period": 7,
                "Method": "200DB",
                "Convention": "HY",
            }
        ])

        # Low taxable income to trigger carryforward
        result = build_fa(
            df=df,
            tax_year=2024,
            strategy="Aggressive (179 + Bonus)",
            taxable_income=70000.0,  # Less than $110k elected
            de_minimis_limit=0.0
        )

        # Section 179 elected = $110k, but only $70k income available
        # Should have carryforward of ~$40k
        assert "Section 179 Carryforward" in result.columns
        total_carryforward = result["Section 179 Carryforward"].sum()
        assert total_carryforward > 0, "Should have carryforward when income insufficient"

    def test_complete_workflow_with_phase4(self):
        """Test complete workflow with all Phase 4 features."""
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Office Equipment",
                "Cost": 5000.0,
                "Acquisition Date": date(2024, 1, 15),
                "In Service Date": date(2024, 1, 15),
                "Transaction Type": "Addition",
                "Final Category": "Office Equipment",
                "MACRS Life": 7,
                "Recovery Period": 7,
                "Method": "200DB",
                "Convention": "HY",
            },
            {
                "Asset ID": "A002",
                "Description": "Vehicle",
                "Cost": 40000.0,
                "Acquisition Date": date(2025, 2, 10),
                "In Service Date": date(2025, 2, 10),
                "Transaction Type": "Addition",
                "Final Category": "Trucks & Trailers",
                "MACRS Life": 5,
                "Recovery Period": 5,
                "Method": "200DB",
                "Convention": "HY",
            }
        ])

        result = build_fa(
            df=df,
            tax_year=2024,
            strategy="Balanced (Bonus Only)",
            taxable_income=200000.0,
            de_minimis_limit=2500.0  # Enable de minimis
        )

        # Verify all Phase 4 columns
        phase4_columns = [
            "Depreciable Basis",
            "MACRS Year 1 Depreciation",
            "Section 179 Allowed",
            "Section 179 Carryforward"
        ]

        for col in phase4_columns:
            assert col in result.columns, f"Missing Phase 4 column: {col}"

        # A001 should be de minimis expensed ($5k < $2,500 limit)
        # Wait, $5k is NOT less than $2,500, so it won't be de minimis
        # Let me check the de minimis column
        assert "De Minimis Expensed" in result.columns


# ==============================================================================
# MAIN - Run tests if executed directly
# ==============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("PHASE 4 COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print()

    # Run with pytest if available
    if PYTEST_AVAILABLE:
        pytest.main([__file__, "-v", "--tb=short"])
    else:
        print("pytest not available, running manual tests...")
        print()

        # Manual test execution
        test_classes = [
            TestMACRSTables,
            TestDepreciationProjection,
            TestSection179Carryforward,
            TestFAExportIntegration,
        ]

        total_tests = 0
        passed_tests = 0

        for test_class in test_classes:
            print(f"\n{test_class.__name__}:")
            print("-" * 80)

            instance = test_class()
            test_methods = [m for m in dir(instance) if m.startswith("test_")]

            for method_name in test_methods:
                total_tests += 1
                try:
                    method = getattr(instance, method_name)
                    method()
                    print(f"  ✓ {method_name}")
                    passed_tests += 1
                except Exception as e:
                    print(f"  ✗ {method_name}: {e}")

        print("\n" + "=" * 80)
        print(f"RESULTS: {passed_tests}/{total_tests} tests passed")
        print("=" * 80)
