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

        # DataFrame-level validations (run first)
        self._validate_duplicates(df)

        for idx, row in df.iterrows():
            row_id = str(row.get("Asset ID", f"Row {idx + 1}"))

            # Core validations
            self._validate_cost(row, row_id)
            self._validate_dates(row, row_id)
            self._validate_description(row, row_id)
            self._validate_transaction_type(row, row_id)
            self._validate_business_use_pct(row, row_id)
            self._validate_business_logic(row, row_id)

        # DataFrame-level validations (run after row validations)
        self._validate_asset_ids_for_fa_cs(df)

        return self.errors

    def _validate_asset_ids_for_fa_cs(self, df: pd.DataFrame):
        """
        Validate Asset IDs for FA CS compatibility.

        CRITICAL: Fixed Asset CS requires Asset # to be NUMERIC ONLY.
        This validation warns users if their Asset IDs contain non-numeric characters.
        The export will auto-generate numeric Asset #s, but this helps users understand
        their original IDs will be preserved separately.
        """
        if "Asset ID" not in df.columns:
            return

        non_numeric_ids = []
        for idx, row in df.iterrows():
            asset_id = row.get("Asset ID")
            if pd.notna(asset_id):
                asset_id_str = str(asset_id).strip()
                # Check if ID is purely numeric
                if asset_id_str and not asset_id_str.replace('.', '').replace('-', '').isdigit():
                    # Has non-numeric characters (letters, special chars)
                    non_numeric_ids.append((idx, asset_id_str))

        if non_numeric_ids:
            # Group by pattern type for better reporting
            has_letters = [aid for _, aid in non_numeric_ids if any(c.isalpha() for c in aid)]
            has_special = [aid for _, aid in non_numeric_ids if any(not c.isalnum() and c not in '.-' for c in aid)]

            sample_ids = [aid for _, aid in non_numeric_ids[:5]]
            self.errors.append(ValidationError(
                "WARNING",
                f"{len(non_numeric_ids)} assets",
                "Asset ID",
                f"FA CS requires numeric-only Asset #s. Found {len(non_numeric_ids)} non-numeric Asset IDs "
                f"(e.g., {', '.join(sample_ids[:3])}). "
                f"AUTO-FIX: Export will generate sequential numeric Asset #s (1, 2, 3...) and preserve "
                f"original IDs in 'Original Asset ID' column for cross-reference.",
                {"count": len(non_numeric_ids), "samples": sample_ids}
            ))

    def _validate_duplicates(self, df: pd.DataFrame):
        """
        Detect duplicate assets that could cause double depreciation.

        CRITICAL: Duplicate Asset IDs cause:
        - Double depreciation deductions (audit risk)
        - Incorrect NBV calculations
        - FA CS import failures
        """
        # Check for duplicate Asset ID
        if "Asset ID" in df.columns:
            asset_ids = df["Asset ID"].dropna()
            if len(asset_ids) > 0:
                duplicates = asset_ids[asset_ids.duplicated(keep=False)]
                if len(duplicates) > 0:
                    dup_values = duplicates.unique()
                    for dup_id in dup_values[:10]:  # Report first 10
                        dup_rows = df[df["Asset ID"] == dup_id].index.tolist()
                        self.errors.append(ValidationError(
                            "CRITICAL", str(dup_id), "Asset ID",
                            f"Duplicate Asset ID found in rows {[r+1 for r in dup_rows]}. "
                            f"FIX: Assign unique Asset IDs to prevent double depreciation.",
                            dup_id
                        ))

        # Check for duplicate descriptions with same cost and date (potential data entry dupes)
        if all(col in df.columns for col in ["Description", "Cost", "In Service Date"]):
            # Create a composite key for duplicate detection
            df_check = df.copy()
            df_check["_dup_key"] = (
                df_check["Description"].astype(str).str.lower().str.strip() + "|" +
                df_check["Cost"].astype(str) + "|" +
                df_check["In Service Date"].astype(str)
            )
            duplicates = df_check[df_check["_dup_key"].duplicated(keep=False)]

            if len(duplicates) > 0:
                dup_keys = duplicates["_dup_key"].unique()
                for key in dup_keys[:5]:  # Report first 5
                    dup_rows = df_check[df_check["_dup_key"] == key].index.tolist()
                    first_row = dup_rows[0]
                    desc = df.iloc[first_row].get("Description", "Unknown")
                    cost = df.iloc[first_row].get("Cost", 0)
                    self.errors.append(ValidationError(
                        "WARNING", f"Rows {[r+1 for r in dup_rows]}", "Duplicate Entry",
                        f"Possible duplicate entries: '{desc}' (${cost:,.2f}) appears in multiple rows. "
                        f"FIX: Verify these are intentional separate assets, not data entry duplicates.",
                        {"rows": [r+1 for r in dup_rows], "description": desc}
                    ))

    def _validate_cost(self, row: pd.Series, row_id: str):
        """Validate cost field."""
        cost = row.get("Cost")
        trans_type = str(row.get("Transaction Type", "")).lower()
        is_disposal = any(x in trans_type for x in ["disposal", "dispose", "sold", "retire"])

        # Check for presence
        if pd.isna(cost) or cost == "":
            severity = "WARNING" if is_disposal else "ERROR"
            self.errors.append(ValidationError(
                severity, row_id, "Cost",
                "Cost is missing or blank - will default to $0. "
                "FIX: Enter the original acquisition cost (for disposals, enter original cost, not proceeds)."
            ))
            return

        # Convert to numeric
        try:
            cost_num = float(cost)
        except (ValueError, TypeError):
            self.errors.append(ValidationError(
                "ERROR", row_id, "Cost",
                f"Cost cannot be converted to number. FIX: Remove currency symbols, commas, or text (e.g., '$1,234.56' -> '1234.56')", cost
            ))
            return

        # CRITICAL: Check for negative costs
        # Note: Disposals should have POSITIVE original cost, and separate proceeds field
        if cost_num < 0:
            if is_disposal:
                self.errors.append(ValidationError(
                    "CRITICAL", row_id, "Cost",
                    f"Disposal has NEGATIVE cost (${cost_num:,.2f}). "
                    f"Cost should be the ORIGINAL COST (positive), not the proceeds. "
                    f"Enter disposal proceeds in the 'Proceeds' or 'Sale Price' field.",
                    cost_num
                ))
            else:
                self.errors.append(ValidationError(
                    "CRITICAL", row_id, "Cost",
                    f"Cost cannot be negative (${cost_num:,.2f}) for additions/transfers. "
                    f"FIX: Enter as positive value, or change Transaction Type to 'Disposal' if this is a sold asset.",
                    cost_num
                ))

        # HIGH PRIORITY: Check for zero-cost assets
        if cost_num == 0:
            if not is_disposal:
                self.errors.append(ValidationError(
                    "WARNING", row_id, "Cost",
                    "$0 cost asset detected. This may be a placeholder or data entry error. "
                    "Zero-cost assets do not generate depreciation."
                ))

        # Check for unreasonable values
        if cost_num > 100_000_000:  # $100M
            self.errors.append(ValidationError(
                "WARNING", row_id, "Cost",
                f"Cost exceeds $100M (${cost_num:,.0f}) - please verify this is correct",
                cost_num
            ))

        # CRITICAL TAX COMPLIANCE: Validate accumulated depreciation doesn't exceed cost
        # IRS rule: Total accumulated depreciation cannot exceed original cost basis
        prior_depreciation = row.get("Tax Prior Depreciation", row.get("Prior Depreciation"))
        if prior_depreciation is not None and not pd.isna(prior_depreciation):
            try:
                prior_dep_num = float(prior_depreciation)

                if prior_dep_num > cost_num:
                    self.errors.append(ValidationError(
                        "CRITICAL", row_id, "Tax Prior Depreciation",
                        f"Accumulated depreciation (${prior_dep_num:,.2f}) EXCEEDS original cost (${cost_num:,.2f}). "
                        f"This violates IRS rules. Maximum accumulated depreciation = original cost. "
                        f"Please verify cost and prior depreciation amounts.",
                        f"Prior Dep: ${prior_dep_num:,.2f} > Cost: ${cost_num:,.2f}"
                    ))
                elif prior_dep_num < 0:
                    self.errors.append(ValidationError(
                        "CRITICAL", row_id, "Tax Prior Depreciation",
                        f"Accumulated depreciation cannot be negative (${prior_dep_num:,.2f})",
                        prior_dep_num
                    ))
            except (ValueError, TypeError):
                # Invalid depreciation value - will be caught by other validators
                pass

        # Check for suspiciously low values for large equipment
        desc = str(row.get("Description", "")).lower()
        if 0 < cost_num < 100 and any(word in desc for word in ["building", "vehicle", "equipment", "machinery"]):
            self.errors.append(ValidationError(
                "WARNING", row_id, "Cost",
                f"Cost (${cost_num:,.2f}) seems unusually low for '{desc}'",
                cost_num
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
                # NOTE: Changed from CRITICAL to WARNING to align with validators.py
                # Future dates are unusual but not necessarily incorrect (e.g., planned acquisitions)
                # They just won't generate depreciation until in service
                self.errors.append(ValidationError(
                    "WARNING", row_id, "In Service Date",
                    f"In-service date ({pis_date_compare}) is in the future. "
                    f"Asset cannot generate depreciation until placed in service. Today's date: {today}",
                    pis_date
                ))

        if acq_date:
            acq_date_compare = acq_date.date() if hasattr(acq_date, 'date') else acq_date
            if acq_date_compare > today:
                # NOTE: Changed from ERROR to WARNING to align with validators.py
                self.errors.append(ValidationError(
                    "WARNING", row_id, "Acquisition Date",
                    f"Acquisition date ({acq_date_compare}) is in the future. "
                    f"Verify this is intended. Today's date: {today}",
                    acq_date
                ))

        # Check for in-service before acquisition
        # NOTE: This is LEGITIMATE in many scenarios:
        #   - Used/demo equipment purchased after already in service
        #   - Lease-to-own (leased equipment, then purchased)
        #   - Trial/rental period before purchase
        #   - Contributed property from partners
        # Changed from ERROR to WARNING to allow export
        if pis_date and acq_date and pis_date < acq_date:
            self.errors.append(ValidationError(
                "WARNING", row_id, "In Service Date",
                f"In-service date ({pis_date}) is before acquisition date ({acq_date}) - "
                f"verify if asset was used/leased before purchase",
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

            # NOTE: Changed broad keywords to be more specific:
            # - "car" matches "card", "carpet", "career" - use "car ", " car"
            # - "van" matches "advantage", "canvas", "relevant" - use " van", "van "
            # - "auto" matches "automatic", "automation" - use "auto ", " auto", "automobile"
            is_likely_listed = (
                "Passenger Automobile" in final_category or
                "Trucks & Trailers" in final_category or
                any(word in desc for word in [
                    "car ", " car", "vehicle", "truck", "suv", " van", "van ",
                    "auto ", " auto", "automobile", "computer", "laptop"
                ])
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
            # Check for None/NaT and convert Timestamp to date before comparison
            if pis_date is not None and not pd.isna(pis_date):
                # Convert pandas Timestamp to date for comparison
                pis_date_obj = pis_date.date() if hasattr(pis_date, 'date') else pis_date
                if pis_date_obj < date(2018, 1, 1):
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
