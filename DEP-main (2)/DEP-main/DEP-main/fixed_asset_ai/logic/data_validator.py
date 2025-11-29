# fixed_asset_ai/logic/data_validator.py
"""
Data Validation Module

Comprehensive validation of asset data before processing.
Prevents crashes, nonsense output, and catches data quality issues.
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
import pandas as pd


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, severity: str, row_id: str, field: str, message: str, value: Any = None):
        """
        Args:
            severity: 'CRITICAL', 'ERROR', 'WARNING'
            row_id: Asset ID or row number
            field: Field name with error
            message: Description of the error
            value: The problematic value (optional)
        """
        self.severity = severity
        self.row_id = row_id
        self.field = field
        self.message = message
        self.value = value

    def __str__(self):
        val_str = f" (value: {self.value})" if self.value is not None else ""
        return f"[{self.severity}] Row {self.row_id}, {self.field}: {self.message}{val_str}"

    def to_dict(self):
        return {
            "severity": self.severity,
            "row_id": self.row_id,
            "field": self.field,
            "message": self.message,
            "value": str(self.value) if self.value is not None else None
        }


class AssetDataValidator:
    """Validates asset data for tax compliance and data integrity."""

    def __init__(self, tax_year: int):
        """
        Args:
            tax_year: Current tax year for date validations
        """
        self.tax_year = tax_year
        self.errors: List[ValidationError] = []

    def validate_dataframe(self, df: pd.DataFrame) -> List[ValidationError]:
        """
        Validate entire dataframe.

        Args:
            df: Asset dataframe

        Returns:
            List of ValidationError objects
        """
        self.errors = []

        for idx, row in df.iterrows():
            row_id = str(row.get("Asset ID", f"Row {idx + 1}"))

            # Core validations
            self._validate_cost(row, row_id)
            self._validate_dates(row, row_id)
            self._validate_description(row, row_id)
            self._validate_transaction_type(row, row_id)
            self._validate_business_use_pct(row, row_id)
            self._validate_business_logic(row, row_id)

        return self.errors

    def _validate_cost(self, row: pd.Series, row_id: str):
        """Validate cost field."""
        cost = row.get("Cost")

        # Check for presence
        if pd.isna(cost) or cost == "":
            self.errors.append(ValidationError(
                "WARNING", row_id, "Cost",
                "Cost is missing or blank - will default to $0"
            ))
            return

        # Convert to numeric
        try:
            cost_num = float(cost)
        except (ValueError, TypeError):
            self.errors.append(ValidationError(
                "ERROR", row_id, "Cost",
                f"Cost cannot be converted to number", cost
            ))
            return

        # Check for negative (disposals may have negative proceeds but not cost)
        if cost_num < 0:
            trans_type = str(row.get("Transaction Type", "")).lower()
            if "disposal" not in trans_type:
                self.errors.append(ValidationError(
                    "ERROR", row_id, "Cost",
                    "Cost cannot be negative for additions/transfers", cost_num
                ))

        # Check for unreasonable values
        if cost_num > 100_000_000:  # $100M
            self.errors.append(ValidationError(
                "WARNING", row_id, "Cost",
                "Cost exceeds $100M - please verify this is correct", cost_num
            ))

        # Check for suspiciously low values for large equipment
        desc = str(row.get("Description", "")).lower()
        if cost_num < 100 and any(word in desc for word in ["building", "vehicle", "equipment"]):
            self.errors.append(ValidationError(
                "WARNING", row_id, "Cost",
                f"Cost seems unusually low for description: '{desc}'", cost_num
            ))

    def _validate_dates(self, row: pd.Series, row_id: str):
        """Validate date fields."""
        from .parse_utils import parse_date

        in_service = row.get("In Service Date")
        acquisition = row.get("Acquisition Date")

        # Parse dates
        pis_date = parse_date(in_service) if in_service else None
        acq_date = parse_date(acquisition) if acquisition else None

        # Check for future dates
        today = date.today()

        # Convert dates to comparable format (handle pandas Timestamp)
        if pis_date:
            pis_date_compare = pis_date.date() if hasattr(pis_date, 'date') else pis_date
            if pis_date_compare > today:
                self.errors.append(ValidationError(
                    "ERROR", row_id, "In Service Date",
                    "In-service date is in the future - not allowed", pis_date
                ))

        if acq_date:
            acq_date_compare = acq_date.date() if hasattr(acq_date, 'date') else acq_date
            if acq_date_compare > today:
                self.errors.append(ValidationError(
                    "WARNING", row_id, "Acquisition Date",
                    "Acquisition date is in the future", acq_date
                ))

        # Check for in-service before acquisition
        if pis_date and acq_date and pis_date < acq_date:
            self.errors.append(ValidationError(
                "ERROR", row_id, "In Service Date",
                f"In-service date ({pis_date}) is before acquisition date ({acq_date})",
                {"in_service": pis_date, "acquisition": acq_date}
            ))

        # Check for dates way in the past (likely data entry errors)
        if pis_date and pis_date.year < 1900:
            self.errors.append(ValidationError(
                "ERROR", row_id, "In Service Date",
                "In-service date is before 1900 - likely data error", pis_date
            ))

        # Check for missing in-service date (required for depreciation)
        trans_type = str(row.get("Transaction Type", "")).lower()
        if not pis_date and "addition" in trans_type:
            self.errors.append(ValidationError(
                "WARNING", row_id, "In Service Date",
                "Missing in-service date for addition - required for depreciation calculation"
            ))

    def _validate_description(self, row: pd.Series, row_id: str):
        """Validate description field."""
        desc = row.get("Description")

        if pd.isna(desc) or str(desc).strip() == "":
            self.errors.append(ValidationError(
                "WARNING", row_id, "Description",
                "Description is missing - may impact classification accuracy"
            ))
            return

        desc_str = str(desc).strip()

        # Check for suspiciously short descriptions
        if len(desc_str) < 3:
            self.errors.append(ValidationError(
                "WARNING", row_id, "Description",
                "Description is very short - may impact classification", desc_str
            ))

        # Check for placeholder text
        placeholders = ["tbd", "to be determined", "unknown", "n/a", "na", "xxx", "test"]
        if desc_str.lower() in placeholders:
            self.errors.append(ValidationError(
                "WARNING", row_id, "Description",
                f"Description appears to be placeholder text: '{desc_str}'"
            ))

    def _validate_transaction_type(self, row: pd.Series, row_id: str):
        """Validate transaction type."""
        trans_type = row.get("Transaction Type")

        if not trans_type or pd.isna(trans_type):
            self.errors.append(ValidationError(
                "WARNING", row_id, "Transaction Type",
                "Transaction type not specified - will default to 'addition'"
            ))
            return

        valid_types = ["addition", "disposal", "transfer"]
        trans_type_lower = str(trans_type).lower()

        if not any(vt in trans_type_lower for vt in valid_types):
            self.errors.append(ValidationError(
                "WARNING", row_id, "Transaction Type",
                f"Unrecognized transaction type: '{trans_type}'", trans_type
            ))

    def _validate_business_use_pct(self, row: pd.Series, row_id: str):
        """
        Validate business use percentage for listed property.

        CRITICAL: IRC §280F requires >50% business use for listed property
        to qualify for Section 179, bonus depreciation, and MACRS.
        """
        # Try to get business use percentage
        business_use_pct = row.get("Business Use %")
        if pd.isna(business_use_pct) or business_use_pct == "":
            # No business use % specified - this is OK if not listed property
            # Listed property check will be done in fa_export.py
            return

        # Parse percentage
        try:
            if isinstance(business_use_pct, str):
                business_use_pct = business_use_pct.strip().rstrip('%')

            pct = float(business_use_pct)

            # If value is >1, assume it's in percentage form (e.g., 75 instead of 0.75)
            if pct > 1:
                pct = pct / 100.0

            # Validate range
            if pct < 0 or pct > 1:
                self.errors.append(ValidationError(
                    "ERROR", row_id, "Business Use %",
                    f"Business use percentage must be between 0% and 100%", business_use_pct
                ))
                return

            # Check for listed property indicators
            desc = str(row.get("Description", "")).lower()
            final_category = str(row.get("Final Category", ""))

            is_likely_listed = (
                "Passenger Automobile" in final_category or
                "Trucks & Trailers" in final_category or
                any(word in desc for word in ["car", "vehicle", "truck", "suv", "van", "auto", "computer", "laptop"])
            )

            if is_likely_listed and pct <= 0.50:
                self.errors.append(ValidationError(
                    "CRITICAL", row_id, "Business Use %",
                    f"Listed property with ≤50% business use ({pct:.0%}). "
                    "IRC §280F: No Section 179/bonus allowed. MUST use ADS (Alternative Depreciation System).",
                    pct
                ))
            elif is_likely_listed and pct < 0.60:
                self.errors.append(ValidationError(
                    "WARNING", row_id, "Business Use %",
                    f"Listed property with {pct:.0%} business use. "
                    "Qualifies for Section 179/bonus (>50%), but close to threshold. Verify documentation.",
                    pct
                ))

        except (ValueError, TypeError):
            self.errors.append(ValidationError(
                "ERROR", row_id, "Business Use %",
                f"Cannot parse business use percentage", business_use_pct
            ))

    def _validate_business_logic(self, row: pd.Series, row_id: str):
        """Validate business logic rules."""
        from .parse_utils import parse_date

        # QIP date validation
        final_category = str(row.get("Final Category", "")).upper()
        if "QIP" in final_category:
            pis_date = parse_date(row.get("In Service Date"))
            if pis_date and pis_date < date(2018, 1, 1):
                self.errors.append(ValidationError(
                    "ERROR", row_id, "Final Category",
                    "QIP classification only valid for assets placed in service after 12/31/2017",
                    {"category": final_category, "date": pis_date}
                ))

        # Land should not have depreciation info
        if "LAND" in final_category and "IMPROVEMENT" not in final_category:
            # Check if MACRS Life or Method has a value (handle pandas NA)
            # CRITICAL: Check pd.notna() separately to avoid pd.NA boolean evaluation
            macrs_life = row.get("MACRS Life")
            method = row.get("Method")

            has_macrs_life = False
            if pd.notna(macrs_life):
                if macrs_life != "" and macrs_life != 0:
                    has_macrs_life = True

            has_method = False
            if pd.notna(method):
                if method != "":
                    has_method = True

            if has_macrs_life or has_method:
                self.errors.append(ValidationError(
                    "WARNING", row_id, "Final Category",
                    "Land is not depreciable - MACRS life and method should be empty"
                ))

        # Check disposal with no proceeds
        trans_type = str(row.get("Transaction Type", "")).lower()
        if "disposal" in trans_type:
            # Handle pandas NA when checking proceeds
            # CRITICAL: Check pd.isna() separately to avoid pd.NA boolean evaluation
            proceeds = row.get("Proceeds")
            if pd.isna(proceeds):
                proceeds = row.get("Sale Price")
            elif proceeds == "" or proceeds == 0:
                proceeds = row.get("Sale Price")

            # Check if proceeds is still empty/zero/NA
            has_proceeds = False
            if pd.notna(proceeds):
                if proceeds != "" and proceeds != 0:
                    has_proceeds = True

            if not has_proceeds:
                self.errors.append(ValidationError(
                    "WARNING", row_id, "Proceeds",
                    "Disposal has no proceeds/sale price - verify if abandonment/writeoff"
                ))

    def get_errors_by_severity(self, severity: str) -> List[ValidationError]:
        """Get errors of a specific severity."""
        return [e for e in self.errors if e.severity == severity]

    def has_critical_errors(self) -> bool:
        """Check if there are any CRITICAL errors."""
        return any(e.severity == "CRITICAL" for e in self.errors)

    def has_errors(self) -> bool:
        """Check if there are any ERROR level issues."""
        return any(e.severity == "ERROR" for e in self.errors)

    def get_summary(self) -> Dict[str, int]:
        """Get count summary by severity."""
        return {
            "CRITICAL": len(self.get_errors_by_severity("CRITICAL")),
            "ERROR": len(self.get_errors_by_severity("ERROR")),
            "WARNING": len(self.get_errors_by_severity("WARNING")),
            "TOTAL": len(self.errors)
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert errors to DataFrame for display."""
        if not self.errors:
            return pd.DataFrame(columns=["Severity", "Row", "Field", "Message", "Value"])

        return pd.DataFrame([e.to_dict() for e in self.errors])


def validate_asset_data(df: pd.DataFrame, tax_year: int) -> tuple[List[ValidationError], bool]:
    """
    Validate asset dataframe.

    Args:
        df: Asset dataframe
        tax_year: Current tax year

    Returns:
        Tuple of (errors_list, should_stop_processing)
        should_stop_processing is True if CRITICAL errors found
    """
    validator = AssetDataValidator(tax_year)
    errors = validator.validate_dataframe(df)

    should_stop = validator.has_critical_errors()

    return errors, should_stop
