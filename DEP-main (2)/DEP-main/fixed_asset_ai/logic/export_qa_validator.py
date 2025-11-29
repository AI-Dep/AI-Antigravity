"""
Fixed Asset CS Export Quality Assurance & Validation

Validates export file quality for Fixed Asset CS import and RPA automation.
Checks for:
1. Data format compliance (dates, numbers, text)
2. Required field validation
3. Data consistency
4. RPA compatibility issues
5. Fixed Asset CS import requirements

CRITICAL: This validation MUST pass before RPA processing to prevent
automation failures and data corruption.
"""

import pandas as pd
from datetime import date, datetime
from typing import List, Dict, Tuple, Optional
import re


# ==============================================================================
# FIXED ASSET CS EXPECTED COLUMNS (UPDATED 2025-01-20)
# ==============================================================================
# Based on user testing and FA CS import field mapping

FIXED_ASSET_CS_REQUIRED_COLUMNS = [
    "Asset #",  # Changed from "Asset ID"
    "Description",  # Changed from "Property Description"
    "Date In Service",
    "Tax Cost",  # Changed from "Cost/Basis"
]

FIXED_ASSET_CS_EXPECTED_COLUMNS = [
    "Asset #",  # Changed from "Asset ID"
    "Description",  # Changed from "Property Description"
    "Date In Service",
    "Acquisition Date",
    "Tax Cost",  # Changed from "Cost/Basis"
    "Tax Method",  # Changed from "Method"
    "Tax Life",  # Changed from "Life"
    "Convention",
    "Tax Sec 179 Expensed",  # Changed from "Section 179 Amount"
    "Bonus Amount",
    "Tax Prior Depreciation",  # NEW field
    "Tax Cur Depreciation",  # NEW field
    "Sheet Role",
    "Transaction Type",
]


# ==============================================================================
# VALIDATION ERROR CLASSES
# ==============================================================================

class ExportValidationError:
    """Represents a validation error in the export file."""

    def __init__(self, severity: str, category: str, message: str, row_index: Optional[int] = None, column: Optional[str] = None):
        self.severity = severity  # CRITICAL, ERROR, WARNING
        self.category = category
        self.message = message
        self.row_index = row_index
        self.column = column

    def __str__(self):
        location = ""
        if self.row_index is not None:
            location += f" [Row {self.row_index + 2}]"  # +2 for Excel (1-indexed + header)
        if self.column:
            location += f" [{self.column}]"

        return f"{self.severity}: {self.message}{location}"


# ==============================================================================
# COLUMN STRUCTURE VALIDATION
# ==============================================================================

def validate_column_structure(df: pd.DataFrame) -> List[ExportValidationError]:
    """
    Validate that all required columns exist and are properly named.

    Args:
        df: Export dataframe

    Returns:
        List of validation errors
    """
    errors = []

    # Check required columns
    missing_required = [col for col in FIXED_ASSET_CS_REQUIRED_COLUMNS if col not in df.columns]

    if missing_required:
        errors.append(ExportValidationError(
            severity="CRITICAL",
            category="Column Structure",
            message=f"Missing required columns: {', '.join(missing_required)}"
        ))

    # Check for unexpected column names (typos, spaces, etc.)
    for col in df.columns:
        # Check for leading/trailing spaces
        if col != col.strip():
            errors.append(ExportValidationError(
                severity="ERROR",
                category="Column Structure",
                message=f"Column name has leading/trailing spaces: '{col}'",
                column=col
            ))

        # Check for special characters that might break RPA
        if re.search(r'[^\w\s\(\)\-\$§%/]', col):
            errors.append(ExportValidationError(
                severity="WARNING",
                category="Column Structure",
                message=f"Column name contains special characters: '{col}'",
                column=col
            ))

    return errors


# ==============================================================================
# DATE FORMAT VALIDATION
# ==============================================================================

def validate_date_columns(df: pd.DataFrame) -> List[ExportValidationError]:
    """
    Validate date columns for proper format and consistency.

    Fixed Asset CS expects dates in Excel date format or MM/DD/YYYY string format.

    Args:
        df: Export dataframe

    Returns:
        List of validation errors
    """
    errors = []

    date_columns = ["Date In Service", "Acquisition Date", "Disposal Date"]

    for col in date_columns:
        if col not in df.columns:
            continue

        for idx, val in enumerate(df[col]):
            if pd.isna(val) or val == "" or val is None:
                # Empty dates are OK for some columns
                if col == "Date In Service":
                    # But required for additions
                    trans_type = str(df.iloc[idx].get("Transaction Type", "")).lower()
                    if "addition" in trans_type or ("disposal" not in trans_type and "transfer" not in trans_type):
                        errors.append(ExportValidationError(
                            severity="CRITICAL",
                            category="Date Format",
                            message=f"Missing required in-service date for addition",
                            row_index=idx,
                            column=col
                        ))
                continue

            # Check if it's a proper date type
            if not isinstance(val, (date, datetime, pd.Timestamp)):
                # Try to parse as string
                if isinstance(val, str):
                    # Check for valid date string format
                    date_formats = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]
                    parsed = False

                    for fmt in date_formats:
                        try:
                            datetime.strptime(val, fmt)
                            parsed = True
                            break
                        except ValueError:
                            continue

                    if not parsed:
                        errors.append(ExportValidationError(
                            severity="ERROR",
                            category="Date Format",
                            message=f"Invalid date format: '{val}' (expected MM/DD/YYYY or YYYY-MM-DD)",
                            row_index=idx,
                            column=col
                        ))
                else:
                    errors.append(ExportValidationError(
                        severity="ERROR",
                        category="Date Format",
                        message=f"Invalid date type: {type(val).__name__} (expected date/datetime)",
                        row_index=idx,
                        column=col
                    ))

            # Check for future dates (potential data entry error)
            try:
                if isinstance(val, str):
                    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                        try:
                            val = datetime.strptime(val, fmt).date()
                            break
                        except ValueError:
                            continue

                if isinstance(val, (date, datetime, pd.Timestamp)):
                    val_date = val if isinstance(val, date) else val.date()

                    if val_date > date.today():
                        errors.append(ExportValidationError(
                            severity="WARNING",
                            category="Date Format",
                            message=f"Future date detected: {val_date} (verify data entry)",
                            row_index=idx,
                            column=col
                        ))

                    # Check for unreasonably old dates (before 1950)
                    if val_date.year < 1950:
                        errors.append(ExportValidationError(
                            severity="WARNING",
                            category="Date Format",
                            message=f"Very old date detected: {val_date} (verify data entry)",
                            row_index=idx,
                            column=col
                        ))
            except (ValueError, TypeError, AttributeError):
                pass  # Already caught by format validation

    return errors


# ==============================================================================
# NUMBER FORMAT VALIDATION
# ==============================================================================

def validate_number_columns(df: pd.DataFrame) -> List[ExportValidationError]:
    """
    Validate numeric columns for proper format and consistency.

    Args:
        df: Export dataframe

    Returns:
        List of validation errors
    """
    errors = []

    # Column names must match actual export output from fa_export.py
    number_columns = [
        "Tax Cost",                          # Was "Cost/Basis"
        "Tax Sec 179 Expensed",              # Was "Section 179 Amount"
        "Bonus Amount",
        "Depreciable Basis",
        "Tax Cur Depreciation",              # Was "MACRS Year 1 Depreciation"
        "Tax Prior Depreciation",            # Added for existing assets
        "Section 179 Allowed",
        "Section 179 Carryforward",
        "De Minimis Expensed",
        "§1245 Recapture (Ordinary Income)",
        "§1250 Recapture (Ordinary Income)",
        "Unrecaptured §1250 Gain (25%)",
        "Capital Gain",
        "Capital Loss",
    ]

    for col in number_columns:
        if col not in df.columns:
            continue

        for idx, val in enumerate(df[col]):
            if pd.isna(val) or val == "" or val is None:
                # Empty is OK, will be treated as 0
                continue

            # Check if it's a number
            try:
                float_val = float(val)

                # Check for negative values where not expected
                # Negative values in these columns indicate serious data issues
                if col in ["Tax Cost", "Depreciable Basis", "Tax Cur Depreciation"]:
                    if float_val < 0:
                        errors.append(ExportValidationError(
                            severity="ERROR",  # Changed from WARNING - negative values are errors
                            category="Number Format",
                            message=f"Negative value in {col}: {float_val} (must be >= 0)",
                            row_index=idx,
                            column=col
                        ))

                # Check for unreasonably large values (possible data entry error)
                if float_val > 1_000_000_000:  # $1 billion
                    errors.append(ExportValidationError(
                        severity="WARNING",
                        category="Number Format",
                        message=f"Unusually large value in {col}: ${float_val:,.2f}",
                        row_index=idx,
                        column=col
                    ))

                # Check for NaN or Infinity
                if pd.isna(float_val) or float_val == float('inf') or float_val == float('-inf'):
                    errors.append(ExportValidationError(
                        severity="ERROR",
                        category="Number Format",
                        message=f"Invalid numeric value in {col}: {val}",
                        row_index=idx,
                        column=col
                    ))

            except (ValueError, TypeError):
                errors.append(ExportValidationError(
                    severity="ERROR",
                    category="Number Format",
                    message=f"Non-numeric value in {col}: '{val}'",
                    row_index=idx,
                    column=col
                ))

    return errors


# ==============================================================================
# TEXT FIELD VALIDATION
# ==============================================================================

def validate_text_columns(df: pd.DataFrame) -> List[ExportValidationError]:
    """
    Validate text columns for RPA compatibility.

    Args:
        df: Export dataframe

    Returns:
        List of validation errors
    """
    errors = []

    # Validate Asset # (must be numeric)
    if "Asset #" in df.columns:
        for idx, val in enumerate(df["Asset #"]):
            if pd.isna(val) or val == "" or val is None:
                errors.append(ExportValidationError(
                    severity="CRITICAL",
                    category="Numeric Format",
                    message=f"Missing required Asset #",
                    row_index=idx,
                    column="Asset #"
                ))
                continue

            # Check if numeric
            try:
                numeric_val = pd.to_numeric(val, errors='raise')
                # Check if integer (no decimals)
                if not float(numeric_val).is_integer():
                    errors.append(ExportValidationError(
                        severity="ERROR",
                        category="Numeric Format",
                        message=f"Asset # must be integer (found: {val})",
                        row_index=idx,
                        column="Asset #"
                    ))
            except (ValueError, TypeError):
                errors.append(ExportValidationError(
                    severity="CRITICAL",
                    category="Numeric Format",
                    message=f"Asset # must be numeric (found: {val})",
                    row_index=idx,
                    column="Asset #"
                ))

    # Validate Description (text)
    if "Description" in df.columns:
        for idx, val in enumerate(df["Description"]):
            if pd.isna(val) or val == "" or val is None:
                errors.append(ExportValidationError(
                    severity="WARNING",
                    category="Text Format",
                    message=f"Missing description",
                    row_index=idx,
                    column="Description"
                ))
                continue

            # Convert to string
            str_val = str(val)

            # Check for excessive length (Excel limit is 32,767 characters)
            if len(str_val) > 255:
                errors.append(ExportValidationError(
                    severity="WARNING",
                    category="Text Format",
                    message=f"Very long description ({len(str_val)} characters)",
                    row_index=idx,
                    column="Description"
                ))

            # Check for problematic characters for RPA
            if re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', str_val):
                errors.append(ExportValidationError(
                    severity="ERROR",
                    category="Text Format",
                    message=f"Control characters detected in description",
                    row_index=idx,
                    column="Description"
                ))

    return errors


# ==============================================================================
# DATA CONSISTENCY VALIDATION
# ==============================================================================

def validate_data_consistency(df: pd.DataFrame) -> List[ExportValidationError]:
    """
    Validate data consistency and business logic.

    Args:
        df: Export dataframe

    Returns:
        List of validation errors
    """
    errors = []

    for idx, row in df.iterrows():
        # Get transaction type for context-aware validation
        trans_type = str(row.get("Transaction Type", "")).lower()
        is_existing_asset = "existing" in trans_type

        # Check: Cost = Section 179 + Bonus + Depreciable Basis
        # ONLY for current year additions - existing assets have PRIOR year S179/Bonus already applied
        # Column names must match actual export output from fa_export.py
        if all(col in df.columns for col in ["Tax Cost", "Tax Sec 179 Expensed", "Bonus Amount", "Depreciable Basis"]):
            # Skip this check for existing assets - their depreciable basis reflects ORIGINAL
            # cost minus PRIOR YEAR Section 179 and Bonus, not current year values
            if not is_existing_asset:
                cost = float(row.get("Tax Cost") or 0)
                sec179 = float(row.get("Tax Sec 179 Expensed") or 0)
                bonus = float(row.get("Bonus Amount") or 0)
                dep_basis = float(row.get("Depreciable Basis") or 0)

                expected_dep_basis = max(cost - sec179 - bonus, 0)

                if abs(dep_basis - expected_dep_basis) > 0.01:  # Allow 1 cent rounding
                    errors.append(ExportValidationError(
                        severity="ERROR",
                        category="Data Consistency",
                        message=f"Depreciable Basis mismatch: Expected ${expected_dep_basis:,.2f}, got ${dep_basis:,.2f}",
                        row_index=idx
                    ))

        # Check: Section 179 + Bonus <= Cost
        if all(col in df.columns for col in ["Tax Cost", "Tax Sec 179 Expensed", "Bonus Amount"]):
            cost = float(row.get("Tax Cost") or 0)
            sec179 = float(row.get("Tax Sec 179 Expensed") or 0)
            bonus = float(row.get("Bonus Amount") or 0)

            if sec179 + bonus > cost + 0.01:  # Allow 1 cent rounding
                errors.append(ExportValidationError(
                    severity="ERROR",
                    category="Data Consistency",
                    message=f"Section 179 (${sec179:,.2f}) + Bonus (${bonus:,.2f}) exceeds Cost (${cost:,.2f})",
                    row_index=idx
                ))

        # Check: Section 179 Allowed + Carryforward = Section 179 Expensed
        if all(col in df.columns for col in ["Tax Sec 179 Expensed", "Section 179 Allowed", "Section 179 Carryforward"]):
            amount = float(row.get("Tax Sec 179 Expensed") or 0)
            allowed = float(row.get("Section 179 Allowed") or 0)
            carryforward = float(row.get("Section 179 Carryforward") or 0)

            if abs(allowed + carryforward - amount) > 0.01:
                errors.append(ExportValidationError(
                    severity="ERROR",
                    category="Data Consistency",
                    message=f"Section 179: Allowed (${allowed:,.2f}) + Carryforward (${carryforward:,.2f}) != Expensed (${amount:,.2f})",
                    row_index=idx
                ))

        # Check: Tax Method/Tax Life/Convention should be empty for disposals/transfers
        trans_type = str(row.get("Transaction Type", "")).lower()
        if "disposal" in trans_type or "transfer" in trans_type:
            if row.get("Tax Method") and str(row.get("Tax Method")).strip() != "":
                errors.append(ExportValidationError(
                    severity="WARNING",
                    category="Data Consistency",
                    message=f"Disposal/Transfer should not have Tax Method populated",
                    row_index=idx
                ))

    return errors


# ==============================================================================
# RPA COMPATIBILITY VALIDATION
# ==============================================================================

def validate_rpa_compatibility(df: pd.DataFrame) -> List[ExportValidationError]:
    """
    Validate file is compatible with RPA automation.

    Args:
        df: Export dataframe

    Returns:
        List of validation errors
    """
    errors = []

    # Check for duplicate Asset # values
    if "Asset #" in df.columns:
        asset_nums = df["Asset #"].dropna()
        duplicates = asset_nums[asset_nums.duplicated()].unique()

        if len(duplicates) > 0:
            errors.append(ExportValidationError(
                severity="CRITICAL",
                category="RPA Compatibility",
                message=f"Duplicate Asset # values detected: {', '.join(str(x) for x in duplicates[:5])}"
            ))

    # Check for empty rows
    empty_rows = df[df.isnull().all(axis=1)]
    if len(empty_rows) > 0:
        errors.append(ExportValidationError(
            severity="WARNING",
            category="RPA Compatibility",
            message=f"Empty rows detected: {len(empty_rows)} rows"
        ))

    # Check for mixed data types in columns
    for col in df.columns:
        types = df[col].dropna().apply(type).unique()
        if len(types) > 2:  # More than 2 types suggests inconsistency
            errors.append(ExportValidationError(
                severity="WARNING",
                category="RPA Compatibility",
                message=f"Mixed data types in column '{col}': {[t.__name__ for t in types]}",
                column=col
            ))

    return errors


# ==============================================================================
# COMPREHENSIVE VALIDATION
# ==============================================================================

def validate_fixed_asset_cs_export(
    df: pd.DataFrame,
    verbose: bool = True
) -> Tuple[bool, List[ExportValidationError], Dict[str, int]]:
    """
    Comprehensive validation of Fixed Asset CS export file.

    Args:
        df: Export dataframe
        verbose: Print validation report

    Returns:
        Tuple of (is_valid, errors, summary)
        - is_valid: True if no critical errors
        - errors: List of all validation errors
        - summary: Dict with count by severity
    """
    all_errors = []

    # Run all validations
    all_errors.extend(validate_column_structure(df))
    all_errors.extend(validate_date_columns(df))
    all_errors.extend(validate_number_columns(df))
    all_errors.extend(validate_text_columns(df))
    all_errors.extend(validate_data_consistency(df))
    all_errors.extend(validate_rpa_compatibility(df))

    # Categorize by severity
    critical = [e for e in all_errors if e.severity == "CRITICAL"]
    errors = [e for e in all_errors if e.severity == "ERROR"]
    warnings = [e for e in all_errors if e.severity == "WARNING"]

    summary = {
        "CRITICAL": len(critical),
        "ERROR": len(errors),
        "WARNING": len(warnings),
        "TOTAL": len(all_errors)
    }

    is_valid = len(critical) == 0 and len(errors) == 0

    if verbose:
        print("\n" + "=" * 80)
        print("FIXED ASSET CS EXPORT QUALITY VALIDATION")
        print("=" * 80)
        print(f"Total rows: {len(df)}")
        print(f"Total columns: {len(df.columns)}")
        print()

        if len(all_errors) == 0:
            print("✅ VALIDATION PASSED - Export file is PERFECT QUALITY")
            print("   Ready for Fixed Asset CS import and RPA automation")
        else:
            print(f"⚠️  VALIDATION ISSUES FOUND: {len(all_errors)} total")
            print()

            if critical:
                print(f"🔴 CRITICAL ({len(critical)}) - MUST FIX BEFORE RPA:")
                for e in critical[:10]:  # Show first 10
                    print(f"   {e}")
                if len(critical) > 10:
                    print(f"   ... and {len(critical) - 10} more")
                print()

            if errors:
                print(f"❌ ERRORS ({len(errors)}) - SHOULD FIX:")
                for e in errors[:10]:
                    print(f"   {e}")
                if len(errors) > 10:
                    print(f"   ... and {len(errors) - 10} more")
                print()

            if warnings:
                print(f"⚠️  WARNINGS ({len(warnings)}) - REVIEW:")
                for e in warnings[:5]:
                    print(f"   {e}")
                if len(warnings) > 5:
                    print(f"   ... and {len(warnings) - 5} more")
                print()

            if is_valid:
                print("✅ NO CRITICAL/ERROR ISSUES - Safe for RPA (review warnings)")
            else:
                print("❌ CRITICAL/ERROR ISSUES DETECTED - NOT SAFE FOR RPA")

        print("=" * 80)
        print()

    return is_valid, all_errors, summary


def export_validation_report(
    df: pd.DataFrame,
    output_path: str = "export_validation_report.xlsx"
):
    """
    Export detailed validation report to Excel.

    Args:
        df: Export dataframe
        output_path: Path to save validation report
    """
    is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=False)

    # Create validation report dataframe
    report_data = []

    for error in errors:
        report_data.append({
            "Severity": error.severity,
            "Category": error.category,
            "Message": error.message,
            "Row": error.row_index + 2 if error.row_index is not None else "",
            "Column": error.column or ""
        })

    report_df = pd.DataFrame(report_data)

    # Create summary dataframe
    summary_df = pd.DataFrame([
        {"Severity": "CRITICAL", "Count": summary["CRITICAL"]},
        {"Severity": "ERROR", "Count": summary["ERROR"]},
        {"Severity": "WARNING", "Count": summary["WARNING"]},
        {"Severity": "TOTAL", "Count": summary["TOTAL"]},
    ])

    # Export to Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        if len(report_df) > 0:
            report_df.to_excel(writer, sheet_name='Validation Errors', index=False)
        else:
            pd.DataFrame([{"Status": "✅ PERFECT QUALITY - No issues found"}]).to_excel(
                writer, sheet_name='Validation Errors', index=False
            )

    print(f"✓ Validation report exported to: {output_path}")

    return is_valid, errors, summary
