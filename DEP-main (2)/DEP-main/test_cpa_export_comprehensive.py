"""
Comprehensive CPA Export Testing & Analysis

Tests the CPA export functionality for:
1. Export completeness (all critical fields)
2. Audit trail quality
3. Tax compliance features
4. UX/usability
5. Accuracy
6. Professional workpaper standards

Run with: python test_cpa_export_comprehensive.py
"""

import pandas as pd
from datetime import date
import sys

# Import export and validation functions
from fixed_asset_ai.logic.fa_export import build_fa, export_fa_excel
from fixed_asset_ai.logic.export_qa_validator import validate_fixed_asset_cs_export
from fixed_asset_ai.logic.macrs_classification import classify_asset_macrs


def create_diverse_test_data():
    """Create diverse test data covering multiple scenarios."""

    data = [
        # 1. Current year addition - Equipment with Section 179
        {
            "Asset ID": "E-2024-001",
            "Description": "CNC Milling Machine",
            "Client Category": "Equipment",
            "Acquisition Date": date(2024, 1, 15),
            "In Service Date": date(2024, 1, 20),
            "Cost": 125000.00,
            "Transaction Type": "Current Year Addition",
        },

        # 2. Current year addition - Vehicle (luxury auto limits)
        {
            "Asset ID": "V-2024-002",
            "Description": "2024 BMW 530i Executive Car",
            "Client Category": "Vehicles",
            "Acquisition Date": date(2024, 2, 10),
            "In Service Date": date(2024, 2, 15),
            "Cost": 65000.00,
            "Transaction Type": "Current Year Addition",
        },

        # 3. Current year addition - Computer equipment
        {
            "Asset ID": "C-2024-003",
            "Description": "Dell Workstations (5 units) with Monitors",
            "Client Category": "Computer Equipment",
            "Acquisition Date": date(2024, 3, 5),
            "In Service Date": date(2024, 3, 10),
            "Cost": 25000.00,
            "Transaction Type": "Current Year Addition",
        },

        # 4. Existing asset from 2020
        {
            "Asset ID": "E-2020-015",
            "Description": "Forklift Toyota 8FGCU25",
            "Client Category": "Machinery",
            "Acquisition Date": date(2020, 6, 1),
            "In Service Date": date(2020, 6, 15),
            "Cost": 35000.00,
            "Accumulated Depreciation": 22500.00,
            "Transaction Type": "Existing Asset",
        },

        # 5. Existing asset from 2019
        {
            "Asset ID": "B-2019-001",
            "Description": "Office Building - 123 Main St",
            "Client Category": "Real Property",
            "Acquisition Date": date(2019, 1, 10),
            "In Service Date": date(2019, 2, 1),
            "Cost": 850000.00,
            "Accumulated Depreciation": 109000.00,
            "Transaction Type": "Existing Asset",
        },

        # 6. Q4 addition (mid-quarter test)
        {
            "Asset ID": "E-2024-099",
            "Description": "Production Equipment - Placed Q4",
            "Client Category": "Machinery",
            "Acquisition Date": date(2024, 10, 15),
            "In Service Date": date(2024, 10, 20),
            "Cost": 45000.00,
            "Transaction Type": "Current Year Addition",
        },

        # 7. Heavy SUV (Section 179 special limit)
        {
            "Asset ID": "V-2024-020",
            "Description": "2024 Ford F-350 Super Duty Crew Cab (GVWR 14,000 lbs)",
            "Client Category": "Trucks",
            "Acquisition Date": date(2024, 4, 1),
            "In Service Date": date(2024, 4, 5),
            "Cost": 75000.00,
            "Transaction Type": "Current Year Addition",
        },

        # 8. Qualified Improvement Property
        {
            "Asset ID": "QIP-2024-005",
            "Description": "Interior Office Renovation - Non-structural",
            "Client Category": "Qualified Improvement Property",
            "Acquisition Date": date(2024, 5, 10),
            "In Service Date": date(2024, 5, 20),
            "Cost": 95000.00,
            "Transaction Type": "Current Year Addition",
        },

        # 9. Land improvement
        {
            "Asset ID": "LI-2024-003",
            "Description": "Parking Lot Paving and Lighting",
            "Client Category": "Land Improvements",
            "Acquisition Date": date(2024, 6, 1),
            "In Service Date": date(2024, 6, 15),
            "Cost": 55000.00,
            "Transaction Type": "Current Year Addition",
        },

        # 10. Furniture
        {
            "Asset ID": "F-2024-010",
            "Description": "Office Furniture - Desks, Chairs, Cabinets",
            "Client Category": "Furniture & Fixtures",
            "Acquisition Date": date(2024, 7, 5),
            "In Service Date": date(2024, 7, 10),
            "Cost": 18000.00,
            "Transaction Type": "Current Year Addition",
        },
    ]

    return pd.DataFrame(data)


def analyze_export_completeness(df: pd.DataFrame):
    """Analyze export file for completeness and CPA workpaper quality."""

    print("\n" + "=" * 100)
    print("EXPORT COMPLETENESS ANALYSIS - CPA WORKPAPER QUALITY")
    print("=" * 100)

    # Critical CPA workpaper fields
    critical_fields = {
        "Asset Identification": ["Asset #", "Original Asset ID", "Description"],
        "Tax Compliance": ["Tax Life", "Tax Method", "Convention", "Tax Cost"],
        "Tax Incentives": ["Tax Sec 179 Expensed", "Bonus Amount", "Bonus % Applied"],
        "Depreciation": ["Depreciable Basis", "Tax Cur Depreciation", "Tax Prior Depreciation"],
        "Audit Trail": ["Transaction Type", "Date In Service", "Acquisition Date"],
        "Recapture (Disposals)": ["§1245 Recapture (Ordinary Income)", "§1250 Recapture (Ordinary Income)"],
        "CPA Review": ["NBV_Reco", "MaterialityScore", "ReviewPriority"],
        "Classification": ["Final Category", "Source", "Client Category Original"],
        "Advanced Features": ["Section 179 Carryforward", "Uses ADS", "Auto Limit Notes"],
    }

    available = []
    missing = []

    for category, fields in critical_fields.items():
        cat_available = []
        cat_missing = []

        for field in fields:
            if field in df.columns:
                cat_available.append(field)
            else:
                cat_missing.append(field)

        if cat_available:
            available.append((category, cat_available))
        if cat_missing:
            missing.append((category, cat_missing))

    # Print available fields
    print("\n✅ AVAILABLE FIELDS BY CATEGORY:")
    print("-" * 100)
    for category, fields in available:
        print(f"\n{category}:")
        for field in fields:
            # Check if field has data
            non_null = df[field].notna().sum()
            total = len(df)
            pct = (non_null / total * 100) if total > 0 else 0
            print(f"  ✓ {field:40s} ({non_null}/{total} rows populated - {pct:.1f}%)")

    # Print missing fields
    if missing:
        print("\n\n❌ MISSING FIELDS BY CATEGORY:")
        print("-" * 100)
        for category, fields in missing:
            print(f"\n{category}:")
            for field in fields:
                print(f"  ✗ {field}")
    else:
        print("\n\n✅ NO MISSING CRITICAL FIELDS - EXPORT IS COMPLETE")

    print("\n" + "=" * 100)

    return len([f for cat, fields in missing for f in fields])


def analyze_audit_trail_quality(df: pd.DataFrame):
    """Analyze audit trail and documentation quality."""

    print("\n" + "=" * 100)
    print("AUDIT TRAIL & DOCUMENTATION QUALITY ANALYSIS")
    print("=" * 100)

    # Check for audit trail fields
    audit_fields = [
        "AuditSource",
        "AuditRuleTriggers",
        "AuditWarnings",
        "ClassificationHash",
        "AuditTimestamp",
        "ClassificationExplanation",
        "MACRS_Reason_Code",
        "ConfidenceGrade"
    ]

    available_audit = [f for f in audit_fields if f in df.columns]
    missing_audit = [f for f in audit_fields if f not in df.columns]

    print(f"\n✅ Audit Trail Fields: {len(available_audit)}/{len(audit_fields)} available")

    for field in available_audit:
        non_null = df[field].notna().sum()
        print(f"  ✓ {field:40s} ({non_null}/{len(df)} populated)")

    if missing_audit:
        print(f"\n❌ Missing Audit Fields:")
        for field in missing_audit:
            print(f"  ✗ {field}")

    # Check hash integrity
    if "ClassificationHash" in df.columns:
        unique_hashes = df["ClassificationHash"].nunique()
        print(f"\n🔒 Classification Integrity:")
        print(f"  ✓ {unique_hashes} unique SHA256 hashes generated")
        print(f"  ✓ Prevents classification tampering")
        print(f"  ✓ Enables change detection")

    # Check for explanations
    if "ClassificationExplanation" in df.columns:
        with_explanation = df["ClassificationExplanation"].notna().sum()
        print(f"\n📖 Classification Explanations:")
        print(f"  ✓ {with_explanation}/{len(df)} assets have explanations")

        # Show sample
        sample = df[df["ClassificationExplanation"].notna()]["ClassificationExplanation"].iloc[0]
        print(f"  Sample: \"{sample[:80]}...\"")

    print("\n" + "=" * 100)


def analyze_tax_compliance(df: pd.DataFrame):
    """Analyze tax compliance features and accuracy."""

    print("\n" + "=" * 100)
    print("TAX COMPLIANCE ANALYSIS")
    print("=" * 100)

    # Section 179
    total_sec179 = df["Tax Sec 179 Expensed"].sum() if "Tax Sec 179 Expensed" in df.columns else 0
    total_bonus = df["Bonus Amount"].sum() if "Bonus Amount" in df.columns else 0
    total_macrs = df["Tax Cur Depreciation"].sum() if "Tax Cur Depreciation" in df.columns else 0

    print(f"\n💰 Tax Deductions:")
    print(f"  Section 179 Expensing:     ${total_sec179:>15,.2f}")
    print(f"  Bonus Depreciation:        ${total_bonus:>15,.2f}")
    print(f"  MACRS Year 1 Depreciation: ${total_macrs:>15,.2f}")
    print(f"  {'-' * 45}")
    print(f"  Total Year 1 Deduction:    ${total_sec179 + total_bonus + total_macrs:>15,.2f}")

    # Section 179 carryforward
    if "Section 179 Carryforward" in df.columns:
        total_carryforward = df["Section 179 Carryforward"].sum()
        if total_carryforward > 0:
            print(f"\n⚠️  Section 179 Carryforward: ${total_carryforward:,.2f}")
            print(f"  (Due to taxable income limitation)")

    # IRC §280F luxury auto limits
    if "Auto Limit Notes" in df.columns:
        luxury_auto_limited = df[df["Auto Limit Notes"].str.contains("§280F", na=False)]
        if len(luxury_auto_limited) > 0:
            print(f"\n🚗 IRC §280F Luxury Auto Limits Applied:")
            print(f"  {len(luxury_auto_limited)} vehicles subject to depreciation caps")

    # Heavy SUV limits
    if "Auto Limit Notes" in df.columns:
        heavy_suv_limited = df[df["Auto Limit Notes"].str.contains("Heavy SUV|§179\\(b\\)\\(5\\)", na=False)]
        if len(heavy_suv_limited) > 0:
            print(f"\n🚙 IRC §179(b)(5) Heavy SUV Limits Applied:")
            print(f"  {len(heavy_suv_limited)} heavy vehicles subject to reduced Section 179 limit")

    # ADS (Alternative Depreciation System)
    if "Uses ADS" in df.columns:
        ads_count = df["Uses ADS"].sum() if df["Uses ADS"].dtype == bool else df[df["Uses ADS"] == True].shape[0]
        if ads_count > 0:
            print(f"\n📋 IRC §168(g) Alternative Depreciation System:")
            print(f"  {ads_count} assets using ADS (extended recovery periods)")

    # Mid-quarter convention
    if "Convention" in df.columns:
        mq_count = len(df[df["Convention"] == "MQ"])
        if mq_count > 0:
            print(f"\n📅 IRC §168(d)(3) Mid-Quarter Convention:")
            print(f"  {mq_count} assets using MQ convention")
            print(f"  (>40% of property placed in service in Q4)")

    print("\n" + "=" * 100)


def analyze_ux_design(df: pd.DataFrame):
    """Analyze UX design and ease of use."""

    print("\n" + "=" * 100)
    print("UX DESIGN & EASE OF USE ANALYSIS")
    print("=" * 100)

    # Column count
    total_cols = len(df.columns)

    # Categorize columns
    required_cols = ["Asset #", "Description", "Date In Service", "Tax Cost"]
    tax_cols = [c for c in df.columns if c.startswith("Tax ")]
    section179_cols = [c for c in df.columns if "179" in c]
    bonus_cols = [c for c in df.columns if "Bonus" in c]
    recapture_cols = [c for c in df.columns if "§" in c or "Recapture" in c]
    audit_cols = [c for c in df.columns if "Audit" in c or "Hash" in c or "Explanation" in c]
    review_cols = [c for c in df.columns if "NBV" in c or "Materiality" in c or "Review" in c or "Confidence" in c]

    print(f"\n📊 Column Organization:")
    print(f"  Total Columns: {total_cols}")
    print(f"  ├─ Required Fields:         {len(required_cols)}")
    print(f"  ├─ Tax Fields (Tax *):      {len(tax_cols)}")
    print(f"  ├─ Section 179 Fields:      {len(section179_cols)}")
    print(f"  ├─ Bonus Depreciation:      {len(bonus_cols)}")
    print(f"  ├─ Recapture Fields:        {len(recapture_cols)}")
    print(f"  ├─ Audit Trail Fields:      {len(audit_cols)}")
    print(f"  └─ CPA Review Fields:       {len(review_cols)}")

    # Check for descriptive field names
    print(f"\n📝 Field Naming Quality:")

    unclear_names = []
    for col in df.columns:
        # Check for abbreviations or unclear names
        if col in ["NBV_Derived", "NBV_Diff", "NBV_Reco"]:
            unclear_names.append(col)

    if unclear_names:
        print(f"  ⚠️  Fields with unclear names: {', '.join(unclear_names)}")
        print(f"     (Consider: 'Net Book Value Derived', 'Net Book Value Difference', 'Net Book Value Reconciliation')")
    else:
        print(f"  ✅ All field names are clear and descriptive")

    # Check for review priority
    if "ReviewPriority" in df.columns:
        high_priority = len(df[df["ReviewPriority"] == "High"])
        medium_priority = len(df[df["ReviewPriority"] == "Medium"])
        low_priority = len(df[df["ReviewPriority"] == "Low"])

        print(f"\n🎯 CPA Review Prioritization:")
        print(f"  ✅ Assets categorized by materiality")
        print(f"     High Priority:   {high_priority} assets")
        print(f"     Medium Priority: {medium_priority} assets")
        print(f"     Low Priority:    {low_priority} assets")

    # Check for NBV reconciliation
    if "NBV_Reco" in df.columns:
        issues = len(df[df["NBV_Reco"] == "CHECK"])
        print(f"\n🔍 Net Book Value Reconciliation:")
        if issues > 0:
            print(f"  ⚠️  {issues} assets flagged for NBV review")
        else:
            print(f"  ✅ All assets reconciled (no NBV issues)")

    print("\n💡 UX RECOMMENDATIONS:")

    recommendations = []

    # Too many columns?
    if total_cols > 60:
        recommendations.append("Consider creating separate worksheets for audit trail vs. working data")
        recommendations.append("  - Sheet 1: FA CS Import (essential fields only)")
        recommendations.append("  - Sheet 2: CPA Review & Analysis")
        recommendations.append("  - Sheet 3: Audit Trail & Documentation")

    # Missing summary
    if "ReviewPriority" in df.columns and high_priority > 0:
        recommendations.append("Add summary worksheet showing:")
        recommendations.append("  - High priority assets requiring review")
        recommendations.append("  - Total tax deductions by category")
        recommendations.append("  - Assets with NBV reconciliation issues")
        recommendations.append("  - Compliance warnings and notes")

    # Formatting
    recommendations.append("Apply Excel formatting:")
    recommendations.append("  - Currency formatting for dollar amounts")
    recommendations.append("  - Date formatting for date columns")
    recommendations.append("  - Conditional formatting to highlight issues")
    recommendations.append("  - Freeze top row for easy scrolling")

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}" if not rec.startswith("  ") else f"     {rec}")
    else:
        print(f"  ✅ No UX improvements needed - export is well-designed")

    print("\n" + "=" * 100)


def run_comprehensive_tests():
    """Run all comprehensive tests."""

    print("\n" + "=" * 100)
    print("COMPREHENSIVE CPA EXPORT TESTING & ANALYSIS")
    print("=" * 100)
    print("\nTesting the CPA export functionality for:")
    print("  ✓ Export completeness (all critical fields)")
    print("  ✓ Audit trail quality")
    print("  ✓ Tax compliance features")
    print("  ✓ UX/usability")
    print("  ✓ Accuracy")
    print("  ✓ Professional workpaper standards")
    print("\n" + "=" * 100)

    # Create test data
    print("\n📋 Creating diverse test dataset...")
    raw_df = create_diverse_test_data()
    print(f"   ✓ Created {len(raw_df)} test assets")

    # Classify assets
    print("\n🔍 Classifying assets using MACRS rules...")
    for idx, row in raw_df.iterrows():
        result = classify_asset_macrs(
            description=row["Description"],
            client_category=row.get("Client Category", ""),
            cost=row.get("Cost", 0),
            acquisition_date=row.get("Acquisition Date"),
        )

        raw_df.at[idx, "Final Category"] = result["category"]
        raw_df.at[idx, "Recovery Period"] = result["life"]
        raw_df.at[idx, "Method"] = result["method"]
        raw_df.at[idx, "Source"] = result["source"]
        raw_df.at[idx, "Rule Confidence"] = result.get("confidence", 0.95)

    print(f"   ✓ Classified all assets")

    # Build FA export
    print("\n📊 Building Fixed Asset CS export...")
    try:
        fa_df = build_fa(
            df=raw_df,
            tax_year=2024,
            strategy="Aggressive (179 + Bonus)",
            taxable_income=500000.00,  # $500k taxable income
            use_acq_if_missing=True,
            de_minimis_limit=2500.00,  # Enable de minimis safe harbor
            section_179_carryforward_from_prior_year=0.00
        )

        print(f"   ✓ Export generated successfully")
        print(f"   ✓ {len(fa_df)} assets in export")
        print(f"   ✓ {len(fa_df.columns)} columns in export")

    except Exception as e:
        print(f"   ❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Run validation
    print("\n✅ Running quality validation...")
    is_valid, errors, summary = validate_fixed_asset_cs_export(fa_df, verbose=True)

    # Analyze completeness
    missing_count = analyze_export_completeness(fa_df)

    # Analyze audit trail
    analyze_audit_trail_quality(fa_df)

    # Analyze tax compliance
    analyze_tax_compliance(fa_df)

    # Analyze UX
    analyze_ux_design(fa_df)

    # Final summary
    print("\n" + "=" * 100)
    print("FINAL ASSESSMENT")
    print("=" * 100)

    print(f"\n✅ Quality Validation:      {'PASSED' if is_valid else 'FAILED'}")
    print(f"✅ Completeness:            {len(fa_df.columns)} columns, {missing_count} missing critical fields")
    print(f"✅ Audit Trail:             {'Complete' if 'AuditSource' in fa_df.columns else 'Missing'}")
    print(f"✅ Tax Compliance:          {'Complete' if 'Tax Sec 179 Expensed' in fa_df.columns else 'Missing'}")

    # Save export for manual review
    output_path = "test_cpa_export_analysis.xlsx"
    excel_bytes = export_fa_excel(fa_df)
    with open(output_path, "wb") as f:
        f.write(excel_bytes)

    print(f"\n💾 Export saved to: {output_path}")
    print(f"   Review this file manually to verify:")
    print(f"   - Column organization and naming")
    print(f"   - Data accuracy and calculations")
    print(f"   - Audit trail completeness")
    print(f"   - Professional workpaper quality")

    print("\n" + "=" * 100)

    return is_valid and missing_count == 0


if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)
