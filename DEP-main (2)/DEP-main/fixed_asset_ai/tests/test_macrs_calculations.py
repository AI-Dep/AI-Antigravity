"""
Unit Tests for MACRS Depreciation Calculations

These tests verify that MACRS tables and calculations match IRS Publication 946.
Run with: pytest tests/test_macrs_calculations.py -v
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.macrs_tables import (
    calculate_macrs_depreciation,
    calculate_disposal_year_depreciation,
    get_macrs_table,
    MACRS_200DB_5Y_HY,
    MACRS_200DB_7Y_HY,
    MACRS_150DB_15Y_HY,
)
from logic.tax_year_config import (
    get_bonus_percentage,
    get_section_179_limits,
)
from logic.recapture import (
    calculate_section_1245_recapture,
    calculate_section_1250_recapture,
)


class TestMACRSTables:
    """Test MACRS table values match IRS Publication 946."""

    def test_5_year_200db_hy_totals_100_percent(self):
        """5-year MACRS table should sum to 100%."""
        total = sum(MACRS_200DB_5Y_HY)
        assert abs(total - 1.0) < 0.001, f"5-year table sums to {total}, expected 1.0"

    def test_7_year_200db_hy_totals_100_percent(self):
        """7-year MACRS table should sum to 100%."""
        total = sum(MACRS_200DB_7Y_HY)
        assert abs(total - 1.0) < 0.001, f"7-year table sums to {total}, expected 1.0"

    def test_15_year_150db_hy_totals_100_percent(self):
        """15-year MACRS table should sum to 100%."""
        total = sum(MACRS_150DB_15Y_HY)
        assert abs(total - 1.0) < 0.001, f"15-year table sums to {total}, expected 1.0"

    def test_5_year_year1_rate(self):
        """5-year property Year 1 rate should be 20% (HY convention)."""
        assert MACRS_200DB_5Y_HY[0] == 0.20, f"Year 1 rate is {MACRS_200DB_5Y_HY[0]}, expected 0.20"

    def test_7_year_year1_rate(self):
        """7-year property Year 1 rate should be 14.29% (HY convention)."""
        assert abs(MACRS_200DB_7Y_HY[0] - 0.1429) < 0.0001, f"Year 1 rate is {MACRS_200DB_7Y_HY[0]}, expected 0.1429"

    def test_15_year_year1_rate(self):
        """15-year property Year 1 rate should be 5% (HY convention, 150DB)."""
        assert MACRS_150DB_15Y_HY[0] == 0.05, f"Year 1 rate is {MACRS_150DB_15Y_HY[0]}, expected 0.05"


class TestMACRSCalculations:
    """Test MACRS depreciation calculations."""

    def test_5_year_computer_year1(self):
        """$10,000 computer: Year 1 depreciation = $2,000 (20%)."""
        depr = calculate_macrs_depreciation(
            basis=10000,
            recovery_period=5,
            method="200DB",
            convention="HY",
            year=1
        )
        assert depr == 2000.0, f"Year 1 depreciation is {depr}, expected 2000"

    def test_7_year_furniture_year1(self):
        """$10,000 furniture: Year 1 depreciation = $1,429 (14.29%)."""
        depr = calculate_macrs_depreciation(
            basis=10000,
            recovery_period=7,
            method="200DB",
            convention="HY",
            year=1
        )
        assert abs(depr - 1429.0) < 1, f"Year 1 depreciation is {depr}, expected 1429"

    def test_zero_basis_returns_zero(self):
        """Zero basis should return zero depreciation."""
        depr = calculate_macrs_depreciation(
            basis=0,
            recovery_period=5,
            method="200DB",
            convention="HY",
            year=1
        )
        assert depr == 0.0

    def test_negative_basis_returns_zero(self):
        """Negative basis should return zero depreciation."""
        depr = calculate_macrs_depreciation(
            basis=-1000,
            recovery_period=5,
            method="200DB",
            convention="HY",
            year=1
        )
        assert depr == 0.0

    def test_year_beyond_recovery_returns_zero(self):
        """Year beyond recovery period should return zero."""
        depr = calculate_macrs_depreciation(
            basis=10000,
            recovery_period=5,
            method="200DB",
            convention="HY",
            year=10  # 5-year property only has 6 years
        )
        assert depr == 0.0


class TestDisposalYearDepreciation:
    """Test disposal year depreciation calculations."""

    def test_hy_disposal_is_half_year(self):
        """HY convention disposal should be half of normal year."""
        # Full year 3 for 5-year property = 19.20%
        full_year = calculate_macrs_depreciation(
            basis=10000, recovery_period=5, method="200DB", convention="HY", year=3
        )

        disposal_year = calculate_disposal_year_depreciation(
            basis=10000,
            recovery_period=5,
            method="200DB",
            convention="HY",
            year_of_recovery=3
        )

        # Disposal should be 50% of full year
        assert abs(disposal_year - full_year * 0.5) < 0.01


class TestBonusDepreciation:
    """Test bonus depreciation percentages per TCJA and OBBBA (enacted July 4, 2025)."""

    def test_2024_bonus_is_60_percent(self):
        """2024 bonus depreciation should be 60% under TCJA phase-down."""
        bonus_pct = get_bonus_percentage(2024)
        assert bonus_pct == 0.60, f"2024 bonus is {bonus_pct}, expected 0.60"

    def test_2023_bonus_is_80_percent(self):
        """2023 bonus depreciation should be 80% under TCJA phase-down."""
        bonus_pct = get_bonus_percentage(2023)
        assert bonus_pct == 0.80, f"2023 bonus is {bonus_pct}, expected 0.80"

    def test_2025_bonus_is_100_percent_post_obbba(self):
        """2025 bonus depreciation should be 100% for post-OBBBA acquisitions."""
        from datetime import date
        # Property acquired and placed in service after Jan 19, 2025
        bonus_pct = get_bonus_percentage(
            2025,
            acquisition_date=date(2025, 2, 1),
            in_service_date=date(2025, 2, 15)
        )
        assert bonus_pct == 1.00, f"2025 post-OBBBA bonus is {bonus_pct}, expected 1.00"

    def test_2025_bonus_is_40_percent_pre_obbba(self):
        """2025 bonus for pre-OBBBA acquisitions should be 40%."""
        from datetime import date
        # Property acquired BEFORE Jan 20, 2025
        bonus_pct = get_bonus_percentage(
            2025,
            acquisition_date=date(2025, 1, 15),  # Before Jan 20
            in_service_date=date(2025, 3, 1)
        )
        assert bonus_pct == 0.40, f"2025 pre-OBBBA bonus is {bonus_pct}, expected 0.40"

    def test_2026_bonus_is_100_percent_post_obbba(self):
        """2026+ bonus should be 100% for OBBBA-eligible property (permanent)."""
        from datetime import date
        bonus_pct = get_bonus_percentage(
            2026,
            acquisition_date=date(2026, 1, 1),
            in_service_date=date(2026, 1, 15)
        )
        assert bonus_pct == 1.00, f"2026 post-OBBBA bonus is {bonus_pct}, expected 1.00"


class TestSection179Limits:
    """Test Section 179 limits per OBBBA (enacted July 4, 2025)."""

    def test_2024_section_179_limit(self):
        """2024 Section 179 limit should be $1,220,000 (pre-OBBBA)."""
        limits = get_section_179_limits(2024)
        assert limits["max_deduction"] == 1220000

    def test_2024_section_179_phaseout(self):
        """2024 Section 179 phaseout threshold should be $3,050,000 (pre-OBBBA)."""
        limits = get_section_179_limits(2024)
        assert limits["phaseout_threshold"] == 3050000

    def test_2025_section_179_limit_obbba(self):
        """2025 Section 179 limit should be $2,500,000 under OBBBA."""
        limits = get_section_179_limits(2025)
        assert limits["max_deduction"] == 2500000, f"2025 limit is {limits['max_deduction']}, expected 2500000"

    def test_2025_section_179_phaseout_obbba(self):
        """2025 Section 179 phaseout should be $4,000,000 under OBBBA."""
        limits = get_section_179_limits(2025)
        assert limits["phaseout_threshold"] == 4000000, f"2025 phaseout is {limits['phaseout_threshold']}, expected 4000000"


class TestRecaptureCalculations:
    """Test depreciation recapture calculations."""

    def test_section_1245_full_recapture(self):
        """Section 1245: All depreciation recaptured when gain >= depreciation."""
        result = calculate_section_1245_recapture(
            cost=10000,
            accumulated_depreciation=6000,  # Includes all depreciation
            proceeds=8000,
            section_179_taken=0,
            bonus_taken=0,
            accum_includes_179_bonus=True
        )

        # Adjusted basis = 10000 - 6000 = 4000
        # Gain = 8000 - 4000 = 4000
        # Recapture = min(6000, 4000) = 4000
        assert result["adjusted_basis"] == 4000
        assert result["gain_on_sale"] == 4000
        assert result["section_1245_recapture"] == 4000
        assert result["capital_gain"] == 0

    def test_section_1245_partial_recapture(self):
        """Section 1245: Partial recapture when gain < depreciation."""
        result = calculate_section_1245_recapture(
            cost=10000,
            accumulated_depreciation=8000,
            proceeds=5000,
            section_179_taken=0,
            bonus_taken=0,
            accum_includes_179_bonus=True
        )

        # Adjusted basis = 10000 - 8000 = 2000
        # Gain = 5000 - 2000 = 3000
        # Recapture = min(8000, 3000) = 3000
        assert result["adjusted_basis"] == 2000
        assert result["gain_on_sale"] == 3000
        assert result["section_1245_recapture"] == 3000

    def test_section_1245_no_recapture_on_loss(self):
        """Section 1245: No recapture when there's a loss."""
        result = calculate_section_1245_recapture(
            cost=10000,
            accumulated_depreciation=5000,
            proceeds=3000,  # Sold at loss
            section_179_taken=0,
            bonus_taken=0,
            accum_includes_179_bonus=True
        )

        # Adjusted basis = 10000 - 5000 = 5000
        # Gain = 3000 - 5000 = -2000 (loss)
        # Recapture = 0
        assert result["adjusted_basis"] == 5000
        assert result["gain_on_sale"] == -2000
        assert result["section_1245_recapture"] == 0
        assert result["capital_loss"] == 2000

    def test_section_1245_no_double_counting(self):
        """Section 1245: No double counting when accum_includes_179_bonus=True."""
        # When accum_includes_179_bonus=True, section_179_taken and bonus_taken
        # should be ignored to prevent double counting
        result = calculate_section_1245_recapture(
            cost=10000,
            accumulated_depreciation=6000,  # Already includes 179/bonus
            proceeds=8000,
            section_179_taken=3000,  # Should be ignored
            bonus_taken=2000,  # Should be ignored
            accum_includes_179_bonus=True
        )

        # Total depreciation should be 6000, NOT 6000+3000+2000=11000
        assert result["total_depreciation"] == 6000


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_basis(self):
        """Very small basis should calculate correctly."""
        depr = calculate_macrs_depreciation(
            basis=0.01,  # 1 cent
            recovery_period=5,
            method="200DB",
            convention="HY",
            year=1
        )
        assert depr == 0.002  # 20% of 1 cent

    def test_very_large_basis(self):
        """Very large basis should calculate correctly."""
        depr = calculate_macrs_depreciation(
            basis=1000000000,  # $1 billion
            recovery_period=5,
            method="200DB",
            convention="HY",
            year=1
        )
        assert depr == 200000000  # $200 million (20%)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
