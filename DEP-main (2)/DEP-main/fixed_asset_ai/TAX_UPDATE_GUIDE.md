# Tax Configuration Annual Update Guide

## Overview

This guide explains how to keep the Fixed Asset AI tool up-to-date with the latest IRS tax regulations. **Failure to update can result in incorrect depreciation calculations.**

## When to Update

| Event | Timing | What to Update |
|-------|--------|----------------|
| IRS Revenue Procedure | October-November | Section 179 limits, Luxury Auto limits |
| New Tax Legislation | When enacted | Bonus rates, new rules, effective dates |
| Annual Inflation Adjustments | Published by IRS | All dollar thresholds |

## Update Checklist

### Annual Updates (Every Fall)

1. **Section 179 Limits** (`SECTION_179_LIMITS` dict)
   - Maximum deduction amount
   - Phase-out threshold
   - Source: IRS Revenue Procedure (e.g., Rev. Proc. 2024-40)

2. **Luxury Auto Limits** (`LUXURY_AUTO_LIMITS` dict)
   - Year 1 limit (with and without bonus)
   - Years 2, 3, 4+ limits
   - Source: IRS Revenue Procedure for §280F

3. **Heavy SUV Section 179 Limit** (`HEAVY_SUV_179_LIMITS` dict)
   - Source: Same Revenue Procedure as Section 179

4. **Tax Year Status** (`SUPPORTED_TAX_YEARS` dict)
   - Change status from `ESTIMATED` to `OFFICIAL` when IRS publishes
   - Add new year with `ESTIMATED` status

5. **Version Tracking**
   - Update `CONFIG_LAST_UPDATED`
   - Increment `CONFIG_VERSION`

### Legislative Updates (As Needed)

1. **Bonus Depreciation Changes**
   - Update `get_bonus_percentage()` function
   - Update effective dates if new legislation

2. **New Tax Provisions**
   - Add new functions/constants as needed
   - Document IRC references

## File to Edit

```
fixed_asset_ai/logic/tax_year_config.py
```

## Step-by-Step Update Process

### 1. Find IRS Source

Look for Revenue Procedures on:
- https://www.irs.gov/irb (Internal Revenue Bulletin)
- Search: "Rev. Proc. [year] section 179" or "§280F inflation"

### 2. Update the Configuration

```python
# Example: Adding 2027 limits
SECTION_179_LIMITS = {
    # ... existing years ...
    2027: {
        "max_deduction": XXXXXXX,  # From Rev. Proc.
        "phaseout_threshold": XXXXXXX,  # From Rev. Proc.
        "indexed_for_inflation": True,
    },
}

LUXURY_AUTO_LIMITS = {
    # ... existing years ...
    2027: {
        "year_1_without_bonus": XXXXX,
        "year_1_with_bonus": XXXXX,
        "year_2": XXXXX,
        "year_3": XXXXX,
        "year_4_plus": XXXX,
    },
}

HEAVY_SUV_179_LIMITS = {
    # ... existing years ...
    2027: XXXXX,
}

# Update the supported years
SUPPORTED_TAX_YEARS = {
    # ... existing years ...
    2027: TaxYearStatus.OFFICIAL,  # or ESTIMATED if not yet published
}
```

### 3. Update Version Info

```python
CONFIG_VERSION = "2.1.0"  # Increment version
CONFIG_LAST_UPDATED = "2026-11-15"  # Today's date
CONFIG_UPDATED_BY = "Your Name"
```

### 4. Validate Changes

Run the validation tool:

```bash
cd /home/user/DEP
python -m fixed_asset_ai.logic.tax_year_config --validate
```

This will show:
- All configured tax years
- Their status (Official/Estimated)
- Any missing configurations

### 5. Test

1. Start the Streamlit app
2. Select the new tax year
3. Verify the status shows correctly (green = official, yellow = estimated)
4. Process a test file and verify calculations

## IRS Reference Sources

| Limit Type | IRC Section | Typical Rev. Proc. |
|------------|-------------|-------------------|
| Section 179 | §179(b) | Rev. Proc. 20XX-XX |
| Luxury Auto | §280F | Rev. Proc. 20XX-XX |
| Heavy SUV | §179(b)(5)(B) | Same as §179 |
| Bonus Depreciation | §168(k) | Statutory (TCJA/OBBB) |

## Emergency Updates

If major tax legislation passes (like TCJA or OBBB Act):

1. Read the actual legislation or reliable tax news
2. Update the affected functions immediately
3. Add effective date constants
4. Update `SUPPORTED_TAX_YEARS`
5. Document the change with source links

## Audit Trail

Keep a changelog in the file header or commit messages:

```
# Changelog:
# 2025-07-15: Added OBBB Act provisions (100% bonus after 1/19/2025)
# 2024-11-01: Updated 2025 limits from Rev. Proc. 2024-40
# 2024-10-15: Added 2025 estimated limits
```

## Support

For questions about tax law interpretation, consult:
- IRS guidance directly
- Tax professional/CPA
- Major accounting firm publications (PWC, Deloitte, EY, KPMG)

---

**Remember: This tool is only as accurate as its configuration. Update it promptly when IRS publishes new guidance.**
