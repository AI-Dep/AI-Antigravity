#!/usr/bin/env python3
"""
Generate test data files for Fixed Asset AI integration tests.

Creates Excel files with various scenarios:
1. Standard format - clean data
2. Edge cases - missing fields, odd formatting
3. Problem data - duplicates, date issues, accum dep anomalies
4. Multi-sheet - additions, disposals, transfers
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, date

OUTPUT_DIR = Path(__file__).parent


def create_standard_test_file():
    """Create a clean, standard format test file."""
    data = {
        "Asset ID": ["ASSET-001", "ASSET-002", "ASSET-003", "ASSET-004", "ASSET-005"],
        "Description": [
            "Dell Laptop Computer - XPS 15",
            "Office Desk - Executive Model",
            "Cisco Server Rack - Model 4500",
            "HP LaserJet Printer",
            "Office Chair - Ergonomic"
        ],
        "Cost": [2500.00, 800.00, 25000.00, 500.00, 350.00],
        "Acquisition Date": [
            "2025-01-15", "2025-02-20", "2025-03-10",
            "2025-04-01", "2025-05-15"
        ],
        "In Service Date": [
            "2025-01-15", "2025-02-20", "2025-03-10",
            "2025-04-01", "2025-05-15"
        ],
        "Category": [
            "Computer Equipment", "Furniture", "Computer Equipment",
            "Office Equipment", "Furniture"
        ],
        "Location": ["HQ-Room-101", "HQ-Room-102", "DC-Room-001", "HQ-Room-103", "HQ-Room-104"],
    }

    df = pd.DataFrame(data)
    output_path = OUTPUT_DIR / "test_standard_format.xlsx"
    df.to_excel(output_path, index=False, sheet_name="Assets")
    print(f"Created: {output_path}")
    return output_path


def create_edge_cases_file():
    """Create file with edge cases - missing fields, odd formatting."""
    data = {
        "Asset #": ["1", "2", "3", "4", "5"],  # Non-standard header
        "Property Description": [  # Non-standard header
            "Laptop",
            "",  # Missing description
            "Server with special chars: $#@!",
            "Very " + "long " * 50 + "description",  # Very long
            "Normal item"
        ],
        "Original Cost": ["$1,500.00", "800", "(500.00)", "25000", "$0.00"],  # Various formats
        "Date Acquired": [
            "01/15/2025",  # US format
            "2025-02-20",  # ISO format
            "March 10, 2025",  # Text format
            "",  # Missing
            "15-May-2025"  # European-ish
        ],
        "Placed in Service": [
            "01/15/2025", "02/20/2025", "03/10/2025", "04/01/2025", "05/15/2025"
        ],
    }

    df = pd.DataFrame(data)
    output_path = OUTPUT_DIR / "test_edge_cases.xlsx"
    df.to_excel(output_path, index=False, sheet_name="Fixed Assets")
    print(f"Created: {output_path}")
    return output_path


def create_problem_data_file():
    """Create file with problems that should trigger warnings."""
    data = {
        "Asset ID": [
            "DUP-001", "DUP-001",  # Duplicate
            "PROB-003", "PROB-004", "PROB-005", "PROB-006"
        ],
        "Description": [
            "Duplicate Asset One",
            "Duplicate Asset One - Same ID!",
            "Asset with future date",
            "Asset with disposal before service",
            "Current year with accum dep (PROBLEM)",
            "Normal asset"
        ],
        "Cost": [1000, 1000, 5000, 3000, 2000, 1500],
        "In Service Date": [
            "2025-01-15",
            "2025-01-15",
            "2099-01-01",  # Future date
            "2025-03-15",
            "2025-02-15",  # Current year
            "2025-04-01"
        ],
        "Disposal Date": [
            None, None, None,
            "2024-01-01",  # Before in-service!
            None, None
        ],
        "Accumulated Depreciation": [
            0, 0, 0, 0,
            800,  # Current year with accum dep - PROBLEM
            0
        ],
        "Transaction Type": [
            "Addition", "Addition", "Addition",
            "Disposal", "Addition", "Addition"
        ]
    }

    df = pd.DataFrame(data)
    output_path = OUTPUT_DIR / "test_problem_data.xlsx"
    df.to_excel(output_path, index=False, sheet_name="Assets")
    print(f"Created: {output_path}")
    return output_path


def create_multi_sheet_file():
    """Create file with multiple sheets - Additions, Disposals, Existing."""
    output_path = OUTPUT_DIR / "test_multi_sheet.xlsx"

    # Additions sheet
    additions = pd.DataFrame({
        "Asset ID": ["ADD-001", "ADD-002", "ADD-003"],
        "Description": ["New Laptop 2025", "New Server 2025", "New Desk 2025"],
        "Cost": [2000, 15000, 500],
        "In Service Date": ["2025-01-15", "2025-02-20", "2025-03-10"],
        "Category": ["Computer Equipment", "Computer Equipment", "Furniture"]
    })

    # Disposals sheet
    disposals = pd.DataFrame({
        "Asset ID": ["DISP-001", "DISP-002"],
        "Description": ["Old Laptop - Sold", "Old Server - Scrapped"],
        "Cost": [1500, 10000],
        "In Service Date": ["2020-01-15", "2019-05-20"],
        "Disposal Date": ["2025-06-15", "2025-07-01"],
        "Sale Proceeds": [200, 0]
    })

    # Existing assets sheet
    existing = pd.DataFrame({
        "Asset ID": ["EXIST-001", "EXIST-002"],
        "Description": ["Existing Server", "Existing Furniture"],
        "Cost": [20000, 5000],
        "In Service Date": ["2023-01-15", "2022-06-20"],
        "Accumulated Depreciation": [8000, 2500]
    })

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        additions.to_excel(writer, sheet_name="2025 Additions", index=False)
        disposals.to_excel(writer, sheet_name="Disposals", index=False)
        existing.to_excel(writer, sheet_name="Existing Assets", index=False)

    print(f"Created: {output_path}")
    return output_path


def create_currency_format_file():
    """Create file with various currency formats to test parsing."""
    data = {
        "Asset ID": ["CUR-001", "CUR-002", "CUR-003", "CUR-004", "CUR-005"],
        "Description": ["Item 1", "Item 2", "Item 3", "Item 4", "Item 5"],
        "Cost": [
            "$1,234.56",      # US format with $
            "1234.56",        # Plain decimal
            "(5,000.00)",     # Accounting negative
            "10000",          # No formatting
            "$0.00"           # Zero
        ],
        "In Service Date": [
            "2025-01-15", "2025-02-15", "2025-03-15", "2025-04-15", "2025-05-15"
        ]
    }

    df = pd.DataFrame(data)
    output_path = OUTPUT_DIR / "test_currency_formats.xlsx"
    df.to_excel(output_path, index=False, sheet_name="Assets")
    print(f"Created: {output_path}")
    return output_path


def create_vehicle_test_file():
    """Create file with vehicles to test luxury auto limits."""
    data = {
        "Asset ID": ["VEH-001", "VEH-002", "VEH-003", "VEH-004"],
        "Description": [
            "2025 BMW 5 Series - Company Car",
            "2025 Ford F-150 - Work Truck",
            "2025 Mercedes GLS 580 SUV",  # Heavy SUV > 6000 lbs
            "2025 Tesla Model 3"
        ],
        "Cost": [65000, 55000, 95000, 45000],
        "In Service Date": ["2025-02-01", "2025-02-15", "2025-03-01", "2025-03-15"],
        "Category": ["Vehicle", "Vehicle", "Vehicle", "Vehicle"],
        "Vehicle Type": ["Passenger Auto", "Truck", "Heavy SUV", "Passenger Auto"],
        "GVWR": [4500, 7000, 7500, 4000]  # Gross Vehicle Weight Rating
    }

    df = pd.DataFrame(data)
    output_path = OUTPUT_DIR / "test_vehicles.xlsx"
    df.to_excel(output_path, index=False, sheet_name="Vehicles")
    print(f"Created: {output_path}")
    return output_path


def create_all_test_files():
    """Generate all test data files."""
    print("=" * 60)
    print("GENERATING TEST DATA FILES")
    print("=" * 60)

    files = []
    files.append(create_standard_test_file())
    files.append(create_edge_cases_file())
    files.append(create_problem_data_file())
    files.append(create_multi_sheet_file())
    files.append(create_currency_format_file())
    files.append(create_vehicle_test_file())

    print("=" * 60)
    print(f"Generated {len(files)} test files in {OUTPUT_DIR}")
    print("=" * 60)

    return files


if __name__ == "__main__":
    create_all_test_files()
