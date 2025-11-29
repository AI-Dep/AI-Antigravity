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
# FIXED ASSET CS EXPECTED COLUMNS (STANDARD IMPORT FORMAT)
# ==============================================================================

FIXED_ASSET_CS_REQUIRED_COLUMNS = [
    "Asset ID",
    "Property Description",
    "Date In Service",
    "Cost/Basis",
]

FIXED_ASSET_CS_EXPECTED_COLUMNS = [
    "Asset ID",
    "Property Description",
    "Date In Service",
    "Acquisition Date",
    "Cost/Basis",
    "Method",
    "Life",
    "Convention",
    "Section 179 Amount",
    "Bonus Amount",
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
            except:
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

    number_columns = [
        "Cost/Basis",
        "Section 179 Amount",
        "Bonus Amount",
        "Depreciable Basis",
        "MACRS Year 1 Depreciation",
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
                if col in ["Cost/Basis", "Depreciable Basis", "MACRS Year 1 Depreciation"]:
                    if float_val < 0:
                        errors.append(ExportValidationError(
                            severity="WARNING",
                            category="Number Format",
                            message=f"Negative value in {col}: {float_val}",
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

    text_columns = ["Asset ID", "Property Description"]

    for col in text_columns:
        if col not in df.columns:
            continue

        for idx, val in enumerate(df[col]):
            if pd.isna(val) or val == "" or val is None:
                if col == "Asset ID":
                    errors.append(ExportValidationError(
                        severity="CRITICAL",
                        category="Text Format",
                        message=f"Missing required Asset ID",
                        row_index=idx,
                        column=col
                    ))
                elif col == "Property Description":
                    errors.append(ExportValidationError(
                        severity="WARNING",
                        category="Text Format",
                        message=f"Missing property description",
                        row_index=idx,
                        column=col
                    ))
                continue

            # Convert to string
            str_val = str(val)

            # Check for excessive length (Excel limit is 32,767 characters)
            if len(str_val) > 255:
                errors.append(ExportValidationError(
                    severity="WARNING",
                    category="Text Format",
                    message=f"Very long text in {col} ({len(str_val)} characters)",
                    row_index=idx,
                    column=col
                ))

            # Check for problematic characters for RPA
            # Control characters, null bytes, etc.
            if re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', str_val):
                errors.append(ExportValidationError(
                    severity="ERROR",
                    category="Text Format",
                    message=f"Control characters detected in {col}",
                    row_index=idx,
                    column=col
                ))

            # Check for Asset ID format (should be consistent)
            if col == "Asset ID":
                # Warn if Asset ID contains spaces or special characters
                if ' ' in str_val:
                    errors.append(ExportValidationError(
                        severity="WARNING",
                        category="Text Format",
                        message=f"Asset ID contains spaces: '{str_val}'",
                        row_index=idx,
                        column=col
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
        # Check: Cost = Section 179 + Bonus + Depreciable Basis
        if all(col in df.columns for col in ["Cost/Basis", "Section 179 Amount", "Bonus Amount", "Depreciable Basis"]):
            cost = float(row.get("Cost/Basis") or 0)
            sec179 = float(row.get("Section 179 Amount") or 0)
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
        if all(col in df.columns for col in ["Cost/Basis", "Section 179 Amount", "Bonus Amount"]):
            cost = float(row.get("Cost/Basis") or 0)
            sec179 = float(row.get("Section 179 Amount") or 0)
            bonus = float(row.get("Bonus Amount") or 0)

            if sec179 + bonus > cost + 0.01:  # Allow 1 cent rounding
                errors.append(ExportValidationError(
                    severity="ERROR",
                    category="Data Consistency",
                    message=f"Section 179 (${sec179:,.2f}) + Bonus (${bonus:,.2f}) exceeds Cost (${cost:,.2f})",
                    row_index=idx
                ))

        # Check: Section 179 Allowed + Carryforward = Section 179 Amount
        if all(col in df.columns for col in ["Section 179 Amount", "Section 179 Allowed", "Section 179 Carryforward"]):
            amount = float(row.get("Section 179 Amount") or 0)
            allowed = float(row.get("Section 179 Allowed") or 0)
            carryforward = float(row.get("Section 179 Carryforward") or 0)

            if abs(allowed + carryforward - amount) > 0.01:
                errors.append(ExportValidationError(
                    severity="ERROR",
                    category="Data Consistency",
                    message=f"Section 179: Allowed (${allowed:,.2f}) + Carryforward (${carryforward:,.2f}) != Amount (${amount:,.2f})",
                    row_index=idx
                ))

        # Check: Method/Life/Convention should be empty for disposals/transfers
        trans_type = str(row.get("Transaction Type", "")).lower()
        if "disposal" in trans_type or "transfer" in trans_type:
            if row.get("Method") and str(row.get("Method")).strip() != "":
                errors.append(ExportValidationError(
                    severity="WARNING",
                    category="Data Consistency",
                    message=f"Disposal/Transfer should not have Method populated",
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

    # Check for duplicate Asset IDs
    if "Asset ID" in df.columns:
        asset_ids = df["Asset ID"].dropna()
        duplicates = asset_ids[asset_ids.duplicated()].unique()

        if len(duplicates) > 0:
            errors.append(ExportValidationError(
                severity="CRITICAL",
                category="RPA Compatibility",
                message=f"Duplicate Asset IDs detected: {', '.join(str(x) for x in duplicates[:5])}"
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
