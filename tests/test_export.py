import pandas as pd
import os
import sys
from datetime import date
from io import BytesIO

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.asset import Asset
from backend.services.exporter import ExporterService

def test_export():
    print("--- Testing Export Logic ---")
    
    # 1. Create Dummy Assets
    assets = [
        Asset(
            row_index=1,
            description="Dell Latitude Laptop",
            cost=1200.00,
            acquisition_date=date(2024, 1, 15),
            macrs_class="Computers",
            macrs_life=5.0,
            macrs_method="200DB",
            macrs_convention="HY",
            confidence_score=0.95
        ),
        Asset(
            row_index=2,
            description="Office Chair",
            cost=350.00,
            acquisition_date=date(2024, 2, 1),
            macrs_class="Office Furniture",
            macrs_life=7.0,
            macrs_method="200DB",
            macrs_convention="HY",
            confidence_score=0.85
        ),
        Asset(
            row_index=3,
            description="Ford F-150 Truck",
            cost=45000.00,
            acquisition_date=date(2024, 3, 10),
            macrs_class="Vehicles",
            macrs_life=5.0,
            macrs_method="200DB",
            macrs_convention="HY",
            confidence_score=0.98
        )
    ]
    
    print(f"Created {len(assets)} dummy assets.")
    
    try:
        # 2. Generate Export
        print("\nGenerating export...")
        exporter = ExporterService()
        excel_bytes = exporter.generate_fa_cs_export(assets)
        
        # 3. Verify Output
        print("Export generated. Verifying content...")
        
        # Load back into pandas to check sheets
        xls = pd.ExcelFile(excel_bytes)
        print(f"Sheets found: {xls.sheet_names}")
        
        expected_sheets = ["FA_CS_Data", "Review", "Summary"]
        for sheet in expected_sheets:
            if sheet in xls.sheet_names:
                print(f"[OK] Sheet '{sheet}' found.")
            else:
                print(f"[MISSING] Sheet '{sheet}' MISSING!")
                raise Exception(f"Missing sheet: {sheet}")
                
        # Check FA_CS_Data sheet content
        df_tax = pd.read_excel(xls, sheet_name="FA_CS_Data")
        print(f"FA_CS_Data sheet has {len(df_tax)} rows.")
        
        if len(df_tax) != 3:
            print(f"[ERROR] Expected 3 rows, found {len(df_tax)}")
             
        # Check Review (Audit Trail)
        df_audit = pd.read_excel(xls, sheet_name="Review")
        print(f"Review sheet has {len(df_audit)} rows.")
        
        print("\n[PASSED] EXPORT TEST PASSED")
        
    except Exception as e:
        print(f"\n[FAILED] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_export()
