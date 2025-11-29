"""
Generate a Realistic Fixed Asset Schedule for Testing
Simulates a mid-size company (e.g., manufacturing/distribution business)
Tax Year: 2024
"""

import pandas as pd
from datetime import date
from pathlib import Path

# Output directory
OUTPUT_DIR = Path(__file__).parent
OUTPUT_FILE = OUTPUT_DIR / "Acme_Manufacturing_2024_Assets.xlsx"

# =============================================================================
# SHEET 1: CURRENT YEAR ADDITIONS (2024)
# Assets placed in service in 2024 - eligible for Section 179 / Bonus
# =============================================================================

additions_2024 = [
    # Computer Equipment (5-year MACRS)
    {"Asset ID": "2024-001", "Description": "Dell PowerEdge R750 Server", "Category": "Computer Equipment",
     "Cost": 12500.00, "Acquisition Date": "2024-01-15", "In Service Date": "2024-01-20", "Location": "Server Room"},
    {"Asset ID": "2024-002", "Description": "HP EliteBook 840 Laptops (10 units)", "Category": "IT Equipment",
     "Cost": 15000.00, "Acquisition Date": "2024-02-01", "In Service Date": "2024-02-05", "Location": "Office"},
    {"Asset ID": "2024-003", "Description": "Cisco Catalyst 9300 Network Switch", "Category": "Network Equipment",
     "Cost": 8500.00, "Acquisition Date": "2024-02-10", "In Service Date": "2024-02-15", "Location": "Server Room"},
    {"Asset ID": "2024-004", "Description": "Apple MacBook Pro M3 - Engineering", "Category": "Computer",
     "Cost": 3499.00, "Acquisition Date": "2024-03-01", "In Service Date": "2024-03-05", "Location": "Engineering"},

    # Office Furniture (7-year MACRS)
    {"Asset ID": "2024-005", "Description": "Herman Miller Aeron Chairs (20 units)", "Category": "Office Furniture",
     "Cost": 28000.00, "Acquisition Date": "2024-01-10", "In Service Date": "2024-01-15", "Location": "Office"},
    {"Asset ID": "2024-006", "Description": "Steelcase Standing Desks (15 units)", "Category": "Furniture",
     "Cost": 22500.00, "Acquisition Date": "2024-02-20", "In Service Date": "2024-02-25", "Location": "Office"},
    {"Asset ID": "2024-007", "Description": "Conference Room Table - Executive", "Category": "Office Furniture",
     "Cost": 4500.00, "Acquisition Date": "2024-03-10", "In Service Date": "2024-03-15", "Location": "Conf Room A"},
    {"Asset ID": "2024-008", "Description": "Reception Desk and Seating Area", "Category": "Furniture",
     "Cost": 8750.00, "Acquisition Date": "2024-04-01", "In Service Date": "2024-04-05", "Location": "Lobby"},

    # Office Equipment (5-7 year MACRS)
    {"Asset ID": "2024-009", "Description": "Canon imageRUNNER ADVANCE Copier/Printer", "Category": "Office Equipment",
     "Cost": 12000.00, "Acquisition Date": "2024-01-20", "In Service Date": "2024-01-25", "Location": "Office"},
    {"Asset ID": "2024-010", "Description": "Shred-it Industrial Paper Shredder", "Category": "Office Equipment",
     "Cost": 2800.00, "Acquisition Date": "2024-02-15", "In Service Date": "2024-02-18", "Location": "Mail Room"},

    # Manufacturing Equipment (7-year MACRS)
    {"Asset ID": "2024-011", "Description": "Haas VF-4 CNC Vertical Machining Center", "Category": "Manufacturing Equipment",
     "Cost": 125000.00, "Acquisition Date": "2024-03-01", "In Service Date": "2024-04-01", "Location": "Plant Floor"},
    {"Asset ID": "2024-012", "Description": "Lincoln Electric MIG Welder - PowerMIG 360MP", "Category": "Machinery",
     "Cost": 8500.00, "Acquisition Date": "2024-03-15", "In Service Date": "2024-03-20", "Location": "Welding Bay"},
    {"Asset ID": "2024-013", "Description": "Bridgeport Series I Milling Machine", "Category": "M&E",
     "Cost": 18500.00, "Acquisition Date": "2024-04-10", "In Service Date": "2024-04-15", "Location": "Machine Shop"},
    {"Asset ID": "2024-014", "Description": "Air Compressor - Ingersoll Rand 80 Gallon", "Category": "Equipment",
     "Cost": 3200.00, "Acquisition Date": "2024-05-01", "In Service Date": "2024-05-05", "Location": "Plant Floor"},
    {"Asset ID": "2024-015", "Description": "Forklift - Toyota 8FGU25 5000lb", "Category": "Warehouse Equipment",
     "Cost": 32000.00, "Acquisition Date": "2024-05-15", "In Service Date": "2024-05-20", "Location": "Warehouse"},

    # Vehicles (5-year MACRS, listed property)
    {"Asset ID": "2024-016", "Description": "2024 Ford F-150 XLT - Sales Rep", "Category": "Vehicle",
     "Cost": 48500.00, "Acquisition Date": "2024-02-01", "In Service Date": "2024-02-05", "Location": "Sales", "Business Use %": 85},
    {"Asset ID": "2024-017", "Description": "2024 Chevrolet Express 2500 Cargo Van", "Category": "Truck",
     "Cost": 42000.00, "Acquisition Date": "2024-03-01", "In Service Date": "2024-03-05", "Location": "Delivery", "Business Use %": 100},
    {"Asset ID": "2024-018", "Description": "2024 Toyota RAV4 Hybrid - Manager", "Category": "Auto",
     "Cost": 38500.00, "Acquisition Date": "2024-06-01", "In Service Date": "2024-06-05", "Location": "Admin", "Business Use %": 60},

    # QIP - Qualified Improvement Property (15-year, bonus eligible post-2017)
    {"Asset ID": "2024-019", "Description": "LED Lighting Retrofit - Office Building", "Category": "Leasehold Improvements",
     "Cost": 45000.00, "Acquisition Date": "2024-04-01", "In Service Date": "2024-04-15", "Location": "Building A"},
    {"Asset ID": "2024-020", "Description": "Interior Renovation - Break Room", "Category": "Tenant Improvements",
     "Cost": 28000.00, "Acquisition Date": "2024-05-01", "In Service Date": "2024-05-20", "Location": "Building A"},
    {"Asset ID": "2024-021", "Description": "New Flooring - Warehouse Office Area", "Category": "Leasehold",
     "Cost": 18500.00, "Acquisition Date": "2024-06-15", "In Service Date": "2024-06-30", "Location": "Warehouse"},

    # Land Improvements (15-year MACRS)
    {"Asset ID": "2024-022", "Description": "Parking Lot Resurfacing and Striping", "Category": "Land Improvement",
     "Cost": 65000.00, "Acquisition Date": "2024-07-01", "In Service Date": "2024-07-15", "Location": "Main Lot"},
    {"Asset ID": "2024-023", "Description": "Security Fence Installation - Perimeter", "Category": "Site Improvement",
     "Cost": 32000.00, "Acquisition Date": "2024-07-15", "In Service Date": "2024-08-01", "Location": "Perimeter"},
    {"Asset ID": "2024-024", "Description": "Landscape and Irrigation System", "Category": "Land Improvement",
     "Cost": 18000.00, "Acquisition Date": "2024-08-01", "In Service Date": "2024-08-15", "Location": "Front Entrance"},

    # Building Equipment (15-year MACRS)
    {"Asset ID": "2024-025", "Description": "Trane HVAC Rooftop Unit Replacement", "Category": "HVAC",
     "Cost": 75000.00, "Acquisition Date": "2024-06-01", "In Service Date": "2024-06-20", "Location": "Building A Roof"},
    {"Asset ID": "2024-026", "Description": "Emergency Generator - Generac 150kW", "Category": "Building Equipment",
     "Cost": 45000.00, "Acquisition Date": "2024-07-01", "In Service Date": "2024-07-20", "Location": "Utility Area"},

    # Software (3-year MACRS)
    {"Asset ID": "2024-027", "Description": "Microsoft Dynamics 365 ERP License (perpetual)", "Category": "Software",
     "Cost": 85000.00, "Acquisition Date": "2024-01-01", "In Service Date": "2024-02-01", "Location": "IT"},
    {"Asset ID": "2024-028", "Description": "AutoCAD 2024 Engineering Suite (5 seats)", "Category": "Computer Software",
     "Cost": 12500.00, "Acquisition Date": "2024-03-01", "In Service Date": "2024-03-15", "Location": "Engineering"},

    # De Minimis / Low Value Items (test threshold handling)
    {"Asset ID": "2024-029", "Description": "Brother Laser Printer HL-L2350DW", "Category": "Office Equipment",
     "Cost": 150.00, "Acquisition Date": "2024-04-01", "In Service Date": "2024-04-01", "Location": "Office"},
    {"Asset ID": "2024-030", "Description": "Desk Lamp - LED Task Light (5 units)", "Category": "Furniture",
     "Cost": 250.00, "Acquisition Date": "2024-04-15", "In Service Date": "2024-04-15", "Location": "Office"},

    # Edge cases / Ambiguous descriptions
    {"Asset ID": "2024-031", "Description": "Equipment for production line #3", "Category": "",
     "Cost": 15000.00, "Acquisition Date": "2024-05-01", "In Service Date": "2024-05-10", "Location": "Plant"},
    {"Asset ID": "2024-032", "Description": "Misc office supplies - bulk purchase", "Category": "",
     "Cost": 4500.00, "Acquisition Date": "2024-06-01", "In Service Date": "2024-06-01", "Location": "Office"},
    {"Asset ID": "2024-033", "Description": "Elevator modernization - Building A", "Category": "Building Improvement",
     "Cost": 185000.00, "Acquisition Date": "2024-08-01", "In Service Date": "2024-09-01", "Location": "Building A"},
]

# =============================================================================
# SHEET 2: EXISTING ASSETS (Prior Years)
# Assets already in service - NOT eligible for Section 179 / Bonus in 2024
# =============================================================================

existing_assets = [
    # 2023 acquisitions
    {"Asset ID": "2023-001", "Description": "Dell OptiPlex Desktop Computers (25 units)", "Category": "Computer Equipment",
     "Cost": 25000.00, "Acquisition Date": "2023-03-15", "In Service Date": "2023-03-20", "Location": "Office",
     "Tax Prior Depreciation": 5000.00},
    {"Asset ID": "2023-002", "Description": "Office Workstations and Cubicles", "Category": "Office Furniture",
     "Cost": 45000.00, "Acquisition Date": "2023-01-10", "In Service Date": "2023-01-15", "Location": "Office",
     "Tax Prior Depreciation": 6428.57},
    {"Asset ID": "2023-003", "Description": "2023 Ford Transit Van - Delivery", "Category": "Vehicle",
     "Cost": 38000.00, "Acquisition Date": "2023-06-01", "In Service Date": "2023-06-05", "Location": "Warehouse",
     "Tax Prior Depreciation": 7600.00, "Business Use %": 100},

    # 2022 acquisitions
    {"Asset ID": "2022-001", "Description": "Mazak Quick Turn 200 CNC Lathe", "Category": "Manufacturing Equipment",
     "Cost": 95000.00, "Acquisition Date": "2022-04-01", "In Service Date": "2022-04-15", "Location": "Machine Shop",
     "Tax Prior Depreciation": 27142.86},
    {"Asset ID": "2022-002", "Description": "Pallet Racking System - Warehouse", "Category": "Warehouse Equipment",
     "Cost": 42000.00, "Acquisition Date": "2022-07-01", "In Service Date": "2022-07-15", "Location": "Warehouse",
     "Tax Prior Depreciation": 12000.00},

    # 2021 acquisitions
    {"Asset ID": "2021-001", "Description": "Building HVAC System - Original Install", "Category": "Building Equipment",
     "Cost": 120000.00, "Acquisition Date": "2021-01-15", "In Service Date": "2021-02-01", "Location": "Building A",
     "Tax Prior Depreciation": 24000.00},
    {"Asset ID": "2021-002", "Description": "Warehouse LED Lighting System", "Category": "Leasehold Improvements",
     "Cost": 35000.00, "Acquisition Date": "2021-06-01", "In Service Date": "2021-06-15", "Location": "Warehouse",
     "Tax Prior Depreciation": 7000.00},

    # 2020 acquisitions
    {"Asset ID": "2020-001", "Description": "Conference Room AV System", "Category": "Office Equipment",
     "Cost": 18000.00, "Acquisition Date": "2020-02-01", "In Service Date": "2020-02-15", "Location": "Conf Room A",
     "Tax Prior Depreciation": 14400.00},
    {"Asset ID": "2020-002", "Description": "Production Line Conveyor System", "Category": "Machinery & Equipment",
     "Cost": 85000.00, "Acquisition Date": "2020-08-01", "In Service Date": "2020-08-20", "Location": "Plant Floor",
     "Tax Prior Depreciation": 36428.57},

    # 2019 acquisitions (almost fully depreciated 5-year property)
    {"Asset ID": "2019-001", "Description": "Dell PowerEdge Server - Legacy", "Category": "Computer Equipment",
     "Cost": 15000.00, "Acquisition Date": "2019-05-01", "In Service Date": "2019-05-10", "Location": "Server Room",
     "Tax Prior Depreciation": 14400.00},

    # 2015 acquisition (39-year property - building component)
    {"Asset ID": "2015-001", "Description": "Warehouse Building Shell", "Category": "Building",
     "Cost": 850000.00, "Acquisition Date": "2015-06-01", "In Service Date": "2015-07-01", "Location": "Main Campus",
     "Tax Prior Depreciation": 196153.85},

    # Land (non-depreciable)
    {"Asset ID": "LAND-001", "Description": "Land - Main Campus 5 Acres", "Category": "Land",
     "Cost": 450000.00, "Acquisition Date": "2015-01-15", "In Service Date": "2015-01-15", "Location": "Main Campus",
     "Tax Prior Depreciation": 0.00},
]

# =============================================================================
# SHEET 3: DISPOSALS (2024)
# Assets sold, retired, or scrapped during 2024
# =============================================================================

disposals_2024 = [
    # Sold assets
    {"Asset ID": "2019-002", "Description": "HP LaserJet Printers (10 units) - Sold", "Category": "Office Equipment",
     "Transaction Type": "Disposal", "Cost": 8500.00, "Acquisition Date": "2019-03-01", "In Service Date": "2019-03-05",
     "Disposal Date": "2024-03-15", "Proceeds": 500.00, "Location": "Office",
     "Tax Prior Depreciation": 8160.00},
    {"Asset ID": "2020-003", "Description": "2020 Chevrolet Silverado - Sold to Employee", "Category": "Vehicle",
     "Transaction Type": "Sold", "Cost": 42000.00, "Acquisition Date": "2020-01-15", "In Service Date": "2020-01-20",
     "Disposal Date": "2024-06-01", "Proceeds": 18500.00, "Location": "Sales",
     "Tax Prior Depreciation": 33600.00, "Business Use %": 100},
    {"Asset ID": "2018-001", "Description": "Dell Desktop Computers (15 units) - End of Life", "Category": "Computer Equipment",
     "Transaction Type": "Disposal", "Cost": 12000.00, "Acquisition Date": "2018-06-01", "In Service Date": "2018-06-05",
     "Disposal Date": "2024-01-31", "Proceeds": 0.00, "Location": "Office",
     "Tax Prior Depreciation": 12000.00},

    # Retired / Scrapped assets
    {"Asset ID": "2017-001", "Description": "Office Furniture - Old Break Room", "Category": "Furniture",
     "Transaction Type": "Retired", "Cost": 8500.00, "Acquisition Date": "2017-02-01", "In Service Date": "2017-02-10",
     "Disposal Date": "2024-05-01", "Proceeds": 0.00, "Location": "Break Room",
     "Tax Prior Depreciation": 8500.00},
    {"Asset ID": "2016-001", "Description": "Bridgeport Milling Machine - Scrapped", "Category": "Machinery",
     "Transaction Type": "Scrap", "Cost": 22000.00, "Acquisition Date": "2016-04-01", "In Service Date": "2016-04-15",
     "Disposal Date": "2024-07-15", "Proceeds": 1200.00, "Location": "Machine Shop",
     "Tax Prior Depreciation": 22000.00},

    # Trade-in
    {"Asset ID": "2021-003", "Description": "2021 Toyota Camry - Trade-in on new vehicle", "Category": "Vehicle",
     "Transaction Type": "Trade-In", "Cost": 32000.00, "Acquisition Date": "2021-04-01", "In Service Date": "2021-04-05",
     "Disposal Date": "2024-06-01", "Proceeds": 22000.00, "Location": "Admin",
     "Tax Prior Depreciation": 19200.00, "Business Use %": 75},
]

# =============================================================================
# SHEET 4: TRANSFERS (2024)
# Asset reclassifications or department transfers
# =============================================================================

transfers_2024 = [
    # Location transfer (same classification)
    {"Asset ID": "2023-004", "Description": "Canon Copier - Moved to Warehouse Office", "Category": "Office Equipment",
     "Transaction Type": "Transfer", "Cost": 9500.00, "Acquisition Date": "2023-08-01", "In Service Date": "2023-08-05",
     "Location": "Warehouse Office", "From Location": "Main Office",
     "Tax Prior Depreciation": 1900.00},

    # Department transfer
    {"Asset ID": "2022-003", "Description": "HP Workstation - Engineering to QA", "Category": "Computer Equipment",
     "Transaction Type": "Transfer", "Cost": 4500.00, "Acquisition Date": "2022-09-01", "In Service Date": "2022-09-05",
     "Location": "QA Lab", "From Location": "Engineering",
     "Tax Prior Depreciation": 1800.00},

    # Reclassification transfer (category change)
    {"Asset ID": "2021-004", "Description": "Tooling - Reclassified from Supplies to Fixed Asset", "Category": "Machinery & Equipment",
     "Transaction Type": "Reclassify", "Cost": 12000.00, "Acquisition Date": "2021-10-01", "In Service Date": "2021-10-05",
     "Location": "Machine Shop", "From Category": "Supplies",
     "Tax Prior Depreciation": 0.00},

    # Split transfer (partial)
    {"Asset ID": "2020-004", "Description": "Server Rack Equipment - Split to new location", "Category": "Computer Equipment",
     "Transaction Type": "Transfer", "Cost": 8000.00, "Acquisition Date": "2020-05-01", "In Service Date": "2020-05-10",
     "Location": "Warehouse Server Room", "From Location": "Main Server Room",
     "Tax Prior Depreciation": 6400.00},
]

# =============================================================================
# CREATE EXCEL FILE
# =============================================================================

def create_test_file():
    """Create the comprehensive test Excel file"""

    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create DataFrames
    df_additions = pd.DataFrame(additions_2024)
    df_existing = pd.DataFrame(existing_assets)
    df_disposals = pd.DataFrame(disposals_2024)
    df_transfers = pd.DataFrame(transfers_2024)

    # Write to Excel with multiple sheets
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        df_additions.to_excel(writer, sheet_name='2024 Additions', index=False)
        df_existing.to_excel(writer, sheet_name='Existing Assets', index=False)
        df_disposals.to_excel(writer, sheet_name='2024 Disposals', index=False)
        df_transfers.to_excel(writer, sheet_name='2024 Transfers', index=False)

    print(f"Created test file: {OUTPUT_FILE}")
    print(f"\nSummary:")
    print(f"  - 2024 Additions: {len(df_additions)} assets (${df_additions['Cost'].sum():,.2f})")
    print(f"  - Existing Assets: {len(df_existing)} assets (${df_existing['Cost'].sum():,.2f})")
    print(f"  - 2024 Disposals: {len(df_disposals)} assets (${df_disposals['Cost'].sum():,.2f})")
    print(f"  - 2024 Transfers: {len(df_transfers)} assets (${df_transfers['Cost'].sum():,.2f})")
    print(f"\nTotal assets: {len(df_additions) + len(df_existing) + len(df_disposals) + len(df_transfers)}")

    return OUTPUT_FILE

if __name__ == "__main__":
    create_test_file()
