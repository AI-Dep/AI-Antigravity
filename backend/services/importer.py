import pandas as pd
from typing import List, Dict, Optional
from backend.models.asset import Asset
from backend.logic import sheet_loader


class ImporterService:
    """
    Service to parse Excel files and extract Asset objects using the advanced SheetLoader.

    CRITICAL: Processes ALL sheets in the workbook to capture:
    - Different asset categories (Office Equipment, F&F, Vehicles, etc.)
    - Disposals and transfers
    - Assets with or without dates (no assets should be excluded due to missing dates)
    """

    def parse_excel(self, file_path: str, filter_by_date: bool = False) -> List[Asset]:
        """
        Reads an Excel file and returns a list of validated Asset objects.

        IMPORTANT:
        - Processes ALL sheets, not just one
        - Includes assets even without dates (filter_by_date=False by default)
        - Uses smart tab analysis to detect sheet roles

        Args:
            file_path: Path to the Excel file
            filter_by_date: If True, only include rows with dates in target fiscal year.
                           Default is False to include ALL assets.

        Returns:
            List of Asset objects from all valid sheets
        """
        # 1. Load ALL sheets from the Excel file (header=None for raw data)
        xl = pd.ExcelFile(file_path)
        sheets = {}
        for sheet_name in xl.sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
                sheets[sheet_name] = df
            except Exception as e:
                print(f"Warning: Could not read sheet '{sheet_name}': {e}")
        xl.close()

        if not sheets:
            print("Error: No readable sheets found in file")
            return []

        print(f"Found {len(sheets)} sheets: {list(sheets.keys())}")

        # 2. Use advanced sheet_loader to build unified dataframe from ALL sheets
        # CRITICAL: filter_by_date=False ensures assets without dates are NOT excluded
        try:
            df_unified = sheet_loader.build_unified_dataframe(
                sheets,
                target_tax_year=None,  # Don't filter by year
                filter_by_date=filter_by_date,  # Default False - include all assets
                client_id=None
            )
        except Exception as e:
            print(f"Error in build_unified_dataframe: {e}")
            # Fallback to basic processing
            return self._parse_excel_basic(file_path)

        if df_unified.empty:
            print("Warning: build_unified_dataframe returned empty - falling back to basic parsing")
            return self._parse_excel_basic(file_path)

        # Log stats from smart processing
        stats = {
            'total_rows': len(df_unified),
            'sheets_processed': df_unified.attrs.get('sheets_processed', 'unknown'),
            'sheets_skipped': df_unified.attrs.get('sheets_skipped', 'unknown'),
        }
        print(f"Processed {stats['total_rows']} assets from {stats['sheets_processed']} sheets")

        # 3. Convert DataFrame rows to Asset objects
        assets = []
        for idx, row in df_unified.iterrows():
            try:
                asset = self._row_to_asset(row, idx)
                if asset:
                    assets.append(asset)
            except Exception as e:
                print(f"Warning: Could not process row {idx}: {e}")

        print(f"Successfully created {len(assets)} Asset objects")
        return assets

    def _row_to_asset(self, row: pd.Series, idx: int) -> Optional[Asset]:
        """
        Convert a DataFrame row to an Asset object.

        IMPORTANT: Does NOT skip assets missing cost or dates.
        All assets with a description should be included.
        """
        # Get description - this is the only required field
        desc = row.get('description', '')
        if pd.isna(desc) or str(desc).strip() == '':
            return None  # Must have description

        description = str(desc).strip()

        # Get asset_id (optional - use row index as fallback)
        asset_id = row.get('asset_id', '')
        if pd.isna(asset_id) or str(asset_id).strip() == '':
            asset_id = None
        else:
            asset_id = str(asset_id).strip()

        # Get cost (optional - 0.0 if not available)
        cost = row.get('cost')
        if pd.isna(cost) or not self._is_valid_number(cost):
            cost = 0.0
        else:
            cost = float(cost)

        # Get dates (all optional)
        acquisition_date = row.get('acquisition_date')
        if pd.isna(acquisition_date):
            acquisition_date = None

        in_service_date = row.get('in_service_date')
        if pd.isna(in_service_date):
            in_service_date = None

        # Get life/method if available
        tax_life = row.get('tax_life')
        if pd.isna(tax_life) or not self._is_valid_number(tax_life):
            tax_life = None
        else:
            tax_life = float(tax_life)

        tax_method = row.get('tax_method')
        if pd.isna(tax_method):
            tax_method = None
        else:
            tax_method = str(tax_method).strip()

        # Get source info for audit trail
        source_row = row.get('source_row', idx + 2)
        sheet_name = row.get('sheet_name', 'Unknown')
        transaction_type = row.get('transaction_type', 'addition')

        # Create Asset Object
        asset = Asset(
            row_index=int(source_row) if not pd.isna(source_row) else idx + 2,
            asset_id=asset_id,
            description=description,
            cost=cost,
            acquisition_date=acquisition_date,
            in_service_date=in_service_date,
            macrs_life=tax_life,
            macrs_method=tax_method,
            # Store additional metadata
            source_sheet=sheet_name,
            transaction_type=transaction_type
        )

        # Run Validation Rules (but don't reject - just flag)
        asset.check_validity()

        return asset

    def _parse_excel_basic(self, file_path: str) -> List[Asset]:
        """
        Basic fallback parsing - processes first valid sheet only.
        Used when advanced parsing fails.
        """
        print("Using basic Excel parsing (fallback mode)")

        xl = pd.ExcelFile(file_path)
        sheet_names = xl.sheet_names
        xl.close()

        best_sheet = None
        for sheet in sheet_names:
            should_skip, reason = sheet_loader._should_skip_sheet(sheet)
            if should_skip:
                continue

            df_preview = pd.read_excel(file_path, sheet_name=sheet, nrows=50, header=None)
            header_row = sheet_loader._detect_header_row(df_preview)

            if header_row is not None:
                best_sheet = sheet
                break

        if not best_sheet:
            best_sheet = sheet_names[0]

        df_preview = pd.read_excel(file_path, sheet_name=best_sheet, nrows=50, header=None)
        header_row_idx = sheet_loader._detect_header_row(df_preview)

        df = pd.read_excel(file_path, sheet_name=best_sheet, header=header_row_idx)

        from backend.logic.column_detector import find_column_match

        col_map = {}
        all_fields = sheet_loader.COL_CRITICAL_FIELDS + sheet_loader.COL_IMPORTANT_FIELDS + sheet_loader.OPTIONAL_FIELDS

        for field in all_fields:
            col_name, mapping = find_column_match(df, field)
            if col_name:
                col_map[field] = col_name

        assets = []
        for idx, row in df.iterrows():
            if self._is_empty_row(row):
                continue

            try:
                desc = row.get(col_map.get("description"))

                # CHANGED: Only require description, not cost
                if pd.isna(desc) or str(desc).strip() == '':
                    continue

                cost = row.get(col_map.get("cost"))
                if pd.isna(cost) or not self._is_valid_number(cost):
                    cost = 0.0

                asset = Asset(
                    row_index=idx + header_row_idx + 2,
                    asset_id=str(row.get(col_map.get("asset_id"))) if col_map.get("asset_id") and not pd.isna(row.get(col_map.get("asset_id"))) else None,
                    description=str(desc),
                    cost=float(cost),
                    acquisition_date=row.get(col_map.get("acquisition_date")),
                    in_service_date=row.get(col_map.get("in_service_date")),
                    macrs_life=float(row.get(col_map.get("life"))) if col_map.get("life") and self._is_valid_number(row.get(col_map.get("life"))) else None,
                    macrs_method=str(row.get(col_map.get("method"))) if col_map.get("method") else None,
                    macrs_convention=str(row.get(col_map.get("convention"))) if col_map.get("convention") else None
                )

                asset.check_validity()
                assets.append(asset)
            except Exception as e:
                print(f"Skipping row {idx}: {e}")

        return assets

    def _is_empty_row(self, row) -> bool:
        return row.dropna().empty

    def _is_valid_number(self, val) -> bool:
        if val is None or pd.isna(val):
            return False
        try:
            float(val)
            return True
        except:
            return False
