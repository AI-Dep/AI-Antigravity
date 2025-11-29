"""
Comprehensive Test: Realistic Asset Schedule Processing
Tests the full pipeline: loading, classification, validation, and export
"""

import sys
import os
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the modules we need to test
from fixed_asset_ai.logic.sheet_loader import build_unified_dataframe
from fixed_asset_ai.logic.macrs_classification import classify_asset, load_rules, load_overrides
from fixed_asset_ai.logic.transaction_classifier import classify_all_transactions, validate_transaction_classification
from fixed_asset_ai.logic.validators import validate_assets
from fixed_asset_ai.logic.data_validator import AssetDataValidator
from fixed_asset_ai.logic.fa_export import export_fa_excel, build_fa

# Test file path
TEST_FILE = Path("test_data/Acme_Manufacturing_2024_Assets.xlsx")
TAX_YEAR = 2024
CLIENT_ID = "Acme_Manufacturing"

# Results tracking
results = {
    "tests_passed": 0,
    "tests_failed": 0,
    "warnings": [],
    "errors": [],
    "classification_results": [],
}

def print_header(title):
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)

def print_subheader(title):
    print(f"\n--- {title} ---")

def test_pass(test_name, details=""):
    results["tests_passed"] += 1
    print(f"  ✅ PASS: {test_name}")
    if details:
        print(f"     {details}")

def test_fail(test_name, details=""):
    results["tests_failed"] += 1
    results["errors"].append(f"{test_name}: {details}")
    print(f"  ❌ FAIL: {test_name}")
    if details:
        print(f"     {details}")

def test_warn(test_name, details=""):
    results["warnings"].append(f"{test_name}: {details}")
    print(f"  ⚠️  WARN: {test_name}")
    if details:
        print(f"     {details}")

# =============================================================================
# TEST 1: FILE LOADING
# =============================================================================
def test_file_loading():
    print_header("TEST 1: FILE LOADING")

    try:
        # Load Excel file into sheets dict first
        xl = pd.ExcelFile(TEST_FILE)
        sheets = {}
        for sheet_name in xl.sheet_names:
            sheets[sheet_name] = pd.read_excel(xl, sheet_name=sheet_name, header=None)

        print(f"    Loaded {len(sheets)} sheets: {', '.join(sheets.keys())}")

        # Test loading the Excel file
        df = build_unified_dataframe(sheets)

        if df is not None and len(df) > 0:
            test_pass("Excel file loaded successfully", f"{len(df)} total rows loaded")
        else:
            test_fail("Excel file loading", "DataFrame is empty or None")
            return None

        # Check expected columns (unified dataframe uses lowercase)
        expected_cols = ["asset_id", "description", "cost", "in_service_date"]
        missing_cols = [c for c in expected_cols if c not in df.columns]

        if not missing_cols:
            test_pass("Required columns detected", f"Found: {', '.join(expected_cols)}")
        else:
            test_fail("Required columns", f"Missing: {', '.join(missing_cols)}")

        # Check sheet roles were detected
        if "sheet_role" in df.columns:
            roles = df["sheet_role"].value_counts()
            test_pass("Sheet roles detected", f"Roles: {dict(roles)}")
        else:
            test_warn("Sheet roles", "sheet_role column not found")

        return df

    except Exception as e:
        test_fail("File loading exception", str(e))
        import traceback
        traceback.print_exc()
        return None

# =============================================================================
# TEST 2: TRANSACTION CLASSIFICATION
# =============================================================================
def test_transaction_classification(df):
    print_header("TEST 2: TRANSACTION TYPE CLASSIFICATION")

    if df is None:
        test_fail("Transaction classification", "No DataFrame to test")
        return None

    try:
        # The unified dataframe already has transaction_type from sheet_loader
        # We need to normalize column names for the transaction classifier
        df_normalized = df.copy()

        # Map lowercase columns to expected format
        col_mapping = {
            "asset_id": "Asset ID",
            "description": "Description",
            "client_category": "Client Category",
            "cost": "Cost",
            "acquisition_date": "Acquisition Date",
            "in_service_date": "In Service Date",
            "disposal_date": "Disposal Date",
            "location": "Location",
            "department": "Department",
            "business_use_pct": "Business Use %",
            "proceeds": "Proceeds",
            "accumulated_depreciation": "Tax Prior Depreciation",
            "transaction_type": "Transaction Type",
            "sheet_role": "Sheet Role",
        }
        df_normalized = df_normalized.rename(columns=col_mapping)

        # Run transaction classification (this uses In Service Date to determine current vs existing)
        df_normalized = classify_all_transactions(df_normalized, TAX_YEAR, verbose=False)

        # Check results
        trans_counts = df_normalized["Transaction Type"].value_counts()
        print_subheader("Transaction Type Counts")
        for trans_type, count in trans_counts.items():
            print(f"    {trans_type}: {count}")

        # Verify current year additions
        additions_2024 = df_normalized[df_normalized["Transaction Type"] == "Current Year Addition"]
        if len(additions_2024) > 0:
            test_pass("Current Year Additions detected", f"{len(additions_2024)} additions")
        else:
            test_fail("Current Year Additions", "No additions detected")

        # Verify existing assets (prior years)
        existing = df_normalized[df_normalized["Transaction Type"] == "Existing Asset"]
        if len(existing) > 0:
            test_pass("Existing Assets detected", f"{len(existing)} existing assets")
        else:
            test_warn("Existing Assets", "No existing assets detected (may be expected)")

        # Verify disposals
        disposals = df_normalized[df_normalized["Transaction Type"] == "Disposal"]
        if len(disposals) > 0:
            test_pass("Disposals detected", f"{len(disposals)} disposals")
        else:
            test_warn("Disposals", "No disposals detected")

        # Verify transfers
        transfers = df_normalized[df_normalized["Transaction Type"] == "Transfer"]
        if len(transfers) > 0:
            test_pass("Transfers detected", f"{len(transfers)} transfers")
        else:
            test_warn("Transfers", "No transfers detected")

        # CRITICAL: Validate no misclassification
        is_valid, errors = validate_transaction_classification(df_normalized, TAX_YEAR)
        if is_valid:
            test_pass("Transaction classification validation", "No misclassifications")
        else:
            test_fail("Transaction classification validation", f"{len(errors)} errors found")
            for err in errors[:3]:
                print(f"       - {err['issue']}")

        return df_normalized

    except Exception as e:
        test_fail("Transaction classification exception", str(e))
        import traceback
        traceback.print_exc()
        return df

# =============================================================================
# TEST 3: MACRS CLASSIFICATION
# =============================================================================
def test_macrs_classification(df):
    print_header("TEST 3: MACRS CLASSIFICATION")

    if df is None:
        test_fail("MACRS classification", "No DataFrame to test")
        return None

    try:
        rules = load_rules()
        overrides = load_overrides()

        # Filter to assets that need classification (additions and transfers)
        needs_classification = df[df["Transaction Type"].isin(["Current Year Addition", "Transfer", "Existing Asset"])]

        print_subheader(f"Classifying {len(needs_classification)} assets")

        classification_summary = {
            "rule": 0,
            "client_category": 0,
            "gpt": 0,
            "override": 0,
            "low_confidence": 0,
        }

        classifications = []

        for idx, row in needs_classification.iterrows():
            # Classify without GPT for testing (faster)
            result = classify_asset(
                row.to_dict(),
                client=None,  # No GPT for speed
                rules=rules,
                overrides=overrides
            )

            source = result.get("source", "unknown")
            classification_summary[source] = classification_summary.get(source, 0) + 1

            if result.get("low_confidence"):
                classification_summary["low_confidence"] += 1

            classifications.append({
                "asset_id": row.get("Asset ID"),
                "description": row.get("Description", "")[:50],
                "trans_type": row.get("Transaction Type"),
                "final_class": result.get("final_class"),
                "life": result.get("final_life"),
                "method": result.get("final_method"),
                "source": source,
                "confidence": result.get("confidence", 0),
                "notes": result.get("notes", "")[:50],
            })

            # Update DataFrame
            df.loc[idx, "Final Category"] = result.get("final_class", "")
            df.loc[idx, "MACRS Life"] = result.get("final_life", "")
            df.loc[idx, "Method"] = result.get("final_method", "")
            df.loc[idx, "Convention"] = result.get("final_convention", "")
            df.loc[idx, "Bonus Eligible"] = result.get("bonus", False)
            df.loc[idx, "QIP"] = result.get("qip", False)
            df.loc[idx, "Classification Source"] = source
            df.loc[idx, "Classification Confidence"] = result.get("confidence", 0)

        # Report results
        print_subheader("Classification Sources")
        for source, count in classification_summary.items():
            pct = count / len(needs_classification) * 100 if len(needs_classification) > 0 else 0
            print(f"    {source}: {count} ({pct:.1f}%)")

        # Test rule-based classification rate
        rule_based = classification_summary.get("rule", 0) + classification_summary.get("client_category", 0)
        rule_pct = rule_based / len(needs_classification) * 100 if len(needs_classification) > 0 else 0

        if rule_pct >= 50:
            test_pass("Rule-based classification rate", f"{rule_pct:.1f}% (target: 50%+)")
        else:
            test_warn("Rule-based classification rate", f"{rule_pct:.1f}% is below target 50%")

        # Check for low confidence items
        low_conf_pct = classification_summary["low_confidence"] / len(needs_classification) * 100 if len(needs_classification) > 0 else 0
        if low_conf_pct <= 20:
            test_pass("Low confidence rate", f"{low_conf_pct:.1f}% (target: <20%)")
        else:
            test_warn("Low confidence rate", f"{low_conf_pct:.1f}% exceeds target 20%")

        # Store for later analysis
        results["classification_results"] = classifications

        # Show sample classifications
        print_subheader("Sample Classifications (first 10)")
        for c in classifications[:10]:
            print(f"    {c['asset_id']}: {c['description'][:30]}...")
            print(f"       → {c['final_class']} ({c['life']}-yr, {c['source']}, conf: {c['confidence']:.2f})")

        # Check for common classification issues
        print_subheader("Classification Quality Checks")

        # Check computers are 5-year
        computers = [c for c in classifications if c['final_class'] and 'Computer' in c['final_class']]
        computer_5yr = [c for c in computers if c['life'] == 5]
        if len(computers) > 0:
            if len(computer_5yr) == len(computers):
                test_pass("Computer Equipment → 5-year", f"{len(computers)} computers correctly classified")
            else:
                test_fail("Computer Equipment classification", f"{len(computers) - len(computer_5yr)} computers have wrong life")

        # Check furniture is 7-year
        furniture = [c for c in classifications if c['final_class'] and 'Furniture' in c['final_class']]
        furniture_7yr = [c for c in furniture if c['life'] == 7]
        if len(furniture) > 0:
            if len(furniture_7yr) == len(furniture):
                test_pass("Office Furniture → 7-year", f"{len(furniture)} furniture items correctly classified")
            else:
                test_fail("Office Furniture classification", f"{len(furniture) - len(furniture_7yr)} items have wrong life")

        # Check QIP is 15-year
        qip = [c for c in classifications if c['final_class'] and 'QIP' in c['final_class']]
        qip_15yr = [c for c in qip if c['life'] == 15]
        if len(qip) > 0:
            if len(qip_15yr) == len(qip):
                test_pass("QIP → 15-year", f"{len(qip)} QIP items correctly classified")
            else:
                test_fail("QIP classification", f"{len(qip) - len(qip_15yr)} QIP items have wrong life")

        # Check land improvements are 15-year
        land_imp = [c for c in classifications if c['final_class'] and 'Land Improvement' in c['final_class']]
        land_15yr = [c for c in land_imp if c['life'] == 15]
        if len(land_imp) > 0:
            if len(land_15yr) == len(land_imp):
                test_pass("Land Improvements → 15-year", f"{len(land_imp)} land improvements correctly classified")
            else:
                test_fail("Land Improvement classification", f"{len(land_imp) - len(land_15yr)} items have wrong life")

        # Check vehicles are 5-year
        vehicles = [c for c in classifications if c['final_class'] and ('Automobile' in c['final_class'] or 'Truck' in c['final_class'])]
        vehicles_5yr = [c for c in vehicles if c['life'] == 5]
        if len(vehicles) > 0:
            if len(vehicles_5yr) == len(vehicles):
                test_pass("Vehicles → 5-year", f"{len(vehicles)} vehicles correctly classified")
            else:
                test_fail("Vehicle classification", f"{len(vehicles) - len(vehicles_5yr)} vehicles have wrong life")

        return df

    except Exception as e:
        test_fail("MACRS classification exception", str(e))
        import traceback
        traceback.print_exc()
        return df

# =============================================================================
# TEST 4: DATA VALIDATION
# =============================================================================
def test_data_validation(df):
    print_header("TEST 4: DATA VALIDATION")

    if df is None:
        test_fail("Data validation", "No DataFrame to test")
        return

    try:
        # Run validators
        issues, details = validate_assets(df.copy())

        print_subheader("Validation Issues Found")
        if issues:
            for issue in issues:
                print(f"    ⚠️  {issue}")
        else:
            print("    No issues found")

        # Run advanced validator
        validator = AssetDataValidator(TAX_YEAR)
        errors = validator.validate_dataframe(df)

        summary = validator.get_summary()

        print_subheader("Advanced Validation Summary")
        print(f"    CRITICAL: {summary['CRITICAL']}")
        print(f"    ERROR:    {summary['ERROR']}")
        print(f"    WARNING:  {summary['WARNING']}")

        # Tests
        if summary['CRITICAL'] == 0:
            test_pass("No CRITICAL validation errors")
        else:
            test_fail("CRITICAL validation errors", f"{summary['CRITICAL']} critical errors found")
            for err in validator.get_errors_by_severity("CRITICAL")[:3]:
                print(f"       - {err}")

        if summary['ERROR'] <= 5:
            test_pass("ERROR count acceptable", f"{summary['ERROR']} errors")
        else:
            test_warn("ERROR count high", f"{summary['ERROR']} errors (target: ≤5)")

        # Check the specific transfer validation issue
        transfer_issues = [i for i in issues if "Transfer" in i]
        if transfer_issues:
            test_warn("Transfer validation", transfer_issues[0])
        else:
            test_pass("No transfer-specific validation issues")

    except Exception as e:
        test_fail("Data validation exception", str(e))
        import traceback
        traceback.print_exc()

# =============================================================================
# TEST 5: EXPORT GENERATION
# =============================================================================
def test_export_generation(df):
    print_header("TEST 5: EXPORT GENERATION")

    if df is None:
        test_fail("Export generation", "No DataFrame to test")
        return

    try:
        output_dir = Path("test_data/output")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build FA export data (requires: df, tax_year, strategy, taxable_income)
        fa_df = build_fa(
            df,
            tax_year=TAX_YEAR,
            strategy="balanced",  # Balanced = Bonus only
            taxable_income=500000.0,  # $500k taxable income
            use_acq_if_missing=True
        )

        if fa_df is not None and len(fa_df) > 0:
            test_pass("FA export data built", f"{len(fa_df)} rows")
        else:
            test_fail("FA export data build", "Empty result")
            return

        # Check required FA CS columns
        required_fa_cols = ["Asset ID", "Description", "Cost", "In Service Date"]
        missing = [c for c in required_fa_cols if c not in fa_df.columns]

        if not missing:
            test_pass("Required FA CS columns present")
        else:
            test_fail("Missing FA CS columns", f"{missing}")

        # Check for Tax Method column
        if "Tax Method" in fa_df.columns:
            # Verify additions have methods, disposals don't
            additions_with_method = fa_df[
                (fa_df["Transaction Type"].str.contains("Addition", case=False, na=False)) &
                (fa_df["Tax Method"].notna()) &
                (fa_df["Tax Method"] != "")
            ]
            if len(additions_with_method) > 0:
                test_pass("Additions have Tax Method populated", f"{len(additions_with_method)} additions")
            else:
                test_warn("Additions Tax Method", "No additions with Tax Method")
        else:
            test_warn("Tax Method column", "Column not found in export")

        # Check disposals don't have classification
        disposals = fa_df[fa_df["Transaction Type"].str.contains("Disposal", case=False, na=False)]
        if len(disposals) > 0:
            disposals_with_method = disposals[
                (disposals.get("Tax Method", pd.Series()).notna()) &
                (disposals.get("Tax Method", pd.Series()) != "")
            ]
            if len(disposals_with_method) == 0:
                test_pass("Disposals have blank Tax Method (correct)")
            else:
                test_warn("Disposals with Tax Method", f"{len(disposals_with_method)} disposals have methods")

        # Generate full export file
        output_file = output_dir / f"{CLIENT_ID}_{TAX_YEAR}_FA_Export.xlsx"

        # Export to Excel (multi-sheet) - export_fa_excel takes fa_df and returns bytes
        excel_bytes = export_fa_excel(fa_df)

        # Write bytes to file
        with open(output_file, 'wb') as f:
            f.write(excel_bytes)

        if output_file.exists():
            file_size = output_file.stat().st_size / 1024  # KB
            test_pass("Excel export file created", f"{output_file.name} ({file_size:.1f} KB)")

            # Verify sheets
            xl = pd.ExcelFile(output_file)
            sheets = xl.sheet_names
            print(f"    Sheets: {', '.join(sheets)}")

            expected_sheets = ["FA_CS_Import", "CPA_Review"]
            for sheet in expected_sheets:
                if sheet in sheets:
                    test_pass(f"Sheet '{sheet}' present")
                else:
                    test_fail(f"Sheet '{sheet}' missing")
        else:
            test_fail("Excel export", "File not created")

    except Exception as e:
        test_fail("Export generation exception", str(e))
        import traceback
        traceback.print_exc()

# =============================================================================
# TEST 6: EDGE CASES
# =============================================================================
def test_edge_cases(df):
    print_header("TEST 6: EDGE CASE HANDLING")

    if df is None:
        test_fail("Edge cases", "No DataFrame to test")
        return

    try:
        # Test: Ambiguous descriptions
        ambiguous = df[df["Description"].str.contains("Equipment for|Misc", case=False, na=False)]
        if len(ambiguous) > 0:
            has_classification = ambiguous["Final Category"].notna() & (ambiguous["Final Category"] != "")
            if has_classification.all():
                test_pass("Ambiguous descriptions classified", f"{len(ambiguous)} items")
            else:
                test_warn("Ambiguous descriptions", f"{(~has_classification).sum()} items unclassified")

        # Test: Elevator (should be 39-year, NOT QIP)
        elevator = df[df["Description"].str.contains("Elevator", case=False, na=False)]
        if len(elevator) > 0:
            for idx, row in elevator.iterrows():
                final_class = str(row.get("Final Category", ""))
                if "QIP" in final_class:
                    test_fail("Elevator classification", "Elevator incorrectly classified as QIP (should be 39-year)")
                elif "39" in str(row.get("MACRS Life", "")) or "Nonresidential" in final_class:
                    test_pass("Elevator → 39-year", "Correctly excluded from QIP")
                else:
                    test_warn("Elevator classification", f"Classified as: {final_class}")

        # Test: Land not depreciable
        land = df[df["Description"].str.contains("Land -", case=False, na=False)]
        if len(land) > 0:
            for idx, row in land.iterrows():
                final_class = str(row.get("Final Category", ""))
                macrs_life = row.get("MACRS Life")
                if "Nondepreciable" in final_class or macrs_life is None or pd.isna(macrs_life):
                    test_pass("Land → Nondepreciable", "Correctly identified")
                else:
                    test_fail("Land classification", f"Land has MACRS life: {macrs_life}")

        # Test: Software is 3-year
        software = df[df["Description"].str.contains("Software|ERP|AutoCAD", case=False, na=False)]
        if len(software) > 0:
            software_3yr = software[software["MACRS Life"] == 3]
            if len(software_3yr) == len(software):
                test_pass("Software → 3-year", f"{len(software)} software items")
            else:
                test_warn("Software classification", f"{len(software) - len(software_3yr)} items not 3-year")

        # Test: Listed property (vehicles) have business use check
        vehicles = df[df["Description"].str.contains("Ford|Chevrolet|Toyota|Vehicle|Van|Truck", case=False, na=False)]
        vehicles = vehicles[~vehicles["Transaction Type"].str.contains("Disposal", case=False, na=False)]
        if len(vehicles) > 0:
            test_pass("Listed property detected", f"{len(vehicles)} vehicles")
            # Check if any have low business use
            low_use = vehicles[vehicles.get("Business Use %", pd.Series()) < 50]
            if len(low_use) > 0:
                test_warn("Low business use vehicles", f"{len(low_use)} vehicles with <50% business use (should use ADS)")

    except Exception as e:
        test_fail("Edge cases exception", str(e))
        import traceback
        traceback.print_exc()

# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
def main():
    print("\n" + "🔬" * 40)
    print(" FIXED ASSET AI - COMPREHENSIVE TEST SUITE")
    print(" Test File: Acme_Manufacturing_2024_Assets.xlsx")
    print(" Tax Year: 2024")
    print("🔬" * 40)

    start_time = datetime.now()

    # Run tests in sequence
    df = test_file_loading()

    if df is not None:
        df = test_transaction_classification(df)
        df = test_macrs_classification(df)
        test_data_validation(df)
        test_export_generation(df)
        test_edge_cases(df)

    # Final summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print_header("TEST SUMMARY")
    print(f"\n    Tests Passed: {results['tests_passed']}")
    print(f"    Tests Failed: {results['tests_failed']}")
    print(f"    Warnings:     {len(results['warnings'])}")
    print(f"    Duration:     {duration:.2f} seconds")

    if results['errors']:
        print("\n    ❌ ERRORS:")
        for err in results['errors']:
            print(f"       - {err}")

    if results['warnings']:
        print("\n    ⚠️  WARNINGS:")
        for warn in results['warnings']:
            print(f"       - {warn}")

    # Overall result
    print("\n" + "=" * 80)
    if results['tests_failed'] == 0:
        print("    ✅✅✅ ALL TESTS PASSED ✅✅✅")
    else:
        print(f"    ❌❌❌ {results['tests_failed']} TESTS FAILED ❌❌❌")
    print("=" * 80 + "\n")

    # Save detailed results
    if results['classification_results']:
        results_df = pd.DataFrame(results['classification_results'])
        results_file = Path("test_data/output/classification_results.csv")
        results_file.parent.mkdir(parents=True, exist_ok=True)
        results_df.to_csv(results_file, index=False)
        print(f"    Detailed results saved to: {results_file}")

    return results['tests_failed'] == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
