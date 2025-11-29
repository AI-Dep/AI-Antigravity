# FA CS Import Testing Guide

## Objective

Determine whether Fixed Asset CS:
- **Scenario A**: Recalculates depreciation when importing (ignores calculated fields)
- **Scenario B**: Uses imported calculated values as-is (accepts our calculations)

This is **critical** because:
- If Scenario A: We can use minimal export (faster, simpler, safer)
- If Scenario B: We must ensure our calculations are 100% accurate

---

## Quick Start

### 1. Generate Test Files

```bash
python test_fa_cs_import_behavior.py
```

This creates:
- `test_minimal_export.xlsx` - Minimal fields only (let FA CS calculate)
- `test_full_export.xlsx` - All calculated fields (use our calculations)

### 2. Complete Manual FA CS Login

**CRITICAL**: You must complete the entire manual login process before testing.

See [FA_CS_LOGIN_LIMITATIONS.md](FA_CS_LOGIN_LIMITATIONS.md) for details.

### 3. Run Test Procedure (below)

---

## Test Procedure

### STEP 1: Manual Entry (Baseline)

**Purpose**: Establish baseline values from FA CS calculations

In FA CS, manually create asset:

```
Asset #: TEST-001
Description: Test Computer - Manual Entry
Date In Service: 1/1/2024
Acquisition Date: 1/1/2024
Tax Cost: $5,000
Tax Method: MACRS GDS
Tax Life: 5
Convention: HY
```

**Let FA CS calculate Section 179, Bonus, and Depreciation.**

**Record FA CS calculated values:**

| Field | FA CS Value |
|-------|-------------|
| Tax Sec 179 Expensed | $_________ |
| Bonus Amount | $_________ |
| Tax Cur Depreciation | $_________ |
| Depreciable Basis | $_________ |
| Total Year 1 Deduction | $_________ |

---

### STEP 2: Import Minimal File

**Purpose**: Test if FA CS recalculates when given minimal fields

In FA CS:
1. File → Import
2. Select `test_minimal_export.xlsx`
3. Map fields (should auto-map correctly)
4. Import

This file contains **TEST-002** with **MINIMAL fields only**:
- Asset #, Description, Dates
- Tax Cost, Tax Method, Tax Life, Convention
- **NO** Section 179, Bonus, or Depreciation values

**Check TEST-002 in FA CS:**

| Field | FA CS Value |
|-------|-------------|
| Tax Sec 179 Expensed | $_________ |
| Bonus Amount | $_________ |
| Tax Cur Depreciation | $_________ |
| Depreciable Basis | $_________ |
| Total Year 1 Deduction | $_________ |

**Question**: Do these values match TEST-001?
- [ ] YES - Same values
- [ ] NO - Different values

---

### STEP 3: Import Full File

**Purpose**: Test if FA CS uses imported calculated values

In FA CS:
1. File → Import
2. Select `test_full_export.xlsx`
3. Map fields (should auto-map correctly)
4. Import

This file contains **TEST-003** with **ALL calculated fields**:
- Basic fields (same as minimal)
- **PLUS** Section 179, Bonus, Depreciation values (pre-calculated by our tool)

**Our tool calculated (from test_full_export.xlsx):**

| Field | Our Calculation |
|-------|-----------------|
| Tax Sec 179 Expensed | (see file) |
| Bonus Amount | (see file) |
| Tax Cur Depreciation | (see file) |
| Depreciable Basis | (see file) |

**Check TEST-003 in FA CS:**

| Field | FA CS Value |
|-------|-------------|
| Tax Sec 179 Expensed | $_________ |
| Bonus Amount | $_________ |
| Tax Cur Depreciation | $_________ |
| Depreciable Basis | $_________ |
| Total Year 1 Deduction | $_________ |

**Question**: Do these values match our tool's calculations?
- [ ] YES - FA CS used our values exactly
- [ ] NO - FA CS recalculated different values

---

## Interpret Results

### ✅ SCENARIO A: FA CS Recalculates (Most Likely)

**Indicators:**
- TEST-001 (manual) = TEST-002 (minimal) = TEST-003 (full)
- All three assets have **SAME** calculated values
- FA CS **ignored** calculated fields in full export and recalculated

**Conclusion:**
- ✓ Safe to use **minimal** export (recommended)
- ✓ Safe to use **full** export (FA CS ignores calculated fields)
- ✓ FA CS calculates depreciation internally
- ✓ No need to worry about calculation accuracy in export

**Recommendation:**
- Use `build_fa_minimal()` for faster, simpler exports
- Include only required fields
- Let FA CS handle all calculations

---

### ⚠️ SCENARIO B: FA CS Uses Imported Values (Possible)

**Indicators:**
- TEST-001 (manual) = TEST-002 (minimal) ≠ TEST-003 (full)
- TEST-003 matches **our tool's calculations** exactly
- FA CS **used** calculated fields from full export without recalculating

**Conclusion:**
- ⚠️ FA CS accepts and uses imported calculated values
- ⚠️ Our calculations must be 100% accurate
- ⚠️ Need to verify calculation logic thoroughly

**Recommendation:**
- Use `build_fa()` (full export) with verified calculations
- Add extensive testing for calculation accuracy
- Consider manual review of calculated values before import

---

## Additional Testing

### Test with Existing Asset (Prior Year)

If you want to test existing assets:

1. Check `test_full_export.xlsx` for **TEST-004** (Existing Asset)
2. Import and verify:
   - Tax Prior Depreciation is correct
   - Tax Cur Depreciation is current year only
   - No Section 179 or Bonus (not allowed for existing assets)

### Test with Disposal

Create a disposal asset and test:
- Recapture calculations
- Capital gain/loss
- Adjusted basis

---

## Reporting Results

After testing, report:

### 1. Primary Question

**Do all three assets (TEST-001, TEST-002, TEST-003) have SAME calculated values?**

- [ ] **YES** → FA CS recalculates (Scenario A)
- [ ] **NO** → FA CS uses imported values (Scenario B)

### 2. Value Comparison

| Field | TEST-001 (Manual) | TEST-002 (Minimal) | TEST-003 (Full) | Match? |
|-------|-------------------|-------------------|-----------------|--------|
| Tax Sec 179 | $_________ | $_________ | $_________ | Y/N |
| Bonus | $_________ | $_________ | $_________ | Y/N |
| Tax Cur Depr | $_________ | $_________ | $_________ | Y/N |
| Depr Basis | $_________ | $_________ | $_________ | Y/N |

### 3. Screenshots (Optional)

Attach screenshots showing:
- FA CS asset details for TEST-001, TEST-002, TEST-003
- Calculated depreciation values
- Any error messages during import

### 4. Import Success

- [ ] Minimal import succeeded without errors
- [ ] Full import succeeded without errors
- [ ] Field mapping was correct
- [ ] No FA CS warnings or errors

---

## Next Steps Based on Results

### If Scenario A (FA CS Recalculates)

1. ✅ Update default export to use `build_fa_minimal()`
2. ✅ Simplify export format
3. ✅ Faster processing
4. ✅ Less risk of calculation mismatches

### If Scenario B (FA CS Uses Imported Values)

1. ⚠️ Verify all calculation logic is correct
2. ⚠️ Add comprehensive unit tests
3. ⚠️ Compare our calculations with FA CS manual entry
4. ⚠️ Consider manual review before import

---

## Troubleshooting

### Import Fails

**Error: "Invalid Method"**
- Check that Tax Method is "MACRS GDS" or "MACRS ADS"
- NOT "200DB", "150DB", "SL"

**Error: "Invalid Life"**
- Check that Tax Life is a number (5, 7, 15, 27.5, 39)
- NOT "5-Year MACRS" or descriptive text

**Error: "Sheet Role not recognized"**
- Check that Sheet Role is "main"
- NOT "addition", "disposal", "transfer"

### Values Don't Match

If TEST-001, TEST-002, TEST-003 all have different values:
- Check FA CS settings (Section 179 election, Bonus %, etc.)
- Verify tax year is 2024
- Check that all three assets have identical input data
- Screenshots may help diagnose

---

## Quick Test Checklist

- [ ] Run `python test_fa_cs_import_behavior.py`
- [ ] Complete manual FA CS login
- [ ] Manually create TEST-001 in FA CS
- [ ] Record TEST-001 calculated values
- [ ] Import `test_minimal_export.xlsx`
- [ ] Record TEST-002 calculated values
- [ ] Import `test_full_export.xlsx`
- [ ] Record TEST-003 calculated values
- [ ] Compare all three assets
- [ ] Determine Scenario A or B
- [ ] Report results

---

## Expected Timeline

- **Setup**: 5 minutes (run script, login to FA CS)
- **Manual Entry**: 5 minutes (create TEST-001)
- **Import Testing**: 10 minutes (import both files, check values)
- **Analysis**: 5 minutes (compare values, determine scenario)

**Total**: ~25 minutes

---

## Contact

If you encounter any issues or need help interpreting results:
1. Share screenshots of FA CS asset details
2. Share the comparison table (values for all three assets)
3. Note any error messages during import

---

**Last Updated**: 2025-01-20
**Author**: Claude Code
**Purpose**: Determine FA CS import behavior to optimize export format
