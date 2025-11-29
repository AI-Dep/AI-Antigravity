"""
Generate FA CS Import Test Files - Version 2
Based on user testing feedback and custom FA CS mapping "AI_Tool_Import"

Column order matches FA CS custom mapping:
1. Asset #
2. Description
3. Date In Service
4. Tax Cost
5. Tax Method
6. Tax Life
7. Tax Sec 179 Expensed (blank OK, or value - ONLY way to set 179!)
8. Tax Cur Depreciation
9. Tax Prior Depreciation
10. Date Disposed
11. Gross Proceeds

Key findings:
- Section 179 MUST be in import file (Task → Elect Section 179 shows nothing post-import!)
- Asset Type doesn't control folder placement (always goes to Misc)
- Header row at 0 (default FA CS setting)
"""

import pandas as pd
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

def generate_test_files():
    """Generate test files matching FA CS custom mapping."""

    # Test assets with Section 179 values
    # IMPORTANT: Tax Cur Depreciation must be BLANK (not 0) so FA CS calculates it
    # If we put 0, FA CS treats it as an override!
    # Testing: Adding Book columns to see if FA CS will import them
    test_assets = [
        {
            "Asset #": 1,
            "Description": "Test Computer - 5 Year Property",
            "Date In Service": "1/1/2024",
            "Tax Cost": 5000.00,
            "Tax Method": "MACRS",
            "Tax Life": 5,
            "Tax Sec 179 Expensed": 5000.00,
            "Tax Cur Depreciation": "",
            "Tax Prior Depreciation": 0,
            "Book Cost": 5000.00,        # TEST: Will FA CS import this?
            "Book Method": "SL",         # Straight Line for Book
            "Book Life": 10,             # 10 year for Book
            "MI Cost": 5000.00,          # Michigan state depreciation
            "MI Method": "MACRS",        # Same as Tax
            "MI Life": 5,                # Same as Tax Life
            "Date Disposed": "",
            "Gross Proceeds": "",
        },
        {
            "Asset #": 2,
            "Description": "Test Office Furniture - 7 Year Property",
            "Date In Service": "2/1/2024",
            "Tax Cost": 8000.00,
            "Tax Method": "MACRS",
            "Tax Life": 7,
            "Tax Sec 179 Expensed": 0,
            "Tax Cur Depreciation": "",
            "Tax Prior Depreciation": 0,
            "Book Cost": 8000.00,
            "Book Method": "SL",
            "Book Life": 10,
            "MI Cost": 8000.00,
            "MI Method": "MACRS",
            "MI Life": 7,
            "Date Disposed": "",
            "Gross Proceeds": "",
        },
        {
            "Asset #": 3,
            "Description": "Test Vehicle - 5 Year Property",
            "Date In Service": "3/15/2024",
            "Tax Cost": 35000.00,
            "Tax Method": "MACRS",
            "Tax Life": 5,
            "Tax Sec 179 Expensed": 0,
            "Tax Cur Depreciation": "",
            "Tax Prior Depreciation": 0,
            "Book Cost": 35000.00,
            "Book Method": "SL",
            "Book Life": 5,
            "MI Cost": 35000.00,
            "MI Method": "MACRS",
            "MI Life": 5,
            "Date Disposed": "",
            "Gross Proceeds": "",
        },
        {
            "Asset #": 4,
            "Description": "Test Disposed Equipment",
            "Date In Service": "1/1/2020",
            "Tax Cost": 10000.00,
            "Tax Method": "MACRS",
            "Tax Life": 5,
            "Tax Sec 179 Expensed": 0,
            "Tax Cur Depreciation": "",
            "Tax Prior Depreciation": 8000.00,
            "Book Cost": 10000.00,
            "Book Method": "SL",
            "Book Life": 5,
            "MI Cost": 10000.00,
            "MI Method": "MACRS",
            "MI Life": 5,
            "Date Disposed": "6/30/2024",
            "Gross Proceeds": 3000.00,
        },
    ]

    df = pd.DataFrame(test_assets)

    # Column order - now includes Book and MI (Michigan) columns for testing
    column_order = [
        "Asset #",
        "Description",
        "Date In Service",
        "Tax Cost",
        "Tax Method",
        "Tax Life",
        "Tax Sec 179 Expensed",
        "Tax Cur Depreciation",
        "Tax Prior Depreciation",
        "Book Cost",      # Book depreciation - FA CS imports these!
        "Book Method",    # Typically "SL" for GAAP
        "Book Life",      # Typically longer than Tax life
        "MI Cost",        # Michigan state depreciation
        "MI Method",      # Same as Tax
        "MI Life",        # Same as Tax Life
        "Date Disposed",
        "Gross Proceeds",
    ]

    df = df[column_order]

    # Save to Excel (header at row 0 - FA CS default)
    output_file = OUTPUT_DIR / "fa_cs_import_test_v2.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="FA_CS_Import", index=False)

    print("=" * 70)
    print("FA CS IMPORT TEST FILE - VERSION 2 (Custom Mapping)")
    print("=" * 70)
    print(f"\nFile created: {output_file}")
    print(f"\nAssets included: {len(df)}")
    print("\nColumn order (matches FA CS 'AI_Tool_Import' mapping):")
    for i, col in enumerate(df.columns, 1):
        sample = df[col].iloc[0]
        print(f"  {i}. {col}: {sample}")

    print("\n" + "=" * 70)
    print("IMPORT INSTRUCTIONS")
    print("=" * 70)
    print("""
1. Open Fixed Asset CS

2. Go to File → Import → Excel

3. Header Row should be 0 (default) - columns start at row 1

4. Select mapping: "AI_Tool_Import" (your custom mapping)

5. Select the file: fa_cs_import_test_v2.xlsx

6. Verify mapping matches:
   Col 1: Asset #            → Asset Number
   Col 2: Description        → Description
   Col 3: Date In Service    → In-Service Date
   Col 4: Tax Cost           → Cost/Basis
   Col 5: Tax Method         → Method
   Col 6: Tax Life           → Recovery Period
   Col 7: Tax Sec 179 Expensed → Section 179
   Col 8: Tax Cur Depreciation → Current Depreciation
   Col 9: Tax Prior Depreciation → Prior Depreciation
   Col 10: Date Disposed     → Disposal Date
   Col 11: Gross Proceeds    → Sale Proceeds

7. Complete import

8. Verify results:
   - Asset 1: $5,000 179 deduction (full expensing)
   - Asset 2: FA CS should calculate MACRS ($1,143)
   - Asset 3: FA CS should calculate MACRS ($7,000)
   - Asset 4: Should show as disposed with $3,000 proceeds
""")

    print("=" * 70)
    print("EXPECTED RESULTS")
    print("=" * 70)
    print("""
| Asset | Description        | 179 Expense | Expected Cur Depr |
|-------|--------------------|-------------|-------------------|
| 1     | Computer ($5K)     | $5,000      | $0 (fully expensed)|
| 2     | Furniture ($8K)    | $0          | $1,143 (FA CS calc)|
| 3     | Vehicle ($35K)     | $0          | $7,000 (FA CS calc)|
| 4     | Disposed ($10K)    | $0          | N/A (disposed)    |

Questions to verify:
1. Did Asset 1 show $5,000 Section 179?
2. Did FA CS calculate depreciation for Assets 2 & 3?
3. Did Asset 4 import correctly as a disposal?
4. Did you need to change header row setting?
""")

    return output_file


if __name__ == "__main__":
    generate_test_files()
