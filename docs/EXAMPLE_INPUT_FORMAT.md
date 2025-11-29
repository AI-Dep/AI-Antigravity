# Example Input Format

## Excel File Format

Your Excel file should contain asset information with the following columns (column names are flexible - the system will auto-detect):

### Required Columns

| Column | Alternate Names | Example |
|--------|----------------|---------|
| Asset ID | asset, asset_id, id, asset number | A-001 |
| Description | desc, asset description, property | Dell Laptop Computer |
| Cost | amount | 1500.00 |

### Optional but Recommended

| Column | Alternate Names | Example |
|--------|----------------|---------|
| Category | class, asset class, type | Computer Equipment |
| In Service Date | in-service date, service date, placed in service | 01/15/2024 |
| Acquisition Date | acq date, purchase date | 01/10/2024 |
| Location | site, room | Office 201 |

## Example Excel Layout

```
| Asset ID | Description           | Category            | Cost     | In Service Date | Location  |
|----------|-----------------------|---------------------|----------|-----------------|-----------|
| A-001    | Dell Laptop Computer  | Computer Equipment  | 1500.00  | 01/15/2024     | Office    |
| A-002    | Oak Desk             | Office Furniture    | 800.00   | 01/20/2024     | Reception |
| A-003    | Conference Table     | Office Furniture    | 2500.00  | 02/01/2024     | Conf Room |
| A-004    | Server Rack          | Computer Equipment  | 5000.00  | 02/15/2024     | Server Rm |
| A-005    | HVAC System          | Building Equipment  | 15000.00 | 03/01/2024     | Building  |
```

## Multi-Sheet Support

The system supports multiple sheets:

- **Main Assets Sheet**: Current year additions
- **Disposals Sheet**: Assets sold/retired
- **Transfers Sheet**: Asset reclassifications

Each sheet is automatically detected and processed.

## Notes

- Headers are auto-detected (they don't have to be in row 1)
- Column order doesn't matter
- The system handles common variations in column names
- Dates can be in various formats (MM/DD/YYYY, DD/MM/YYYY, etc.)
- Cost can include currency symbols and commas

## Sample File

To create a test file:

1. Open Excel
2. Create columns: Asset ID, Description, Cost, In Service Date
3. Add 5-10 sample assets
4. Save as `.xlsx`
5. Upload to the application

## Common Categories

The AI recognizes common asset categories:

- Computer Equipment (5-year)
- Office Furniture (7-year)
- Vehicles (5-year)
- Machinery & Equipment (varies)
- Building Improvements (15 or 39-year)
- Land Improvements (15-year)
- Software (3-year)

But you can also use custom descriptions - the AI will classify them correctly.
