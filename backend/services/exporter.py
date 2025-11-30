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

    def generate_fa_cs_export(self, assets: List[Asset], tax_year: int = None, de_minimis_limit: float = 0.0) -> BytesIO:
        """
        Generates Fixed Assets CS import file with three sheets:
        1. "FA CS Entry" - Full data for manual FA CS entry with proper wizard categories,
           disposal fields, and transfer handling
        2. "Audit Trail" - Full data including Book/State for audit purposes
        3. "Change Log" - Shows what changed from original data with before/after values and reasons

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
        # transfer handling, Section 179/Bonus depreciation, de minimis safe harbor, etc.
        effective_tax_year = tax_year if tax_year else date.today().year
        try:
            export_df = build_fa(
                df=df,
                tax_year=effective_tax_year,
                strategy="Balanced",
                taxable_income=10000000.0,  # High default to avoid limits
                use_acq_if_missing=True,
                de_minimis_limit=de_minimis_limit  # Pass de minimis threshold for safe harbor expensing
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
                "Tax Year": effective_tax_year,
                "Export Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            audit_data.append(row)

        audit_df = pd.DataFrame(audit_data)

        # Generate multi-sheet Excel export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: FA CS Entry - Data formatted for manual FA CS entry via RPA
            fa_cs_import_df.to_excel(writer, sheet_name='FA CS Entry', index=False)

            # Sheet 2: Audit Trail (full data with Book/State)
            audit_df.to_excel(writer, sheet_name='Audit Trail', index=False)

            # Sheet 3: Change Log - Shows what changed from original data
            change_log_df = self._build_change_log(df, export_df, assets)
            if change_log_df is not None and not change_log_df.empty:
                change_log_df.to_excel(writer, sheet_name='Change Log', index=False)
                # Apply formatting to Change Log sheet
                ws_changelog = writer.sheets['Change Log']
                _apply_professional_formatting(ws_changelog, change_log_df)

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

    def _build_change_log(self, original_df: pd.DataFrame, processed_df: pd.DataFrame, assets: List[Asset]) -> pd.DataFrame:
        """
        Build a change log showing what the engine modified from original data.

        Shows:
        - Asset identifier
        - Field that changed
        - Original value
        - New value
        - Reason for the change

        This helps CPAs verify and approve/deny engine decisions.
        """
        changes = []

        # Fields to track for changes (original column -> processed column mapping)
        tracked_fields = {
            # Classification changes
            "Final Category": {
                "original_col": "Final Category",
                "processed_col": "Final Category",
                "reason_fn": lambda orig, new, row: self._get_classification_reason(orig, new, row)
            },
            "Tax Life": {
                "original_col": "MACRS Life",
                "processed_col": "Tax Life",
                "reason_fn": lambda orig, new, row: f"MACRS life determined from '{row.get('Final Category', 'category')}' classification"
            },
            "Tax Method": {
                "original_col": "Method",
                "processed_col": "Tax Method",
                "reason_fn": lambda orig, new, row: "Standard MACRS method applied for FA CS compatibility"
            },
            "Convention": {
                "original_col": "Convention",
                "processed_col": "Convention",
                "reason_fn": lambda orig, new, row: self._get_convention_reason(orig, new, row)
            },
            # Wizard category (always computed, show if different from Final Category)
            "FA_CS_Wizard_Category": {
                "original_col": None,  # Computed field
                "processed_col": "FA_CS_Wizard_Category",
                "reason_fn": lambda orig, new, row: f"Mapped from '{row.get('Final Category', '')}' to FA CS wizard dropdown selection"
            },
        }

        # Also check for typo corrections from build_fa
        typo_fields = ["Desc_TypoFlag", "Desc_TypoNote", "Cat_TypoFlag", "Cat_TypoNote"]

        # Iterate through each asset
        for idx in range(len(original_df)):
            if idx >= len(processed_df):
                break

            orig_row = original_df.iloc[idx]
            proc_row = processed_df.iloc[idx]

            asset_num = proc_row.get("Asset #", orig_row.get("Asset #", idx + 1))
            description = proc_row.get("Description", orig_row.get("Description", ""))[:50]

            # Check each tracked field for changes
            for field_name, field_config in tracked_fields.items():
                orig_col = field_config["original_col"]
                proc_col = field_config["processed_col"]

                # Get original value
                if orig_col and orig_col in orig_row:
                    orig_val = orig_row[orig_col]
                else:
                    orig_val = None

                # Get processed value
                if proc_col in proc_row:
                    proc_val = proc_row[proc_col]
                else:
                    continue

                # Normalize values for comparison
                orig_str = self._normalize_value(orig_val)
                proc_str = self._normalize_value(proc_val)

                # Check if values are different
                if orig_str != proc_str and proc_str:  # Only log if there's a new value
                    # For computed fields (orig_col is None), always show
                    if orig_col is None or orig_str:
                        reason = field_config["reason_fn"](orig_val, proc_val, proc_row)
                        changes.append({
                            "Asset #": asset_num,
                            "Description": description,
                            "Field Changed": field_name,
                            "Original Value": orig_str if orig_str else "(not set)",
                            "New Value": proc_str,
                            "Reason": reason
                        })

            # Check for typo corrections
            if "Desc_TypoFlag" in proc_row.index and proc_row.get("Desc_TypoFlag"):
                changes.append({
                    "Asset #": asset_num,
                    "Description": description,
                    "Field Changed": "Description (Typo)",
                    "Original Value": proc_row.get("Desc_TypoNote", "").split(" → ")[0] if " → " in str(proc_row.get("Desc_TypoNote", "")) else "",
                    "New Value": proc_row.get("Desc_TypoNote", "").split(" → ")[1] if " → " in str(proc_row.get("Desc_TypoNote", "")) else proc_row.get("Desc_TypoNote", ""),
                    "Reason": "Automatic typo correction applied"
                })

            if "Cat_TypoFlag" in proc_row.index and proc_row.get("Cat_TypoFlag"):
                changes.append({
                    "Asset #": asset_num,
                    "Description": description,
                    "Field Changed": "Category (Typo)",
                    "Original Value": proc_row.get("Cat_TypoNote", "").split(" → ")[0] if " → " in str(proc_row.get("Cat_TypoNote", "")) else "",
                    "New Value": proc_row.get("Cat_TypoNote", "").split(" → ")[1] if " → " in str(proc_row.get("Cat_TypoNote", "")) else proc_row.get("Cat_TypoNote", ""),
                    "Reason": "Automatic category name correction applied"
                })

            # Check for Section 179/Bonus elections (computed values)
            sec179 = pd.to_numeric(proc_row.get("Tax Sec 179 Expensed", 0), errors='coerce') or 0
            bonus = pd.to_numeric(proc_row.get("Bonus Amount", 0), errors='coerce') or 0

            if sec179 > 0:
                changes.append({
                    "Asset #": asset_num,
                    "Description": description,
                    "Field Changed": "Section 179 Expensing",
                    "Original Value": "$0",
                    "New Value": f"${sec179:,.2f}",
                    "Reason": f"Section 179 election applied per depreciation strategy"
                })

            if bonus > 0:
                changes.append({
                    "Asset #": asset_num,
                    "Description": description,
                    "Field Changed": "Bonus Depreciation",
                    "Original Value": "$0",
                    "New Value": f"${bonus:,.2f}",
                    "Reason": f"Bonus depreciation calculated for eligible asset"
                })

            # Check for NBV reconciliation issues
            nbv_reco = proc_row.get("NBV_Reco", "")
            if nbv_reco == "CHECK":
                nbv_diff = proc_row.get("NBV_Diff", 0)
                changes.append({
                    "Asset #": asset_num,
                    "Description": description,
                    "Field Changed": "NBV Reconciliation",
                    "Original Value": "Client NBV",
                    "New Value": f"Difference: ${nbv_diff:,.2f}" if isinstance(nbv_diff, (int, float)) else str(nbv_diff),
                    "Reason": "NBV does not reconcile - CPA review required"
                })

        # If no changes, return a single-row dataframe explaining this
        if not changes:
            return pd.DataFrame([{
                "Asset #": "-",
                "Description": "No changes detected",
                "Field Changed": "-",
                "Original Value": "-",
                "New Value": "-",
                "Reason": "All values match between input and processed output"
            }])

        return pd.DataFrame(changes)

    def _normalize_value(self, val) -> str:
        """Normalize a value for comparison."""
        if val is None or pd.isna(val):
            return ""
        if isinstance(val, (int, float)):
            if val == 0:
                return ""
            return str(val)
        return str(val).strip()

    def _get_classification_reason(self, orig, new, row) -> str:
        """Get reason for classification change."""
        confidence = row.get("ConfidenceGrade", row.get("Confidence", ""))
        source = row.get("Source", "")
        explanation = row.get("ClassificationExplanation", "")

        if explanation:
            return explanation[:100]  # Truncate long explanations
        elif source:
            return f"Classification determined by {source} (confidence: {confidence})"
        else:
            return f"MACRS class assigned based on asset description analysis"

    def _get_convention_reason(self, orig, new, row) -> str:
        """Get reason for convention change."""
        category = str(row.get("Final Category", "")).lower()
        if "real" in category or "building" in category or "improvement" in category:
            return "Mid-month convention required for real property"
        elif "auto" in category or "vehicle" in category:
            return "Mid-quarter convention may apply (check 40% test)"
        else:
            return "Half-year convention applied (standard for personal property)"
