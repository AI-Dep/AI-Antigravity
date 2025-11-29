import pandas as pd
from io import BytesIO
from typing import List
from datetime import date, datetime
from backend.models.asset import Asset
from backend.logic.fa_export import build_fa, export_fa_excel
from backend.logic.fa_export_formatters import _apply_professional_formatting

class ExporterService:
    """
    Generates Excel files formatted for Fixed Assets CS import.
    """

    def generate_fa_cs_export(self, assets: List[Asset]) -> BytesIO:
        """
        Generates Fixed Assets CS import file with two sheets:
        1. "FA CS Import" - Clean data for UiPath/RPA
        2. "Audit Trail" - Full data including Book/State for audit purposes
        """
        # Sheet 1: FA CS Import (for UiPath - only essential fields)
        rpa_data = []
        for asset in assets:
            row = {
                "Asset ID": asset.asset_id or asset.row_index,
                "Description": asset.description,
                "Date in Service": asset.in_service_date or asset.acquisition_date,
                "Cost": asset.cost,
                "Category": asset.macrs_class,  # For FA CS Wizard selection
            }
            rpa_data.append(row)

        rpa_df = pd.DataFrame(rpa_data)

        # Sheet 2: Audit Trail (full data for records)
        audit_data = []
        for asset in assets:
            row = {
                "Asset ID": asset.asset_id or asset.row_index,
                "Description": asset.description,
                "Cost": asset.cost,
                "Acquisition Date": asset.acquisition_date,
                "In Service Date": asset.in_service_date or asset.acquisition_date,

                # Tax Depreciation (Federal)
                "Tax Class": asset.macrs_class,
                "Tax Life": asset.macrs_life,
                "Tax Method": asset.macrs_method,
                "Tax Convention": asset.macrs_convention,

                # Book Depreciation (GAAP)
                "Book Life": asset.book_life or asset.macrs_life,
                "Book Method": asset.book_method or "SL",
                "Book Convention": asset.book_convention or asset.macrs_convention,

                # State Depreciation
                "State Life": asset.state_life or asset.macrs_life,
                "State Method": asset.state_method or asset.macrs_method,
                "State Convention": asset.state_convention or asset.macrs_convention,
                "State Bonus Allowed": asset.state_bonus_allowed,

                # Metadata
                "Confidence Score": asset.confidence_score,
                "Transaction Type": "Addition",
                "Business Use %": 1.0,
                "Tax Year": date.today().year,
                "Export Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            audit_data.append(row)

        audit_df = pd.DataFrame(audit_data)

        # Also prepare data for build_fa engine (uses specific column names)
        engine_data = []
        for asset in assets:
            row = {
                "Asset ID": asset.asset_id or asset.row_index,
                "Description": asset.description,
                "Cost": asset.cost,
                "Acquisition Date": asset.acquisition_date,
                "In Service Date": asset.in_service_date or asset.acquisition_date,
                "Final Category": asset.macrs_class,
                "MACRS Life": asset.macrs_life,
                "Method": asset.macrs_method,
                "Convention": asset.macrs_convention,
                "Confidence": asset.confidence_score,
                "Source": "rules",
                "Transaction Type": "Addition",
                "Business Use %": 1.0,
                "Tax Year": date.today().year
            }
            engine_data.append(row)

        df = pd.DataFrame(engine_data)
        
        # Call the advanced export builder for additional processing
        # Using defaults for tax parameters for now
        try:
            export_df = build_fa(
                df=df,
                tax_year=date.today().year,
                strategy="Balanced",
                taxable_income=10000000.0,  # High default to avoid limits
                use_acq_if_missing=True
            )
        except Exception as e:
            # If build_fa fails, use the raw data
            print(f"Warning: build_fa failed ({e}), using raw data")
            export_df = df

        # Generate multi-sheet Excel export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: FA CS Import (for UiPath/RPA) - FIRST SHEET
            rpa_df.to_excel(writer, sheet_name='FA CS Import', index=False)

            # Sheet 2: Audit Trail (full data with Book/State)
            audit_df.to_excel(writer, sheet_name='Audit Trail', index=False)

            # Sheet 3: Engine Output (advanced calculations if available)
            if export_df is not None and not export_df.empty:
                export_df.to_excel(writer, sheet_name='Engine Output', index=False)

        output.seek(0)
        return output
