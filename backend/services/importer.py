import pandas as pd
from typing import List, Dict, Optional
from backend.models.asset import Asset
from backend.logic import sheet_loader


class ImporterService:
    """
    Service to parse Excel files and extract Asset objects using the advanced SheetLoader.
    """
    
    def parse_excel(self, file_path: str) -> List[Asset]:
        """
        Reads an Excel file and returns a list of validated Asset objects.
        """
        # 1. Analyze the file using the advanced sheet loader
        # We need to find the best sheet first
        xl = pd.ExcelFile(file_path)
        sheet_names = xl.sheet_names
        xl.close()
        
        best_sheet = None
        best_analysis = None
        
        # Simple heuristic: find the first "Main" role sheet or just the first one that isn't skipped
        for sheet in sheet_names:
            # Check if we should skip
            should_skip, reason = sheet_loader._should_skip_sheet(sheet)
            if should_skip:
                continue
                
            # Analyze header
            df_preview = pd.read_excel(file_path, sheet_name=sheet, nrows=50, header=None)
            header_row = sheet_loader._detect_header_row(df_preview)
            
            # If we found a valid header, use this sheet
            if header_row is not None:
                best_sheet = sheet
                break
        
        if not best_sheet:
            best_sheet = sheet_names[0] # Fallback
            
        # 2. Load the data using the detected header
        # Re-read with correct header
        df_preview = pd.read_excel(file_path, sheet_name=best_sheet, nrows=50, header=None)
        header_row_idx = sheet_loader._detect_header_row(df_preview)
        
        df = pd.read_excel(file_path, sheet_name=best_sheet, header=header_row_idx)
        
        # 3. Map Columns using ColumnDetector (via sheet_loader logic)
        # We'll use the column mappings from the logic module
        from backend.logic.column_detector import find_column_match
        
        col_map = {}
        # Map critical and important fields
        all_fields = sheet_loader.COL_CRITICAL_FIELDS + sheet_loader.COL_IMPORTANT_FIELDS + sheet_loader.OPTIONAL_FIELDS
        
        for field in all_fields:
            col_name, mapping = find_column_match(df, field)
            if col_name:
                col_map[field] = col_name
                
        # 4. Extract Data
        assets = []
        for idx, row in df.iterrows():
            if self._is_empty_row(row):
                continue
                
            try:
                # Extract raw values
                desc = row.get(col_map.get("description"))
                cost = row.get(col_map.get("cost"))
                
                # Skip invalid rows (must have description and cost)
                if pd.isna(desc) or pd.isna(cost):
                    continue
                    
                # Create Asset Object
                asset = Asset(
                    row_index=idx + header_row_idx + 2,
                    asset_id=str(row.get(col_map.get("asset_id"))) if col_map.get("asset_id") else None,
                    description=str(desc),
                    cost=float(cost) if self._is_valid_number(cost) else 0.0,
                    acquisition_date=row.get(col_map.get("acquisition_date")),
                    in_service_date=row.get(col_map.get("in_service_date")),
                    
                    # Capture other fields if available
                    macrs_life=float(row.get(col_map.get("life"))) if col_map.get("life") and self._is_valid_number(row.get(col_map.get("life"))) else None,
                    macrs_method=str(row.get(col_map.get("method"))) if col_map.get("method") else None,
                    macrs_convention=str(row.get(col_map.get("convention"))) if col_map.get("convention") else None
                )
                
                # Run Validation Rules
                asset.check_validity()
                
                assets.append(asset)
            except Exception as e:
                print(f"Skipping row {idx}: {e}")
                
        return assets

    def _is_empty_row(self, row) -> bool:
        return row.dropna().empty

    def _is_valid_number(self, val) -> bool:
        try:
            float(val)
            return True
        except:
            return False
