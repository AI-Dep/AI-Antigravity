import pandas as pd
from io import BytesIO
from typing import List
from datetime import date
from backend.models.asset import Asset
from backend.logic.fa_export import build_fa, export_fa_excel
from backend.logic.fa_export_formatters import _apply_professional_formatting

class ExporterService:
    """
    Generates Excel files formatted for Fixed Assets CS import.
    """

    def generate_fa_cs_export(self, assets: List[Asset]) -> BytesIO:
        """
        Generates Fixed Assets CS import file using the advanced engine.
        """
        # Convert Assets to DataFrame for the engine
        # Note: build_fa expects specific column names (Final Category, MACRS Life, Method, Convention)
        data = []
        for asset in assets:
            row = {
                "Asset ID": asset.asset_id or asset.row_index,
                "Description": asset.description,
                "Cost": asset.cost,
                "Acquisition Date": asset.acquisition_date,
                "In Service Date": asset.in_service_date or asset.acquisition_date,

                # Tax Depreciation (Federal) - column names expected by build_fa
                "Final Category": asset.macrs_class,
                "MACRS Life": asset.macrs_life,
                "Method": asset.macrs_method,
                "Convention": asset.macrs_convention,

                # Book Depreciation (GAAP) - for UiPath manual entry
                "Book Life": asset.book_life or asset.macrs_life,  # Default to Tax if not set
                "Book Method": asset.book_method or "SL",  # Default to Straight-Line
                "Book Convention": asset.book_convention or asset.macrs_convention,

                # State Depreciation - for UiPath manual entry
                "State Life": asset.state_life or asset.macrs_life,  # Default to Tax if not set
                "State Method": asset.state_method or asset.macrs_method,
                "State Convention": asset.state_convention or asset.macrs_convention,
                "State Bonus Allowed": asset.state_bonus_allowed,

                # Metadata
                "Confidence": asset.confidence_score,
                "Source": "rules",  # Default to rules for now
                "Transaction Type": "Addition",  # Default to Addition
                "Business Use %": 1.0,  # Default to 100%
                "Tax Year": date.today().year  # Default to current year
            }
            data.append(row)

        df = pd.DataFrame(data)
        
        # Call the advanced export builder
        # Using defaults for tax parameters for now
        export_df = build_fa(
            df=df,
            tax_year=date.today().year,
            strategy="Balanced",
            taxable_income=10000000.0, # High default to avoid limits
            use_acq_if_missing=True
        )

        # Generate professional multi-sheet export
        # This returns bytes directly
        excel_bytes = export_fa_excel(export_df)
        
        # Convert bytes to BytesIO for compatibility
        return BytesIO(excel_bytes)
