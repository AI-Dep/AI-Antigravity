import sys
import os
import pandas as pd
from datetime import date

# Add project root to sys.path
sys.path.append(os.getcwd())

# Mock backend package structure if needed, but adding cwd should work
from backend.services.exporter import ExporterService
from backend.models.asset import Asset

def test_custom_export():
    print("Initializing ExporterService...")
    try:
        exporter = ExporterService()
    except Exception as e:
        print(f"Failed to initialize ExporterService: {e}")
        import traceback
        traceback.print_exc()
        return

    # Create dummy assets
    assets = [
        Asset(
            row_index=1,
            description="Test Computer",
            cost=1500.0,
            acquisition_date=date(2024, 1, 15),
            macrs_class="Computer Equipment",
            macrs_life=5.0,
            macrs_method="200DB",
            macrs_convention="HY",
            confidence_score=0.95
        ),
        Asset(
            row_index=2,
            description="Test Desk",
            cost=500.0,
            acquisition_date=date(2024, 2, 20),
            macrs_class="Office Furniture",
            macrs_life=7.0,
            macrs_method="200DB",
            macrs_convention="HY",
            confidence_score=0.85
        )
    ]
    
    print(f"Generating export for {len(assets)} assets...")
    try:
        excel_file = exporter.generate_fa_cs_export(assets)
        print("Export generated successfully.")
        
        # Save to file for manual inspection if needed
        with open("test_export_output.xlsx", "wb") as f:
            f.write(excel_file.getvalue())
        print("Saved to test_export_output.xlsx")
        
        # Verify content
        df = pd.read_excel("test_export_output.xlsx", sheet_name='FA_CS_Data')
        print("\nColumns in export:")
        print(df.columns.tolist())
        
        # Check for critical columns from custom logic
        expected_cols = ["Asset #", "Description", "Tax Cost", "Tax Method", "Tax Life", "FA_CS_Wizard_Category"]
        missing = [col for col in expected_cols if col not in df.columns]
        
        if missing:
            print(f"FAIL: Missing columns: {missing}")
        else:
            print("PASS: All critical columns present.")
            
            # Verify Wizard Category mapping
            print("\nVerifying Wizard Categories:")
            for idx, row in df.iterrows():
                desc = row['Description']
                cat = row.get('FA_CS_Wizard_Category', 'N/A')
                print(f"Asset: {desc} -> Wizard Category: {cat}")

    except Exception as e:
        print(f"Failed to generate export: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_custom_export()
