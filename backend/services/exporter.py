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

    FA CS REQUIRED COLUMNS (must match exactly):
    - Asset #
    - Description
    - Date In Service (NOT "In Service Date")
    - Tax Cost
    - Tax Method
    - Tax Life
    - FA_CS_Wizard_Category (for RPA automation)

    IMPORTANT: ALL assets are exported, even those with validation errors.
    The CPA reviews and decides what to do - the system doesn't exclude anything.
    """

    def _format_asset_number(self, asset_id, row_index: int) -> int:
        """
        Format Asset # for FA CS - must be numeric, strip leading zeros.
        FA CS rules: 001 → 1, 0001 → 1, "A-001" → use row_index
        """
        if asset_id is None:
            return row_index

        # Convert to string and strip whitespace
        asset_str = str(asset_id).strip()

        # Try to extract numeric value
        # Remove common prefixes like "A-", "Asset-", etc.
        import re
        numeric_match = re.search(r'(\d+)', asset_str)

        if numeric_match:
            # Found numeric part - convert to int (strips leading zeros)
            return int(numeric_match.group(1))
        else:
            # No numeric part found - use row index
            return row_index

    def generate_fa_cs_export(self, assets: List[Asset]) -> BytesIO:
        """
        Generates Fixed Assets CS import file with three sheets:
        1. "FA CS Import" - Clean data for UiPath/RPA (matches FA CS input fields)
        2. "Audit Trail" - Full data including Book/State for audit purposes
        3. "Engine Output" - Advanced calculations

        FA CS Input Requirements:
        - Asset #: Numeric only (001 → 1, 0001 → 1)
        - Description: Text
        - Date in Service: Date
        - Cost: Numeric
        - Category: For Wizard button (MACRS class)
        - Life: For Wizard (years)
        """
        # Sheet 1: FA CS Import (for UiPath - matches FA CS input exactly)
        rpa_data = []
        for asset in assets:
            row = {
                "Asset #": self._format_asset_number(asset.asset_id, asset.row_index),
                "Description": asset.description,
                "Date in Service": asset.in_service_date or asset.acquisition_date,
                "Cost": asset.cost,
                "Category": asset.macrs_class,  # For FA CS Wizard selection
                "Life": asset.macrs_life,  # For FA CS Wizard
            }
            rpa_data.append(row)

        rpa_df = pd.DataFrame(rpa_data)

        # Sheet 2: Audit Trail (full data for records)
        audit_data = []
        for asset in assets:
            row = {
                "Asset #": self._format_asset_number(asset.asset_id, asset.row_index),
                "Original Asset ID": asset.asset_id,  # Keep original for reference
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
                "Asset #": self._format_asset_number(asset.asset_id, asset.row_index),
                "Description": asset.description,

                # Dates - FA CS requires "Date In Service" column name
                # The build_fa function converts "In Service Date" -> "Date In Service"
                "Acquisition Date": asset.acquisition_date,
                "In Service Date": asset.in_service_date if asset.in_service_date else asset.acquisition_date,

                # Cost and depreciation
                "Cost": asset.cost if asset.cost else 0.0,

                # Classification (from AI/rules)
                "Final Category": asset.macrs_class if asset.macrs_class else "Unclassified",
                "MACRS Life": asset.macrs_life,
                "Method": asset.macrs_method,
                "Convention": asset.macrs_convention,

                # Metadata for tracking
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
