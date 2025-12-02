import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from threading import local
from backend.models.asset import Asset
from backend.logic import sheet_loader
from backend.logic.sheet_loader import infer_macrs_class_from_sheet_name


@dataclass
class ParseResult:
    """Thread-safe result of a parse operation - prevents race conditions."""
    assets: List[Asset] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    stats: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "warnings": self.warnings,
            "errors": self.errors,
            "stats": self.stats,
            "asset_count": len(self.assets)
        }


# Thread-local storage for per-request parse results
_thread_local = local()


class ImporterService:
    """
    Service to parse Excel files and extract Asset objects using the advanced SheetLoader.

    CRITICAL: Processes ALL sheets in the workbook to capture:
    - Different asset categories (Office Equipment, F&F, Vehicles, etc.)
    - Disposals and transfers
    - Assets with or without dates (no assets should be excluded due to missing dates)

    NOTE: Parse results are now thread-local to prevent race conditions in concurrent requests.
    Use get_last_parse_report() only within the same request/thread that called parse_excel().
    """

    def __init__(self):
        # No longer store mutable state on instance - use thread-local storage instead
        pass

    def get_last_parse_report(self) -> Dict:
        """
        Get detailed report from last parse operation in this thread.

        IMPORTANT: Only valid within the same request/thread that called parse_excel().
        For concurrent safety, prefer using parse_excel_with_report() which returns
        both assets and the report together.
        """
        result = getattr(_thread_local, 'last_parse_result', None)
        if result:
            return result.to_dict()
        return {"warnings": [], "errors": [], "stats": {}}

    def parse_excel_with_report(self, file_path: str, filter_by_date: bool = False) -> Tuple[List[Asset], Dict]:
        """
        Parse Excel file and return both assets and parse report.

        This method is thread-safe and preferred over parse_excel() + get_last_parse_report().

        Returns:
            Tuple of (list of Asset objects, parse report dictionary)
        """
        assets = self.parse_excel(file_path, filter_by_date)
        report = self.get_last_parse_report()
        return assets, report

    def parse_excel(self, file_path: str, filter_by_date: bool = False, target_tax_year: Optional[int] = None) -> List[Asset]:
        """
        Reads an Excel file and returns a list of validated Asset objects.

        IMPORTANT:
        - Processes ALL sheets, not just one
        - Includes assets even without dates (filter_by_date=False by default)
        - Uses smart tab analysis to detect sheet roles
        - Results are stored in thread-local storage for thread safety
        - Skips prior year sheets to optimize performance

        Args:
            file_path: Path to the Excel file
            filter_by_date: If True, only include rows with dates in target fiscal year.
                           Default is False to include ALL assets.
            target_tax_year: Tax year to process (e.g., 2025). Sheets from prior years
                            will be skipped for performance. If None, uses current year.

        Returns:
            List of Asset objects from all valid sheets
        """
        # Initialize thread-local parse result (prevents race conditions)
        result = ParseResult()
        _thread_local.last_parse_result = result

        # 1. Load ALL sheets from the Excel file (header=None for raw data)
        try:
            xl = pd.ExcelFile(file_path)
        except Exception as e:
            error = f"Could not open Excel file: {e}"
            result.errors.append(error)
            print(f"Error: {error}")
            return []

        sheets = {}
        for sheet_name in xl.sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
                sheets[sheet_name] = df
            except Exception as e:
                warning = f"Could not read sheet '{sheet_name}': {e}"
                result.warnings.append(warning)
                print(f"Warning: {warning}")
        xl.close()

        if not sheets:
            error = "No readable sheets found in file"
            result.errors.append(error)
            print(f"Error: {error}")
            return []

        print(f"Found {len(sheets)} sheets: {list(sheets.keys())}")

        # 2. Use advanced sheet_loader to build unified dataframe from ALL sheets
        # CRITICAL: filter_by_date=False ensures assets without dates are NOT excluded
        # PERFORMANCE: target_tax_year enables skipping prior year sheets
        from datetime import datetime
        effective_tax_year = target_tax_year or datetime.now().year

        try:
            df_unified = sheet_loader.build_unified_dataframe(
                sheets,
                target_tax_year=effective_tax_year,  # Skip prior year sheets for performance
                filter_by_date=filter_by_date,  # Default False - include all assets
                client_id=None
            )
        except Exception as e:
            print(f"Error in build_unified_dataframe: {e}")
            # Fallback to basic processing
            return self._parse_excel_basic(file_path, result)

        if df_unified.empty:
            print("Warning: build_unified_dataframe returned empty - falling back to basic parsing")
            return self._parse_excel_basic(file_path, result)

        # Log stats from smart processing
        result.stats = {
            'total_rows': len(df_unified),
            'sheets_processed': df_unified.attrs.get('sheets_processed', 'unknown'),
            'sheets_skipped': df_unified.attrs.get('sheets_skipped', 'unknown'),
            'skipped_reasons': df_unified.attrs.get('skipped_reasons', []),
        }
        print(f"Processed {result.stats['total_rows']} assets from {result.stats['sheets_processed']} sheets")

        # 3. Convert DataFrame rows to Asset objects
        assets = []
        row_errors = []
        for idx, row in df_unified.iterrows():
            try:
                asset = self._row_to_asset(row, idx)
                if asset:
                    assets.append(asset)
            except Exception as e:
                error_msg = f"Row {idx}: {e}"
                row_errors.append(error_msg)
                print(f"Warning: Could not process row {idx}: {e}")

        # Track row-level errors (limit to prevent memory issues)
        if row_errors:
            result.warnings.extend(row_errors[:10])  # Limit to first 10
            if len(row_errors) > 10:
                result.warnings.append(f"... and {len(row_errors) - 10} more row errors")

        result.stats['assets_created'] = len(assets)
        result.stats['row_errors'] = len(row_errors)
        result.assets = assets

        # Track assets missing asset_id (important for CPA review)
        missing_asset_id_count = sum(1 for a in assets if not a.asset_id)
        result.stats['missing_asset_id'] = missing_asset_id_count
        if missing_asset_id_count > 0:
            pct = (missing_asset_id_count / len(assets) * 100) if assets else 0
            warning_msg = f"{missing_asset_id_count} assets ({pct:.0f}%) are missing Asset ID/Number"
            result.warnings.append(warning_msg)
            print(f"Warning: {warning_msg}")

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

        # Infer MACRS class from sheet name if not provided in data
        # This helps when files don't have explicit MACRS class columns
        inferred_macrs_class = None
        inferred_life = None
        inferred_method = None
        if sheet_name and sheet_name != 'Unknown':
            inferred_macrs_class, inferred_life, inferred_method = infer_macrs_class_from_sheet_name(sheet_name)
            if inferred_macrs_class:
                print(f"[MACRS Inference] Sheet '{sheet_name}' -> {inferred_macrs_class} ({inferred_life}yr)")

        # Use inferred values if not already set from file
        if tax_life is None and inferred_life is not None and inferred_life > 0:
            tax_life = float(inferred_life)
        if tax_method is None and inferred_method is not None:
            tax_method = inferred_method

        # Get disposal fields (for disposed assets)
        disposal_date = row.get('disposal_date')
        if pd.isna(disposal_date):
            disposal_date = None
        proceeds = row.get('proceeds')
        if pd.isna(proceeds) or not self._is_valid_number(proceeds):
            proceeds = None
        else:
            proceeds = float(proceeds)
        accumulated_depreciation = row.get('accumulated_depreciation')
        if pd.isna(accumulated_depreciation) or not self._is_valid_number(accumulated_depreciation):
            accumulated_depreciation = None
        else:
            accumulated_depreciation = float(accumulated_depreciation)

        # Get transfer fields (for transferred assets)
        transfer_date = row.get('transfer_date')
        if pd.isna(transfer_date):
            transfer_date = None
        from_location = row.get('from_location', '')
        if pd.isna(from_location):
            from_location = None
        to_location = row.get('to_location', '')
        if pd.isna(to_location):
            to_location = None

        # Create Asset Object
        asset = Asset(
            row_index=int(source_row) if not pd.isna(source_row) else idx + 2,
            asset_id=asset_id,
            description=description,
            cost=cost,
            acquisition_date=acquisition_date,
            in_service_date=in_service_date,
            macrs_class=inferred_macrs_class,  # Use inferred class from sheet name
            macrs_life=tax_life,
            macrs_method=tax_method,
            # Disposal fields
            disposal_date=disposal_date,
            proceeds=proceeds,
            accumulated_depreciation=accumulated_depreciation,
            # Transfer fields
            transfer_date=transfer_date,
            from_location=from_location,
            to_location=to_location,
            # Store additional metadata
            source_sheet=sheet_name,
            transaction_type=transaction_type
        )

        # Run Validation Rules (but don't reject - just flag)
        asset.check_validity()

        return asset

    def _parse_excel_basic(self, file_path: str, result: ParseResult = None) -> List[Asset]:
        """
        Basic fallback parsing - processes first valid sheet only.
        Used when advanced parsing fails.
        """
        print("Using basic Excel parsing (fallback mode)")

        # Use existing result or get from thread-local storage
        if result is None:
            result = getattr(_thread_local, 'last_parse_result', ParseResult())
            _thread_local.last_parse_result = result

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
        
        # 3. Map Columns using ColumnDetector
        from backend.logic.column_detector import detect_columns

        # Get column headers as list
        column_headers = df.columns.tolist()

        # Detect column mappings
        col_map, mappings, warnings = detect_columns(column_headers)
                
        # 4. Extract Data
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

                # NOTE: Validation is run AFTER classification in classifier.py
                # This ensures we can check if classification succeeded
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
        except (ValueError, TypeError):
            return False
