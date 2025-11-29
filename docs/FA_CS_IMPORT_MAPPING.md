# Fixed Asset CS Import Field Mapping

## Overview

This document maps the Excel export columns from our Fixed Asset AI tool to the expected Fixed Asset CS import fields.

**Based on**: FA CS import field mapping screenshots (2025-01-20)

---

## Critical Field Mappings

### Core Asset Information

| FA CS Import Field | Our Export Column | Format | Notes |
|-------------------|-------------------|--------|-------|
| **Asset #** | Asset ID | Text | Unique identifier |
| **Description** | Property Description | Text | Asset description |
| **Date In Service** | Date In Service | Date (M/D/YYYY) | Placed in service date |
| **Acquisition Date** | Acquisition Date | Date (M/D/YYYY) | Optional, can match PIS date |

### Tax (Federal) Depreciation Fields

| FA CS Import Field | Our Export Column | Format | Notes |
|-------------------|-------------------|--------|-------|
| **Tax Cost** | Tax Cost | Number | Original cost |
| **Tax Method** | Tax Method | Text | **MUST be "MACRS" (user tested 2025-01-20)** |
| **Tax Life** | Tax Life | Number | **MUST be just number (5, 7, 15, 27.5, 39)** |
| **Tax Sec 179 Expensed** | Tax Sec 179 Expensed | Number | Section 179 expensed |
| **Tax Prior Depreciation** | Tax Prior Depreciation | Number | For existing assets only |
| **Tax Cur Depreciation** | Tax Cur Depreciation | Number | Current year depreciation |
| **Convention** | Convention | Text | HY, MQ, MM |
| **Sheet Role** | Sheet Role | Text | **MUST be "main" not "addition"** |

### AMT (Alternative Minimum Tax) Fields

| FA CS Import Field | Our Export Column | Format | Notes |
|-------------------|-------------------|--------|-------|
| **AMT Cost** | *(Optional)* | Number | Usually same as Tax Cost |
| **AMT Method** | *(Optional)* | Text | Usually MACRS ADS |
| **AMT Life** | *(Optional)* | Number | Usually longer than Tax Life |
| **AMT Sec 179 Expensed** | *(Optional)* | Number | No Sec 179 for AMT |
| **AMT Prior Depreciation** | *(Optional)* | Number | For existing assets |
| **AMT Cur Depreciation** | *(Optional)* | Number | Current year AMT depreciation |

### State Depreciation Fields

| FA CS Import Field | Our Export Column | Format | Notes |
|-------------------|-------------------|--------|-------|
| **State Cost** | *(Optional)* | Number | State cost if different |
| **State Method** | *(Optional)* | Text | State method if different |
| **State Life** | *(Optional)* | Number | State life if different |
| **State Sec 179 Expensed** | *(Optional)* | Number | State Sec 179 if different |
| **State Prior Depreciation** | *(Optional)* | Number | For existing assets |
| **State Cur Depreciation** | *(Optional)* | Number | Current year state depreciation |

### Tracking/Classification Fields

| FA CS Import Field | Our Export Column | Format | Notes |
|-------------------|-------------------|--------|-------|
| **Source** | Source | Text | "upload", "rule", "gpt", etc. |
| **Client Category Original** | Client Category Original | Text | Original client-provided category |
| **Final Category** | Final Category | Text | Our computed MACRS category |

---

## Critical Format Requirements

### ❌ WRONG Formats

```
Method: "200DB", "150DB", "SL", "MACRS GDS", "MACRS ADS"
Life: "5-Year MACRS", "7-Year MACRS", "39-Year Real Property"
Sheet Role: "addition", "disposal", "transfer", "existing"
Date: "2024-01-01 00:00:00" (with timestamp)
```

### ✅ CORRECT Formats (FA CS Expects - User Tested 2025-01-20)

```
Tax Method: "MACRS" (only this value accepted)
Tax Life: 5, 7, 15, 27.5, 39 (just numbers)
Sheet Role: "main" (for all transaction types)
Date In Service: "1/1/2024" (M/D/YYYY format, no timestamp)
```

---

## Example FA CS Import Data

From screenshot, Asset A-200:

```
Asset #: A-200
Description: CNC Router Shopbot
Date In Service: 2/14/2024
Acquisition Date: 2/14/2024
Tax Cost: 45700
Tax Method: MACRS
Tax Life: 5
Convention: HY
Sheet Role: main
Tax Sec 179 Expensed: 45700
```

---

## Transaction Type Handling

### Current Year Additions

```
Asset #: A-200
Sheet Role: main
Tax Cost: 45700
Tax Method: MACRS
Tax Life: 5
Tax Sec 179 Expensed: 45700  (if elected)
Bonus Amount: 0 (or bonus amount if applicable)
```

### Existing Assets (Prior Year Additions)

```
Asset #: T-301
Sheet Role: main
Date In Service: 1/1/2019
Tax Cost: 28900
Tax Method: MACRS
Tax Life: 7
Tax Prior Depreciation: (accumulated depreciation from prior years)
Tax Cur Depreciation: (current year MACRS depreciation)
Tax Sec 179 Expensed: 0  (Section 179 NOT allowed for existing assets)
Bonus Amount: 0 (Bonus NOT allowed for existing assets)
```

### Disposals

```
Asset #: D-401
Sheet Role: main  (still use "main")
Date In Service: 1/1/2018
Disposal Date: (add disposal date column if available)
Proceeds: (disposal proceeds)
Tax Prior Depreciation: (total accumulated depreciation)
§1245 Recapture: (calculated recapture)
Capital Gain/Loss: (calculated gain/loss)
```

---

## Required Changes to fa_export.py

### 1. Rename Columns to Match FA CS

```python
# WRONG (current):
fa["Cost/Basis"] = df["Cost"]
fa["Method"] = df["Method"]
fa["Life"] = df["MACRS Life"]

# CORRECT (should be):
fa["Tax Cost"] = df["Cost"]
fa["Tax Method"] = df["Method"].apply(convert_to_macrs_gds_format)
fa["Tax Life"] = df["Recovery Period"]  # Just numbers
fa["Tax Sec 179 Expensed"] = df["Section 179 Amount"]
```

### 2. Fix Method Format

```python
def _convert_method_to_fa_cs_format(uses_ads: bool) -> str:
    """Convert internal method format to FA CS format.

    Based on user testing (2025-01-20), FA CS only accepts "MACRS"
    during import, not "MACRS GDS" or "MACRS ADS".
    """
    return "MACRS"  # FA CS only accepts this value
```

### 3. Fix Life Format

```python
# WRONG:
fa["Life"] = "5-Year MACRS"

# CORRECT:
fa["Tax Life"] = 5  # Just the number
```

### 4. Fix Sheet Role

```python
# WRONG:
fa["Sheet Role"] = "addition"  # or "disposal", "transfer", "existing"

# CORRECT:
fa["Sheet Role"] = "main"  # Always use "main"
```

### 5. Add Prior/Current Depreciation for Existing Assets

```python
# For existing assets (in service < current tax year):
fa["Tax Prior Depreciation"] = df["Accumulated Depreciation"]
fa["Tax Cur Depreciation"] = df["MACRS Year 1 Depreciation"]  # Current year only

# For current year additions:
fa["Tax Prior Depreciation"] = 0
fa["Tax Cur Depreciation"] = df["MACRS Year 1 Depreciation"]
```

---

## Optional Fields (Can Leave Blank)

### AMT Fields
- Leave blank unless client has AMT requirement
- Typically only needed for large C-corps or specific tax situations

### State Fields
- Leave blank if state follows federal depreciation
- Only populate if state has different rules (e.g., California)

---

## Column Order Recommendation

Based on FA CS screenshots, the import expects columns in this order:

1. **Asset #**
2. **Description**
3. **Date In Service**
4. **Acquisition Date**
5. **Tax Cost**
6. **Tax Method**
7. **Tax Life**
8. **Convention**
9. **Tax Sec 179 Expensed**
10. **Tax Prior Depreciation**
11. **Tax Cur Depreciation**
12. **Bonus Amount** *(if applicable)*
13. **Sheet Role**
14. AMT fields (if used)
15. State fields (if used)
16. **Source**
17. **Client Category Original**
18. **Final Category**
19. Recapture fields (for disposals)

---

## Testing Checklist

Before running RPA automation:

- [ ] Column names match FA CS exactly ("Tax Cost" not "Cost/Basis")
- [ ] Method format is "MACRS GDS" or "MACRS ADS" (not "200DB")
- [ ] Life is just numbers (5, 7, 39) not "5-Year MACRS"
- [ ] Sheet Role is "main" for all rows
- [ ] Date format is M/D/YYYY
- [ ] Section 179 amounts are correct for current year additions only
- [ ] Existing assets have $0 for Section 179 and Bonus
- [ ] Prior depreciation populated for existing assets
- [ ] Disposal assets have recapture columns populated

---

## Common Import Errors

### Error: "Invalid Method"
**Cause**: Method format is "200DB", "MACRS GDS", or "MACRS ADS" instead of "MACRS"
**Fix**: Convert all methods to just "MACRS" (user tested 2025-01-20)

### Error: "Invalid Life"
**Cause**: Life is "5-Year MACRS" instead of just "5"
**Fix**: Extract just the number from MACRS Life

### Error: "Sheet Role not recognized"
**Cause**: Sheet Role is "addition" instead of "main"
**Fix**: Use "main" for all rows

### Error: "Section 179 not allowed"
**Cause**: Section 179 claimed on existing asset (prior year)
**Fix**: Only allow Section 179 for current year additions

---

## Summary

**Critical changes needed:**

1. ✅ Rename "Cost/Basis" → "Tax Cost"
2. ✅ Rename "Method" → "Tax Method" and convert to "MACRS GDS" format
3. ✅ Rename "Life" → "Tax Life" and use just numbers
4. ✅ Rename "Section 179 Amount" → "Tax Sec 179 Expensed"
5. ✅ Change Sheet Role to always use "main"
6. ✅ Add "Tax Prior Depreciation" for existing assets
7. ✅ Add "Tax Cur Depreciation" for all assets

**Next steps:**
1. Update fa_export.py with correct column names and formats
2. Test import with FA CS using small sample file
3. Verify RPA automation can handle the new format
4. Update RPA field mappings if needed

---

**Last Updated**: 2025-01-20
**Based on**: FA CS import screenshots showing field mapping interface
