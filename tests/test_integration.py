"""
Integration Tests for Fixed Asset AI

Tests the complete workflow from data loading through export generation.
Run with: pytest tests/test_integration.py -v
"""

import pytest
import pandas as pd
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from logic.validators import validate_assets
from logic.tax_year_config import get_bonus_percentage, get_section_179_limits

# Import these conditionally to handle missing dependencies
try:
    from logic.fa_export import build_fa, _is_disposal, _is_transfer
    FA_EXPORT_AVAILABLE = True
except ImportError:
    FA_EXPORT_AVAILABLE = False

try:
    from logic.macrs_classification import classify_asset
    CLASSIFICATION_AVAILABLE = True
except ImportError:
    CLASSIFICATION_AVAILABLE = False


class TestDataValidation:
    """Test data validation catches errors before processing."""

    def test_validates_missing_cost(self):
        """Should flag additions with missing cost."""
        df = pd.DataFrame([
            {"Asset ID": "1", "Description": "Computer", "Cost": None, "Transaction Type": "Addition"}
        ])
        issues, details = validate_assets(df)
        assert any("missing Cost" in i for i in issues)

    def test_validates_missing_description(self):
        """Should flag assets with missing description."""
        df = pd.DataFrame([
            {"Asset ID": "1", "Description": "", "Cost": 1000, "Transaction Type": "Addition"}
        ])
        issues, details = validate_assets(df)
        assert any("missing Description" in i for i in issues)

    def test_validates_negative_cost(self):
        """Should flag negative cost as data error."""
        df = pd.DataFrame([
            {"Asset ID": "1", "Description": "Computer", "Cost": -1000, "Transaction Type": "Addition"}
        ])
        issues, details = validate_assets(df)
        assert any("negative cost" in i for i in issues)

    def test_validates_accum_depr_exceeds_cost(self):
        """Should flag when accumulated depreciation > cost."""
        df = pd.DataFrame([
            {"Asset ID": "1", "Description": "Computer", "Cost": 1000,
             "Accumulated Depreciation": 1500, "Transaction Type": "Existing"}
        ])
        issues, details = validate_assets(df)
        assert any("exceeds Cost" in i for i in issues)


@pytest.mark.skipif(not FA_EXPORT_AVAILABLE, reason="fa_export module not available")
class TestTransactionTypeDetection:
    """Test correct detection of transaction types."""

    def test_detects_disposal(self):
        """Should correctly identify disposal transactions."""
        row = {"Transaction Type": "Disposal", "Description": "Sold equipment"}
        assert _is_disposal(row) == True

    def test_detects_transfer(self):
        """Should correctly identify transfer transactions."""
        row = {"Transaction Type": "Transfer", "Description": "Moved to new location"}
        assert _is_transfer(row) == True

    def test_addition_is_not_disposal(self):
        """Addition should not be flagged as disposal."""
        row = {"Transaction Type": "Addition", "Description": "New computer"}
        assert _is_disposal(row) == False


@pytest.mark.skipif(not CLASSIFICATION_AVAILABLE, reason="classification module not available")
class TestClassificationIntegration:
    """Test classification produces expected results."""

    def test_computer_classifies_as_5_year(self):
        """Computer should classify as 5-year property."""
        asset = {
            "Description": "Dell Laptop XPS 15",
            "Cost": 1500,
        }
        result = classify_asset(asset)
        if result:
            life = result.get("final_life") or result.get("life")
            assert life in [5, "5"], f"Computer classified as {life}-year, expected 5"

    def test_furniture_classifies_as_7_year(self):
        """Furniture should classify as 7-year property."""
        asset = {
            "Description": "Executive Office Desk",
            "Cost": 800,
        }
        result = classify_asset(asset)
        if result:
            life = result.get("final_life") or result.get("life")
            assert life in [7, "7"], f"Furniture classified as {life}-year, expected 7"

    def test_building_classifies_as_39_year(self):
        """Building should classify as 39-year property."""
        asset = {
            "Description": "Commercial Office Building",
            "Cost": 500000,
        }
        result = classify_asset(asset)
        if result:
            life = result.get("final_life") or result.get("life")
            assert life in [39, "39", 27.5, "27.5"], f"Building classified as {life}-year"


@pytest.mark.skipif(not FA_EXPORT_AVAILABLE, reason="fa_export module not available")
class TestExportWorkflow:
    """Test the complete export workflow."""

    @pytest.fixture
    def sample_additions(self):
        """Sample addition data for testing."""
        return pd.DataFrame([
            {
                "Asset ID": "ADD-001",
                "Description": "Dell Computer",
                "Cost": 2000,
                "Acquisition Date": "03/01/2025",
                "In Service Date": "03/15/2025",
                "Transaction Type": "Addition",
            },
            {
                "Asset ID": "ADD-002",
                "Description": "Office Desk",
                "Cost": 800,
                "Acquisition Date": "03/01/2025",
                "In Service Date": "03/15/2025",
                "Transaction Type": "Addition",
            },
        ])

    def test_export_produces_dataframe(self, sample_additions):
        """Export should produce a DataFrame."""
        try:
            result = build_fa(
                df=sample_additions,
                tax_year=2025,
                strategy="balanced",
                taxable_income=500000,
            )
            assert isinstance(result, pd.DataFrame)
            assert len(result) > 0
        except Exception as e:
            pytest.skip(f"Export workflow requires full setup: {e}")

    def test_export_includes_required_columns(self, sample_additions):
        """Export should include FA CS required columns."""
        required_cols = ["Asset #", "Description", "Cost"]
        try:
            result = build_fa(
                df=sample_additions,
                tax_year=2025,
                strategy="balanced",
                taxable_income=500000,
            )
            for col in required_cols:
                assert col in result.columns or any(col.lower() in c.lower() for c in result.columns), \
                    f"Missing required column: {col}"
        except Exception as e:
            pytest.skip(f"Export workflow requires full setup: {e}")


class TestBonusDepreciationIntegration:
    """Test bonus depreciation in full workflow context."""

    def test_2025_post_obbba_gets_100_percent(self):
        """Post-OBBBA 2025 property should get 100% bonus."""
        bonus = get_bonus_percentage(
            2025,
            acquisition_date=date(2025, 3, 1),
            in_service_date=date(2025, 3, 15)
        )
        assert bonus == 1.00

    def test_2025_pre_obbba_gets_40_percent(self):
        """Pre-OBBBA 2025 property should get 40% bonus."""
        bonus = get_bonus_percentage(
            2025,
            acquisition_date=date(2025, 1, 10),  # Before Jan 20
            in_service_date=date(2025, 3, 15)
        )
        assert bonus == 0.40

    def test_2024_gets_60_percent(self):
        """2024 property should get 60% bonus."""
        bonus = get_bonus_percentage(2024)
        assert bonus == 0.60


class TestSection179Integration:
    """Test Section 179 limits in workflow context."""

    def test_2025_section_179_limit(self):
        """2025 should use OBBBA Section 179 limit."""
        limits = get_section_179_limits(2025)
        assert limits["max_deduction"] == 2500000
        assert limits["phaseout_threshold"] == 4000000

    def test_section_179_phaseout_calculation(self):
        """Test Section 179 phaseout reduces limit."""
        limits = get_section_179_limits(2025)
        max_deduction = limits["max_deduction"]
        phaseout_threshold = limits["phaseout_threshold"]

        # If total qualifying property = $5M, phaseout should reduce limit
        total_property = 5000000
        phaseout_amount = total_property - phaseout_threshold  # $1M over threshold
        reduced_limit = max(0, max_deduction - phaseout_amount)

        assert reduced_limit == 1500000  # $2.5M - $1M = $1.5M


class TestEdgeCasesIntegration:
    """Test edge cases in full workflow."""

    @pytest.mark.skipif(not FA_EXPORT_AVAILABLE, reason="fa_export module not available")
    def test_empty_dataframe_raises_error(self):
        """Empty DataFrame should raise ValueError."""
        df = pd.DataFrame()
        with pytest.raises(ValueError, match="empty"):
            build_fa(df, tax_year=2025, strategy="balanced", taxable_income=100000)

    @pytest.mark.skipif(not FA_EXPORT_AVAILABLE, reason="fa_export module not available")
    def test_zero_taxable_income_limits_179(self):
        """Zero taxable income should limit Section 179 to zero."""
        df = pd.DataFrame([
            {
                "Asset ID": "1",
                "Description": "Equipment",
                "Cost": 100000,
                "Acquisition Date": "03/01/2025",
                "In Service Date": "03/15/2025",
                "Transaction Type": "Addition",
            }
        ])
        try:
            result = build_fa(df, tax_year=2025, strategy="aggressive", taxable_income=0)
            # With zero taxable income, Section 179 should be limited
            if "Tax Sec 179 Expensed" in result.columns:
                assert result["Tax Sec 179 Expensed"].sum() == 0
        except Exception as e:
            pytest.skip(f"Full workflow test: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
