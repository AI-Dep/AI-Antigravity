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
    - FA_CS_Wizard_Category (for RPA automation - exact wizard dropdown text)

    DISPOSAL COLUMNS (for disposed assets):
    - Date Disposed
    - Gross Proceeds
    - §1245 Recapture (Ordinary Income)
    - §1250 Recapture (Ordinary Income)
    - Capital Gain / Capital Loss

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
        1. "FA CS Import" - Full data for FA CS import with proper wizard categories,
           disposal fields, and transfer handling
        2. "Audit Trail" - Full data including Book/State for audit purposes
        3. "Engine Output" - Advanced calculations from build_fa engine

        FA CS Input Requirements:
        - Asset #: Numeric only (001 → 1, 0001 → 1)
        - Description: Text
        - Date In Service: Date (M/D/YYYY format)
        - Tax Cost: Numeric
        - Tax Method: "MACRS" (FA CS only accepts this)
        - Tax Life: Numeric (5, 7, 15, 27.5, 39)
        - FA_CS_Wizard_Category: Exact wizard dropdown text for RPA automation

        Disposal Requirements:
        - Date Disposed: Date disposed (M/D/YYYY format)
        - Gross Proceeds: Sale proceeds
        - Recapture columns for gain/loss reporting
        """
        # Prepare data for build_fa engine (uses specific column names)
        engine_data = []
        for asset in assets:
            # Detect transaction type first
            trans_type = self._detect_transaction_type(asset)

            row = {
                "Asset #": self._format_asset_number(asset.asset_id, asset.row_index),
                "Asset ID": str(asset.asset_id) if asset.asset_id else str(asset.row_index),
                "Description": asset.description,

                # Dates - FA CS requires "Date In Service" column name
                "Acquisition Date": asset.acquisition_date,
                "In Service Date": asset.in_service_date if asset.in_service_date else asset.acquisition_date,

                # Cost and depreciation
                "Cost": asset.cost if asset.cost else 0.0,

                # Classification (from AI/rules)
                "Final Category": asset.macrs_class if asset.macrs_class else "Unclassified",
                "MACRS Life": asset.macrs_life,
                "Recovery Period": asset.macrs_life,  # Alias for build_fa
                "Method": asset.macrs_method,
                "Convention": asset.macrs_convention,

                # Disposal fields (if present on asset)
                "Disposal Date": getattr(asset, 'disposal_date', None),
                "Proceeds": getattr(asset, 'proceeds', None) or getattr(asset, 'sale_price', None),
                "Accumulated Depreciation": getattr(asset, 'accumulated_depreciation', 0.0) or 0.0,

                # Transfer fields (if present on asset)
                "From Location": getattr(asset, 'from_location', None),
                "To Location": getattr(asset, 'to_location', None),
                "Transfer Date": getattr(asset, 'transfer_date', None),

                # Transaction type - detect from asset attributes
                "Transaction Type": trans_type,

                # Metadata for tracking
                "Confidence": asset.confidence_score,
                "Source": "rules",
                "Business Use %": 1.0,
                "Tax Year": date.today().year,

                # Additional columns required by build_fa for recapture calculations
                # These are initialized and will be computed by build_fa
                "Section 179 Amount": 0.0,
                "Bonus Amount": 0.0,
                "Bonus Percentage Used": 0.0,
                "MACRS Year 1 Depreciation": 0.0,
                "Auto Limit Notes": "",
                "Uses ADS": False,
                "§1245 Recapture (Ordinary Income)": 0.0,
                "§1250 Recapture (Ordinary Income)": 0.0,
                "Unrecaptured §1250 Gain (25% rate)": 0.0,
                "Capital Gain": 0.0,
                "Capital Loss": 0.0,
                "Adjusted Basis at Disposal": 0.0,
            }
            engine_data.append(row)

        df = pd.DataFrame(engine_data)

        # Call the advanced export builder for full processing
        # This applies: FA_CS_Wizard_Category mapping, disposal recapture calculations,
        # transfer handling, Section 179/Bonus depreciation, etc.
        try:
            export_df = build_fa(
                df=df,
                tax_year=date.today().year,
                strategy="Balanced",
                taxable_income=10000000.0,  # High default to avoid limits
                use_acq_if_missing=True
            )
        except Exception as e:
            # If build_fa fails, use the raw data with basic formatting
            print(f"Warning: build_fa failed ({e}), using raw data")
            export_df = df

        # ================================================================
        # FA CS IMPORT SHEET - Use comprehensive build_fa output
        # ================================================================
        # Select columns that FA CS needs for import and RPA automation
        fa_cs_import_cols = [
            # Core required fields
            "Asset #",
            "Description",
            "Date In Service",
            "Tax Cost",
            "Tax Method",
            "Tax Life",
            "Convention",

            # RPA automation - EXACT wizard dropdown text (NOT generic category!)
            "FA_CS_Wizard_Category",

            # Depreciation fields
            "Tax Sec 179 Expensed",
            "Tax Prior Depreciation",

            # Transaction type for CPA review
            "Transaction Type",

            # Disposal fields (populated for disposed assets)
            "Date Disposed",
            "Gross Proceeds",
            "§1245 Recapture (Ordinary Income)",
            "§1250 Recapture (Ordinary Income)",
            "Capital Gain",
            "Capital Loss",
            "Adjusted Basis at Disposal",
        ]

        # Select available columns from export_df
        available_cols = [c for c in fa_cs_import_cols if c in export_df.columns]
        fa_cs_import_df = export_df[available_cols].copy()

        # ================================================================
        # AUDIT TRAIL SHEET - Full data for records
        # ================================================================
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
                "Book Life": getattr(asset, 'book_life', None) or asset.macrs_life,
                "Book Method": getattr(asset, 'book_method', None) or "SL",
                "Book Convention": getattr(asset, 'book_convention', None) or asset.macrs_convention,

                # State Depreciation
                "State Life": getattr(asset, 'state_life', None) or asset.macrs_life,
                "State Method": getattr(asset, 'state_method', None) or asset.macrs_method,
                "State Convention": getattr(asset, 'state_convention', None) or asset.macrs_convention,
                "State Bonus Allowed": getattr(asset, 'state_bonus_allowed', True),

                # Disposal fields
                "Disposal Date": getattr(asset, 'disposal_date', None),
                "Proceeds": getattr(asset, 'proceeds', None),
                "Accumulated Depreciation": getattr(asset, 'accumulated_depreciation', None),

                # Transfer fields
                "From Location": getattr(asset, 'from_location', None),
                "To Location": getattr(asset, 'to_location', None),
                "Transfer Date": getattr(asset, 'transfer_date', None),

                # Metadata
                "Confidence Score": asset.confidence_score,
                "Transaction Type": self._detect_transaction_type(asset),
                "Business Use %": 1.0,
                "Tax Year": date.today().year,
                "Export Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            audit_data.append(row)

        audit_df = pd.DataFrame(audit_data)

        # Generate multi-sheet Excel export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: FA CS Import - Comprehensive data from build_fa engine
            fa_cs_import_df.to_excel(writer, sheet_name='FA CS Import', index=False)

            # Sheet 2: Audit Trail (full data with Book/State)
            audit_df.to_excel(writer, sheet_name='Audit Trail', index=False)

            # Sheet 3: Engine Output (all calculations from build_fa)
            if export_df is not None and not export_df.empty:
                export_df.to_excel(writer, sheet_name='Engine Output', index=False)

        output.seek(0)
        return output

    def _detect_transaction_type(self, asset: Asset) -> str:
        """
        Detect transaction type from asset attributes.

        Returns:
            - "Disposal" if asset has disposal indicators
            - "Transfer" if asset has transfer indicators
            - "Addition" for new assets (default)
        """
        # Check for disposal indicators
        if getattr(asset, 'disposal_date', None):
            return "Disposal"
        if getattr(asset, 'is_disposed', False):
            return "Disposal"

        # Check for transfer indicators
        if getattr(asset, 'transfer_date', None):
            return "Transfer"
        if getattr(asset, 'from_location', None) and getattr(asset, 'to_location', None):
            return "Transfer"
        if getattr(asset, 'is_transfer', False):
            return "Transfer"

        # Default to Addition
        return "Addition"
