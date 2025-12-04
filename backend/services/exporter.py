import pandas as pd
from io import BytesIO
from typing import List
from datetime import date, datetime
from backend.models.asset import Asset
from backend.logic.fa_export import build_fa, export_fa_excel
from backend.logic.fa_export_formatters import _apply_professional_formatting


class ExporterService:
    """
    Generates Excel workpapers for Fixed Assets CS.

    TWO SEPARATE EXPORTS (Option B - Industry Standard):
    =====================================================

    1. FA CS PREP WORKPAPER (generate_fa_cs_prep_workpaper)
       Purpose: Data entry prep, review, and quality control
       Audience: Staff/Senior preparing FA CS entries
       Sheets:
       - FA CS Entry: Core fields needed for FA CS software input
       - De Minimis Expenses: Items to expense (not add to FA CS)
       - Items Requiring Review: Low confidence, missing data flags
       - Summary: Quick counts and totals

    2. AUDIT DOCUMENTATION (generate_audit_workpaper)
       Purpose: Complete audit trail and workpaper documentation
       Audience: Managers/Partners for review; Auditors for testing
       Sheets:
       - Complete Asset Schedule: ALL assets, ALL fields (Tax/Book/State)
       - Change Log: What changed from original data with reasons
       - Summary: Counts and totals with Tax vs Book reconciliation

    FA CS REQUIRED COLUMNS:
    - Asset #, Description, Date In Service, Tax Cost
    - Tax Method, Tax Life, FA_CS_Wizard_Category

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

                # FA CS Wizard Category - the exact dropdown text for RPA automation
                # This is the category shown in FA CS software's asset wizard
                "FA_CS_Wizard_Category": getattr(asset, 'fa_cs_wizard_category', None),

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
            export_df = df.copy()
            # Normalize column names to match what FA CS expects
            # build_fa renames these columns, so we need to do it manually in fallback
            column_renames = {
                "Cost": "Tax Cost",
                "In Service Date": "Date In Service",
                "MACRS Life": "Tax Life",
                "Method": "Tax Method",
            }
            for old_col, new_col in column_renames.items():
                if old_col in export_df.columns and new_col not in export_df.columns:
                    export_df[new_col] = export_df[old_col]

        # ================================================================
        # MERGE ELECTION DATA - build_fa doesn't preserve these columns
        # ================================================================
        # Add election columns back from original df (build_fa drops them)
        if "Depreciation Election" in df.columns and "Depreciation Election" not in export_df.columns:
            export_df["Depreciation Election"] = df["Depreciation Election"].values
        if "Election Reason" in df.columns and "Election Reason" not in export_df.columns:
            export_df["Election Reason"] = df["Election Reason"].values

        # ================================================================
        # FA CS IMPORT SHEET - ONLY what FA CS software requires
        # ================================================================
        # These are the exact fields needed to enter assets into FA CS software.
        # Election Reason is NOT included - it's internal audit documentation,
        # not something FA CS needs. See Audit Trail sheet for full documentation.
        fa_cs_import_cols = [
            # Core required fields for FA CS entry
            "Asset #",
            "Description",
            "Date In Service",
            "Tax Cost",
            "Tax Method",
            "Tax Life",
            "Convention",

            # FA CS Asset Category - EXACT wizard dropdown text for RPA automation
            # This maps to FA CS's asset category dropdown (e.g., "Computer Equipment")
            "FA_CS_Wizard_Category",

            # Section 179/Prior depreciation (if applicable)
            "Tax Sec 179 Expensed",
            "Tax Prior Depreciation",

            # Transaction type for CPA to know what action to take
            "Transaction Type",
        ]

        # ================================================================
        # SEPARATE DE MINIMIS ASSETS - These are expensed, not capitalized
        # ================================================================
        # De Minimis Safe Harbor items should NOT go into FA CS
        # They are immediate expenses, not depreciable assets
        # NOTE: Filter on export_df FIRST (which has Depreciation Election), then select columns
        if "Depreciation Election" in export_df.columns:
            de_minimis_mask = export_df["Depreciation Election"] == "DeMinimis"
            de_minimis_df = export_df[de_minimis_mask].copy()
            non_de_minimis_df = export_df[~de_minimis_mask].copy()
        else:
            de_minimis_df = pd.DataFrame()
            non_de_minimis_df = export_df.copy()

        # Select available columns for FA CS Entry (only non-De Minimis assets)
        available_cols = [c for c in fa_cs_import_cols if c in non_de_minimis_df.columns]
        fa_cs_import_df = non_de_minimis_df[available_cols].copy()

        # Create De Minimis Expenses sheet with expense account suggestions
        if not de_minimis_df.empty:
            de_minimis_expenses = []
            for _, row in de_minimis_df.iterrows():
                desc = str(row.get("Description", "")).lower()
                # Properly extract cost, handling None/NaN values and different column names
                cost_val = row.get("Tax Cost", row.get("Cost", 0))
                cost = float(cost_val) if pd.notna(cost_val) and cost_val else 0.0

                # Get date (handle different column names from build_fa vs raw data)
                date_val = row.get("Date In Service", row.get("In Service Date", ""))

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
                    "Date": date_val,
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
                "Gain/Loss": getattr(asset, 'gain_loss', None),

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
            ws_facs = writer.sheets['FA CS Entry']
            _apply_professional_formatting(ws_facs, fa_cs_import_df)

            # Sheet 2: De Minimis Expenses - Items to expense (NOT add to FA CS)
            if de_minimis_expenses_df is not None and not de_minimis_expenses_df.empty:
                de_minimis_expenses_df.to_excel(writer, sheet_name='De Minimis Expenses', index=False)
                ws_deminimis = writer.sheets['De Minimis Expenses']
                _apply_professional_formatting(ws_deminimis, de_minimis_expenses_df)
                # Add summary row after formatting
                total_row = len(de_minimis_expenses_df) + 2
                ws_deminimis.cell(row=total_row, column=1, value="TOTAL TO EXPENSE:")
                ws_deminimis.cell(row=total_row, column=2, value=de_minimis_expenses_df['Cost'].sum())
                ws_deminimis.cell(row=total_row, column=1).font = ws_deminimis.cell(row=total_row, column=1).font.copy(bold=True)

            # =====================================================================
            # AUDIT PROTECTION SHEETS - Separate tabs by transaction type
            # =====================================================================

            # Split audit data by transaction type for clear audit trail
            # Handle multiple transaction type formats (e.g., "Addition", "Current Year Addition", "Existing Asset")
            # IMPORTANT: Exclude De Minimis assets from Current_Year_Addition - they're expensed, not capitalized
            if 'Transaction Type' in audit_df.columns:
                # De Minimis mask for audit_df (these go to separate De Minimis sheet only)
                is_de_minimis = audit_df['Depreciation Election'] == 'DeMinimis' if 'Depreciation Election' in audit_df.columns else pd.Series([False] * len(audit_df))

                # Current Year Additions - assets placed in service in the tax year
                # EXCLUDES De Minimis items (they're expensed, not added to FA CS)
                additions_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Addition|addition', case=False, na=False) &
                    ~audit_df['Transaction Type'].str.contains('Existing', case=False, na=False) &
                    ~is_de_minimis
                ].copy()

                # Disposals - all disposal types (De Minimis items are not typically disposed)
                disposals_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Disposal|disposal', case=False, na=False)
                ].copy()

                # Transfers - all transfer types
                transfers_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Transfer|transfer', case=False, na=False)
                ].copy()

                # Existing Assets - assets placed in service BEFORE the tax year
                # EXCLUDES De Minimis items
                existing_df = audit_df[
                    audit_df['Transaction Type'].str.contains('Existing', case=False, na=False) &
                    ~is_de_minimis
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
            ws_audit = writer.sheets['Audit Trail']
            _apply_professional_formatting(ws_audit, audit_df)

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
            ws_summary = writer.sheets['Summary']
            _apply_professional_formatting(ws_summary, summary_df)

        output.seek(0)
        return output

    # ========================================================================
    # OPTION B: TWO SEPARATE EXPORTS (Industry Standard)
    # ========================================================================

    def generate_fa_cs_prep_workpaper(self, assets: List[Asset], tax_year: int = None,
                                       de_minimis_limit: float = 0.0) -> BytesIO:
        """
        Generate FA CS PREP WORKPAPER - for data entry prep and review.

        Purpose: Staff/Senior preparing FA CS entries uses this for:
        - Data entry into FA CS software
        - Quality control before entry
        - Identifying items needing attention

        Sheets (separated by action type):
        1. Addition Entry - ONLY Current Year Additions for FA CS input
        2. Disposal Entry - Disposals with Method, Proceeds, Gain/Loss
        3. Transfer Entry - Transfers with From/To locations
        4. De Minimis Expenses - Items to expense immediately (not add to FA CS)
        5. Items Requiring Review - Low confidence, missing data, warnings
        """
        effective_tax_year = tax_year if tax_year else date.today().year

        # Prepare data using build_fa engine
        engine_data = []
        for asset in assets:
            trans_type = self._detect_transaction_type(asset, effective_tax_year)
            row = self._build_engine_row(asset, trans_type, effective_tax_year)
            engine_data.append(row)

        df = pd.DataFrame(engine_data)

        # Process through build_fa for full calculations
        try:
            export_df = build_fa(
                df=df,
                tax_year=effective_tax_year,
                strategy="Balanced (Bonus Only)",
                taxable_income=10000000.0,
                use_acq_if_missing=True,
                de_minimis_limit=de_minimis_limit
            )
        except Exception as e:
            print(f"Warning: build_fa failed ({e}), using raw data")
            export_df = df.copy()
            self._normalize_columns(export_df)

        # Merge election data back
        if "Depreciation Election" in df.columns and "Depreciation Election" not in export_df.columns:
            export_df["Depreciation Election"] = df["Depreciation Election"].values
        # Merge Gain/Loss data back (build_fa may not preserve this)
        if "Gain/Loss" in df.columns and "Gain/Loss" not in export_df.columns:
            export_df["Gain/Loss"] = df["Gain/Loss"].values
        if "Proceeds" in df.columns and "Proceeds" not in export_df.columns:
            export_df["Proceeds"] = df["Proceeds"].values
        if "Disposal Date" in df.columns and "Disposal Date" not in export_df.columns:
            export_df["Disposal Date"] = df["Disposal Date"].values
        if "Transfer Date" in df.columns and "Transfer Date" not in export_df.columns:
            export_df["Transfer Date"] = df["Transfer Date"].values
        if "From Location" in df.columns and "From Location" not in export_df.columns:
            export_df["From Location"] = df["From Location"].values
        if "To Location" in df.columns and "To Location" not in export_df.columns:
            export_df["To Location"] = df["To Location"].values

        # ================================================================
        # SEPARATE BY TRANSACTION TYPE
        # ================================================================

        # De Minimis assets (expense, not capitalize)
        if "Depreciation Election" in export_df.columns:
            de_minimis_mask = export_df["Depreciation Election"] == "DeMinimis"
            de_minimis_df = export_df[de_minimis_mask].copy()
            non_de_minimis_df = export_df[~de_minimis_mask].copy()
        else:
            de_minimis_df = pd.DataFrame()
            non_de_minimis_df = export_df.copy()

        # Helper to check transaction type
        def is_addition(trans_type):
            if not trans_type:
                return False
            t = str(trans_type).lower()
            return 'addition' in t and 'existing' not in t

        def is_disposal(trans_type):
            if not trans_type:
                return False
            return 'disposal' in str(trans_type).lower()

        def is_transfer(trans_type):
            if not trans_type:
                return False
            return 'transfer' in str(trans_type).lower()

        def is_existing(trans_type):
            if not trans_type:
                return False
            return 'existing' in str(trans_type).lower()

        # Split by transaction type
        if 'Transaction Type' in non_de_minimis_df.columns:
            additions_mask = non_de_minimis_df['Transaction Type'].apply(is_addition)
            disposals_mask = non_de_minimis_df['Transaction Type'].apply(is_disposal)
            transfers_mask = non_de_minimis_df['Transaction Type'].apply(is_transfer)
            existing_mask = non_de_minimis_df['Transaction Type'].apply(is_existing)

            additions_df = non_de_minimis_df[additions_mask].copy()
            disposals_df = non_de_minimis_df[disposals_mask].copy()
            transfers_df = non_de_minimis_df[transfers_mask].copy()
            existing_df = non_de_minimis_df[existing_mask].copy()
        else:
            additions_df = non_de_minimis_df.copy()
            disposals_df = pd.DataFrame()
            transfers_df = pd.DataFrame()
            existing_df = pd.DataFrame()

        # ================================================================
        # SHEET 1: ADDITION ENTRY (ONLY Current Year Additions)
        # ================================================================
        addition_entry_cols = [
            "Asset #",
            "Client Asset ID",
            "Description",
            "Date In Service",
            "Tax Cost",
            "Tax Method",
            "Tax Life",
            "Convention",
            "FA_CS_Wizard_Category",
            "Tax Sec 179 Expensed",
        ]
        available_cols = [c for c in addition_entry_cols if c in additions_df.columns]
        addition_entry_df = additions_df[available_cols].copy() if not additions_df.empty else pd.DataFrame(columns=available_cols)

        # ================================================================
        # SHEET 2: DISPOSAL ENTRY (with proper FA CS disposal fields)
        # ================================================================
        disposal_entry_df = self._build_disposal_entry_sheet(disposals_df, assets, effective_tax_year)

        # ================================================================
        # SHEET 3: TRANSFER ENTRY
        # ================================================================
        transfer_entry_df = self._build_transfer_entry_sheet(transfers_df)

        # ================================================================
        # SHEET 4: DE MINIMIS EXPENSES
        # ================================================================
        de_minimis_expenses_df = self._build_de_minimis_sheet(de_minimis_df)

        # ================================================================
        # SHEET 5: EXISTING ASSETS (for FA CS reconciliation/tie-out)
        # ================================================================
        existing_assets_df = self._build_existing_assets_sheet(existing_df)

        # ================================================================
        # SHEET 6: ITEMS REQUIRING REVIEW
        # ================================================================
        items_requiring_review_df = self._build_items_requiring_review(assets, export_df, effective_tax_year)

        # ================================================================
        # SHEET 7: SUMMARY (for FA CS reconciliation)
        # ================================================================
        summary_df = self._build_reconciliation_summary(
            additions_df, disposals_df, transfers_df, existing_df,
            de_minimis_df, disposal_entry_df, effective_tax_year
        )

        # Generate Excel workbook
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Addition Entry (Current Year Additions ONLY)
            if not addition_entry_df.empty:
                addition_entry_df.to_excel(writer, sheet_name='Addition Entry', index=False)
                ws_entry = writer.sheets['Addition Entry']
                _apply_professional_formatting(ws_entry, addition_entry_df)
            else:
                # Create placeholder sheet if no additions
                pd.DataFrame([{"Note": "No Current Year Additions"}]).to_excel(
                    writer, sheet_name='Addition Entry', index=False)

            # Sheet 2: Disposal Entry
            if disposal_entry_df is not None and not disposal_entry_df.empty:
                disposal_entry_df.to_excel(writer, sheet_name='Disposal Entry', index=False)
                ws_disposal = writer.sheets['Disposal Entry']
                _apply_professional_formatting(ws_disposal, disposal_entry_df)
                # Add gain/loss total
                if 'Gain/Loss' in disposal_entry_df.columns:
                    total_row = len(disposal_entry_df) + 2
                    ws_disposal.cell(row=total_row, column=1, value="TOTAL GAIN/(LOSS):")
                    gain_loss_col = list(disposal_entry_df.columns).index('Gain/Loss') + 1
                    total_gain_loss = disposal_entry_df['Gain/Loss'].sum()
                    ws_disposal.cell(row=total_row, column=gain_loss_col, value=total_gain_loss)
                    ws_disposal.cell(row=total_row, column=1).font = ws_disposal.cell(row=total_row, column=1).font.copy(bold=True)

            # Sheet 3: Transfer Entry
            if transfer_entry_df is not None and not transfer_entry_df.empty:
                transfer_entry_df.to_excel(writer, sheet_name='Transfer Entry', index=False)
                ws_transfer = writer.sheets['Transfer Entry']
                _apply_professional_formatting(ws_transfer, transfer_entry_df)

            # Sheet 4: De Minimis Expenses
            if de_minimis_expenses_df is not None and not de_minimis_expenses_df.empty:
                de_minimis_expenses_df.to_excel(writer, sheet_name='De Minimis Expenses', index=False)
                ws_deminimis = writer.sheets['De Minimis Expenses']
                _apply_professional_formatting(ws_deminimis, de_minimis_expenses_df)
                # Add total row
                total_row = len(de_minimis_expenses_df) + 2
                ws_deminimis.cell(row=total_row, column=1, value="TOTAL TO EXPENSE:")
                ws_deminimis.cell(row=total_row, column=2, value=de_minimis_expenses_df['Cost'].sum())
                ws_deminimis.cell(row=total_row, column=1).font = ws_deminimis.cell(row=total_row, column=1).font.copy(bold=True)

            # Sheet 5: Existing Assets (for FA CS tie-out)
            if existing_assets_df is not None and not existing_assets_df.empty:
                existing_assets_df.to_excel(writer, sheet_name='Existing Assets', index=False)
                ws_existing = writer.sheets['Existing Assets']
                _apply_professional_formatting(ws_existing, existing_assets_df)
                # Add totals row
                total_row = len(existing_assets_df) + 2
                ws_existing.cell(row=total_row, column=1, value="TOTALS:")
                if 'Tax Cost' in existing_assets_df.columns:
                    cost_col = list(existing_assets_df.columns).index('Tax Cost') + 1
                    ws_existing.cell(row=total_row, column=cost_col, value=existing_assets_df['Tax Cost'].sum())
                if 'Accum. Depreciation' in existing_assets_df.columns:
                    accum_col = list(existing_assets_df.columns).index('Accum. Depreciation') + 1
                    ws_existing.cell(row=total_row, column=accum_col, value=existing_assets_df['Accum. Depreciation'].sum())
                ws_existing.cell(row=total_row, column=1).font = ws_existing.cell(row=total_row, column=1).font.copy(bold=True)

            # Sheet 6: Items Requiring Review
            if items_requiring_review_df is not None and not items_requiring_review_df.empty:
                items_requiring_review_df.to_excel(writer, sheet_name='Items Requiring Review', index=False)
                ws_review = writer.sheets['Items Requiring Review']
                _apply_professional_formatting(ws_review, items_requiring_review_df)

            # Sheet 7: Summary (for FA CS reconciliation)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            ws_summary = writer.sheets['Summary']
            _apply_professional_formatting(ws_summary, summary_df)

        output.seek(0)
        return output

    def generate_audit_workpaper(self, assets: List[Asset], tax_year: int = None,
                                  de_minimis_limit: float = 0.0) -> BytesIO:
        """
        Generate AUDIT DOCUMENTATION - for complete audit trail.

        Purpose: Managers/Partners and Auditors use this for:
        - Complete workpaper documentation
        - Audit trail of all decisions
        - Tax vs Book vs State reconciliation

        Sheets:
        1. Complete Asset Schedule - ALL assets with ALL fields (Tax/Book/State)
        2. Change Log - What changed from original data with reasons
        3. Summary - Counts, totals, and reconciliation
        """
        effective_tax_year = tax_year if tax_year else date.today().year

        # Prepare data using build_fa engine
        engine_data = []
        for asset in assets:
            trans_type = self._detect_transaction_type(asset, effective_tax_year)
            row = self._build_engine_row(asset, trans_type, effective_tax_year)
            engine_data.append(row)

        df = pd.DataFrame(engine_data)

        # Process through build_fa for full calculations
        try:
            export_df = build_fa(
                df=df,
                tax_year=effective_tax_year,
                strategy="Balanced (Bonus Only)",
                taxable_income=10000000.0,
                use_acq_if_missing=True,
                de_minimis_limit=de_minimis_limit
            )
        except Exception as e:
            print(f"Warning: build_fa failed ({e}), using raw data")
            export_df = df.copy()
            self._normalize_columns(export_df)

        # Merge election data back
        if "Depreciation Election" in df.columns and "Depreciation Election" not in export_df.columns:
            export_df["Depreciation Election"] = df["Depreciation Election"].values
        if "Election Reason" in df.columns and "Election Reason" not in export_df.columns:
            export_df["Election Reason"] = df["Election Reason"].values

        # ================================================================
        # SHEET 1: COMPLETE ASSET SCHEDULE (ALL assets, ALL fields)
        # ================================================================
        complete_schedule_df = self._build_complete_asset_schedule(assets, effective_tax_year)

        # ================================================================
        # SHEET 2: CHANGE LOG
        # ================================================================
        change_log_df = self._build_change_log(df, export_df, assets)

        # ================================================================
        # SHEET 3: SUMMARY with Transaction Type Breakdown
        # ================================================================
        summary_df = self._build_audit_summary(complete_schedule_df, effective_tax_year)

        # Generate Excel workbook
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Complete Asset Schedule
            complete_schedule_df.to_excel(writer, sheet_name='Complete Asset Schedule', index=False)
            ws_schedule = writer.sheets['Complete Asset Schedule']
            _apply_professional_formatting(ws_schedule, complete_schedule_df)

            # Sheet 2: Change Log
            if change_log_df is not None and not change_log_df.empty:
                change_log_df.to_excel(writer, sheet_name='Change Log', index=False)
                ws_changelog = writer.sheets['Change Log']
                _apply_professional_formatting(ws_changelog, change_log_df)

            # Sheet 3: Summary
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            ws_summary = writer.sheets['Summary']
            _apply_professional_formatting(ws_summary, summary_df)

        output.seek(0)
        return output

    def generate_both_workpapers(self, assets: List[Asset], tax_year: int = None,
                                  de_minimis_limit: float = 0.0) -> dict:
        """
        Generate BOTH workpapers (convenience method).

        Returns:
            dict with keys:
            - 'prep_workpaper': BytesIO of FA CS Prep Workpaper
            - 'audit_workpaper': BytesIO of Audit Documentation
        """
        return {
            'prep_workpaper': self.generate_fa_cs_prep_workpaper(assets, tax_year, de_minimis_limit),
            'audit_workpaper': self.generate_audit_workpaper(assets, tax_year, de_minimis_limit)
        }

    # ========================================================================
    # HELPER METHODS FOR NEW EXPORTS
    # ========================================================================

    def _build_engine_row(self, asset: Asset, trans_type: str, tax_year: int) -> dict:
        """Build a row for the build_fa engine from an Asset object."""
        return {
            "Asset #": self._format_asset_number(asset),
            "Client Asset ID": str(asset.asset_id) if asset.asset_id else f"Row-{asset.row_index}",
            "Description": asset.description,
            "Acquisition Date": asset.acquisition_date,
            "In Service Date": asset.in_service_date if asset.in_service_date else asset.acquisition_date,
            "Cost": asset.cost if asset.cost else 0.0,
            "Final Category": asset.macrs_class if asset.macrs_class else "Unclassified",
            "MACRS Life": asset.macrs_life,
            "Recovery Period": asset.macrs_life,
            "Method": asset.macrs_method,
            "Convention": asset.macrs_convention,
            "FA_CS_Wizard_Category": getattr(asset, 'fa_cs_wizard_category', None),
            "Disposal Date": getattr(asset, 'disposal_date', None),
            "Proceeds": getattr(asset, 'proceeds', None) or getattr(asset, 'sale_price', None),
            "Accumulated Depreciation": getattr(asset, 'accumulated_depreciation', 0.0) or 0.0,
            "Net Book Value": getattr(asset, 'net_book_value', None),
            "Gain/Loss": getattr(asset, 'gain_loss', None),
            "From Location": getattr(asset, 'from_location', None),
            "To Location": getattr(asset, 'to_location', None),
            "Transfer Date": getattr(asset, 'transfer_date', None),
            "Transaction Type": trans_type,
            "Confidence": asset.confidence_score,
            "Source": "rules",
            "Business Use %": 1.0,
            "Tax Year": tax_year,
            "Depreciation Election": getattr(asset, 'depreciation_election', 'MACRS') or 'MACRS',
            "Election Reason": getattr(asset, 'election_reason', '') or '',
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

    def _normalize_columns(self, df: pd.DataFrame) -> None:
        """Normalize column names when build_fa fails (fallback)."""
        column_renames = {
            "Cost": "Tax Cost",
            "In Service Date": "Date In Service",
            "MACRS Life": "Tax Life",
            "Method": "Tax Method",
        }
        for old_col, new_col in column_renames.items():
            if old_col in df.columns and new_col not in df.columns:
                df[new_col] = df[old_col]

    def _build_de_minimis_sheet(self, de_minimis_df: pd.DataFrame) -> pd.DataFrame:
        """Build De Minimis Expenses sheet with expense account suggestions."""
        if de_minimis_df.empty:
            return None

        de_minimis_expenses = []
        for _, row in de_minimis_df.iterrows():
            desc = str(row.get("Description", "")).lower()
            cost_val = row.get("Tax Cost", row.get("Cost", 0))
            cost = float(cost_val) if pd.notna(cost_val) and cost_val else 0.0
            date_val = row.get("Date In Service", row.get("In Service Date", ""))

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
                "Date": date_val,
                "Suggested Expense Account": expense_account,
                "Tax Treatment": "De Minimis Safe Harbor (Rev. Proc. 2015-20)",
                "Note": "Expense immediately - DO NOT add to FA CS"
            })

        return pd.DataFrame(de_minimis_expenses)

    def _build_disposal_entry_sheet(self, disposals_df: pd.DataFrame, assets: List[Asset],
                                     tax_year: int) -> pd.DataFrame:
        """
        Build Disposal Entry sheet with FA CS disposal fields.

        FA CS Disposal Requirements:
        - Asset # (to identify which asset is being disposed)
        - Description (for reference)
        - Original Cost (Tax Cost)
        - Date In Service (original)
        - Disposal Date
        - Disposal Method: Sold, Scrapped, Abandoned, Traded, Converted to Personal Use
        - Proceeds (sale price, 0 if scrapped/abandoned)
        - Accumulated Depreciation
        - Gain/Loss (calculated)
        """
        if disposals_df.empty:
            return None

        # Standard FA CS disposal methods
        DISPOSAL_METHODS = ["Sold", "Scrapped", "Abandoned", "Traded", "Converted to Personal Use"]

        disposal_entries = []
        for _, row in disposals_df.iterrows():
            # Get values with fallbacks
            asset_num = row.get("Asset #", "")
            client_id = row.get("Client Asset ID", "")
            description = row.get("Description", "")
            tax_cost = row.get("Tax Cost", row.get("Cost", 0)) or 0
            date_in_service = row.get("Date In Service", row.get("In Service Date", ""))
            disposal_date = row.get("Disposal Date", "")
            proceeds = row.get("Proceeds", row.get("Gross Proceeds", 0)) or 0
            accum_depr = row.get("Accumulated Depreciation", 0) or 0
            gain_loss = row.get("Gain/Loss", row.get("Capital Gain/Loss", None))

            # Calculate gain/loss if not provided
            if gain_loss is None and tax_cost and proceeds is not None:
                # Gain/Loss = Proceeds - (Cost - Accumulated Depreciation)
                adjusted_basis = float(tax_cost) - float(accum_depr)
                gain_loss = float(proceeds) - adjusted_basis

            # Determine disposal method from description/data
            desc_lower = str(description).lower()
            if any(x in desc_lower for x in ["sold", "sale"]):
                disposal_method = "Sold"
            elif any(x in desc_lower for x in ["scrap", "junk", "discard"]):
                disposal_method = "Scrapped"
            elif any(x in desc_lower for x in ["abandon", "written off"]):
                disposal_method = "Abandoned"
            elif any(x in desc_lower for x in ["trade", "exchange"]):
                disposal_method = "Traded"
            elif any(x in desc_lower for x in ["personal", "convert"]):
                disposal_method = "Converted to Personal Use"
            elif proceeds and float(proceeds) > 0:
                disposal_method = "Sold"  # Default to Sold if there are proceeds
            else:
                disposal_method = "Scrapped"  # Default to Scrapped if no proceeds

            disposal_entries.append({
                "Asset #": asset_num,
                "Client Asset ID": client_id,
                "Description": description,
                "Original Cost": tax_cost,
                "Date In Service": date_in_service,
                "Disposal Date": disposal_date,
                "Disposal Method": disposal_method,
                "Proceeds": proceeds,
                "Accum. Depreciation": accum_depr,
                "Gain/Loss": gain_loss,
            })

        return pd.DataFrame(disposal_entries)

    def _build_transfer_entry_sheet(self, transfers_df: pd.DataFrame) -> pd.DataFrame:
        """
        Build Transfer Entry sheet for asset transfers.

        Transfer Entry Fields:
        - Asset # (to identify which asset is being transferred)
        - Description
        - Transfer Date
        - From Location/Department
        - To Location/Department
        - Notes
        """
        if transfers_df.empty:
            return None

        transfer_entries = []
        for _, row in transfers_df.iterrows():
            transfer_entries.append({
                "Asset #": row.get("Asset #", ""),
                "Client Asset ID": row.get("Client Asset ID", ""),
                "Description": row.get("Description", ""),
                "Tax Cost": row.get("Tax Cost", row.get("Cost", 0)),
                "Transfer Date": row.get("Transfer Date", ""),
                "From Location": row.get("From Location", ""),
                "To Location": row.get("To Location", ""),
            })

        return pd.DataFrame(transfer_entries)

    def _build_existing_assets_sheet(self, existing_df: pd.DataFrame) -> pd.DataFrame:
        """
        Build Existing Assets sheet for FA CS reconciliation/tie-out.

        This sheet helps CPAs reconcile the workpaper to the FA CS depreciation report:
        - Total asset basis
        - Accumulated depreciation
        - Net book value

        Existing Assets = Assets placed in service BEFORE the current tax year.
        These are already in FA CS - no action needed, just for reference/tie-out.
        """
        if existing_df.empty:
            return None

        existing_entries = []
        for _, row in existing_df.iterrows():
            # Get accumulated depreciation and calculate NBV
            tax_cost = row.get("Tax Cost", row.get("Cost", 0)) or 0
            accum_depr = row.get("Accumulated Depreciation", row.get("Tax Prior Depreciation", 0)) or 0
            nbv = float(tax_cost) - float(accum_depr) if tax_cost else 0

            existing_entries.append({
                "Asset #": row.get("Asset #", ""),
                "Client Asset ID": row.get("Client Asset ID", ""),
                "Description": row.get("Description", ""),
                "Date In Service": row.get("Date In Service", row.get("In Service Date", "")),
                "Tax Cost": tax_cost,
                "Tax Life": row.get("Tax Life", ""),
                "Tax Method": row.get("Tax Method", ""),
                "Accum. Depreciation": accum_depr,
                "Net Book Value": nbv,
            })

        return pd.DataFrame(existing_entries)

    def _build_reconciliation_summary(self, additions_df: pd.DataFrame, disposals_df: pd.DataFrame,
                                       transfers_df: pd.DataFrame, existing_df: pd.DataFrame,
                                       de_minimis_df: pd.DataFrame, disposal_entry_df: pd.DataFrame,
                                       tax_year: int) -> pd.DataFrame:
        """
        Build Summary sheet for FA CS reconciliation/tie-out.

        This summary helps CPAs verify the workpaper ties to FA CS reports:
        - Beginning balance (Existing Assets)
        - + Current Year Additions
        - - Current Year Disposals
        - = Ending balance
        """
        # Calculate totals
        def safe_sum(df, col):
            if df is None or df.empty:
                return 0
            if col in df.columns:
                return df[col].sum() or 0
            # Try alternate column names
            alt_cols = {"Tax Cost": ["Cost"], "Gain/Loss": ["Capital Gain/Loss"]}
            for alt in alt_cols.get(col, []):
                if alt in df.columns:
                    return df[alt].sum() or 0
            return 0

        # Existing assets totals
        existing_cost = safe_sum(existing_df, "Tax Cost")
        existing_accum = safe_sum(existing_df, "Accumulated Depreciation") or safe_sum(existing_df, "Tax Prior Depreciation")
        existing_count = len(existing_df) if existing_df is not None and not existing_df.empty else 0

        # Additions totals
        additions_cost = safe_sum(additions_df, "Tax Cost")
        additions_count = len(additions_df) if additions_df is not None and not additions_df.empty else 0

        # Disposals totals
        disposals_cost = safe_sum(disposals_df, "Tax Cost")
        disposals_count = len(disposals_df) if disposals_df is not None and not disposals_df.empty else 0
        disposals_gain_loss = safe_sum(disposal_entry_df, "Gain/Loss") if disposal_entry_df is not None else 0

        # Transfers (no cost impact, just count)
        transfers_count = len(transfers_df) if transfers_df is not None and not transfers_df.empty else 0

        # De Minimis (expensed, not capitalized)
        de_minimis_cost = safe_sum(de_minimis_df, "Tax Cost") or safe_sum(de_minimis_df, "Cost")
        de_minimis_count = len(de_minimis_df) if de_minimis_df is not None and not de_minimis_df.empty else 0

        # Calculate ending balance
        ending_cost = existing_cost + additions_cost - disposals_cost

        summary_data = {
            'Category': [
                '=== FA CS RECONCILIATION ===',
                '',
                'Beginning Balance (Existing Assets)',
                '  + Current Year Additions',
                '  - Current Year Disposals',
                '  = Ending Balance',
                '',
                '=== DETAIL COUNTS ===',
                'Existing Assets (no action needed)',
                'Current Year Additions',
                'Current Year Disposals',
                'Transfers',
                'De Minimis Expenses (not capitalized)',
                '',
                '=== DISPOSAL SUMMARY ===',
                'Disposal Proceeds Total',
                'Total Gain/(Loss)',
                '',
                f'=== TAX YEAR {tax_year} ==='
            ],
            'Count': [
                '',
                '',
                existing_count,
                additions_count,
                disposals_count,
                existing_count + additions_count - disposals_count,
                '',
                '',
                existing_count,
                additions_count,
                disposals_count,
                transfers_count,
                de_minimis_count,
                '',
                '',
                '',
                '',
                '',
                ''
            ],
            'Tax Cost': [
                '',
                '',
                existing_cost,
                additions_cost,
                disposals_cost,
                ending_cost,
                '',
                '',
                existing_cost,
                additions_cost,
                disposals_cost,
                '',
                de_minimis_cost,
                '',
                '',
                safe_sum(disposal_entry_df, "Proceeds") if disposal_entry_df is not None else 0,
                disposals_gain_loss,
                '',
                ''
            ],
            'Accum. Depreciation': [
                '',
                '',
                existing_accum,
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                ''
            ]
        }

        return pd.DataFrame(summary_data)

    def _build_items_requiring_review(self, assets: List[Asset], export_df: pd.DataFrame,
                                       tax_year: int) -> pd.DataFrame:
        """
        Build Items Requiring Review sheet.

        IMPORTANT: Only reviews ACTIONABLE items (Current Year Additions, Disposals, Transfers).
        Existing Assets are EXCLUDED - they're already classified in FA CS.

        Flags items that need CPA attention:
        - Low confidence classifications (< 0.7)
        - Missing required data (cost, date, category)
        - Unusual values (very high cost, old assets with no depreciation)
        - De Minimis items that exceed limit
        - Disposals with no proceeds
        """
        review_items = []

        for idx, asset in enumerate(assets):
            # SKIP Existing Assets - they don't need review (already in FA CS)
            trans_type = self._detect_transaction_type(asset, tax_year)
            if 'existing' in str(trans_type).lower():
                continue  # Skip existing assets

            flags = []
            priority = "Low"

            # Check confidence score (only for new additions that need classification)
            confidence = asset.confidence_score or 0
            if 'addition' in str(trans_type).lower():
                if confidence < 0.5:
                    flags.append("LOW CONFIDENCE: Classification may be incorrect")
                    priority = "High"
                elif confidence < 0.7:
                    flags.append("MEDIUM CONFIDENCE: Review classification")
                    priority = "Medium" if priority == "Low" else priority

            # Check missing required data
            if not asset.cost or asset.cost <= 0:
                flags.append("MISSING: Cost is zero or missing")
                priority = "High"

            if not asset.in_service_date and not asset.acquisition_date:
                flags.append("MISSING: No in-service or acquisition date")
                priority = "High"

            if not asset.macrs_class or asset.macrs_class == "Unclassified":
                flags.append("MISSING: No MACRS class assigned")
                priority = "Medium" if priority == "Low" else priority

            if not asset.macrs_life:
                flags.append("MISSING: No tax life assigned")
                priority = "Medium" if priority == "Low" else priority

            # Check for unusual values
            if asset.cost and asset.cost > 1000000:
                flags.append("REVIEW: High value asset (>$1M)")
                priority = "Medium" if priority == "Low" else priority

            # Check disposals without proceeds
            if getattr(asset, 'disposal_date', None) and not getattr(asset, 'proceeds', None):
                flags.append("REVIEW: Disposal with no proceeds recorded")
                priority = "Medium" if priority == "Low" else priority

            # Check for description issues
            if not asset.description or len(asset.description.strip()) < 3:
                flags.append("MISSING: Description is empty or too short")
                priority = "Medium" if priority == "Low" else priority

            # Only add if there are flags
            if flags:
                review_items.append({
                    "Asset #": self._format_asset_number(asset),
                    "Client Asset ID": asset.asset_id,
                    "Description": asset.description[:50] if asset.description else "",
                    "Cost": asset.cost,
                    "Priority": priority,
                    "Flags": " | ".join(flags),
                    "Confidence Score": confidence,
                    "Action Needed": self._get_review_action(flags)
                })

        if not review_items:
            return pd.DataFrame([{
                "Asset #": "-",
                "Client Asset ID": "-",
                "Description": "No items require review",
                "Cost": 0,
                "Priority": "-",
                "Flags": "All items passed quality checks",
                "Confidence Score": "-",
                "Action Needed": "None"
            }])

        # Sort by priority (High first)
        df = pd.DataFrame(review_items)
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        df["_sort"] = df["Priority"].map(priority_order)
        df = df.sort_values("_sort").drop("_sort", axis=1)

        return df

    def _get_review_action(self, flags: List[str]) -> str:
        """Determine recommended action based on flags."""
        if any("MISSING: Cost" in f or "MISSING: No in-service" in f for f in flags):
            return "Obtain missing data from client"
        elif any("LOW CONFIDENCE" in f for f in flags):
            return "Verify classification with supporting documentation"
        elif any("MISSING: No MACRS" in f or "MISSING: No tax life" in f for f in flags):
            return "Complete classification"
        elif any("High value" in f for f in flags):
            return "Verify cost and classification"
        else:
            return "Review and correct as needed"

    def _build_complete_asset_schedule(self, assets: List[Asset], tax_year: int) -> pd.DataFrame:
        """Build complete asset schedule with ALL fields for audit purposes."""
        schedule_data = []

        for asset in assets:
            trans_type = self._detect_transaction_type(asset, tax_year)

            row = {
                # Identification
                "Asset #": self._format_asset_number(asset),
                "Client Asset ID": asset.asset_id,
                "Description": asset.description,

                # Transaction Info
                "Transaction Type": trans_type,
                "Depreciation Election": getattr(asset, 'depreciation_election', 'MACRS') or 'MACRS',
                "Election Reason": getattr(asset, 'election_reason', '') or '',

                # Dates
                "Acquisition Date": asset.acquisition_date,
                "In Service Date": asset.in_service_date or asset.acquisition_date,

                # Cost Basis
                "Tax Cost": asset.cost,

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
                "State Bonus Allowed": getattr(asset, 'state_bonus_allowed', True),

                # Disposal Info
                "Disposal Date": getattr(asset, 'disposal_date', None),
                "Proceeds": getattr(asset, 'proceeds', None),
                "Accumulated Depreciation": getattr(asset, 'accumulated_depreciation', None),
                "Gain/Loss": getattr(asset, 'gain_loss', None),

                # Transfer Info
                "Transfer Date": getattr(asset, 'transfer_date', None),
                "From Location": getattr(asset, 'from_location', None),
                "To Location": getattr(asset, 'to_location', None),

                # Metadata
                "Confidence Score": asset.confidence_score,
                "Tax Year": tax_year,
                "Export Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            schedule_data.append(row)

        return pd.DataFrame(schedule_data)

    def _build_prep_summary(self, fa_cs_entry_df: pd.DataFrame, de_minimis_df: pd.DataFrame,
                            review_df: pd.DataFrame, non_de_minimis_df: pd.DataFrame) -> pd.DataFrame:
        """Build summary for Prep Workpaper."""
        # Count by transaction type
        trans_counts = {}
        if 'Transaction Type' in non_de_minimis_df.columns:
            trans_counts = non_de_minimis_df['Transaction Type'].value_counts().to_dict()

        # Count review items by priority
        review_high = 0
        review_medium = 0
        if review_df is not None and 'Priority' in review_df.columns:
            priority_counts = review_df['Priority'].value_counts().to_dict()
            review_high = priority_counts.get('High', 0)
            review_medium = priority_counts.get('Medium', 0)

        summary_data = {
            'Category': [
                'Assets for FA CS Entry',
                '  - Current Year Additions',
                '  - Existing Assets',
                '  - Disposals',
                '  - Transfers',
                'De Minimis Expenses',
                '',
                'Items Requiring Review',
                '  - High Priority',
                '  - Medium Priority',
                '',
                'TOTAL ASSETS'
            ],
            'Count': [
                len(fa_cs_entry_df),
                trans_counts.get('Current Year Addition', 0),
                trans_counts.get('Existing Asset', 0),
                trans_counts.get('Disposal', 0),
                trans_counts.get('Transfer', 0),
                len(de_minimis_df) if de_minimis_df is not None else 0,
                '',
                len(review_df) - 1 if review_df is not None and len(review_df) > 0 and review_df.iloc[0]['Asset #'] != '-' else 0,
                review_high,
                review_medium,
                '',
                len(fa_cs_entry_df) + (len(de_minimis_df) if de_minimis_df is not None else 0)
            ],
            'Total Cost': [
                fa_cs_entry_df['Tax Cost'].sum() if 'Tax Cost' in fa_cs_entry_df.columns else 0,
                '',
                '',
                '',
                '',
                de_minimis_df['Cost'].sum() if de_minimis_df is not None and 'Cost' in de_minimis_df.columns else 0,
                '',
                '',
                '',
                '',
                '',
                (fa_cs_entry_df['Tax Cost'].sum() if 'Tax Cost' in fa_cs_entry_df.columns else 0) +
                (de_minimis_df['Cost'].sum() if de_minimis_df is not None and 'Cost' in de_minimis_df.columns else 0)
            ]
        }

        return pd.DataFrame(summary_data)

    def _build_audit_summary(self, complete_schedule_df: pd.DataFrame, tax_year: int) -> pd.DataFrame:
        """Build summary for Audit Workpaper with full reconciliation."""
        # Transaction type breakdown
        trans_counts = {}
        trans_costs = {}
        if 'Transaction Type' in complete_schedule_df.columns:
            for trans_type in complete_schedule_df['Transaction Type'].unique():
                mask = complete_schedule_df['Transaction Type'] == trans_type
                trans_counts[trans_type] = mask.sum()
                trans_costs[trans_type] = complete_schedule_df.loc[mask, 'Tax Cost'].sum() if 'Tax Cost' in complete_schedule_df.columns else 0

        # Election breakdown
        election_counts = {}
        if 'Depreciation Election' in complete_schedule_df.columns:
            election_counts = complete_schedule_df['Depreciation Election'].value_counts().to_dict()

        # Calculate gain/loss total for disposals
        disposal_gain_loss = 0
        if 'Gain/Loss' in complete_schedule_df.columns:
            disposal_gain_loss = complete_schedule_df['Gain/Loss'].sum()

        summary_data = {
            'Category': [
                '=== TRANSACTION SUMMARY ===',
                'Current Year Additions',
                'Existing Assets',
                'Disposals',
                'Transfers',
                'TOTAL',
                '',
                '=== ELECTION BREAKDOWN ===',
                'MACRS (Standard)',
                'Section 179',
                'Bonus Depreciation',
                'De Minimis Safe Harbor',
                'ADS (Alternative)',
                '',
                '=== DISPOSAL ANALYSIS ===',
                'Total Gain/Loss',
                '',
                '=== TAX YEAR ===',
                'Current Tax Year'
            ],
            'Count': [
                '',
                trans_counts.get('Current Year Addition', 0),
                trans_counts.get('Existing Asset', 0),
                trans_counts.get('Disposal', 0),
                trans_counts.get('Transfer', 0),
                len(complete_schedule_df),
                '',
                '',
                election_counts.get('MACRS', 0),
                election_counts.get('Section179', 0),
                election_counts.get('Bonus', 0),
                election_counts.get('DeMinimis', 0),
                election_counts.get('ADS', 0),
                '',
                '',
                '',
                '',
                '',
                tax_year
            ],
            'Total Cost': [
                '',
                trans_costs.get('Current Year Addition', 0),
                trans_costs.get('Existing Asset', 0),
                trans_costs.get('Disposal', 0),
                trans_costs.get('Transfer', 0),
                complete_schedule_df['Tax Cost'].sum() if 'Tax Cost' in complete_schedule_df.columns else 0,
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                '',
                disposal_gain_loss,
                '',
                '',
                ''
            ]
        }

        return pd.DataFrame(summary_data)

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
