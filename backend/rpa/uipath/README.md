# FA CS Asset Entry - UiPath Automation

This UiPath workflow automates asset entry into Thomson Reuters Fixed Asset CS by reading data from the Fixed Asset AI Tool export file.

## Overview

The automation:
1. Reads the Excel export file (FA_CS_Import worksheet)
2. For each asset, clicks Add and enters data using the wizard
3. After all assets are added, elects Section 179 for all assets

## Prerequisites

### Software Requirements
- UiPath Studio (Community Edition is free)
- Thomson Reuters Fixed Asset CS installed
- Microsoft Excel

### Before Running

1. **Open FA CS** and log in
2. **Select the client** you want to add assets to
3. **Navigate to the asset list** (e.g., Miscellaneous folder)
4. **Have the export file ready** from the Fixed Asset AI Tool

## Setup Instructions

### Step 1: Import Workflow into UiPath

1. Open UiPath Studio
2. Create a new project or open existing
3. In Project panel, right-click and select "Import Workflow"
4. Select `FA_CS_Asset_Entry.xaml`

### Step 2: Install Required Packages

In UiPath Studio:
1. Go to Manage Packages
2. Install these packages if not already installed:
   - `UiPath.Excel.Activities`
   - `UiPath.UIAutomation.Activities`

### Step 3: Verify Selectors (IMPORTANT)

The workflow uses UI selectors to find FA CS elements. You may need to update these selectors to match your FA CS version:

1. Open the workflow in UiPath Studio
2. Use **UI Explorer** to verify each selector
3. Key selectors to check:
   - Add button
   - Description field
   - Date in Service field
   - Tax Cost field
   - Wizard button
   - OK button
   - Tasks menu
   - Elect Section 179 menu item
   - Max All button

### Step 4: Run the Workflow

1. Make sure FA CS is open with client selected
2. Run the workflow from UiPath Studio
3. When prompted, enter the path to your export Excel file
4. Watch as assets are added automatically

## Export File Requirements

The export file must have these columns (from Fixed Asset AI Tool):

| Column | Description | Required |
|--------|-------------|----------|
| Description | Asset description | Yes |
| Date In Service | In-service date (M/D/YYYY) | Yes |
| Tax Cost | Cost/basis amount | Yes |
| FA_CS_Wizard_Category | FA CS wizard dropdown selection | Yes |

## Troubleshooting

### Selectors Not Working

FA CS is a Visual Basic 6 application with custom controls. If selectors don't work:

1. Use **UiPath UI Explorer** to capture new selectors
2. Try using **Image-based activities** as fallback
3. Use **CV (Computer Vision)** activities for more reliability

### Wizard Dropdown Selection Fails

If the wizard dropdown selection fails:

1. Try using `TypeInto` activity to type the first few characters
2. Then use `SendHotkey` with Down Arrow and Enter
3. Or use `Click` with image recognition

### Section 179 Election Fails

If Tasks menu or 179 election fails:

1. Verify the Tasks menu selector
2. Check if menu item text matches exactly
3. Try using keyboard shortcuts if available

## Customization

### Changing Default Values

Edit the workflow variables:
- `ExcelFilePath` - Default export file path

### Adding Group Field

To add group assignment, add a `TypeInto` activity after Date in Service:
- Selector: Target the Group dropdown
- Text: Group name from export file

### Skip Section 179

To skip 179 election:
- Delete or disable the "Section 179 Election Sequence" section

## Support

For issues with:
- **The export file**: Check Fixed Asset AI Tool documentation
- **UiPath workflow**: UiPath Community Forum
- **FA CS behavior**: Thomson Reuters support

## Version History

- v1.0 - Initial release with asset entry and 179 election
