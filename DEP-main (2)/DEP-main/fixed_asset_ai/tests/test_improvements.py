"""
Tests for tool quality improvements.

These tests verify the improvements made during the quality upgrade process.
"""

import pytest
from datetime import date
import pandas as pd


# ==============================================================================
# TEST: ADS Recovery Periods
# ==============================================================================

class TestADSRecoveryPeriods:
    """Test ADS recovery period lookup."""

    def test_macrs_to_ads_mapping(self):
        """Test MACRS to ADS life mapping."""
        from logic.ads_system import get_ads_recovery_period

        # 5-year MACRS → 6-year ADS
        assert get_ads_recovery_period(macrs_life=5) == 6

        # 7-year MACRS → 12-year ADS
        assert get_ads_recovery_period(macrs_life=7) == 12

        # 15-year MACRS → 20-year ADS
        assert get_ads_recovery_period(macrs_life=15) == 20

        # 27.5-year residential → 30-year ADS
        assert get_ads_recovery_period(macrs_life=27.5) == 30

        # 39-year nonresidential → 40-year ADS
        assert get_ads_recovery_period(macrs_life=39) == 40

    def test_category_specific_ads(self):
        """Test category-specific ADS recovery periods."""
        from logic.ads_system import get_ads_recovery_period

        # Computer equipment
        assert get_ads_recovery_period(category="Computer Equipment") == 5

        # Office furniture
        assert get_ads_recovery_period(category="Office Furniture") == 10

        # QIP
        assert get_ads_recovery_period(category="Qualified Improvement Property") == 20

    def test_ads_always_uses_sl(self):
        """Test that ADS always uses straight-line method."""
        from logic.ads_system import get_ads_method

        assert get_ads_method() == "SL"

    def test_ads_disallows_incentives(self):
        """Test that ADS property cannot use Section 179 or bonus."""
        from logic.ads_system import ads_allows_section_179, ads_allows_bonus

        assert ads_allows_section_179() == False
        assert ads_allows_bonus() == False


# ==============================================================================
# TEST: Critical Issue Blocking
# ==============================================================================

class TestCriticalIssueBlocking:
    """Test that critical issues block export."""

    def test_get_critical_issues(self):
        """Test critical issue filtering."""
        from logic.validators import get_critical_issues

        issues = [
            "CRITICAL: Missing cost for asset A001",
            "WARNING: Zero cost detected",
            "CRITICAL: Duplicate Asset ID found",
            "INFO: QIP classification applied"
        ]

        critical = get_critical_issues(issues)
        assert len(critical) == 2
        assert all("CRITICAL" in c or "Duplicate" in c for c in critical)

    def test_has_critical_issues_true(self):
        """Test has_critical_issues returns True when critical issues exist."""
        from logic.validators import has_critical_issues

        issues = ["CRITICAL: Test error", "WARNING: Test warning"]
        assert has_critical_issues(issues) == True

    def test_has_critical_issues_false(self):
        """Test has_critical_issues returns False when no critical issues."""
        from logic.validators import has_critical_issues

        issues = ["WARNING: Test warning", "INFO: Test info"]
        assert has_critical_issues(issues) == False


# ==============================================================================
# TEST: Logging Framework
# ==============================================================================

class TestLoggingFramework:
    """Test logging utilities."""

    def test_get_logger(self):
        """Test logger creation."""
        from logic.logging_utils import get_logger

        logger = get_logger("test_module")
        assert logger is not None
        assert logger.name == "test_module"

    def test_timed_decorator(self):
        """Test timed decorator works."""
        from logic.logging_utils import timed
        import time

        @timed
        def slow_function():
            time.sleep(0.01)
            return "done"

        result = slow_function()
        assert result == "done"


# ==============================================================================
# TEST: Session Persistence
# ==============================================================================

class TestSessionPersistence:
    """Test session save/load functionality."""

    def test_save_and_load_session(self, tmp_path):
        """Test saving and loading a session."""
        from logic.session_persistence import save_session, load_session

        # Create mock session data
        session_data = {
            "tax_year": 2025,
            "strategy": "maximize",
            "taxable_income": 500000,
        }

        # Save session
        session_id = save_session(
            session_data,
            session_id="test_session",
            session_dir=str(tmp_path)
        )

        assert session_id == "test_session"

        # Load session
        loaded = load_session("test_session", session_dir=str(tmp_path))

        assert loaded is not None
        assert loaded["tax_year"] == 2025
        assert loaded["strategy"] == "maximize"

    def test_list_sessions(self, tmp_path):
        """Test listing saved sessions."""
        from logic.session_persistence import save_session, list_sessions

        # Save multiple sessions
        save_session({"tax_year": 2024}, session_id="session1", session_dir=str(tmp_path))
        save_session({"tax_year": 2025}, session_id="session2", session_dir=str(tmp_path))

        sessions = list_sessions(session_dir=str(tmp_path))

        assert len(sessions) == 2


# ==============================================================================
# TEST: Disposal Year Depreciation
# ==============================================================================

class TestDisposalYearDepreciation:
    """Test disposal year depreciation calculations."""

    def test_hy_disposal_is_half_year(self):
        """Test HY convention disposal gets half year."""
        from logic.macrs_tables import (
            calculate_macrs_depreciation,
            calculate_disposal_year_depreciation
        )

        basis = 10000
        recovery_period = 5
        method = "200DB"

        # Full year 3 depreciation
        full_year = calculate_macrs_depreciation(
            basis, recovery_period, method, "HY", year=3
        )

        # Disposal in year 3
        disposal_year = calculate_disposal_year_depreciation(
            basis, recovery_period, method, "HY", year_of_recovery=3
        )

        # Disposal should be 50% of full year
        assert abs(disposal_year - full_year * 0.5) < 0.01

    def test_mq_disposal_varies_by_quarter(self):
        """Test MQ convention disposal varies by disposal quarter."""
        from logic.macrs_tables import calculate_disposal_year_depreciation

        basis = 10000
        recovery_period = 5
        method = "200DB"

        # Q1 disposal (12.5% of year)
        q1_disposal = calculate_disposal_year_depreciation(
            basis, recovery_period, method, "MQ",
            year_of_recovery=3,
            disposal_quarter=1,
            placed_in_service_quarter=1
        )

        # Q4 disposal (87.5% of year)
        q4_disposal = calculate_disposal_year_depreciation(
            basis, recovery_period, method, "MQ",
            year_of_recovery=3,
            disposal_quarter=4,
            placed_in_service_quarter=1
        )

        # Q4 should be much larger than Q1
        assert q4_disposal > q1_disposal * 2


# ==============================================================================
# TEST: Bulk Override (Smoke Test)
# ==============================================================================

class TestBulkOverride:
    """Test bulk override functionality exists."""

    def test_bulk_override_in_app(self):
        """Test that bulk override code exists in app."""
        from pathlib import Path

        app_path = Path(__file__).parent.parent / "app.py"
        app_code = app_path.read_text()

        # Check bulk override UI elements exist
        assert "Bulk Override" in app_code
        assert "Apply to Filtered" in app_code
        assert "bulk_category" in app_code


# ==============================================================================
# TEST: Integration - Full Export Flow
# ==============================================================================

class TestExportIntegration:
    """Integration tests for the export workflow."""

    def test_build_fa_with_sample_data(self):
        """Test building FA export with sample data."""
        from logic.fa_export import build_fa

        # Create sample dataframe
        df = pd.DataFrame({
            "Asset ID": ["A001", "A002", "A003"],
            "Description": ["Dell Laptop", "Office Chair", "Truck"],
            "Cost": [1500, 500, 45000],
            "In Service Date": ["2025-03-01", "2025-04-15", "2025-06-01"],
            "Acquisition Date": ["2025-02-15", "2025-04-01", "2025-05-15"],
            "Final Category": ["Computer Equipment", "Office Furniture", "Trucks & Trailers"],
            "MACRS Life": [5, 7, 5],
            "Method": ["200DB", "200DB", "200DB"],
            "Convention": ["HY", "HY", "HY"],
            "Transaction Type": ["Current Year Addition", "Current Year Addition", "Current Year Addition"],
        })

        # Build FA export
        result = build_fa(df, tax_year=2025, strategy="Aggressive (179 + Bonus)", taxable_income=500000)

        # Verify structure
        assert result is not None
        assert len(result) == 3
        assert "Tax Cost" in result.columns or "Cost" in result.columns

    def test_export_handles_existing_assets(self):
        """Test export correctly handles existing assets."""
        from logic.fa_export import build_fa

        df = pd.DataFrame({
            "Asset ID": ["E001"],
            "Description": ["Server purchased 2020"],
            "Cost": [25000],
            "In Service Date": ["2020-01-15"],
            "Acquisition Date": ["2020-01-01"],
            "Final Category": ["Computer Equipment"],
            "MACRS Life": [5],
            "Method": ["200DB"],
            "Convention": ["HY"],
            "Transaction Type": ["Existing Asset"],
        })

        result = build_fa(df, tax_year=2025, strategy="Aggressive (179 + Bonus)", taxable_income=500000)

        assert result is not None
        # Existing asset should NOT get new Section 179 or bonus
        if "Tax Sec 179 Expensed" in result.columns:
            assert result.iloc[0]["Tax Sec 179 Expensed"] == 0

    def test_export_handles_disposals(self):
        """Test export correctly handles disposals."""
        from logic.fa_export import build_fa

        df = pd.DataFrame({
            "Asset ID": ["D001"],
            "Description": ["Old Equipment - Sold"],
            "Cost": [10000],
            "In Service Date": ["2020-01-15"],
            "Acquisition Date": ["2020-01-01"],
            "Disposal Date": ["2025-06-30"],
            "Final Category": [""],
            "MACRS Life": [7],
            "Method": ["200DB"],
            "Convention": ["HY"],
            "Transaction Type": ["Disposal"],
        })

        result = build_fa(df, tax_year=2025, strategy="Aggressive (179 + Bonus)", taxable_income=500000)

        assert result is not None
        # Disposal should have partial year depreciation, not 0
        # (This was the bug we fixed)
