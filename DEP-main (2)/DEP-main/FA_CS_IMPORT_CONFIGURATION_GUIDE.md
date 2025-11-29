# FA CS Import Configuration Guide

## Overview

This guide explains how to configure the **Tier 1: Import-Based RPA** automation for Fixed Asset CS. This method is **significantly faster** than field-by-field UI automation.

### Performance Comparison

| Assets | Import Method (Tier 1) | UI Automation (Tier 2) | Time Saved |
|--------|------------------------|------------------------|------------|
| 100    | ~10-20 seconds        | ~10 minutes           | 98% faster |
| 500    | ~15-30 seconds        | ~50 minutes           | 99% faster |
| 1000   | ~20-40 seconds        | ~100 minutes          | 99% faster |

---

## How Import-Based RPA Works

The system uses a **3-tier strategy**:

### **Tier 1: Import Feature (Primary)**
1. Generate Excel export with FA CS data
2. Use RPA to automate FA CS import feature:
   - Navigate: `Tools → Import → Fixed Assets`
   - Load Excel file
   - Apply field mapping (per client)
   - Execute import
   - Validate results

### **Tier 2: UI Automation (Automatic Fallback)**
- If import fails, automatically falls back to field-by-field entry
- Uses existing UI automation (proven, reliable)
- No data loss or manual intervention required

### **Tier 3: Manual (Last Resort)**
- For complex scenarios RPA cannot handle
- Disposal entries that require special handling
- One-off corrections

---

## Client Mapping Configuration

### Location
```
fixed_asset_ai/logic/fa_cs_import_mappings.json
```

### Structure

```json
{
  "client_id": {
    "mapping_name": "Display name for this mapping",
    "description": "What makes this mapping unique",
    "field_mappings": {
      "Source Column (Our Export)": "Target Field (FA CS Import)",
      "Asset #": "Asset Number",
      "Description": "Asset Description",
      ...
    },
    "import_settings": {
      "skip_header_rows": 0,
      "update_existing_assets": false,
      "validate_before_import": true,
      "create_backup": true
    }
  }
}
```

### Default Mapping

The system includes a `"default"` mapping that works for standard FA CS configurations:

```json
"default": {
  "field_mappings": {
    "Asset #": "Asset Number",
    "Description": "Asset Description",
    "Date In Service": "Date Placed in Service",
    "Acquisition Date": "Acquisition Date",
    "Tax Cost": "Cost/Basis",
    "Tax Method": "Depreciation Method",
    "Tax Life": "Recovery Period",
    "Convention": "Convention",
    "Tax Sec 179 Expensed": "Section 179 Deduction",
    "Bonus Amount": "Bonus Depreciation",
    "Tax Prior Depreciation": "Prior Depreciation",
    "Tax Cur Depreciation": "Current Year Depreciation"
  }
}
```

---

## Setting Up a New Client

### Step 1: Identify Client Requirements

1. **Manual Test Import**
   - Export a sample file (2-3 assets)
   - Manually import into FA CS: `Tools → Import → Fixed Assets`
   - Note the field names FA CS expects

2. **Document Field Mappings**
   ```
   Our Export          →  FA CS Import Field
   ─────────────────────────────────────────
   Asset #             →  Asset ID
   Description         →  Property Description
   Date In Service     →  Service Date
   Tax Cost            →  Basis
   ...
   ```

### Step 2: Create Client Mapping

Add to `fa_cs_import_mappings.json`:

```json
{
  "default": { ... },

  "client_abc_corp": {
    "mapping_name": "ABC Corp Custom Mapping",
    "description": "ABC Corp uses custom field names in FA CS",
    "field_mappings": {
      "Asset #": "Asset ID",
      "Description": "Property Description",
      "Date In Service": "Service Date",
      "Acquisition Date": "Purchase Date",
      "Tax Cost": "Basis",
      "Tax Method": "Method",
      "Tax Life": "Life (Years)",
      "Convention": "Convention",
      "Tax Sec 179 Expensed": "Sec 179",
      "Bonus Amount": "Bonus Depr"
    },
    "import_settings": {
      "skip_header_rows": 0,
      "update_existing_assets": false,
      "validate_before_import": true,
      "create_backup": true
    }
  }
}
```

### Step 3: Save Import Template in FA CS (Optional but Recommended)

1. Complete one manual import with correct field mapping
2. In FA CS import dialog, click **"Save Template"** or **"Save Mapping"**
3. Name it exactly as specified in `mapping_name` (e.g., "ABC Corp Custom Mapping")
4. Next time, RPA will automatically load this saved template (faster!)

### Step 4: Test with Preview Mode

```python
from fixed_asset_ai.logic.ai_rpa_orchestrator import AIRPAOrchestrator

orchestrator = AIRPAOrchestrator(use_import_automation=True)

results = orchestrator.run_full_workflow(
    classified_df=df,
    tax_year=2024,
    strategy="Balanced",
    taxable_income=500000,
    preview_mode=True,  # Test with first 3 assets
    auto_run_rpa=True,
    client_id="client_abc_corp"  # Use your client ID
)

print(f"Method used: {results['steps']['rpa_automation']['method']}")
print(f"Status: {results['steps']['rpa_automation']['status']}")
```

### Step 5: Run Full Import

Once preview succeeds, run full import:

```python
results = orchestrator.run_full_workflow(
    classified_df=df,
    tax_year=2024,
    strategy="Balanced",
    taxable_income=500000,
    preview_mode=False,  # Process all assets
    auto_run_rpa=True,
    client_id="client_abc_corp"
)
```

---

## Available Configuration Options

### Field Mappings

Map any of these source columns to your FA CS fields:

**Source Columns (Our Export):**
- `Asset #`
- `Description`
- `Date In Service`
- `Acquisition Date`
- `Tax Cost`
- `Tax Method`
- `Tax Life`
- `Convention`
- `Tax Sec 179 Expensed`
- `Bonus Amount`
- `Tax Prior Depreciation`
- `Tax Cur Depreciation`
- `Transaction Type`
- `Quarter (MQ)`
- `Disposal Date` (for disposals)
- `Disposal Proceeds` (for disposals)

### Import Settings

```json
"import_settings": {
  "skip_header_rows": 0,           // How many rows to skip at top
  "update_existing_assets": false, // Update or create new assets
  "validate_before_import": true,  // Validate data before import
  "create_backup": true            // Backup before import
}
```

---

## Using the Import Automation

### From Python Code

```python
from fixed_asset_ai.logic.rpa_fa_cs_import import HybridFACSAutomation

hybrid = HybridFACSAutomation()

results = hybrid.process_assets(
    excel_file_path="/path/to/export.xlsx",
    df=asset_dataframe,  # For UI fallback
    client_id="client_abc_corp",
    force_ui_automation=False  # Set True to skip import, use UI only
)

print(f"Method: {results['method_used']}")  # 'import' or 'ui_automation'
print(f"Succeeded: {results['succeeded']}/{results['total_assets']}")
```

### From Streamlit App

The app will automatically use import automation when enabled:

```python
# In app.py
orchestrator = AIRPAOrchestrator(use_import_automation=True)

# Select client
client_id = st.selectbox("Client", ["default", "client_abc_corp", ...])

# Run automation
if st.button("Run RPA"):
    results = orchestrator.run_full_workflow(
        ...,
        client_id=client_id,
        force_ui_automation=False  # Checkbox to force UI automation
    )
```

---

## Troubleshooting

### Import Method Not Working

**Symptom:** System always falls back to UI automation

**Solutions:**
1. Verify FA CS import feature is available (check FA CS version/license)
2. Verify menu path is correct: `Tools → Import → Fixed Assets`
3. Check FA CS import dialog appears when running manually
4. Ensure Excel file is not open in Excel (file lock)
5. Check logs for specific error messages

### Field Mapping Issues

**Symptom:** Import succeeds but data is in wrong fields

**Solutions:**
1. Verify field names in mapping match FA CS exactly (case-sensitive)
2. Complete manual import to confirm field names
3. Check if FA CS has custom field labels
4. Update `field_mappings` in configuration

### Import Succeeds but No Data

**Symptom:** Import completes but assets don't appear in FA CS

**Solutions:**
1. Check FA CS filters (may hide imported assets)
2. Verify tax year filter in FA CS
3. Check transaction type (additions vs disposals)
4. Review FA CS import log for warnings

### Performance Issues

**Symptom:** Import takes longer than expected

**Solutions:**
1. Check FA CS performance (may be slow due to network, VM, etc.)
2. Increase `import_timeout` in code (default: 60 seconds)
3. Break large imports into batches (500 assets per batch)
4. Ensure FA CS is on local drive (not network share)

---

## Advanced Configuration

### Multiple Mappings per Client

You can create multiple mappings for different scenarios:

```json
{
  "client_abc_additions": {
    "mapping_name": "ABC Corp - Additions",
    "field_mappings": { ... }
  },
  "client_abc_disposals": {
    "mapping_name": "ABC Corp - Disposals",
    "field_mappings": { ... }
  }
}
```

### Custom Menu Paths

If your FA CS has different menu structure:

```python
# In rpa_fa_cs_import.py
class FACSImportAutomation:
    def __init__(self, ...):
        # Customize menu path
        self.import_menu_path = ["File", "Import", "Assets"]  # Your path
```

### Batch Processing

For very large imports:

```python
def batch_import(df, batch_size=500):
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        hybrid.process_assets(excel_file_path, df=batch, ...)
        print(f"Batch {i//batch_size + 1} complete")
```

---

## Best Practices

1. **Start with Preview Mode**
   - Always test with 3 assets first
   - Verify data appears correctly in FA CS
   - Check field alignment

2. **Save FA CS Import Templates**
   - Saves 5-10 seconds per import
   - More reliable than manual mapping
   - One-time setup per client

3. **Use Client IDs Consistently**
   - Use descriptive names: `client_abc_corp` not `client1`
   - Document client ID in client files
   - Include in file naming: `ABC_Corp_2024.xlsx`

4. **Monitor First Few Imports**
   - Review FA CS data after first import
   - Spot-check 5-10 random assets
   - Verify calculations (179, Bonus, Depreciation)

5. **Keep Fallback Ready**
   - Don't disable UI automation entirely
   - Useful for edge cases and troubleshooting
   - Provides redundancy

---

## FAQ

**Q: Do I need to configure mapping for every client?**
A: No. The `default` mapping works for most clients. Only create custom mappings if client has non-standard FA CS field names.

**Q: Can I use import for disposals?**
A: Yes, but ensure your mapping includes disposal-specific fields (`Disposal Date`, `Disposal Proceeds`). Some FA CS versions require separate disposal import workflow.

**Q: What if import fails mid-way?**
A: The hybrid system automatically falls back to UI automation. No data loss. You can also resume from last successful asset.

**Q: Does this work with FA CS cloud/hosted versions?**
A: Yes, as long as FA CS import feature is available. RPA works with any FA CS deployment (desktop, RemoteApp, cloud).

**Q: How do I know which method was used?**
A: Check the results:
```python
print(results['steps']['rpa_automation']['method'])
# Output: 'import' or 'ui_automation'
```

---

## Getting Help

If you encounter issues:

1. Check execution logs: `workflow_log_*.json`
2. Review screenshots: `rpa_screenshot_*.png`
3. Test manual import first
4. Try with `force_ui_automation=True` to verify UI automation works
5. Check FA CS version and import feature availability

---

**Last Updated:** 2024-11-21
**Version:** 1.0
