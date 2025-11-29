"""
Generate test data CSV files for FA CS Import Validation
Run this script to create all test data sets.
"""

import pandas as pd
from datetime import datetime
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def create_test_set_1_basic_additions():
    """Test Set 1: Basic Additions (10 assets)"""
    data = [
        {"Asset ID": "ADD-001", "Description": "Office Desk - Executive", "Cost": 500, "Acquisition Date": "01/15/2024", "In Service Date": "01/15/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-002", "Description": "Dell Laptop XPS 15", "Cost": 1200, "Acquisition Date": "02/01/2024", "In Service Date": "02/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-003", "Description": "Ford Transit Delivery Van", "Cost": 35000, "Acquisition Date": "03/15/2024", "In Service Date": "03/15/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-004", "Description": "Office Building - 123 Main St", "Cost": 500000, "Acquisition Date": "04/01/2024", "In Service Date": "04/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-005", "Description": "Warehouse Shelving System", "Cost": 8000, "Acquisition Date": "05/01/2024", "In Service Date": "05/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-006", "Description": "HVAC System - Rooftop Unit", "Cost": 25000, "Acquisition Date": "06/01/2024", "In Service Date": "06/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-007", "Description": "Toyota Forklift Model 8FGU25", "Cost": 18000, "Acquisition Date": "07/01/2024", "In Service Date": "07/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-008", "Description": "Security Camera System", "Cost": 5000, "Acquisition Date": "08/01/2024", "In Service Date": "08/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-009", "Description": "Parking Lot - Asphalt Paving", "Cost": 45000, "Acquisition Date": "09/01/2024", "In Service Date": "09/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "ADD-010", "Description": "Cisco Phone System VoIP", "Cost": 3500, "Acquisition Date": "10/01/2024", "In Service Date": "10/01/2024", "Transaction Type": "Addition"},
    ]
    df = pd.DataFrame(data)
    df.to_csv(os.path.join(OUTPUT_DIR, "test_set_1_basic_additions.csv"), index=False)
    print(f"Created: test_set_1_basic_additions.csv ({len(df)} assets)")
    return df


def create_test_set_2_section_179_bonus():
    """Test Set 2: Section 179 & Bonus Depreciation (5 assets)"""
    data = [
        {"Asset ID": "179-001", "Description": "Manufacturing Equipment - Full 179", "Cost": 50000, "Acquisition Date": "01/15/2024", "In Service Date": "01/15/2024", "Transaction Type": "Addition", "Section 179": 50000, "Bonus %": 0},
        {"Asset ID": "179-002", "Description": "Production Machinery - 60% Bonus", "Cost": 100000, "Acquisition Date": "02/01/2024", "In Service Date": "02/01/2024", "Transaction Type": "Addition", "Section 179": 0, "Bonus %": 60},
        {"Asset ID": "179-003", "Description": "Industrial Equipment - Partial 179 + Bonus", "Cost": 75000, "Acquisition Date": "03/15/2024", "In Service Date": "03/15/2024", "Transaction Type": "Addition", "Section 179": 25000, "Bonus %": 60},
        {"Asset ID": "179-004", "Description": "Chevrolet Tahoe SUV (6000+ lbs GVW)", "Cost": 65000, "Acquisition Date": "04/01/2024", "In Service Date": "04/01/2024", "Transaction Type": "Addition", "Section 179": 28900, "Bonus %": 60},
        {"Asset ID": "179-005", "Description": "Company Vehicle - Listed Property 50% Business", "Cost": 10000, "Acquisition Date": "05/01/2024", "In Service Date": "05/01/2024", "Transaction Type": "Addition", "Section 179": 0, "Bonus %": 0, "Business Use %": 50},
    ]
    df = pd.DataFrame(data)
    df.to_csv(os.path.join(OUTPUT_DIR, "test_set_2_section_179_bonus.csv"), index=False)
    print(f"Created: test_set_2_section_179_bonus.csv ({len(df)} assets)")
    return df


def create_test_set_3_disposals():
    """Test Set 3: Disposals (5 assets)"""
    data = [
        {"Asset ID": "DISP-001", "Description": "Old Desktop Computer - Sold", "Cost": 2000, "Acquisition Date": "01/15/2020", "In Service Date": "01/15/2020", "Transaction Type": "Disposal", "Disposal Date": "03/15/2024", "Proceeds": 200, "Accumulated Depreciation": 1800},
        {"Asset ID": "DISP-002", "Description": "Company Vehicle - Sold", "Cost": 30000, "Acquisition Date": "06/01/2019", "In Service Date": "06/01/2019", "Transaction Type": "Disposal", "Disposal Date": "06/30/2024", "Proceeds": 15000, "Accumulated Depreciation": 20000},
        {"Asset ID": "DISP-003", "Description": "Obsolete Equipment - Scrapped", "Cost": 5000, "Acquisition Date": "03/01/2018", "In Service Date": "03/01/2018", "Transaction Type": "Disposal", "Disposal Date": "09/01/2024", "Proceeds": 0, "Accumulated Depreciation": 5000},
        {"Asset ID": "DISP-004", "Description": "Office Furniture - Trade-in", "Cost": 10000, "Acquisition Date": "07/15/2020", "In Service Date": "07/15/2020", "Transaction Type": "Disposal", "Disposal Date": "12/01/2024", "Proceeds": 3000, "Accumulated Depreciation": 7000},
        {"Asset ID": "DISP-005", "Description": "Partial Equipment Disposal", "Cost": 50000, "Acquisition Date": "01/01/2021", "In Service Date": "01/01/2021", "Transaction Type": "Disposal", "Disposal Date": "07/15/2024", "Proceeds": 10000, "Accumulated Depreciation": 15000},
    ]
    df = pd.DataFrame(data)
    df.to_csv(os.path.join(OUTPUT_DIR, "test_set_3_disposals.csv"), index=False)
    print(f"Created: test_set_3_disposals.csv ({len(df)} assets)")
    return df


def create_test_set_4_existing_assets():
    """Test Set 4: Existing Assets (5 assets)"""
    data = [
        {"Asset ID": "EXIST-001", "Description": "3-Year Old Manufacturing Equipment", "Cost": 20000, "Acquisition Date": "01/01/2021", "In Service Date": "01/01/2021", "Transaction Type": "Existing Asset", "Accumulated Depreciation": 12000, "Prior Section 179": 0, "Prior Bonus": 10000},
        {"Asset ID": "EXIST-002", "Description": "5-Year Old Commercial Building", "Cost": 300000, "Acquisition Date": "07/01/2019", "In Service Date": "07/01/2019", "Transaction Type": "Existing Asset", "Accumulated Depreciation": 35000, "Prior Section 179": 0, "Prior Bonus": 0},
        {"Asset ID": "EXIST-003", "Description": "2-Year Old Delivery Vehicle", "Cost": 40000, "Acquisition Date": "06/15/2022", "In Service Date": "06/15/2022", "Transaction Type": "Existing Asset", "Accumulated Depreciation": 20000, "Prior Section 179": 0, "Prior Bonus": 24000},
        {"Asset ID": "EXIST-004", "Description": "Fully Depreciated Office Furniture", "Cost": 8000, "Acquisition Date": "03/01/2018", "In Service Date": "03/01/2018", "Transaction Type": "Existing Asset", "Accumulated Depreciation": 8000, "Prior Section 179": 0, "Prior Bonus": 0},
        {"Asset ID": "EXIST-005", "Description": "Equipment with Partial 179 Taken", "Cost": 15000, "Acquisition Date": "01/01/2023", "In Service Date": "01/01/2023", "Transaction Type": "Existing Asset", "Accumulated Depreciation": 3000, "Prior Section 179": 5000, "Prior Bonus": 0},
    ]
    df = pd.DataFrame(data)
    df.to_csv(os.path.join(OUTPUT_DIR, "test_set_4_existing_assets.csv"), index=False)
    print(f"Created: test_set_4_existing_assets.csv ({len(df)} assets)")
    return df


def create_test_set_5_transfers():
    """Test Set 5: Transfers (3 assets)"""
    data = [
        {"Asset ID": "XFER-001", "Description": "Equipment Transfer - Building A to B", "Cost": 15000, "Acquisition Date": "01/01/2022", "In Service Date": "01/01/2022", "Transaction Type": "Transfer", "Transfer Date": "04/01/2024", "From Location": "Building A", "To Location": "Building B", "From Department": "Sales", "To Department": "Marketing"},
        {"Asset ID": "XFER-002", "Description": "Asset Reclassification - Dept Change", "Cost": 8000, "Acquisition Date": "06/15/2021", "In Service Date": "06/15/2021", "Transaction Type": "Transfer", "Transfer Date": "07/15/2024", "From Location": "", "To Location": "", "From Department": "Dept 100", "To Department": "Dept 200"},
        {"Asset ID": "XFER-003", "Description": "Location Move Only", "Cost": 12000, "Acquisition Date": "03/01/2023", "In Service Date": "03/01/2023", "Transaction Type": "Transfer", "Transfer Date": "10/01/2024", "From Location": "Site 1", "To Location": "Site 2", "From Department": "", "To Department": ""},
    ]
    df = pd.DataFrame(data)
    df.to_csv(os.path.join(OUTPUT_DIR, "test_set_5_transfers.csv"), index=False)
    print(f"Created: test_set_5_transfers.csv ({len(df)} assets)")
    return df


def create_test_set_6_edge_cases():
    """Test Set 6: Edge Cases (10 scenarios)"""
    data = [
        {"Asset ID": "EDGE-001", "Description": "Zero Cost Asset - Donated Equipment", "Cost": 0, "Acquisition Date": "01/15/2024", "In Service Date": "01/15/2024", "Transaction Type": "Addition"},
        {"Asset ID": "EDGE-002", "Description": "Future In-Service Date Asset", "Cost": 5000, "Acquisition Date": "01/01/2024", "In Service Date": "12/31/2025", "Transaction Type": "Addition"},
        {"Asset ID": "EDGE-003", "Description": "Very Long Description - " + "X" * 500, "Cost": 1000, "Acquisition Date": "02/01/2024", "In Service Date": "02/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "EDGE-004", "Description": "Special Chars: @#$%^&*()!<>\"'", "Cost": 2000, "Acquisition Date": "03/01/2024", "In Service Date": "03/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "", "Description": "Missing Asset ID Test", "Cost": 3000, "Acquisition Date": "04/01/2024", "In Service Date": "04/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "EDGE-001", "Description": "Duplicate Asset ID Test", "Cost": 4000, "Acquisition Date": "05/01/2024", "In Service Date": "05/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "EDGE-007", "Description": "Negative Cost Asset", "Cost": -5000, "Acquisition Date": "06/01/2024", "In Service Date": "06/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "EDGE-008", "Description": "Minimal Cost Asset - One Cent", "Cost": 0.01, "Acquisition Date": "07/01/2024", "In Service Date": "07/01/2024", "Transaction Type": "Addition"},
        {"Asset ID": "EDGE-009", "Description": "Listed Property 100% Business Use", "Cost": 8000, "Acquisition Date": "08/01/2024", "In Service Date": "08/01/2024", "Transaction Type": "Addition", "Business Use %": 100},
        {"Asset ID": "EDGE-010", "Description": "Land - Non-Depreciable", "Cost": 100000, "Acquisition Date": "09/01/2024", "In Service Date": "09/01/2024", "Transaction Type": "Addition"},
    ]
    df = pd.DataFrame(data)
    df.to_csv(os.path.join(OUTPUT_DIR, "test_set_6_edge_cases.csv"), index=False)
    print(f"Created: test_set_6_edge_cases.csv ({len(df)} assets)")
    return df


def create_combined_test_file():
    """Create a combined file with all test sets"""
    all_data = []

    # Collect all test sets
    sets = [
        create_test_set_1_basic_additions(),
        create_test_set_2_section_179_bonus(),
        create_test_set_3_disposals(),
        create_test_set_4_existing_assets(),
        create_test_set_5_transfers(),
        create_test_set_6_edge_cases(),
    ]

    for df in sets:
        all_data.append(df)

    combined = pd.concat(all_data, ignore_index=True)
    combined.to_csv(os.path.join(OUTPUT_DIR, "test_set_ALL_combined.csv"), index=False)
    print(f"\nCreated: test_set_ALL_combined.csv ({len(combined)} total assets)")

    # Also create Excel version
    try:
        combined.to_excel(os.path.join(OUTPUT_DIR, "test_set_ALL_combined.xlsx"), index=False)
        print(f"Created: test_set_ALL_combined.xlsx ({len(combined)} total assets)")
    except Exception as e:
        print(f"Could not create Excel file: {e}")


def create_expected_results():
    """Create expected results for validation"""
    expected = [
        # Test Set 1 - Basic Additions Expected Results
        {"Asset ID": "ADD-001", "Expected Category": "Furniture and Fixtures", "Expected Life": 7, "Expected Method": "200DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-002", "Expected Category": "Computer Equipment", "Expected Life": 5, "Expected Method": "200DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-003", "Expected Category": "Vehicles", "Expected Life": 5, "Expected Method": "200DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-004", "Expected Category": "Nonresidential Real Property", "Expected Life": 39, "Expected Method": "SL", "Expected Convention": "MM"},
        {"Asset ID": "ADD-005", "Expected Category": "Furniture and Fixtures", "Expected Life": 7, "Expected Method": "200DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-006", "Expected Category": "Land Improvements", "Expected Life": 15, "Expected Method": "150DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-007", "Expected Category": "Machinery and Equipment", "Expected Life": 7, "Expected Method": "200DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-008", "Expected Category": "Computer Equipment", "Expected Life": 5, "Expected Method": "200DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-009", "Expected Category": "Land Improvements", "Expected Life": 15, "Expected Method": "150DB", "Expected Convention": "HY"},
        {"Asset ID": "ADD-010", "Expected Category": "Computer Equipment", "Expected Life": 5, "Expected Method": "200DB", "Expected Convention": "HY"},
    ]
    df = pd.DataFrame(expected)
    df.to_csv(os.path.join(OUTPUT_DIR, "expected_results_test_set_1.csv"), index=False)
    print(f"\nCreated: expected_results_test_set_1.csv (for validation)")


if __name__ == "__main__":
    print("=" * 60)
    print("Generating FA CS Import Test Data")
    print("=" * 60)
    print()

    create_combined_test_file()
    create_expected_results()

    print()
    print("=" * 60)
    print("Test data generation complete!")
    print(f"Files saved to: {OUTPUT_DIR}")
    print("=" * 60)
