# Fixed Asset CS Export Format Changes

## Summary

Updated the Excel export format in `fa_export.py` to match Fixed Asset CS import requirements exactly, based on FA CS import field mapping screenshots.

**Date**: 2025-01-20
**Files Modified**: `fixed_asset_ai/logic/fa_export.py`

---

## Column Mapping Changes

### ✅ Core Asset Fields

| Before (Old Format) | After (FA CS Format) | Change Type |
|---------------------|----------------------|-------------|
| `Asset ID` | `Asset #` | **Renamed** |
| `Property Description` | `Description` | **Renamed** |
| `Date In Service` | `Date In Service` | ✓ Same |
| `Acquisition Date` | `Acquisition Date` | ✓ Same |

### ✅ Tax Depreciation Fields

| Before (Old Format) | After (FA CS Format) | Change Type |
|---------------------|----------------------|-------------|
| `Cost/Basis` | `Tax Cost` | **Renamed** with "Tax" prefix |
| `Method` (values: "200DB", "150DB", "SL") | `Tax Method` (values: "MACRS GDS", "MACRS ADS") | **Renamed** + **Format Changed** |
| `Life` (values: "5-Year MACRS", "7-Year", etc.) | `Tax Life` (values: 5, 7, 15, 27.5, 39) | **Renamed** + **Format Changed** |
| `Convention` (HY, MQ, MM) | `Convention` | ✓ Same |
| `Section 179 Amount` | `Tax Sec 179 Expensed` | **Renamed** with "Tax" prefix |
| *(Not in export)* | `Tax Prior Depreciation` | **NEW** - For existing assets |
| *(Not in export)* | `Tax Cur Depreciation` | **NEW** - Current year depreciation |

### ✅ Transaction Type & Sheet Role

| Before (Old Format) | After (FA CS Format) | Change Type |
|---------------------|----------------------|-------------|
| `Transaction Type` (internal) | `Transaction Type` | ✓ Same (kept for tracking) |
| `Sheet Role` (values: "addition", "disposal", "transfer", "existing") | `Sheet Role` (value: "main" for all) | **Format Changed** |

### ✅ Supplemental Fields (Unchanged)

These columns remain the same and are optional for FA CS import:

- `Bonus Amount`
- `Bonus % Applied`
- `Depreciable Basis`
- `Section 179 Allowed`
- `Section 179 Carryforward`
- `De Minimis Expensed`
- `Quarter (MQ)`
- `Auto Limit Notes`
- `§1245 Recapture (Ordinary Income)`
- `§1250 Recapture (Ordinary Income)`
- `Unrecaptured §1250 Gain (25%)`
- `Capital Gain`
- `Capital Loss`
- `Adjusted Basis at Disposal`
- `Uses ADS`
- `Source`
- `Client Category Original`
- `Final Category`

---

## Critical Format Changes Explained

### 1. Method Format Change

**Before:**
```
Method: "200DB"  (200% declining balance)
Method: "150DB"  (150% declining balance)
Method: "SL"     (Straight line)
```

**After (UPDATED 2025-01-20 based on user testing):**
```
Tax Method: "MACRS"  (for all depreciation methods)
```

**Why**: Based on actual FA CS import testing, FA CS only accepts "MACRS" as the method value during import. Earlier documentation suggested "MACRS GDS" or "MACRS ADS", but user testing confirmed FA CS only accepts "MACRS".

**Implementation**: Helper function `_convert_method_to_fa_cs_format(uses_ads)` now returns "MACRS" for all assets (both GDS and ADS).

---

### 2. Life Format Change

**Before:**
```
Life: "5-Year MACRS"
Life: "7-Year MACRS"
Life: "39-Year Real Property"
```

**After:**
```
Tax Life: 5
Tax Life: 7
Tax Life: 39
```

**Why**: FA CS expects plain numbers for the Tax Life field, not descriptive text.

**Implementation**: Uses `Recovery Period` or `MACRS Life` column directly (which already contains numbers).

---

### 3. Sheet Role Format Change

**Before:**
```
Sheet Role: "addition"    (for current year additions)
Sheet Role: "disposal"    (for disposals)
Sheet Role: "transfer"    (for transfers)
Sheet Role: "existing"    (for existing assets)
```

**After:**
```
Sheet Role: "main"  (for ALL transaction types)
```

**Why**: FA CS uses "main" as a constant value for all assets, regardless of transaction type. The transaction type is determined by other fields (presence of disposal data, prior depreciation, etc.) not by the Sheet Role field.

**Implementation**: `fa["Sheet Role"] = "main"` - constant value for all rows.

---

### 4. NEW: Prior & Current Depreciation Fields

**New Fields Added:**

```python
fa["Tax Prior Depreciation"] = accumulated depreciation (for existing assets)
                                or 0 (for current year additions)

fa["Tax Cur Depreciation"] = current year MACRS depreciation (for all assets)
```

**Why**: FA CS needs to track:
- **Prior Depreciation**: Total depreciation taken in all prior years (for assets placed in service before current tax year)
- **Current Depreciation**: Depreciation for the current tax year only

**Implementation**:
- For **Existing Assets**: `Tax Prior Depreciation` = `Accumulated Depreciation` column (from disposal/existing asset data)
- For **Current Year Additions**: `Tax Prior Depreciation` = 0 (no prior depreciation)
- For **All Assets**: `Tax Cur Depreciation` = `MACRS Year 1 Depreciation` (calculated depreciation for current year)

---

## Example: Before vs After

### Current Year Addition (2024)

**Before (Old Format):**
```
Asset ID: A-200
Property Description: CNC Router Shopbot
Date In Service: 2/14/2024
Cost/Basis: 45700
Method: 200DB
Life: 5-Year MACRS
Convention: HY
Section 179 Amount: 45700
Sheet Role: addition
```

**After (FA CS Format - UPDATED 2025-01-20):**
```
Asset #: A-200
Description: CNC Router Shopbot
Date In Service: 2/14/2024
Acquisition Date: 2/14/2024
Tax Cost: 45700
Tax Method: MACRS
Tax Life: 5
Convention: HY
Tax Sec 179 Expensed: 45700
Tax Prior Depreciation: 0
Tax Cur Depreciation: 0
Sheet Role: main
```

### Existing Asset (2019)

**Before (Old Format):**
```
Asset ID: T-301
Property Description: Forklift Toyota 8FGCU25
Date In Service: 1/1/2019
Cost/Basis: 28900
Method: 200DB
Life: 7-Year MACRS
Convention: HY
Section 179 Amount: 0
Sheet Role: existing
```

**After (FA CS Format - UPDATED 2025-01-20):**
```
Asset #: T-301
Description: Forklift Toyota 8FGCU25
Date In Service: 1/1/2019
Acquisition Date: 1/1/2019
Tax Cost: 28900
Tax Method: MACRS
Tax Life: 7
Convention: HY
Tax Sec 179 Expensed: 0
Tax Prior Depreciation: 18500  (example - accumulated through 2023)
Tax Cur Depreciation: 2100  (example - 2024 depreciation)
Sheet Role: main
```

---

## Code Changes Summary

### New Helper Function

Added `_convert_method_to_fa_cs_format(uses_ads: bool) -> str` at line 231:

```python
def _convert_method_to_fa_cs_format(uses_ads: bool) -> str:
    """
    Convert internal method format to Fixed Asset CS import format.

    FA CS expects:
    - "MACRS GDS" for regular MACRS (200DB, 150DB, SL on GDS)
    - "MACRS ADS" for Alternative Depreciation System
    """
    return "MACRS ADS" if uses_ads else "MACRS GDS"
```

### Updated Export Section (Lines 900-1021)

- Renamed columns to match FA CS field names
- Added "Tax" prefix to federal tax fields
- Converted method format using helper function
- Changed life to use plain numbers
- Added Tax Prior Depreciation and Tax Cur Depreciation
- Changed Sheet Role to constant "main" value

---

## Testing Recommendations

### 1. Test with Sample Data

Create a test file with:
- **Current year additions** (2024 in-service dates)
- **Existing assets** (prior year in-service dates)
- **Disposals** (with disposal data)

Expected behavior:
- Current additions: `Tax Prior Depreciation` = 0, `Tax Sec 179 Expensed` > 0 (if elected)
- Existing assets: `Tax Prior Depreciation` > 0, `Tax Sec 179 Expensed` = 0
- All assets: `Tax Method` = "MACRS GDS" or "MACRS ADS", `Tax Life` = numbers only, `Sheet Role` = "main"

### 2. Verify FA CS Import

1. Export Excel file using updated format
2. Open Fixed Asset CS
3. Use File → Import → Select Excel file
4. **Verify field mapping**:
   - `Asset #` maps to FA CS "Asset #"
   - `Description` maps to FA CS "Description"
   - `Tax Cost` maps to FA CS "Tax Cost"
   - `Tax Method` maps to FA CS "Tax Method"
   - `Tax Life` maps to FA CS "Tax Life"
   - `Tax Sec 179 Expensed` maps to FA CS "Tax Sec 179 Expensed"
   - `Sheet Role` maps to FA CS "Sheet Role"
5. **Check for import errors** - should import cleanly with no errors

### 3. RPA Compatibility Test

1. Complete manual FA CS login (see FA_CS_LOGIN_LIMITATIONS.md)
2. Run RPA automation with updated export format
3. Verify RPA can:
   - Navigate to correct screens
   - Enter data in correct fields
   - Handle all transaction types
   - Complete without errors

---

## Rollback Plan

If FA CS import fails with the new format:

1. **Check field mapping**: Verify FA CS is mapping columns correctly in the import dialog
2. **Check error messages**: FA CS will show specific errors (e.g., "Invalid Method")
3. **Compare with screenshots**: Ensure export matches screenshot examples exactly

If issues persist, the changes can be reverted by:
```bash
git checkout HEAD~1 -- fixed_asset_ai/logic/fa_export.py
```

---

## Next Steps

1. ✅ Test export with sample data
2. ✅ Verify FA CS import accepts the new format
3. ✅ Update RPA field mappings if needed
4. ✅ Run end-to-end test with RPA automation
5. ✅ Document any additional findings

---

## Related Documentation

- `FA_CS_IMPORT_MAPPING.md` - Detailed field mapping reference
- `FA_CS_LOGIN_LIMITATIONS.md` - RPA login limitations and manual process
- `README_RPA.md` - Full RPA documentation

---

**Created**: 2025-01-20
**Author**: Claude Code
**Based on**: FA CS import field mapping screenshots
