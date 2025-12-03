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

    def _format_asset_number(self, asset: Asset) -> int:
        """
        Format Asset # for FA CS - must be numeric.

        Priority:
        1. Use fa_cs_asset_number if explicitly set by CPA
        2. Extract numeric part from client's asset_id
        3. Fall back to row_index

        FA CS rules: 001 → 1, 0001 → 1, "A-001" → extract 1
        """
        # Priority 1: Use explicit FA CS number if set
        if asset.fa_cs_asset_number is not None:
            return asset.fa_cs_asset_number

        # Priority 2: Try to extract from client asset_id
        if asset.asset_id is not None:
            asset_str = str(asset.asset_id).strip()

            # Try to extract numeric value
            import re
            numeric_match = re.search(r'(\d+)', asset_str)

            if numeric_match:
                # Found numeric part - convert to int (strips leading zeros)
                return int(numeric_match.group(1))

        # Priority 3: Fall back to row index
        return asset.row_index

    def detect_asset_number_collisions(self, assets: List[Asset]) -> dict:
        """
        Detect collisions where multiple client Asset IDs would map to the same FA CS Asset #.

        Returns dict with:
        - collisions: List of collision groups [{fa_cs_number, assets: [{asset_id, description}]}]
        - warnings: List of warning messages
        - has_collisions: bool
        """
        # Map FA CS numbers to the assets that would use them
        fa_cs_to_assets = {}

        for asset in assets:
            fa_cs_num = self._format_asset_number(asset)
            if fa_cs_num not in fa_cs_to_assets:
                fa_cs_to_assets[fa_cs_num] = []
            fa_cs_to_assets[fa_cs_num].append({
                "unique_id": asset.unique_id,
                "client_asset_id": asset.asset_id,
                "description": asset.description[:50] if asset.description else "",
                "row_index": asset.row_index,
                "has_explicit_fa_cs_number": asset.fa_cs_asset_number is not None
            })

        # Find collisions (FA CS numbers used by multiple assets)
        collisions = []
        warnings = []

        for fa_cs_num, asset_list in fa_cs_to_assets.items():
            if len(asset_list) > 1:
                # Check if at least one doesn't have explicit FA CS number
                # (if all are explicit, user intentionally set them the same - still warn but different message)
                all_explicit = all(a["has_explicit_fa_cs_number"] for a in asset_list)

                collision = {
                    "fa_cs_number": fa_cs_num,
                    "asset_count": len(asset_list),
                    "assets": asset_list,
                    "all_explicit": all_explicit
                }
                collisions.append(collision)

                # Generate warning message
                asset_ids = [a["client_asset_id"] or f"Row {a['row_index']}" for a in asset_list]
                if all_explicit:
                    warnings.append(
                        f"⚠️ FA CS Asset # {fa_cs_num} is explicitly assigned to {len(asset_list)} assets: "
                        f"{', '.join(asset_ids[:3])}{'...' if len(asset_ids) > 3 else ''}. "
                        f"FA CS requires unique Asset #s."
                    )
                else:
                    warnings.append(
                        f"⚠️ COLLISION: Client Asset IDs {', '.join(asset_ids[:3])}{'...' if len(asset_ids) > 3 else ''} "
                        f"all map to FA CS Asset # {fa_cs_num}. "
                        f"Please assign unique FA CS numbers in Review table."
                    )

        return {
            "collisions": collisions,
            "warnings": warnings,
            "has_collisions": len(collisions) > 0,
            "collision_count": len(collisions),
            "affected_assets": sum(c["asset_count"] for c in collisions)
        }

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
        # Determine effective tax year FIRST (needed for transaction type classification)
        effective_tax_year = tax_year if tax_year else date.today().year

        # Prepare data for build_fa engine (uses specific column names)
        engine_data = []
        for asset in assets:
            # Detect transaction type first (with date-based classification)
            trans_type = self._detect_transaction_type(asset, effective_tax_year)

            row = {
                "Asset #": self._format_asset_number(asset),
                "Client Asset ID": str(asset.asset_id) if asset.asset_id else f"Row-{asset.row_index}",
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
                "Net Book Value": getattr(asset, 'net_book_value', None),
                "Gain/Loss": getattr(asset, 'gain_loss', None),

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

                # Depreciation Election (CPA decision for tax treatment)
                "Depreciation Election": getattr(asset, 'depreciation_election', 'MACRS') or 'MACRS',
                "Election Reason": getattr(asset, 'election_reason', '') or '',

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
        try:
            export_df = build_fa(
                df=df,
                tax_year=effective_tax_year,
                strategy="Balanced (Bonus Only)",
                taxable_income=10000000.0,  # High default to avoid limits
                use_acq_if_missing=True,
                de_minimis_limit=de_minimis_limit  # Pass de minimis threshold for safe harbor expensing
            )
        except Exception as e:
            # If build_fa fails, use the raw data with basic formatting
            print(f"Warning: build_fa failed ({e}), using raw data")
            export_df = df

        # ================================================================
        # MERGE ELECTION DATA - build_fa doesn't preserve these columns
        # ================================================================
        # Add election columns back from original df (build_fa drops them)
        if "Depreciation Election" in df.columns and "Depreciation Election" not in export_df.columns:
            export_df["Depreciation Election"] = df["Depreciation Election"].values
        if "Election Reason" in df.columns and "Election Reason" not in export_df.columns:
            export_df["Election Reason"] = df["Election Reason"].values

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

            # Depreciation Election (CPA decision)
            "Depreciation Election",
            "Election Reason",

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
        # SEPARATE DE MINIMIS ASSETS - These are expensed, not capitalized
        # ================================================================
        # De Minimis Safe Harbor items should NOT go into FA CS
        # They are immediate expenses, not depreciable assets
        de_minimis_mask = fa_cs_import_df["Depreciation Election"] == "DeMinimis"
        de_minimis_df = fa_cs_import_df[de_minimis_mask].copy()
        fa_cs_import_df = fa_cs_import_df[~de_minimis_mask].copy()

        # Create De Minimis Expenses sheet with expense account suggestions
        if not de_minimis_df.empty:
            de_minimis_expenses = []
            for _, row in de_minimis_df.iterrows():
                desc = str(row.get("Description", "")).lower()
                # Properly extract cost, handling None/NaN values
                cost_val = row.get("Tax Cost", 0)
                cost = float(cost_val) if pd.notna(cost_val) and cost_val else 0.0

                # Suggest expense account based on description
                if any(x in desc for x in ["computer", "laptop", "monitor", "keyboard", "mouse", "printer"]):
                    expense_account = "Computer Equipment Expense"
                elif any(x in desc for x in ["furniture", "desk", "chair", "cabinet", "shelf"]):
                    expense_account = "Furniture & Fixtures Expense"
                elif any(x in desc for x in ["phone", "tablet", "mobile"]):
                    expense_account = "Telecommunications Expense"
                elif any(x in desc for x in ["tool", "equipment"]):
                    expense_account = "Small Equipment Expense"
                else:
                    expense_account = "Office Supplies Expense"

                de_minimis_expenses.append({
                    "Description": row.get("Description", ""),
                    "Cost": cost,
                    "Date": row.get("Date In Service", ""),
                    "Suggested Expense Account": expense_account,
                    "Tax Treatment": "De Minimis Safe Harbor (Rev. Proc. 2015-20)",
                    "Note": "Expense immediately - DO NOT add to FA CS"
                })

            de_minimis_expenses_df = pd.DataFrame(de_minimis_expenses)
        else:
            de_minimis_expenses_df = None

        # ================================================================
        # AUDIT TRAIL SHEET - Full data for records
        # ================================================================
        audit_data = []
        for asset in assets:
            row = {
                "Asset #": self._format_asset_number(asset),
                "Client Asset ID": asset.asset_id,  # Keep original for reference
                "Description": asset.description,
                "Tax Cost": asset.cost,  # Use "Tax Cost" for FA CS consistency
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

                # Depreciation Election
                "Depreciation Election": getattr(asset, 'depreciation_election', 'MACRS') or 'MACRS',
                "Election Reason": getattr(asset, 'election_reason', '') or '',

                # Metadata
                "Confidence Score": asset.confidence_score,
                "Transaction Type": self._detect_transaction_type(asset, effective_tax_year),
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
            # NOTE: De Minimis items are EXCLUDED - they go to separate sheet
            fa_cs_import_df.to_excel(writer, sheet_name='FA CS Entry', index=False)

            # Sheet 2: De Minimis Expenses - Items to expense (NOT add to FA CS)
            if de_minimis_expenses_df is not None and not de_minimis_expenses_df.empty:
                de_minimis_expenses_df.to_excel(writer, sheet_name='De Minimis Expenses', index=False)
                # Add summary row
                ws_deminimis = writer.sheets['De Minimis Expenses']
                total_row = len(de_minimis_expenses_df) + 2
                ws_deminimis.cell(row=total_row, column=1, value="TOTAL TO EXPENSE:")
                ws_deminimis.cell(row=total_row, column=2, value=de_minimis_expenses_df['Cost'].sum())
                ws_deminimis.cell(row=total_row, column=1).font = ws_deminimis.cell(row=total_row, column=1).font.copy(bold=True)

            # =====================================================================
            # AUDIT PROTECTION SHEETS - Separate tabs by transaction type
            # =====================================================================

            # Split audit data by transaction type for clear audit trail
            # Handle multiple transaction type formats (e.g., "Addition", "Current Year Addition", "Existing Asset")
            if 'Transaction Type' in audit_df.columns:
                # Current Year Additions - assets placed in service in the tax year
                additions_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Addition|addition', case=False, na=False) &
                    ~audit_df['Transaction Type'].str.contains('Existing', case=False, na=False)
                ].copy()

                # Disposals - all disposal types
                disposals_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Disposal|disposal', case=False, na=False)
                ].copy()

                # Transfers - all transfer types
                transfers_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Transfer|transfer', case=False, na=False)
                ].copy()

                # Existing Assets - assets placed in service BEFORE the tax year
                existing_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Existing', case=False, na=False)
                ].copy()
            else:
                additions_df = pd.DataFrame()
                disposals_df = pd.DataFrame()
                transfers_df = pd.DataFrame()
                existing_df = audit_df.copy()

            # Sheet 3: Current Year Additions (for audit)
            if not additions_df.empty:
                additions_df.to_excel(writer, sheet_name='Current_Year_Addition', index=False)
                ws_add = writer.sheets['Current_Year_Addition']
                _apply_professional_formatting(ws_add, additions_df)

            # Sheet 4: Current Year Disposals (for audit) - WITH GAIN/LOSS INFO
            if not disposals_df.empty:
                # Ensure disposal-specific columns are included
                # Include both client-provided Gain/Loss and calculated recapture amounts
                disposal_cols = ['Asset #', 'Description', 'Date In Service', 'Tax Cost',
                                'Disposal Date', 'Proceeds', 'Gross Proceeds', 'Accumulated Depreciation',
                                'Net Book Value', 'Gain/Loss',
                                'Adjusted Basis at Disposal', '§1245 Recapture', '§1250 Recapture',
                                'Capital Gain/Loss', 'Transaction Type', 'Confidence Score']
                # Only keep columns that exist
                disposal_cols = [c for c in disposal_cols if c in disposals_df.columns]
                disposals_export = disposals_df[disposal_cols] if disposal_cols else disposals_df
                disposals_export.to_excel(writer, sheet_name='Current_Year_Disposal', index=False)
                ws_disp = writer.sheets['Current_Year_Disposal']
                _apply_professional_formatting(ws_disp, disposals_export)

            # Sheet 5: Transfers (for audit)
            if not transfers_df.empty:
                transfer_cols = ['Asset #', 'Description', 'Date In Service', 'Tax Cost',
                                'Transfer Date', 'From Location', 'To Location',
                                'Transaction Type', 'Confidence Score']
                transfer_cols = [c for c in transfer_cols if c in transfers_df.columns]
                transfers_export = transfers_df[transfer_cols] if transfer_cols else transfers_df
                transfers_export.to_excel(writer, sheet_name='Transfers', index=False)
                ws_trans = writer.sheets['Transfers']
                _apply_professional_formatting(ws_trans, transfers_export)

            # Sheet 6: Existing Assets (no action needed - prior year assets)
            if not existing_df.empty:
                existing_df.to_excel(writer, sheet_name='Existing_Asset', index=False)
                ws_exist = writer.sheets['Existing_Asset']
                _apply_professional_formatting(ws_exist, existing_df)

            # Sheet 7: Full Audit Trail (all data for complete audit record)
            audit_df.to_excel(writer, sheet_name='Audit Trail', index=False)

            # Sheet 8: Change Log - Shows what changed from original data
            change_log_df = self._build_change_log(df, export_df, assets)
            if change_log_df is not None and not change_log_df.empty:
                change_log_df.to_excel(writer, sheet_name='Change Log', index=False)
                # Apply formatting to Change Log sheet
                ws_changelog = writer.sheets['Change Log']
                _apply_professional_formatting(ws_changelog, change_log_df)

            # Sheet 9: Summary - Quick overview for CPA review
            # Calculate disposal gain/loss totals
            disposal_gain_loss = 0
            if not disposals_df.empty:
                if 'Gain/Loss' in disposals_df.columns:
                    disposal_gain_loss = disposals_df['Gain/Loss'].sum()
                elif 'Capital Gain/Loss' in disposals_df.columns:
                    disposal_gain_loss = disposals_df['Capital Gain/Loss'].sum()

            summary_data = {
                'Category': ['Current Year Additions', 'Current Year Disposals', 'Transfers', 'Existing Assets', 'De Minimis Expenses', 'TOTAL'],
                'Count': [
                    len(additions_df),
                    len(disposals_df),
                    len(transfers_df),
                    len(existing_df),
                    len(de_minimis_expenses_df) if de_minimis_expenses_df is not None else 0,
                    len(audit_df)
                ],
                'Total Cost': [
                    additions_df['Tax Cost'].sum() if 'Tax Cost' in additions_df.columns and not additions_df.empty else 0,
                    disposals_df['Tax Cost'].sum() if 'Tax Cost' in disposals_df.columns and not disposals_df.empty else 0,
                    transfers_df['Tax Cost'].sum() if 'Tax Cost' in transfers_df.columns and not transfers_df.empty else 0,
                    existing_df['Tax Cost'].sum() if 'Tax Cost' in existing_df.columns and not existing_df.empty else 0,
                    de_minimis_expenses_df['Cost'].sum() if de_minimis_expenses_df is not None and not de_minimis_expenses_df.empty else 0,
                    audit_df['Tax Cost'].sum() if 'Tax Cost' in audit_df.columns else 0
                ],
                'Gain/Loss': [
                    0,  # Additions
                    disposal_gain_loss,  # Disposals
                    0,  # Transfers
                    0,  # Existing
                    0,  # De Minimis
                    disposal_gain_loss  # Total
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

        output.seek(0)
        return output

    def _detect_transaction_type(self, asset: Asset, tax_year: int = None) -> str:
        """
        Detect transaction type from asset attributes with proper date-based classification.

        CRITICAL: Properly distinguishes between:
        - "Current Year Addition" - asset placed in service in tax year (eligible for Sec 179/Bonus)
        - "Existing Asset" - asset placed in service BEFORE tax year (NOT eligible for Sec 179/Bonus)
        - "Disposal" - asset disposed/sold
        - "Transfer" - asset transferred between locations/departments

        Args:
            asset: The Asset object
            tax_year: Current tax year for date-based classification

        Returns:
            Transaction type string
        """
        # First, check if asset already has a valid transaction_type set
        existing_type = getattr(asset, 'transaction_type', None)
        if existing_type and existing_type.lower() not in ['', 'addition', 'unknown']:
            # Use the pre-classified type (from transaction_classifier)
            # Normalize casing for consistency
            type_lower = existing_type.lower()
            if 'existing' in type_lower:
                return "Existing Asset"
            elif 'current year addition' in type_lower or type_lower == 'current year addition':
                return "Current Year Addition"
            elif 'disposal' in type_lower:
                return "Disposal"
            elif 'transfer' in type_lower:
                return "Transfer"

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

        # Date-based classification: Current Year Addition vs Existing Asset
        if tax_year:
            in_service = getattr(asset, 'in_service_date', None)
            acquisition = getattr(asset, 'acquisition_date', None)
            effective_date = in_service or acquisition

            if effective_date:
                # Get year from date object
                if hasattr(effective_date, 'year'):
                    asset_year = effective_date.year
                    if asset_year == tax_year:
                        return "Current Year Addition"
                    elif asset_year < tax_year:
                        return "Existing Asset"

        # Default to Current Year Addition only if no date info available
        return "Current Year Addition"

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

            # Check for Depreciation Election (CPA decision)
            election = proc_row.get("Depreciation Election", "MACRS")
            election_reason = proc_row.get("Election Reason", "")
            if election and election != "MACRS":
                changes.append({
                    "Asset #": asset_num,
                    "Description": description,
                    "Field Changed": "Depreciation Election",
                    "Original Value": "MACRS (default)",
                    "New Value": election,
                    "Reason": election_reason if election_reason else f"{election} election selected"
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
