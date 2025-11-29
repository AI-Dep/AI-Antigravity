import pandas as pd
import os
import sys
import logging

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fixed_asset_ai.logic.sheet_loader import analyze_excel_structure, build_unified_dataframe

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_parsing_with_overrides():
    print("Creating dummy Excel file...")
    # Create a dataframe with "weird" column names
    df = pd.DataFrame({
        "Item Name": ["Laptop", "Desk"],
        "Purchase Value": [1000, 500],
        "Date Bought": ["2023-01-01", "2023-02-01"],
        "Tag #": ["A001", "A002"]
    })
    
    dummy_file = "test_assets.xlsx"
    df.to_excel(dummy_file, sheet_name="Sheet1", index=False)
    
    try:
        print("Loading Excel file...")
        xls = pd.ExcelFile(dummy_file)
        sheets = {name: xls.parse(name, header=None) for name in xls.sheet_names}
        
        print("Analyzing structure...")
        analysis = analyze_excel_structure(sheets)
        sheet_analysis = analysis["Sheet1"]
        
        print("Detected columns:", sheet_analysis.detected_columns)
        
        # Verify auto-detection (it should be decent)
        # "Tag #" -> asset_id
        # "Item Name" -> description
        # "Purchase Value" -> cost
        # "Date Bought" -> acquisition_date (maybe?)
        
        # Let's force an override to simulate user correction
        # Say we want "Date Bought" to be "in_service_date" instead of "acquisition_date"
        
        overrides = {
            "Sheet1": {
                "in_service_date": "Date Bought"
            }
        }
        
        print(f"Applying overrides: {overrides}")
        
        df_unified = build_unified_dataframe(sheets, column_mapping_overrides=overrides)
        
        print("Unified DataFrame Columns:", df_unified.columns.tolist())
        print(df_unified.head())
        
        # Check if 'in_service_date' is populated
        if "in_service_date" in df_unified.columns and not df_unified["in_service_date"].isnull().all():
            print("SUCCESS: Override applied correctly!")
        else:
            print("FAILURE: Override not applied.")
            
    finally:
        if os.path.exists(dummy_file):
            os.remove(dummy_file)

if __name__ == "__main__":
    test_parsing_with_overrides()
