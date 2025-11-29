"""
Multi-Year Depreciation Projection

Calculates year-by-year MACRS depreciation schedules for tax planning and cashflow forecasting.
Uses IRS depreciation tables from macrs_tables.py to project 10+ years of depreciation.

Critical for:
- Tax planning and estimated tax payments
- Cashflow forecasting
- Capital expenditure analysis
- Tax return preparation
"""

from typing import List, Dict, Optional, Any
from datetime import date
import pandas as pd

from .macrs_tables import get_macrs_table, calculate_macrs_depreciation


# ==============================================================================
# SINGLE ASSET DEPRECIATION PROJECTION
# ==============================================================================

def project_asset_depreciation(
    depreciable_basis: float,
    recovery_period: int,
    method: str = "200DB",
    convention: str = "HY",
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    in_service_year: int = 2024,
    projection_years: int = 15
) -> Dict[str, Any]:
    """
    Project depreciation for a single asset over multiple years.

    Args:
        depreciable_basis: Basis for depreciation (cost - Section 179 - bonus)
        recovery_period: MACRS recovery period (3, 5, 7, 10, 15, 20, 27.5, 39)
        method: Depreciation method ("200DB", "150DB", "SL")
        convention: Convention ("HY", "MQ", "MM")
        quarter: Quarter if MQ (1-4)
        month: Month if MM (1-12)
        in_service_year: Year asset placed in service
        projection_years: Number of years to project (default 15)

    Returns:
        Dict with:
        - years: List of tax years
        - depreciation: List of annual depreciation amounts
        - accumulated_depreciation: List of cumulative depreciation
        - remaining_basis: List of remaining basis each year
        - metadata: Asset details
    """
    if depreciable_basis <= 0:
        # No depreciation if basis is zero or negative
        return {
            "years": [],
            "depreciation": [],
            "accumulated_depreciation": [],
            "remaining_basis": [],
            "metadata": {
                "depreciable_basis": depreciable_basis,
                "recovery_period": recovery_period,
                "method": method,
                "convention": convention,
                "in_service_year": in_service_year,
                "reason": "Zero or negative basis - no depreciation"
            }
        }

    # Get MACRS table for this asset
    table = get_macrs_table(recovery_period, method, convention, quarter, month)

    # Calculate depreciation for each year
    years = []
    depreciation_amounts = []
    accumulated_dep = []
    remaining_basis_list = []

    accumulated = 0.0

    for year_num in range(1, projection_years + 1):
        tax_year = in_service_year + year_num - 1
        years.append(tax_year)

        # Calculate depreciation for this year
        if year_num <= len(table):
            # Within MACRS table range
            annual_depreciation = calculate_macrs_depreciation(
                depreciable_basis,
                recovery_period,
                method,
                convention,
                year_num,
                quarter,
                month
            )
        else:
            # Beyond table range - no more depreciation
            annual_depreciation = 0.0

        # Update accumulated depreciation
        accumulated += annual_depreciation

        # Ensure we don't exceed basis (rounding protection)
        if accumulated > depreciable_basis:
            excess = accumulated - depreciable_basis
            annual_depreciation -= excess
            accumulated = depreciable_basis

        # Calculate remaining basis
        remaining_basis = depreciable_basis - accumulated

        depreciation_amounts.append(annual_depreciation)
        accumulated_dep.append(accumulated)
        remaining_basis_list.append(remaining_basis)

        # Stop if fully depreciated
        if remaining_basis <= 0.01:  # Allow 1 cent tolerance for rounding
            break

    return {
        "years": years,
        "depreciation": depreciation_amounts,
        "accumulated_depreciation": accumulated_dep,
        "remaining_basis": remaining_basis_list,
        "metadata": {
            "depreciable_basis": depreciable_basis,
            "recovery_period": recovery_period,
            "method": method,
            "convention": convention,
            "quarter": quarter,
            "month": month,
            "in_service_year": in_service_year,
            "total_years": len(years),
        }
    }


# ==============================================================================
# MULTI-ASSET PORTFOLIO PROJECTION
# ==============================================================================

def project_portfolio_depreciation(
    df: pd.DataFrame,
    current_tax_year: int,
    projection_years: int = 10
) -> pd.DataFrame:
    """
    Project depreciation for entire asset portfolio over multiple years.

    Creates a summary table with total depreciation by year for tax planning.

    Args:
        df: Asset dataframe with depreciation details
        current_tax_year: Current tax year
        projection_years: Number of years to project forward

    Returns:
        DataFrame with columns:
        - Tax Year
        - Total Depreciation
        - Count of Assets Depreciating
        - Average Per Asset
    """
    # Required columns
    required_cols = [
        "Depreciable Basis",
        "Recovery Period",
        "Method",
        "Convention",
        "In Service Date"
    ]

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Initialize summary by year
    year_totals = {year: 0.0 for year in range(current_tax_year, current_tax_year + projection_years)}
    year_counts = {year: 0 for year in range(current_tax_year, current_tax_year + projection_years)}

    # Project each asset
    for idx, row in df.iterrows():
        depreciable_basis = float(row.get("Depreciable Basis") or 0.0)

        if depreciable_basis <= 0:
            continue  # Skip assets with no depreciable basis

        recovery_period = row.get("Recovery Period")
        method = row.get("Method", "200DB")
        convention = row.get("Convention", "HY")
        quarter = row.get("Quarter")
        month = row.get("Month")

        # Get in-service year
        in_service_date = row.get("In Service Date")
        if isinstance(in_service_date, date):
            in_service_year = in_service_date.year
        elif isinstance(in_service_date, str):
            try:
                in_service_year = int(in_service_date[:4])
            except (ValueError, TypeError):
                in_service_year = current_tax_year
        else:
            in_service_year = current_tax_year

        # Project this asset
        projection = project_asset_depreciation(
            depreciable_basis=depreciable_basis,
            recovery_period=recovery_period,
            method=method,
            convention=convention,
            quarter=quarter,
            month=month,
            in_service_year=in_service_year,
            projection_years=projection_years
        )

        # Add to year totals
        for year, depreciation in zip(projection["years"], projection["depreciation"]):
            if year in year_totals:
                year_totals[year] += depreciation
                year_counts[year] += 1

    # Build summary dataframe
    summary_data = []
    for year in sorted(year_totals.keys()):
        total_dep = year_totals[year]
        count = year_counts[year]
        avg_per_asset = total_dep / count if count > 0 else 0.0

        summary_data.append({
            "Tax Year": year,
            "Total Depreciation": total_dep,
            "Assets Depreciating": count,
            "Average Per Asset": avg_per_asset,
        })

    summary_df = pd.DataFrame(summary_data)

    return summary_df


# ==============================================================================
# DETAILED ASSET-BY-YEAR PROJECTION
# ==============================================================================

def create_detailed_projection_table(
    df: pd.DataFrame,
    current_tax_year: int,
    projection_years: int = 10
) -> pd.DataFrame:
    """
    Create detailed asset-by-year depreciation projection table.

    Returns a wide table with one row per asset and columns for each year.

    Args:
        df: Asset dataframe
        current_tax_year: Current tax year
        projection_years: Number of years to project

    Returns:
        DataFrame with:
        - Asset identification columns (Asset ID, Description, etc.)
        - Year_YYYY columns with depreciation for each year
        - Total Depreciation column
        - Remaining Life column
    """
    # Required columns
    required_cols = [
        "Depreciable Basis",
        "Recovery Period",
        "Method",
        "Convention",
        "In Service Date"
    ]

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Build projection for each asset
    projection_data = []

    for idx, row in df.iterrows():
        # Updated 2025-01-20: Support both old and new FA CS column names
        asset_info = {
            "Asset #": row.get("Asset #", row.get("Asset ID", "")),
            "Description": row.get("Description", ""),
            "Final Category": row.get("Final Category", ""),
            "Cost": row.get("Tax Cost", row.get("Cost", 0.0)),
            "Section 179": row.get("Tax Sec 179 Expensed", row.get("Section 179", 0.0)),
            "Bonus Depreciation": row.get("Bonus Amount", row.get("Bonus Depreciation", 0.0)),
            "Depreciable Basis": row.get("Depreciable Basis", 0.0),
            "Recovery Period": row.get("Recovery Period", ""),
            "Method": row.get("Method", ""),
            "Convention": row.get("Convention", ""),
        }

        depreciable_basis = float(row.get("Depreciable Basis") or 0.0)

        if depreciable_basis <= 0:
            # No depreciation - fill with zeros
            for year in range(current_tax_year, current_tax_year + projection_years):
                asset_info[f"Year_{year}"] = 0.0
            asset_info["Total_Depreciation"] = 0.0
            asset_info["Remaining_Life"] = 0
            projection_data.append(asset_info)
            continue

        recovery_period = row.get("Recovery Period")
        method = row.get("Method", "200DB")
        convention = row.get("Convention", "HY")
        quarter = row.get("Quarter")
        month = row.get("Month")

        # Get in-service year
        in_service_date = row.get("In Service Date")
        if isinstance(in_service_date, date):
            in_service_year = in_service_date.year
        elif isinstance(in_service_date, str):
            try:
                in_service_year = int(in_service_date[:4])
            except (ValueError, TypeError):
                in_service_year = current_tax_year
        else:
            in_service_year = current_tax_year

        # Project this asset
        projection = project_asset_depreciation(
            depreciable_basis=depreciable_basis,
            recovery_period=recovery_period,
            method=method,
            convention=convention,
            quarter=quarter,
            month=month,
            in_service_year=in_service_year,
            projection_years=projection_years
        )

        # Fill in year columns
        total_depreciation = 0.0
        for year in range(current_tax_year, current_tax_year + projection_years):
            # Find depreciation for this year
            if year in projection["years"]:
                year_idx = projection["years"].index(year)
                depreciation = projection["depreciation"][year_idx]
            else:
                depreciation = 0.0

            asset_info[f"Year_{year}"] = depreciation
            total_depreciation += depreciation

        asset_info["Total_Depreciation"] = total_depreciation
        asset_info["Remaining_Life"] = len(projection["years"])

        projection_data.append(asset_info)

    projection_df = pd.DataFrame(projection_data)

    return projection_df


# ==============================================================================
# EXPORT HELPER FUNCTIONS
# ==============================================================================

def export_projection_to_excel(
    df: pd.DataFrame,
    current_tax_year: int,
    output_path: str,
    projection_years: int = 10
):
    """
    Export depreciation projection to Excel with multiple sheets.

    Creates:
    - Summary sheet: Total depreciation by year
    - Detail sheet: Asset-by-year depreciation table
    - Chart sheet: Visualization of depreciation trend

    Args:
        df: Asset dataframe
        current_tax_year: Current tax year
        output_path: Path to save Excel file
        projection_years: Number of years to project
    """
    import openpyxl
    from openpyxl.chart import BarChart, Reference

    # Create summary and detail projections
    summary_df = project_portfolio_depreciation(df, current_tax_year, projection_years)
    detail_df = create_detailed_projection_table(df, current_tax_year, projection_years)

    # Write to Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Summary sheet
        summary_df.to_excel(writer, sheet_name='Summary', index=False)

        # Detail sheet
        detail_df.to_excel(writer, sheet_name='Asset Detail', index=False)

        # Format summary sheet
        workbook = writer.book
        summary_sheet = writer.sheets['Summary']

        # Auto-width columns
        for column in summary_sheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except (TypeError, AttributeError):
                    pass
            adjusted_width = min(max_length + 2, 50)
            summary_sheet.column_dimensions[column_letter].width = adjusted_width

        # Add chart
        chart = BarChart()
        chart.title = "Depreciation Projection"
        chart.x_axis.title = "Tax Year"
        chart.y_axis.title = "Total Depreciation ($)"

        # Data for chart
        data = Reference(summary_sheet, min_col=2, min_row=1, max_row=len(summary_df) + 1)
        cats = Reference(summary_sheet, min_col=1, min_row=2, max_row=len(summary_df) + 1)

        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)

        summary_sheet.add_chart(chart, "F2")

    print(f"\n✓ Depreciation projection exported to: {output_path}")
    print(f"  - Summary: {len(summary_df)} years of total depreciation")
    print(f"  - Detail: {len(detail_df)} assets with year-by-year breakdown")


# ==============================================================================
# PLANNING ANALYSIS FUNCTIONS
# ==============================================================================

def analyze_depreciation_cliff(
    df: pd.DataFrame,
    current_tax_year: int,
    projection_years: int = 10,
    cliff_threshold: float = 0.20  # 20% drop year-over-year
) -> Dict[str, Any]:
    """
    Analyze depreciation projections for potential "cliffs" (large year-over-year drops).

    Critical for tax planning - identify years where depreciation drops significantly,
    which may indicate need for additional capital expenditures to maintain tax benefits.

    Args:
        df: Asset dataframe
        current_tax_year: Current tax year
        projection_years: Number of years to project
        cliff_threshold: Percentage drop to flag as a cliff (default 20%)

    Returns:
        Dict with:
        - cliffs: List of years with significant drops
        - recommendations: Planning recommendations
    """
    summary_df = project_portfolio_depreciation(df, current_tax_year, projection_years)

    cliffs = []

    for i in range(1, len(summary_df)):
        prior_year_dep = summary_df.iloc[i - 1]["Total Depreciation"]
        current_year_dep = summary_df.iloc[i]["Total Depreciation"]

        if prior_year_dep > 0:
            pct_change = (current_year_dep - prior_year_dep) / prior_year_dep

            if pct_change < -cliff_threshold:
                cliffs.append({
                    "year": summary_df.iloc[i]["Tax Year"],
                    "prior_year_depreciation": prior_year_dep,
                    "current_year_depreciation": current_year_dep,
                    "dollar_drop": prior_year_dep - current_year_dep,
                    "percent_drop": pct_change,
                })

    # Generate recommendations
    recommendations = []

    if cliffs:
        recommendations.append(
            f"ALERT: {len(cliffs)} depreciation cliff(s) detected. "
            "Consider timing capital expenditures to smooth tax deductions."
        )

        for cliff in cliffs:
            recommendations.append(
                f"  - Year {cliff['year']}: ${cliff['dollar_drop']:,.0f} drop "
                f"({cliff['percent_drop']:.1%}) from prior year"
            )
    else:
        recommendations.append(
            "✓ No significant depreciation cliffs detected. "
            "Tax deductions remain relatively stable."
        )

    return {
        "cliffs": cliffs,
        "recommendations": recommendations,
        "summary": summary_df,
    }
