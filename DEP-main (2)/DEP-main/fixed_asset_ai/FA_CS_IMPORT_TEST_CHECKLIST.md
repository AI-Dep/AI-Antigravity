# FA CS Import Test Checklist

**Target Version:** Fixed Asset CS 24.1.6 (TS Network 236)
**Created:** November 24, 2025
**Purpose:** Systematic validation of Fixed Asset AI export compatibility with FA CS

---

## PRE-IMPORT SETUP

### 1. FA CS Environment Preparation
- [ ] Open FA CS version 24.1.6
- [ ] Create a TEST client (do not use production data)
- [ ] Note the client's tax year setting
- [ ] Verify FA CS is in "Import" mode (File → Import)

### 2. Export File Preparation
- [ ] Run Fixed Asset AI classification on test data
- [ ] Export in Excel format (.xlsx)
- [ ] Export in CSV format (.csv)
- [ ] Export in TSV format (.tsv)
- [ ] Note file locations

---

## TEST DATA REQUIREMENTS

### Minimum Test Dataset (10-15 assets covering):

| Asset Type | Recovery Period | Convention | Purpose |
|------------|-----------------|------------|---------|
| Computer Equipment | 5-year | HY | Standard personal property |
| Office Furniture | 7-year | HY | Standard personal property |
| Vehicle (car) | 5-year | HY | Luxury auto limits |
| Heavy SUV >6,000 lbs | 5-year | HY | Heavy vehicle 179 |
| Office Building | 39-year | MM | Real property |
| Residential Rental | 27.5-year | MM | Real property |
| Land Improvements | 15-year | HY | 150DB method |
| QIP (post-2018) | 15-year | HY | Qualified Improvement Property |
| Existing Asset | 7-year | HY | Prior year acquisition |
| Disposal | 5-year | HY | Partial year depreciation |
| Current Year Q4 | 5-year | MQ | Mid-quarter test |

---

## IMPORT TESTS

### Test 1: Basic Excel Import
- [ ] File → Import → Excel/CSV
- [ ] Select exported .xlsx file
- [ ] Map columns to FA CS fields
- [ ] Document any mapping errors
- [ ] Complete import
- [ ] **PASS/FAIL:** _______________

**Column Mapping Notes:**
| FA AI Column | FA CS Field | Mapped? |
|--------------|-------------|---------|
| Asset # | Asset Number | [ ] |
| Description | Description | [ ] |
| Cost | Cost | [ ] |
| In Service Date | Date Placed in Service | [ ] |
| Tax Life | Tax Life | [ ] |
| Tax Method | Tax Method | [ ] |
| Tax Sec 179 Expensed | Section 179 | [ ] |
| Tax Bonus Amount | Bonus | [ ] |
| Convention | Convention | [ ] |
| Final Category | Category | [ ] |

### Test 2: CSV Import
- [ ] File → Import → Excel/CSV
- [ ] Select exported .csv file
- [ ] Verify delimiter detection (comma)
- [ ] Map columns
- [ ] Complete import
- [ ] **PASS/FAIL:** _______________

### Test 3: TSV Import
- [ ] File → Import → Excel/CSV
- [ ] Select exported .tsv file
- [ ] Verify delimiter detection (tab)
- [ ] Map columns
- [ ] Complete import
- [ ] **PASS/FAIL:** _______________

---

## POST-IMPORT VALIDATION

### For Each Imported Asset, Verify:

#### Asset Information
- [ ] Asset Number matches
- [ ] Description matches
- [ ] Cost matches exactly (no rounding)
- [ ] In-Service Date correct

#### Tax Depreciation Settings
- [ ] Tax Life correct (3/5/7/10/15/20/27.5/39)
- [ ] Tax Method correct (200DB/150DB/SL)
- [ ] Convention correct (HY/MQ/MM)
- [ ] Section 179 amount correct
- [ ] Bonus depreciation amount correct

#### Calculated Values
- [ ] Year 1 depreciation matches FA AI calculation
- [ ] Accumulated depreciation correct (for existing assets)
- [ ] NBV (Net Book Value) correct

---

## SPECIFIC SCENARIO TESTS

### Test A: Section 179 Asset
**Test Data:** Asset with $50,000 cost, full Section 179

| Field | Expected | FA CS Shows | Match? |
|-------|----------|-------------|--------|
| Cost | $50,000 | | [ ] |
| Section 179 | $50,000 | | [ ] |
| Depreciable Basis | $0 | | [ ] |
| Year 1 Depreciation | $50,000 | | [ ] |

### Test B: Bonus Depreciation (100% OBBBA)
**Test Data:** Asset acquired after 1/19/2025, 100% bonus eligible

| Field | Expected | FA CS Shows | Match? |
|-------|----------|-------------|--------|
| Cost | $25,000 | | [ ] |
| Bonus (100%) | $25,000 | | [ ] |
| Depreciable Basis | $0 | | [ ] |
| Year 1 Depreciation | $25,000 | | [ ] |

### Test C: Real Property (39-Year)
**Test Data:** Office building, mid-month convention

| Field | Expected | FA CS Shows | Match? |
|-------|----------|-------------|--------|
| Cost | $500,000 | | [ ] |
| Tax Life | 39 years | | [ ] |
| Method | SL | | [ ] |
| Convention | MM | | [ ] |
| Month Placed in Service | [Month] | | [ ] |
| Year 1 Depreciation | [Calculate] | | [ ] |

### Test D: Mid-Quarter Convention
**Test Data:** >40% of basis in Q4, forces MQ

| Field | Expected | FA CS Shows | Match? |
|-------|----------|-------------|--------|
| Convention | MQ | | [ ] |
| Quarter | Q4 | | [ ] |
| Year 1 Rate | 5.00% (5-yr Q4) | | [ ] |

### Test E: Disposal (Partial Year)
**Test Data:** Asset disposed mid-year

| Field | Expected | FA CS Shows | Match? |
|-------|----------|-------------|--------|
| Disposal Date | [Date] | | [ ] |
| Final Year Depreciation | [Partial] | | [ ] |
| Gain/Loss Calculated | [ ] | | [ ] |

### Test F: Existing Asset (Prior Year)
**Test Data:** Asset from prior year with accumulated depreciation

| Field | Expected | FA CS Shows | Match? |
|-------|----------|-------------|--------|
| Original In-Service Date | [Prior Year] | | [ ] |
| Accumulated Depreciation | [Amount] | | [ ] |
| Current Year Depreciation | [Amount] | | [ ] |

---

## COMMON ISSUES CHECKLIST

### Date Format Issues
- [ ] MM/DD/YYYY format accepted?
- [ ] YYYY-MM-DD format accepted?
- [ ] Blank dates handled correctly?

### Numeric Format Issues
- [ ] Decimal costs handled? (e.g., $1,234.56)
- [ ] Negative values rejected?
- [ ] Zero cost handled?
- [ ] Large numbers handled? (>$1M)

### Text Field Issues
- [ ] Special characters in descriptions? (& ' " etc.)
- [ ] Long descriptions truncated?
- [ ] UTF-8 characters handled?

### Method/Convention Codes
- [ ] "200DB" recognized? (vs "200% DB" or "GDS 200%")
- [ ] "150DB" recognized?
- [ ] "SL" recognized? (vs "S/L" or "Straight Line")
- [ ] "HY" recognized? (vs "Half-Year")
- [ ] "MQ" recognized? (vs "Mid-Quarter")
- [ ] "MM" recognized? (vs "Mid-Month")

---

## KNOWN FA CS QUIRKS (Document findings here)

| Issue | FA CS Behavior | Workaround |
|-------|----------------|------------|
| | | |
| | | |
| | | |

---

## FINAL VALIDATION

### Depreciation Report Comparison
1. [ ] Generate FA CS Tax Depreciation Report
2. [ ] Compare totals to FA AI export summary
3. [ ] Document any differences

| Metric | FA AI | FA CS | Difference |
|--------|-------|-------|------------|
| Total Cost | | | |
| Total Section 179 | | | |
| Total Bonus | | | |
| Total Year 1 Depreciation | | | |
| Total Accumulated Depreciation | | | |

### Sign-Off
- [ ] All critical tests passed
- [ ] Issues documented
- [ ] Workarounds identified (if any)

**Test Completed By:** _______________
**Date:** _______________
**FA CS Version Confirmed:** 24.1.6

---

## ISSUE LOG

| # | Issue Description | Severity | FA AI Fix Needed? | Status |
|---|-------------------|----------|-------------------|--------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

---

## NOTES

```
[Add notes from testing here]




```

---

*This checklist should be completed each time a new version of Fixed Asset AI is released or when FA CS is updated.*
