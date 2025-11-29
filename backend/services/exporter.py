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

    def generate_fa_cs_export(self, assets: List[Asset]) -> BytesIO:
        """
        Generates Fixed Assets CS import file using the advanced engine.

        CRITICAL: Exports ALL assets - no filtering/exclusion.
        Assets with validation errors are flagged for CPA review but NOT excluded.
        """
        if not assets:
            raise ValueError("No assets to export")

        # Convert Assets to DataFrame for the engine
        # IMPORTANT: Include all fields needed for FA CS import
        data = []
        for asset in assets:
            row = {
                # Core identifiers
                "Asset ID": asset.asset_id if asset.asset_id else str(asset.row_index),
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
                "Source": "rules",  # Classification source
                "Transaction Type": asset.transaction_type if asset.transaction_type else "addition",
                "Business Use %": 1.0,  # Default to 100% business use
                "Tax Year": date.today().year,

                # Source tracking for audit
                "Source Sheet": asset.source_sheet if hasattr(asset, 'source_sheet') else "",

                # Validation status (for CPA review - NOT for exclusion)
                "Has Validation Errors": "Yes" if asset.validation_errors else "No",
            }
            data.append(row)

        df = pd.DataFrame(data)

        print(f"Exporting {len(df)} assets to FA CS format")
        print(f"  - With In Service Date: {df['In Service Date'].notna().sum()}")
        print(f"  - Without In Service Date: {df['In Service Date'].isna().sum()}")
        print(f"  - With validation errors: {(df['Has Validation Errors'] == 'Yes').sum()}")

        # Call the advanced export builder
        # IMPORTANT: use_acq_if_missing=True ensures assets without in-service date
        # still get a date (using acquisition date as fallback)
        try:
            export_df = build_fa(
                df=df,
                tax_year=date.today().year,
                strategy="Balanced",
                taxable_income=10000000.0,  # High default to avoid Section 179 limits
                use_acq_if_missing=True  # Use acquisition date if no in-service date
            )
        except ValueError as e:
            # If build_fa raises critical error, still try to export basic data
            print(f"Warning: build_fa raised error: {e}")
            print("Attempting basic export without advanced processing...")
            return self._generate_basic_export(df)

        # Generate professional multi-sheet export
        # This returns bytes directly
        excel_bytes = export_fa_excel(export_df)

        # Convert bytes to BytesIO for compatibility
        return BytesIO(excel_bytes)

    def _generate_basic_export(self, df: pd.DataFrame) -> BytesIO:
        """
        Fallback basic export when advanced processing fails.

        Ensures ALL assets are exported even if validation fails.
        CPA can review and fix issues manually.
        """
        print("Using basic export fallback...")

        # Create basic FA CS compatible columns
        export_df = pd.DataFrame({
            "Asset #": range(1, len(df) + 1),
            "Description": df["Description"],
            "Date In Service": df["In Service Date"].apply(
                lambda x: x.strftime("%m/%d/%Y") if pd.notna(x) and hasattr(x, 'strftime') else ""
            ),
            "Acquisition Date": df["Acquisition Date"].apply(
                lambda x: x.strftime("%m/%d/%Y") if pd.notna(x) and hasattr(x, 'strftime') else ""
            ),
            "Tax Cost": df["Cost"].fillna(0).round(2),
            "Tax Life": df["MACRS Life"],
            "Tax Method": df["Method"].fillna(""),
            "Final Category": df["Final Category"].fillna("Unclassified"),
            "Transaction Type": df["Transaction Type"],
            "Needs Review": df["Has Validation Errors"],
        })

        # Write to Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name="FA_CS_Data", index=False)
        output.seek(0)

        return output
