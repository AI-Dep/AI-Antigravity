"""
Unit tests for the validators module.

Tests validation logic including:
- Duplicate detection
- Date chronology
- Critical issue detection
- Required field validation
"""

import pytest
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from logic.validators import (
    validate_assets,
    get_critical_issues,
    has_critical_issues,
    format_validation_summary,
)
from logic.parse_utils import validate_date_chronology, parse_date


class TestDuplicateDetection:
    """Test duplicate Asset ID detection."""

    def test_detects_duplicate_asset_ids(self):
        """Should detect duplicate Asset IDs."""
        df = pd.DataFrame([
            {"Asset ID": "A001", "Description": "Computer 1", "Cost": 1000},
            {"Asset ID": "A001", "Description": "Computer 2", "Cost": 1500},  # Duplicate
            {"Asset ID": "A002", "Description": "Desk", "Cost": 500},
        ])

        issues, details = validate_assets(df)

        assert any("Duplicate Asset ID" in i for i in issues)
        assert "duplicate_asset_ids" in details
        assert len(details["duplicate_asset_ids"]) == 2

    def test_ignores_empty_asset_ids(self):
        """Should not flag empty Asset IDs as duplicates."""
        df = pd.DataFrame([
            {"Asset ID": "", "Description": "Computer 1", "Cost": 1000},
            {"Asset ID": "", "Description": "Computer 2", "Cost": 1500},
            {"Asset ID": "A001", "Description": "Desk", "Cost": 500},
        ])

        issues, details = validate_assets(df)

        # Should NOT flag empty IDs as duplicates
        assert not any("Duplicate Asset ID" in i for i in issues)

    def test_no_duplicates_when_unique(self):
        """Should not flag unique Asset IDs."""
        df = pd.DataFrame([
            {"Asset ID": "A001", "Description": "Computer 1", "Cost": 1000},
            {"Asset ID": "A002", "Description": "Computer 2", "Cost": 1500},
            {"Asset ID": "A003", "Description": "Desk", "Cost": 500},
        ])

        issues, details = validate_assets(df)

        assert not any("Duplicate Asset ID" in i for i in issues)


class TestDateChronology:
    """Test date chronology validation."""

    def test_valid_chronology(self):
        """Dates in correct order should pass."""
        acq = parse_date("2024-01-01")
        pis = parse_date("2024-02-01")
        disp = parse_date("2024-12-31")

        is_valid, errors = validate_date_chronology(acq, pis, disp)

        assert is_valid is True
        assert len(errors) == 0

    def test_acquisition_after_in_service(self):
        """Acquisition after in-service should fail."""
        acq = parse_date("2024-06-01")
        pis = parse_date("2024-01-01")  # Before acquisition

        is_valid, errors = validate_date_chronology(acq, pis, None)

        assert is_valid is False
        assert len(errors) == 1
        assert "Acquisition Date" in errors[0]

    def test_in_service_after_disposal(self):
        """In-service after disposal should fail."""
        acq = parse_date("2024-01-01")
        pis = parse_date("2024-12-01")
        disp = parse_date("2024-06-01")  # Before in-service

        is_valid, errors = validate_date_chronology(acq, pis, disp)

        assert is_valid is False
        assert len(errors) >= 1

    def test_validates_disposal_before_pis(self):
        """Disposal before in-service should be caught."""
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Computer",
                "Cost": 1000,
                "Acquisition Date": "2024-01-01",
                "In Service Date": "2024-06-01",
                "Disposal Date": "2024-03-01",  # Before in-service
            },
        ])

        issues, details = validate_assets(df)

        assert any("Disposal Date earlier than In-Service" in i for i in issues)


class TestCriticalIssueDetection:
    """Test critical issue filtering."""

    def test_critical_prefix_detected(self):
        """Issues starting with CRITICAL: should be detected."""
        issues = [
            "CRITICAL: Accumulated Depreciation exceeds Cost",
            "WARNING: Some minor issue",
            "INFO: Just informational",
        ]

        critical = get_critical_issues(issues)

        assert len(critical) == 1
        assert "CRITICAL:" in critical[0]

    def test_duplicate_asset_id_is_critical(self):
        """Duplicate Asset IDs should be treated as critical."""
        issues = [
            "CRITICAL: Duplicate Asset IDs detected (2 IDs, 4 total rows).",
            "WARNING: Some warning",
        ]

        critical = get_critical_issues(issues)

        assert len(critical) == 1

    def test_has_critical_issues_true(self):
        """has_critical_issues should return True when critical issues exist."""
        issues = ["CRITICAL: Something bad", "WARNING: Minor thing"]

        assert has_critical_issues(issues) is True

    def test_has_critical_issues_false(self):
        """has_critical_issues should return False when no critical issues."""
        issues = ["WARNING: Minor thing", "INFO: Just info"]

        assert has_critical_issues(issues) is False


class TestAccumulatedDepreciationValidation:
    """Test accumulated depreciation > cost validation."""

    def test_flags_accum_exceeds_cost(self):
        """Should flag when accumulated depreciation exceeds cost."""
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Computer",
                "Cost": 1000,
                "Accumulated Depreciation": 1500,  # Exceeds cost
            },
        ])

        issues, details = validate_assets(df)

        assert any("Accumulated Depreciation exceeds Cost" in i for i in issues)
        assert "accum_depr_exceeds_cost" in details

    def test_valid_accum_depreciation(self):
        """Should not flag valid accumulated depreciation."""
        df = pd.DataFrame([
            {
                "Asset ID": "A001",
                "Description": "Computer",
                "Cost": 1000,
                "Accumulated Depreciation": 500,  # Valid
            },
        ])

        issues, details = validate_assets(df)

        assert not any("Accumulated Depreciation exceeds Cost" in i for i in issues)


class TestEmptyDataframe:
    """Test empty dataframe handling."""

    def test_empty_dataframe_flagged(self):
        """Empty dataframe should be flagged as critical."""
        df = pd.DataFrame()

        issues, details = validate_assets(df)

        assert any("Empty dataframe" in i for i in issues)


class TestFormatValidationSummary:
    """Test validation summary formatting."""

    def test_no_issues_message(self):
        """No issues should return success message."""
        summary = format_validation_summary([], {})

        assert "No issues found" in summary

    def test_summary_with_issues(self):
        """Summary should include all issue types."""
        issues = [
            "CRITICAL: Major problem",
            "WARNING: Minor issue",
            "INFO: Just info",
        ]

        summary = format_validation_summary(issues, {})

        # Check that summary contains counts
        assert "Critical: 1" in summary or "CRITICAL" in summary
        assert "Warnings: 1" in summary or "WARNING" in summary
        assert "Info: 1" in summary or "INFO" in summary
        assert "Total Issues: 3" in summary
