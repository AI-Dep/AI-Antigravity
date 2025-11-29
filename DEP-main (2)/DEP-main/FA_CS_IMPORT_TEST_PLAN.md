# FA CS Import Validation Test Plan

## Overview

This test plan validates that exports from Fixed Asset AI can be successfully imported into Thomson Reuters Fixed Asset CS without errors or data loss.

**Goal:** 100% import success rate with zero manual corrections required.

---

## Phase 1: Environment Setup

### Prerequisites

| Item | Required | Notes |
|------|----------|-------|
| FA CS License | Yes | Need active Thomson Reuters Fixed Asset CS |
| Test Client Database | Yes | Create dedicated test client (don't use real client data) |
| FA CS Version | Document | Record exact version for compatibility notes |
| Import Feature Access | Yes | Confirm import from Excel/CSV is enabled |

### Test Client Setup in FA CS

1. Create new client: `TEST_IMPORT_VALIDATION`
2. Set tax year: Current year (e.g., 2024)
3. Set entity type: Corporation (most common)
4. Enable all depreciation books: Tax, AMT, Book, State
5. **Document baseline:** Export empty client to see expected format

---

## Phase 2: Test Data Sets

### Test Set 1: Basic Additions (10 assets)

| # | Description | Cost | Date | Expected Category | Expected Life |
|---|-------------|------|------|-------------------|---------------|
| 1 | Office Desk | $500 | 01/15/2024 | Furniture | 7-year |
| 2 | Dell Laptop | $1,200 | 02/01/2024 | Computer Equipment | 5-year |
| 3 | Delivery Van | $35,000 | 03/15/2024 | Vehicles | 5-year |
| 4 | Office Building | $500,000 | 04/01/2024 | Nonresidential Real Property | 39-year |
| 5 | Warehouse Shelving | $8,000 | 05/01/2024 | Furniture | 7-year |
| 6 | HVAC System | $25,000 | 06/01/2024 | Land Improvements | 15-year |
| 7 | Forklift | $18,000 | 07/01/2024 | Machinery & Equipment | 7-year |
| 8 | Security System | $5,000 | 08/01/2024 | Computer Equipment | 5-year |
| 9 | Parking Lot | $45,000 | 09/01/2024 | Land Improvements | 15-year |
| 10 | Phone System | $3,500 | 10/01/2024 | Computer Equipment | 5-year |

**Test Criteria:**
- [ ] All 10 assets import without errors
- [ ] Categories match expected
- [ ] MACRS lives match expected
- [ ] Conventions applied correctly (HY vs. MM vs. MQ)
- [ ] Depreciation calculations match FA CS auto-calculation

---

### Test Set 2: Section 179 & Bonus (5 assets)

| # | Description | Cost | Sec 179 | Bonus % | Expected Treatment |
|---|-------------|------|---------|---------|-------------------|
| 1 | Equipment A | $50,000 | $50,000 | 0% | Full 179 expense |
| 2 | Equipment B | $100,000 | $0 | 60% | 60% bonus + MACRS |
| 3 | Equipment C | $75,000 | $25,000 | 60% | Partial 179 + bonus |
| 4 | Vehicle (6000+ lbs) | $65,000 | $28,900 | 60% | SUV 179 limit |
| 5 | Listed Property | $10,000 | $0 | 0% | 50% business use |

**Test Criteria:**
- [ ] Section 179 amounts import correctly
- [ ] Bonus depreciation calculates correctly
- [ ] SUV limitations applied ($28,900 limit for 2024)
- [ ] Listed property business use % imports
- [ ] Total Year 1 deduction matches manual calculation

---

### Test Set 3: Disposals (5 assets)

| # | Description | Original Cost | Disposal Date | Proceeds | Accum Depr |
|---|-------------|---------------|---------------|----------|------------|
| 1 | Old Computer | $2,000 | 03/15/2024 | $200 | $1,800 |
| 2 | Sold Vehicle | $30,000 | 06/30/2024 | $15,000 | $20,000 |
| 3 | Scrapped Equip | $5,000 | 09/01/2024 | $0 | $5,000 |
| 4 | Trade-in Asset | $10,000 | 12/01/2024 | $3,000 | $7,000 |
| 5 | Partial Disposal | $50,000 | 07/15/2024 | $10,000 | $15,000 |

**Test Criteria:**
- [ ] Disposal dates import correctly
- [ ] Proceeds recorded accurately
- [ ] Gain/loss calculates correctly in FA CS
- [ ] Accumulated depreciation matches
- [ ] Recapture (if any) flagged correctly

---

### Test Set 4: Existing Assets (5 assets)

| # | Description | Cost | In-Service | Accum Depr | Prior 179 | Prior Bonus |
|---|-------------|------|------------|------------|-----------|-------------|
| 1 | 3-yr old Equipment | $20,000 | 01/01/2021 | $12,000 | $0 | $10,000 |
| 2 | 5-yr old Building | $300,000 | 07/01/2019 | $35,000 | $0 | $0 |
| 3 | 2-yr old Vehicle | $40,000 | 06/15/2022 | $20,000 | $0 | $24,000 |
| 4 | Old Furniture | $8,000 | 03/01/2018 | $8,000 | $0 | $0 |
| 5 | Partial 179 Asset | $15,000 | 01/01/2023 | $3,000 | $5,000 | $0 |

**Test Criteria:**
- [ ] In-service dates preserved (not changed to current year)
- [ ] Accumulated depreciation imports correctly
- [ ] Prior Section 179 recorded
- [ ] Prior bonus depreciation recorded
- [ ] Current year depreciation calculates correctly (not Year 1!)
- [ ] Remaining basis correct

---

### Test Set 5: Transfers (3 assets)

| # | Description | From Location | To Location | From Dept | To Dept | Transfer Date |
|---|-------------|---------------|-------------|-----------|---------|---------------|
| 1 | Transferred Equip | Building A | Building B | Sales | Marketing | 04/01/2024 |
| 2 | Reclass Asset | - | - | Dept 100 | Dept 200 | 07/15/2024 |
| 3 | Location Move | Site 1 | Site 2 | - | - | 10/01/2024 |

**Test Criteria:**
- [ ] Transfer records import (or are handled appropriately)
- [ ] Location changes reflected
- [ ] Department/cost center changes reflected
- [ ] No depreciation impact from transfer alone

---

### Test Set 6: Edge Cases (10 scenarios)

| # | Scenario | Expected Behavior |
|---|----------|-------------------|
| 1 | $0 cost asset | Should import (fully expensed or donated) |
| 2 | Future in-service date | Warning or rejection |
| 3 | Very long description (500+ chars) | Truncate without error |
| 4 | Special characters in description | Handle or sanitize |
| 5 | Missing Asset ID | Auto-generate or reject |
| 6 | Duplicate Asset ID | Reject with clear error |
| 7 | Negative cost | Reject with error |
| 8 | Cost = $0.01 | Should import |
| 9 | 100% business use listed property | No limitation applied |
| 10 | Land (non-depreciable) | Import with no depreciation |

---

## Phase 3: Import Testing Process

### For Each Test Set:

```
Step 1: Generate Export
├── Load test data into Fixed Asset AI
├── Run classification
├── Generate FA CS export file
└── Save export file with timestamp

Step 2: Pre-Import Validation
├── Open export file in Excel
├── Check column headers match FA CS expected format
├── Verify no #N/A, #REF!, or error values
├── Check date formats (MM/DD/YYYY)
└── Check numeric formats (no $ or , in numbers)

Step 3: Import to FA CS
├── Open FA CS test client
├── Go to File > Import
├── Select export file
├── Document any warnings during import
└── Document any errors during import

Step 4: Post-Import Validation
├── Count imported assets (should match source)
├── Spot-check 100% of assets for:
│   ├── Description matches
│   ├── Cost matches
│   ├── Dates match
│   ├── Category/class matches
│   ├── Method matches (GDS/ADS, 200DB/150DB/SL)
│   ├── Convention matches
│   ├── Section 179 matches
│   ├── Bonus matches
│   └── Depreciation calculates correctly
└── Run FA CS depreciation calculation

Step 5: Document Results
├── Screenshot any errors
├── Note any manual corrections needed
├── Record pass/fail for each asset
└── Calculate success rate
```

---

## Phase 4: Field Mapping Validation

### Critical Fields to Verify

| Export Column | FA CS Field | Validation Method |
|---------------|-------------|-------------------|
| Asset ID | Asset Number | Exact match |
| Description | Description | Exact match (check truncation) |
| Cost | Unadjusted Basis | Exact match |
| In Service Date | Placed in Service | Date format correct |
| Category | Asset Class | Maps to valid FA CS class |
| MACRS Life | Recovery Period | Valid values (3,5,7,10,15,20,27.5,39) |
| Method | Depreciation Method | Valid FA CS method code |
| Convention | Convention | HY, MQ, MM, or S/L |
| Section 179 | Section 179 Expense | Numeric, within limits |
| Bonus % | Special Depreciation | Valid percentage |
| Disposal Date | Disposal Date | Date format correct |
| Proceeds | Sales Price | Numeric |

### FA CS Import Field Requirements

```
Required Fields (import will fail without):
- Description
- Cost/Basis
- Placed in Service Date
- Asset Class OR Recovery Period

Recommended Fields:
- Asset Number (auto-generates if blank)
- Method
- Convention

Optional Fields:
- Location
- Department
- Vendor
- Invoice Number
- Serial Number
```

---

## Phase 5: Depreciation Calculation Validation

### Manual Verification Spreadsheet

For each test asset, calculate expected depreciation manually:

```
Asset: Dell Laptop
Cost: $1,200
In-Service: 02/01/2024
Class: 5-year
Method: 200% DB
Convention: Half-Year

Year 1 Depreciation Calculation:
- Rate: 20% (from MACRS table)
- Full year: $1,200 × 20% = $240
- Half-year convention: $240 (already factored in MACRS rate)
- Expected: $240

Compare to FA CS calculated: $_____
Match: [ ] Yes [ ] No
```

### Depreciation Test Matrix

| Asset Type | Method | Convention | Year 1 Rate | Verify |
|------------|--------|------------|-------------|--------|
| 5-year property | 200DB | HY | 20.00% | [ ] |
| 7-year property | 200DB | HY | 14.29% | [ ] |
| 15-year property | 150DB | HY | 5.00% | [ ] |
| 39-year property | SL | MM | Varies | [ ] |
| Bonus 60% | - | - | 60% + MACRS | [ ] |
| Section 179 | - | - | 100% (to limit) | [ ] |

---

## Phase 6: Error Documentation

### Error Log Template

| Date | Test Set | Asset | Error Message | Root Cause | Fix Applied | Retested |
|------|----------|-------|---------------|------------|-------------|----------|
| | | | | | | [ ] |

### Common Import Errors to Watch For

1. **"Invalid asset class"** - Category not mapping to FA CS class
2. **"Invalid date format"** - Date not in MM/DD/YYYY
3. **"Invalid method"** - Depreciation method code wrong
4. **"Duplicate asset number"** - Asset ID conflict
5. **"Required field missing"** - Missing description or cost
6. **"Value out of range"** - Negative numbers, invalid percentages

---

## Phase 7: Success Criteria

### Minimum Viable Product (MVP)

| Criteria | Target | Actual | Status |
|----------|--------|--------|--------|
| Basic additions import | 100% | | [ ] |
| Correct depreciation | 100% | | [ ] |
| No manual corrections | 0 | | [ ] |
| Import errors | 0 | | [ ] |

### Production Ready

| Criteria | Target | Actual | Status |
|----------|--------|--------|--------|
| All test sets pass | 100% | | [ ] |
| Edge cases handled | 90%+ | | [ ] |
| Clear error messages | Yes | | [ ] |
| Documentation complete | Yes | | [ ] |
| Beta tester validation | 2+ CPAs | | [ ] |

---

## Phase 8: Beta Testing

### Beta Tester Recruitment

Target: 2-3 CPA firms willing to test with real (anonymized) data

**Beta Tester Agreement:**
- Provide anonymized client fixed asset data
- Test import process and report issues
- Provide feedback on usability
- In exchange: Free access during beta + discounted pricing

### Beta Test Protocol

1. Tester provides sample data (10-50 assets)
2. You run through Fixed Asset AI
3. Tester imports to their FA CS
4. Tester validates accuracy
5. Document all issues
6. Iterate until 100% success

---

## Appendix A: FA CS Version Compatibility

| FA CS Version | Tested | Status | Notes |
|---------------|--------|--------|-------|
| 2024.x | [ ] | | |
| 2023.x | [ ] | | |
| 2022.x | [ ] | | |

---

## Appendix B: Quick Reference - FA CS Import Format

### Expected Column Headers (verify against your export)

```
Asset Number
Description
Date Acquired
Date Placed in Service
Cost
Asset Class
Recovery Period
Depreciation Method
Convention
Section 179 Expense
Special Depreciation Allowance
Disposal Date
Sales Price
```

### Valid Depreciation Methods

| Code | Description |
|------|-------------|
| 200DB | 200% Declining Balance |
| 150DB | 150% Declining Balance |
| SL | Straight Line |
| MACRS | MACRS (default) |

### Valid Conventions

| Code | Description |
|------|-------------|
| HY | Half-Year |
| MQ | Mid-Quarter |
| MM | Mid-Month |

---

## Appendix C: Test Execution Checklist

```
[ ] Phase 1: Environment setup complete
[ ] Phase 2: Test data sets created
[ ] Phase 3: Test Set 1 (Basic Additions) - PASS/FAIL
[ ] Phase 3: Test Set 2 (179 & Bonus) - PASS/FAIL
[ ] Phase 3: Test Set 3 (Disposals) - PASS/FAIL
[ ] Phase 3: Test Set 4 (Existing Assets) - PASS/FAIL
[ ] Phase 3: Test Set 5 (Transfers) - PASS/FAIL
[ ] Phase 3: Test Set 6 (Edge Cases) - PASS/FAIL
[ ] Phase 4: Field mapping validated
[ ] Phase 5: Depreciation calculations verified
[ ] Phase 6: All errors documented and fixed
[ ] Phase 7: Success criteria met
[ ] Phase 8: Beta testing complete

FINAL STATUS: [ ] READY FOR PRODUCTION / [ ] NEEDS MORE WORK
```

---

## Next Steps After Validation

1. **If all tests pass:**
   - Document supported FA CS versions
   - Create user guide for import process
   - Launch with confidence

2. **If tests fail:**
   - Prioritize fixes by frequency/severity
   - Re-test after each fix
   - Don't launch until 100% success rate

3. **Ongoing:**
   - Test with each new FA CS version
   - Collect user feedback on import issues
   - Maintain error log for patterns
