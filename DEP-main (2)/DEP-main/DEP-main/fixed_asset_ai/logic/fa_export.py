# logic/fa_export.py

from io import BytesIO
from datetime import datetime, date
from typing import Optional

import pandas as pd

from .parse_utils import parse_date, parse_number
from .tax_year_config import (
    get_bonus_percentage,
    get_section_179_limits,
    get_luxury_auto_limits,
    get_heavy_suv_179_limit,
    validate_tax_year_config,
)
from .data_validator import validate_asset_data
from .ads_system import should_use_ads, apply_ads_to_asset
from .listed_property import (
    is_listed_property,
    get_business_use_percentage,
    validate_business_use_for_incentives,
)
from .recapture import (
    calculate_section_1245_recapture,
    calculate_section_1250_recapture,
    determine_recapture_type,
)
from .convention_rules import (
    detect_mid_quarter_convention,
    get_quarter,
)
from .macrs_tables import calculate_macrs_depreciation
from .section_179_carryforward import (
    apply_section_179_carryforward_to_dataframe,
    generate_section_179_report,
)
from .export_qa_validator import validate_fixed_asset_cs_export
from .transaction_classifier import (
    classify_all_transactions,
    validate_transaction_classification,
)


# --------------------------------------------------------------
# IRC §280F LUXURY AUTO DEPRECIATION LIMITS
# NOTE: Now loaded from tax_year_config.py for flexibility
# --------------------------------------------------------------


def _is_passenger_auto(row) -> bool:
    """
    Check if asset is a passenger automobile subject to §280F limits.

    Returns True for passenger vehicles, False for heavy trucks/SUVs >6,000 lbs.
    """
    final_class = str(row.get("Final Category", "")).lower()
    desc = str(row.get("Description", "")).lower()

    # Check if classified as passenger auto
    if "passenger" in final_class and "auto" in final_class:
        return True

    # Also check description for typical passenger vehicles
    passenger_indicators = ["car", "sedan", "suv", "crossover", "van", "minivan"]
    heavy_indicators = ["heavy duty", "f-250", "f-350", "2500", "3500", "commercial truck"]

    # If heavy truck indicators, not subject to passenger limits
    if any(h in desc for h in heavy_indicators):
        return False

    # If passenger indicators, subject to limits
    if any(p in desc for p in passenger_indicators):
        return True

    return False


def _is_heavy_suv(row) -> bool:
    """
    Check if vehicle is a heavy SUV/truck (>6,000 lbs GVWR).

    Heavy SUVs are:
    - NOT subject to IRC §280F luxury auto limits
    - BUT subject to special Section 179 limit (currently $28,900 for 2024)

    Per IRC §179(b)(5), heavy SUVs have a reduced Section 179 limit.

    Returns:
        True if heavy SUV/truck (>6,000 lbs)
        False otherwise
    """
    final_class = str(row.get("Final Category", "")).lower()
    desc = str(row.get("Description", "")).lower()

    # Must be in Trucks & Trailers category or have truck/suv indicators
    is_truck_category = "truck" in final_class or "trailer" in final_class

    # Check for heavy SUV/truck indicators in description
    heavy_suv_indicators = [
        # Explicit weight indicators
        "gvwr 6", "6000 lbs", "6,000 lbs", "6000lbs", "6,000lbs",
        "gross vehicle weight", "over 6000", "over 6,000",

        # Common heavy SUV models
        "suburban", "tahoe", "yukon", "expedition", "navigator",
        "escalade", "land cruiser", "sequoia", "armada",
        "gx 460", "lx 570", "lx 600", "gx 550",
        "qx80", "range rover", "land rover defender",

        # Heavy duty trucks
        "f-250", "f-350", "f250", "f350",
        "2500", "3500", "2500hd", "3500hd",
        "heavy duty", "hd", "crew cab diesel",
        "dually", "super duty",

        # Commercial trucks
        "commercial truck", "work truck", "cargo van",
        "sprinter", "transit 250", "transit 350",
        "promaster 2500", "promaster 3500",
    ]

    # Check if description contains heavy SUV/truck indicators
    has_heavy_indicator = any(ind in desc for ind in heavy_suv_indicators)

    # Light truck/SUV indicators (NOT heavy)
    light_indicators = [
        "f-150", "f150", "1500", "tacoma", "ranger",
        "colorado", "canyon", "ridgeline", "maverick",
        "cr-v", "rav4", "highlander", "pilot", "pathfinder"
    ]

    has_light_indicator = any(ind in desc for ind in light_indicators)

    # Heavy SUV if:
    # 1. In truck category AND has heavy indicators AND NOT light indicators
    # 2. OR has explicit GVWR >6,000 lbs
    if "gvwr" in desc or "gross vehicle weight" in desc:
        return True  # Explicit weight spec

    if is_truck_category and has_heavy_indicator and not has_light_indicator:
        return True

    return False


def _apply_luxury_auto_caps(row, sec179: float, bonus: float, tax_year: int) -> tuple[float, float, str]:
    """
    Apply IRC §280F luxury automobile depreciation limitations.

    Args:
        row: Asset row with classification data
        sec179: Calculated Section 179 amount
        bonus: Calculated bonus depreciation amount
        tax_year: Current tax year

    Returns:
        Tuple of (capped_sec179, capped_bonus, notes)
    """
    if not _is_passenger_auto(row):
        return sec179, bonus, ""

    cost = float(row.get("Cost") or 0.0)
    in_service = row.get("In Service Date")

    # Only apply to current year additions
    if not _is_current_year(in_service, tax_year):
        return sec179, bonus, ""

    # Calculate total year 1 depreciation requested
    total_requested = sec179 + bonus

    # Get limits for the tax year (dynamically loaded)
    limits = get_luxury_auto_limits(tax_year, asset_year=1)

    # Determine applicable limit
    if bonus > 0:
        year_1_limit = limits["year_1_with_bonus"]
        limit_type = "with bonus"
    else:
        year_1_limit = limits["year_1_without_bonus"]
        limit_type = "without bonus"

    # If requested amount exceeds limit, apply cap
    if total_requested > year_1_limit:
        # Priority: Bonus first, then Section 179
        capped_bonus = min(bonus, year_1_limit)
        remaining = year_1_limit - capped_bonus
        capped_sec179 = min(sec179, remaining)

        notes = f"IRC §280F luxury auto limit applied: Year 1 {limit_type} = ${year_1_limit:,.0f} (requested ${total_requested:,.0f}, excess ${total_requested - year_1_limit:,.0f} not allowed)"

        return capped_sec179, capped_bonus, notes

    return sec179, bonus, ""


# --------------------------------------------------------------
# Helpers
# --------------------------------------------------------------

def _pick(col1, col2):
    """Return first non-null value."""
    if pd.notna(col1) and col1 not in ("", None):
        return col1
    return col2


def _is_current_year(date_val: Optional[date], tax_year: int) -> bool:
    """Check if placed-in-service date is in current tax year."""
    if not isinstance(date_val, (datetime, date)):
        return False
    return date_val.year == tax_year


def _is_disposal(row) -> bool:
    """Determine if row represents a disposal."""
    raw = str(row.get("Sheet Role", "")).lower()
    if raw == "":
        raw = str(row.get("Transaction Type", "")).lower()
    return any(x in raw for x in ["dispos", "disposal", "disposed", "sold", "retire"])


def _is_transfer(row) -> bool:
    raw = str(row.get("Sheet Role", "")).lower()
    if raw == "":
        raw = str(row.get("Transaction Type", "")).lower()
    return any(x in raw for x in ["transfer", "xfer", "reclass"])


# --------------------------------------------------------------
# Main export builder
# --------------------------------------------------------------

def build_fa(
    df: pd.DataFrame,
    tax_year: int,
    strategy: str,
    taxable_income: float,
    use_acq_if_missing: bool = True,
    de_minimis_limit: float = 0.0,  # Set to 2500 or 5000 to enable de minimis safe harbor
) -> pd.DataFrame:

    df = df.copy()

    # ----------------------------------------------------------------------
    # DATA VALIDATION - Catch errors before processing
    # ----------------------------------------------------------------------
    validation_errors, should_stop = validate_asset_data(df, tax_year)

    if validation_errors:
        print(f"\n{'='*70}")
        print(f"DATA VALIDATION RESULTS: {len(validation_errors)} issues found")
        print(f"{'='*70}")

        # Group by severity
        critical = [e for e in validation_errors if e.severity == "CRITICAL"]
        errors = [e for e in validation_errors if e.severity == "ERROR"]
        warnings = [e for e in validation_errors if e.severity == "WARNING"]

        if critical:
            print(f"\n🔴 CRITICAL ({len(critical)}):")
            for e in critical[:5]:  # Show first 5
                print(f"  {e}")

        if errors:
            print(f"\n❌ ERRORS ({len(errors)}):")
            for e in errors[:10]:  # Show first 10
                print(f"  {e}")

        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)}):")
            for e in warnings[:10]:  # Show first 10
                print(f"  {e}")

        print(f"\n{'='*70}\n")

        if should_stop:
            raise ValueError(
                f"CRITICAL data validation errors found. "
                f"Processing stopped to prevent incorrect results. "
                f"Fix data quality issues and try again."
            )

    # ============================================================================
    # CRITICAL FIX: TRANSACTION TYPE CLASSIFICATION
    # ============================================================================
    # ISSUE: System was defaulting ALL assets to "addition" even if they were
    # placed in service in prior years (e.g., 2020 assets being treated as 2024 additions).
    #
    # This caused:
    # ❌ Section 179 claimed on old assets (NOT ALLOWED per IRC §179)
    # ❌ Bonus depreciation on old assets (NOT ALLOWED per IRC §168(k))
    # ❌ Massive tax deduction overstatement
    # ❌ IRS audit risk
    #
    # SOLUTION: Properly classify based on in-service date vs tax year:
    # ✅ Current Year Addition: In-service date = current tax year
    # ✅ Existing Asset: In-service date < current tax year
    # ✅ Disposal: Transaction type or disposal date indicates sale
    # ✅ Transfer: Transaction type indicates transfer/reclass

    df = classify_all_transactions(df, tax_year, verbose=True)

    # Validate that no existing assets are being treated as additions
    is_valid, classification_errors = validate_transaction_classification(df, tax_year)

    if not is_valid:
        raise ValueError(
            f"CRITICAL: Transaction classification errors detected. "
            f"Found {len(classification_errors)} assets incorrectly classified. "
            f"This would cause incorrect Section 179/Bonus claims. "
            f"See error details above."
        )

    # ----------------------------------------------------------------------
    # Basic cleanup
    # ----------------------------------------------------------------------
    if "Asset ID" not in df.columns:
        df["Asset ID"] = df.index.astype(str)

    # Parse cost
    if "Cost" in df.columns:
        df["Cost"] = df["Cost"].apply(parse_number)
    else:
        df["Cost"] = 0.0

    # Parse dates
    df["Acquisition Date"] = df.get("Acquisition Date", None).apply(parse_date)
    df["In Service Date"] = df.get("In Service Date", None).apply(parse_date)

    if use_acq_if_missing:
        df["In Service Date"] = df.apply(
            lambda r: r["In Service Date"] or r["Acquisition Date"],
            axis=1
        )

    # ============================================================================
    # TIER 3: DE MINIMIS SAFE HARBOR (Rev. Proc. 2015-20)
    # ============================================================================
    # Election to immediately expense items ≤$2,500 (or ≤$5,000 with AFS)
    # - Does NOT count against Section 179 limits
    # - Reduces depreciation tracking burden
    # - Separate from bonus depreciation
    #
    # NOTE: This is an ELECTION that taxpayers can make. We apply it if the
    # de_minimis_limit parameter is set.

    if de_minimis_limit and de_minimis_limit > 0:
        de_minimis_expensed = []

        for idx, row in df.iterrows():
            cost = float(row.get("Cost") or 0.0)
            trans_type = str(row.get("Transaction Type", ""))

            # CRITICAL: Only for CURRENT YEAR additions (not existing assets)
            # De minimis safe harbor only applies to property placed in service in current year
            if "Current Year Addition" in trans_type:
                if 0 < cost <= de_minimis_limit:
                    # Mark as de minimis expensed
                    de_minimis_expensed.append(cost)
                    # Set cost to 0 so it doesn't get depreciation calculated
                    df.at[idx, "De Minimis Expensed"] = cost
                    df.at[idx, "Cost"] = 0.0
                else:
                    de_minimis_expensed.append(0.0)
            else:
                de_minimis_expensed.append(0.0)

        df["De Minimis Expensed"] = de_minimis_expensed

        # Print summary if any de minimis items
        total_de_minimis = sum(de_minimis_expensed)
        count_de_minimis = sum(1 for x in de_minimis_expensed if x > 0)

        if total_de_minimis > 0:
            print("\n" + "=" * 80)
            print(f"DE MINIMIS SAFE HARBOR - Rev. Proc. 2015-20")
            print("=" * 80)
            print(f"Limit: ${de_minimis_limit:,.2f} per item")
            print(f"Items expensed immediately: {count_de_minimis}")
            print(f"Total de minimis expensed: ${total_de_minimis:,.2f}")
            print(f"(Does NOT count against Section 179 limits)")
            print("=" * 80 + "\n")
    else:
        # No de minimis election
        df["De Minimis Expensed"] = 0.0

    # ----------------------------------------------------------------------
    # Depreciation classification only applies to ADDITIONS
    # ----------------------------------------------------------------------

    # Validate tax year configuration and warn if using estimated values
    config_warnings = validate_tax_year_config(tax_year)
    for warning in config_warnings:
        print(f"TAX CONFIG WARNING: {warning}")

    # ============================================================================
    # TIER 3: MID-QUARTER CONVENTION DETECTION (IRC §168(d)(3))
    # ============================================================================
    # CRITICAL: If >40% of property placed in service in Q4, must use MQ convention
    # This is one of the most common IRS audit adjustments

    global_convention, mq_details = detect_mid_quarter_convention(df, tax_year, verbose=True)

    # Store mid-quarter test results for later use
    df.attrs["mid_quarter_test"] = mq_details
    df.attrs["global_convention"] = global_convention

    # Apply mid-quarter convention to all assets and add quarter column
    conventions = []
    quarters = []

    for _, row in df.iterrows():
        category = str(row.get("Final Category", ""))
        in_service = row.get("In Service Date")

        # Check if real property (always uses MM)
        is_real = any(x in category for x in ["Residential", "Nonresidential", "Real Property", "Building"])

        if is_real:
            conventions.append("MM")  # Mid-month for real property
            quarters.append(None)  # No quarter needed for MM
        else:
            # Personal property uses global convention (HY or MQ)
            conventions.append(global_convention)

            # If MQ, store which quarter for depreciation calculation
            if global_convention == "MQ" and in_service:
                quarter = get_quarter(in_service)
                quarters.append(quarter)
            else:
                quarters.append(None)

    df["Convention"] = conventions
    df["Quarter"] = quarters  # Used for MQ depreciation calculations

    # Get tax year configuration
    section_179_config = get_section_179_limits(tax_year)
    # Note: bonus_percentage is now calculated per asset based on acquisition/in-service dates
    # to handle OBBB Act 100% bonus eligibility

    # Calculate total Section 179-eligible property cost for phase-out
    # CRITICAL: Only count CURRENT YEAR ADDITIONS (not existing assets)
    total_179_eligible_cost = 0.0
    for _, row in df.iterrows():
        trans_type = str(row.get("Transaction Type", ""))

        # Only current year additions are eligible for Section 179
        if "Current Year Addition" in trans_type:
            cost = float(row.get("Cost") or 0.0)
            is_qip = row.get("qip", False) or "QIP" in str(row.get("Final Category", ""))

            if cost > 0 and not is_qip:
                total_179_eligible_cost += cost

    # Apply IRC §179(b)(2) phase-out
    # Dollar limit is reduced (but not below zero) by the amount by which the cost of
    # section 179 property placed in service exceeds the threshold
    phaseout_reduction = max(0.0, total_179_eligible_cost - section_179_config["phaseout_threshold"])
    section_179_dollar_limit = max(0.0, section_179_config["max_deduction"] - phaseout_reduction)

    # Apply business income limitation
    section_179_effective_limit = min(section_179_dollar_limit, max(float(taxable_income), 0.0))

    section179_amounts = []
    bonus_amounts = []
    bonus_percentages_used = []  # Track which bonus % was applied (for audit trail)
    luxury_auto_notes = []
    ads_flags = []  # Track which assets use ADS
    remaining_179 = section_179_effective_limit

    for _, row in df.iterrows():

        # Skip depreciation for disposals and transfers
        if _is_disposal(row) or _is_transfer(row):
            section179_amounts.append(0.0)
            bonus_amounts.append(0.0)
            bonus_percentages_used.append(0.0)
            luxury_auto_notes.append("")
            ads_flags.append(False)
            continue

        cost = float(row.get("Cost") or 0.0)
        in_service = row.get("In Service Date")
        acquisition = row.get("Acquisition Date")
        is_current = _is_current_year(in_service, tax_year)

        # ============================================================================
        # CRITICAL FIX: Check transaction type for Section 179/Bonus eligibility
        # ============================================================================
        # ONLY "Current Year Addition" assets are eligible for Section 179/Bonus
        # "Existing Asset" (prior year assets) are NOT eligible per IRC §179 and §168(k)
        trans_type = str(row.get("Transaction Type", ""))
        is_current_year_addition = "Current Year Addition" in trans_type

        # ============================================================================
        # TIER 2: ADS (Alternative Depreciation System) Detection
        # ============================================================================
        # CRITICAL: Check if asset requires ADS per IRC §168(g)
        # ADS required for: listed property ≤50% business use, tax-exempt property, etc.

        uses_ads, ads_reason = should_use_ads(row.to_dict())

        # Validate business use for listed property (IRC §280F)
        is_section179_eligible = True
        bonus_eligible = True

        # ============================================================================
        # TIER 3: QIP Section 179 Eligibility (OBBB Act vs Pre-OBBB)
        # ============================================================================
        # CRITICAL TAX COMPLIANCE CHANGE (OBBB Act - July 4, 2025):
        # - Pre-OBBB (before 1/1/2025): QIP NOT eligible for Section 179 per IRC §179(d)(1)
        # - OBBB Act (1/1/2025+): QIP IS eligible for Section 179 (subject to $2.5M limit)
        #
        # NOTE: Buildings, land, and land improvements still NOT eligible

        is_qip = row.get("qip", False) or "QIP" in str(row.get("Final Category", ""))
        final_category = str(row.get("Final Category", ""))

        if is_qip:
            # Check if placed in service after 12/31/2024 (OBBB effective date)
            if in_service and in_service > date(2024, 12, 31):
                # OBBB Act: QIP IS eligible for Section 179
                is_section179_eligible = True
            else:
                # Pre-OBBB: QIP NOT eligible for Section 179
                is_section179_eligible = False

        # Buildings, land improvements, and land are NEVER eligible (even under OBBB)
        if any(x in final_category for x in ["Nonresidential Real Property", "Residential", "Land"]):
            if "Improvement" not in final_category and "QIP" not in final_category:
                is_section179_eligible = False  # Building or land = no Section 179

        # Check listed property business use requirements
        is_section179_eligible, bonus_eligible, business_use_warnings = validate_business_use_for_incentives(
            row.to_dict(),
            allow_section_179=is_section179_eligible,
            allow_bonus=True
        )

        # Calculate bonus percentage for this specific asset
        # OBBB Act: 100% if acquired AND placed in service after 1/19/2025
        # Otherwise: TCJA phase-down (80% for 2024-2025, etc.)
        asset_bonus_pct = get_bonus_percentage(tax_year, acquisition, in_service)

        sec179 = 0.0
        bonus = 0.0
        auto_note = ""

        # ============================================================================
        # TIER 2: ADS Property - NO Section 179, NO Bonus (IRC §168(g))
        # ============================================================================
        if uses_ads:
            # ADS property is NOT eligible for Section 179 or bonus depreciation
            sec179 = 0.0
            bonus = 0.0
            asset_bonus_pct = 0.0

            # Add ADS note
            auto_note = f"ADS REQUIRED: {ads_reason}. No Section 179/bonus allowed per IRC §168(g)"

        # ============================================================================
        # Standard MACRS with Section 179/Bonus (if eligible)
        # ============================================================================
        # CRITICAL: Only apply to CURRENT YEAR ADDITIONS (not existing assets)
        elif cost > 0 and is_current_year_addition:

            if strategy == "Aggressive (179 + Bonus)":
                # Section 179 up to limit (ONLY for eligible property)
                if remaining_179 > 0 and is_section179_eligible:
                    sec179 = min(cost, remaining_179)

                    # ============================================================================
                    # TIER 3: Heavy SUV Special Section 179 Limit (IRC §179(b)(5))
                    # ============================================================================
                    # Heavy SUVs (>6,000 lbs GVWR) are NOT subject to luxury auto caps
                    # BUT have a special reduced Section 179 limit ($28,900 for 2024)
                    if _is_heavy_suv(row):
                        heavy_suv_limit = get_heavy_suv_179_limit(tax_year)
                        if sec179 > heavy_suv_limit:
                            sec179 = heavy_suv_limit
                            if auto_note:
                                auto_note += " | "
                            auto_note = f"Heavy SUV §179 limit applied: ${heavy_suv_limit:,.0f} (IRC §179(b)(5))"

                    remaining_179 -= sec179

                # Bonus for remainder (ONLY if eligible)
                if bonus_eligible:
                    # CRITICAL: Apply asset-specific bonus percentage
                    # OBBB Act: 100% for property acquired AND placed in service after 1/19/2025
                    # TCJA phase-down: 2024-2025: 80%, 2026: 60%, 2027: 40%, 2028: 20%, 2029+: 0%
                    bonus = max(cost - sec179, 0.0) * asset_bonus_pct
                else:
                    bonus = 0.0
                    asset_bonus_pct = 0.0

            elif strategy == "Balanced (Bonus Only)":
                # Apply asset-specific bonus percentage (ONLY if eligible)
                if bonus_eligible:
                    bonus = cost * asset_bonus_pct
                else:
                    bonus = 0.0
                    asset_bonus_pct = 0.0

            elif strategy == "Conservative (MACRS Only)":
                sec179 = 0.0
                bonus = 0.0
                asset_bonus_pct = 0.0  # No bonus in conservative strategy

            # CRITICAL: Apply IRC §280F luxury auto limits (for non-ADS property)
            sec179, bonus, auto_note = _apply_luxury_auto_caps(row, sec179, bonus, tax_year)

        # ============================================================================
        # Compliance Notes
        # ============================================================================

        # Add business use warnings
        for warning in business_use_warnings:
            if auto_note:
                auto_note += " | "
            auto_note += warning

        # Add note if QIP was excluded from Section 179
        if is_qip and cost > 0 and is_current and strategy == "Aggressive (179 + Bonus)" and not uses_ads:
            if auto_note:
                auto_note += " | "
            auto_note += "QIP not eligible for §179 per IRC §179(d)(1)"

        # Add note if OBBB 100% bonus applied
        if asset_bonus_pct == 1.0 and bonus > 0:
            if auto_note:
                auto_note += " | "
            auto_note += f"OBBB Act: 100% bonus (acquired {acquisition}, in-service {in_service})"

        section179_amounts.append(sec179)
        bonus_amounts.append(bonus)
        bonus_percentages_used.append(asset_bonus_pct)
        luxury_auto_notes.append(auto_note)
        ads_flags.append(uses_ads)

    df["Section 179 Amount"] = section179_amounts
    df["Bonus Amount"] = bonus_amounts
    df["Bonus Percentage Used"] = bonus_percentages_used  # Track OBBB vs TCJA bonus %
    df["Uses ADS"] = ads_flags  # Track which assets use Alternative Depreciation System
    df["Auto Limit Notes"] = luxury_auto_notes

    # ============================================================================
    # PHASE 4: MACRS FIRST YEAR DEPRECIATION (IRS Publication 946 Tables)
    # ============================================================================
    # Calculate Year 1 MACRS depreciation using official IRS percentage tables
    # Basis for MACRS = Cost - Section 179 - Bonus Depreciation

    macrs_year1_depreciation = []
    depreciable_basis_list = []

    for idx, row in df.iterrows():
        cost = float(row.get("Cost") or 0.0)
        sec179 = float(row.get("Section 179 Amount") or 0.0)
        bonus = float(row.get("Bonus Amount") or 0.0)

        # Calculate depreciable basis for MACRS
        depreciable_basis = max(cost - sec179 - bonus, 0.0)
        depreciable_basis_list.append(depreciable_basis)

        # Skip MACRS calculation if no depreciable basis
        if depreciable_basis <= 0:
            macrs_year1_depreciation.append(0.0)
            continue

        # Skip for disposals and transfers
        if _is_disposal(row) or _is_transfer(row):
            macrs_year1_depreciation.append(0.0)
            continue

        # Get MACRS parameters
        recovery_period = row.get("Recovery Period")
        method = row.get("Method", "200DB")
        convention = row.get("Convention", "HY")
        quarter = row.get("Quarter")  # For MQ convention
        in_service_date = row.get("In Service Date")

        # Get month for MM convention (real property)
        month = None
        if convention == "MM" and in_service_date:
            if isinstance(in_service_date, date):
                month = in_service_date.month

        # Calculate Year 1 MACRS depreciation using IRS tables
        try:
            macrs_dep_year1 = calculate_macrs_depreciation(
                basis=depreciable_basis,
                recovery_period=recovery_period,
                method=method,
                convention=convention,
                year=1,  # First year
                quarter=quarter,
                month=month
            )
        except Exception as e:
            # Fallback to 0 if calculation fails
            print(f"Warning: MACRS calculation failed for asset {row.get('Asset ID', idx)}: {e}")
            macrs_dep_year1 = 0.0

        macrs_year1_depreciation.append(macrs_dep_year1)

    df["Depreciable Basis"] = depreciable_basis_list
    df["MACRS Year 1 Depreciation"] = macrs_year1_depreciation

    # Print summary of first-year depreciation
    total_sec179 = sum(section179_amounts)
    total_bonus = sum(bonus_amounts)
    total_macrs_year1 = sum(macrs_year1_depreciation)
    total_year1_deduction = total_sec179 + total_bonus + total_macrs_year1

    print("\n" + "=" * 80)
    print(f"YEAR 1 DEPRECIATION SUMMARY - Tax Year {tax_year}")
    print("=" * 80)
    print(f"Section 179 Expensing:        ${total_sec179:>15,.2f}")
    print(f"Bonus Depreciation:           ${total_bonus:>15,.2f}")
    print(f"MACRS Year 1 Depreciation:    ${total_macrs_year1:>15,.2f}")
    print(f"{'─' * 80}")
    print(f"Total Year 1 Deduction:       ${total_year1_deduction:>15,.2f}")
    print("=" * 80 + "\n")

    # ============================================================================
    # PHASE 4: SECTION 179 CARRYFORWARD TRACKING (IRC §179(b)(3))
    # ============================================================================
    # Apply taxable income limitation to Section 179 deduction
    # Any disallowed Section 179 carries forward indefinitely to future years
    #
    # NOTE: In production, carryforward_from_prior_years should come from prior
    # year tax return (Form 4562, Part I, Line 13). For now, we assume 0.

    carryforward_from_prior_years = 0.0  # TODO: Load from prior year data

    if total_sec179 > 0 and taxable_income > 0:
        # Apply income limitation and allocate across assets
        df, sec179_summary = apply_section_179_carryforward_to_dataframe(
            df=df,
            taxable_business_income=taxable_income,
            carryforward_from_prior_years=carryforward_from_prior_years
        )

        # Print Section 179 carryforward report
        sec179_report = generate_section_179_report(sec179_summary)
        print(sec179_report)

        # Store carryforward summary in dataframe metadata for export
        df.attrs["section_179_summary"] = sec179_summary

    elif total_sec179 > 0 and taxable_income <= 0:
        # No taxable income - entire Section 179 must be carried forward
        print("\n" + "=" * 80)
        print("⚠️  CRITICAL: SECTION 179 TAXABLE INCOME LIMITATION")
        print("=" * 80)
        print(f"Section 179 Elected: ${total_sec179:,.2f}")
        print(f"Taxable Business Income: ${taxable_income:,.2f}")
        print("")
        print("ENTIRE Section 179 deduction disallowed due to insufficient taxable income.")
        print(f"Carryforward to next year: ${total_sec179:,.2f}")
        print("")
        print("MUST disclose on Form 4562, Part I, Line 13 of next year's return.")
        print("=" * 80 + "\n")

        # Set all Section 179 to carryforward
        df["Section 179 Allowed"] = 0.0
        df["Section 179 Carryforward"] = df["Section 179 Amount"]

    else:
        # No Section 179 - add empty columns
        df["Section 179 Allowed"] = df["Section 179 Amount"]
        df["Section 179 Carryforward"] = 0.0

    # ============================================================================
    # TIER 2: RECAPTURE CALCULATIONS (IRC §1245 / §1250)
    # ============================================================================
    # Calculate depreciation recapture for disposals

    recapture_1245 = []
    recapture_1250_ordinary = []
    recapture_1250_unrecaptured = []
    recapture_capital_gain = []
    recapture_capital_loss = []
    recapture_adjusted_basis = []

    for idx, row in df.iterrows():
        if not _is_disposal(row):
            # Not a disposal - no recapture
            recapture_1245.append(0.0)
            recapture_1250_ordinary.append(0.0)
            recapture_1250_unrecaptured.append(0.0)
            recapture_capital_gain.append(0.0)
            recapture_capital_loss.append(0.0)
            recapture_adjusted_basis.append(0.0)
            continue

        # Get disposal data
        cost = float(row.get("Cost") or 0.0)
        proceeds = float(row.get("Proceeds") or 0.0)
        final_category = str(row.get("Final Category", ""))

        # Get depreciation taken (for disposed assets, this would come from historical data)
        # For now, we'll estimate based on Section 179/Bonus that would have been taken
        # In production, this should come from prior year data
        accumulated_dep = float(row.get("Accumulated Depreciation") or 0.0)
        sec179_taken = float(row.get("Section 179 Taken (Historical)") or 0.0)
        bonus_taken = float(row.get("Bonus Taken (Historical)") or 0.0)

        # Determine recapture type
        recapture_type = determine_recapture_type(final_category)

        if recapture_type == "none":
            # Land - no depreciation, no recapture
            recapture_1245.append(0.0)
            recapture_1250_ordinary.append(0.0)
            recapture_1250_unrecaptured.append(0.0)
            recapture_capital_gain.append(proceeds - cost if proceeds > cost else 0.0)
            recapture_capital_loss.append(cost - proceeds if cost > proceeds else 0.0)
            recapture_adjusted_basis.append(cost)

        elif recapture_type == "1245":
            # Section 1245 - Personal property
            result = calculate_section_1245_recapture(
                cost=cost,
                accumulated_depreciation=accumulated_dep,
                proceeds=proceeds,
                section_179_taken=sec179_taken,
                bonus_taken=bonus_taken
            )

            recapture_1245.append(result["section_1245_recapture"])
            recapture_1250_ordinary.append(0.0)
            recapture_1250_unrecaptured.append(0.0)
            recapture_capital_gain.append(result["capital_gain"])
            recapture_capital_loss.append(result["capital_loss"])
            recapture_adjusted_basis.append(result["adjusted_basis"])

        elif recapture_type == "1250":
            # Section 1250 - Real property
            result = calculate_section_1250_recapture(
                cost=cost,
                accumulated_depreciation=accumulated_dep,
                proceeds=proceeds,
                accelerated_depreciation=0.0  # Post-1986 real property uses SL only
            )

            recapture_1245.append(0.0)
            recapture_1250_ordinary.append(result["section_1250_recapture"])
            recapture_1250_unrecaptured.append(result["unrecaptured_1250_gain"])
            recapture_capital_gain.append(result["capital_gain"])
            recapture_capital_loss.append(result["capital_loss"])
            recapture_adjusted_basis.append(result["adjusted_basis"])

    # Add recapture columns to dataframe
    df["§1245 Recapture (Ordinary Income)"] = recapture_1245
    df["§1250 Recapture (Ordinary Income)"] = recapture_1250_ordinary
    df["Unrecaptured §1250 Gain (25% rate)"] = recapture_1250_unrecaptured
    df["Capital Gain"] = recapture_capital_gain
    df["Capital Loss"] = recapture_capital_loss
    df["Adjusted Basis at Disposal"] = recapture_adjusted_basis

    # ----------------------------------------------------------------------
    # Build FA CS Export
    # ----------------------------------------------------------------------
    fa = pd.DataFrame()

    fa["Asset ID"] = df["Asset ID"].astype(str)
    fa["Property Description"] = df["Description"].astype(str)
    fa["Date In Service"] = df["In Service Date"]
    fa["Acquisition Date"] = df["Acquisition Date"]
    fa["Cost/Basis"] = df["Cost"]

    # ---------------------------------------------------------
    # Depreciation fields — ONLY for additions
    # ---------------------------------------------------------
    fa["Method"] = df.apply(
        lambda r: r["Method"] if not _is_disposal(r) and not _is_transfer(r) else "",
        axis=1,
    )
    fa["Life"] = df.apply(
        lambda r: r["MACRS Life"] if not _is_disposal(r) and not _is_transfer(r) else "",
        axis=1,
    )
    fa["Convention"] = df.apply(
        lambda r: r["Convention"] if not _is_disposal(r) and not _is_transfer(r) else "",
        axis=1,
    )

    # ============================================================================
    # CRITICAL FIX: Transaction Type from classifier (no more defaulting to "addition")
    # ============================================================================
    # Transaction Type has been properly classified earlier in build_fa()
    # Based on in-service date vs tax year:
    # - "Current Year Addition": In-service date = current tax year
    # - "Existing Asset": In-service date < current tax year
    # - "Disposal": Disposal indicators
    # - "Transfer": Transfer indicators

    # Transaction Type (from classifier - already set)
    fa["Transaction Type"] = df["Transaction Type"]

    # Sheet Role (backward compatibility - map from Transaction Type)
    fa["Sheet Role"] = df["Transaction Type"].apply(
        lambda t: "addition" if "Addition" in t else
                  "disposal" if "Disposal" in t else
                  "transfer" if "Transfer" in t else
                  "existing"  # Existing assets
    )

    # Section 179 & Bonus
    fa["Section 179 Amount"] = df["Section 179 Amount"]
    fa["Bonus Amount"] = df["Bonus Amount"]
    fa["Bonus % Applied"] = df["Bonus Percentage Used"].apply(lambda x: f"{x:.0%}" if x > 0 else "")

    # PHASE 4: MACRS Depreciation
    fa["Depreciable Basis"] = df.get("Depreciable Basis", 0.0)
    fa["MACRS Year 1 Depreciation"] = df.get("MACRS Year 1 Depreciation", 0.0)

    # PHASE 4: Section 179 Carryforward (IRC §179(b)(3))
    fa["Section 179 Allowed"] = df.get("Section 179 Allowed", df.get("Section 179 Amount", 0.0))
    fa["Section 179 Carryforward"] = df.get("Section 179 Carryforward", 0.0)

    # TIER 3: De Minimis Safe Harbor
    fa["De Minimis Expensed"] = df.get("De Minimis Expensed", 0.0)

    # TIER 3: Mid-Quarter Convention Quarter
    fa["Quarter (MQ)"] = df.get("Quarter", None)

    # IRC §280F luxury auto limit notes
    fa["Auto Limit Notes"] = df["Auto Limit Notes"]

    # TIER 2: Recapture columns (for disposals)
    fa["§1245 Recapture (Ordinary Income)"] = df["§1245 Recapture (Ordinary Income)"]
    fa["§1250 Recapture (Ordinary Income)"] = df["§1250 Recapture (Ordinary Income)"]
    fa["Unrecaptured §1250 Gain (25%)"] = df["Unrecaptured §1250 Gain (25% rate)"]
    fa["Capital Gain"] = df["Capital Gain"]
    fa["Capital Loss"] = df["Capital Loss"]
    fa["Adjusted Basis at Disposal"] = df["Adjusted Basis at Disposal"]

    # TIER 2: ADS flag
    fa["Uses ADS"] = df["Uses ADS"]

    # Source tracking
    fa["Source"] = df.get("Source", "")

    # Original Category (client-provided)
    fa["Client Category Original"] = df.get("Client Category Original", df.get("Client Category", ""))

    # Final Computed Category (for additions only)
    fa["Final Category"] = df.apply(
        lambda r: r["Final Category"] if not _is_disposal(r) and not _is_transfer(r) else "",
        axis=1,
    )

    # ===========================================================================
    # EXPORT QUALITY VALIDATION - Fixed Asset CS & RPA Compatibility
    # ===========================================================================
    # Validate export file quality before returning
    # CRITICAL: This ensures the file is ready for Fixed Asset CS import
    # and RPA automation without errors

    is_valid, validation_errors, summary = validate_fixed_asset_cs_export(
        fa, verbose=True
    )

    if not is_valid:
        print("\n⚠️  WARNING: Export validation found CRITICAL/ERROR issues.")
        print("   Review validation report above before proceeding with RPA.")
        print("   Fix critical issues to prevent automation failures.\n")

    return fa


def export_fa_excel(fa_df: pd.DataFrame) -> bytes:
    """Return Excel file bytes."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        fa_df.to_excel(writer, sheet_name="FA_Import", index=False)
    output.seek(0)
    return output.getvalue()


# ==============================================================================
# PHASE 4: MULTI-YEAR DEPRECIATION PROJECTION EXPORT
# ==============================================================================

def export_depreciation_projection(
    fa_df: pd.DataFrame,
    tax_year: int,
    projection_years: int = 10,
    output_path: Optional[str] = None
) -> pd.DataFrame:
    """
    Generate and export multi-year depreciation projection.

    Creates a projection showing year-by-year depreciation for all assets
    over the specified number of years. Useful for tax planning and cashflow forecasting.

    Args:
        fa_df: Fixed asset dataframe from build_fa()
        tax_year: Current tax year
        projection_years: Number of years to project (default 10)
        output_path: Optional path to save Excel file

    Returns:
        DataFrame with depreciation projection summary by year
    """
    from .depreciation_projection import (
        project_portfolio_depreciation,
        export_projection_to_excel,
    )

    # Verify required columns exist
    required_cols = [
        "Depreciable Basis",
        "Recovery Period",
        "Method",
        "Convention",
        "Date In Service"
    ]

    missing = [col for col in required_cols if col not in fa_df.columns]
    if missing:
        raise ValueError(
            f"Cannot generate projection - missing columns: {missing}. "
            "Run build_fa() first to calculate MACRS parameters."
        )

    # Prepare dataframe for projection (rename columns to match projection module)
    projection_df = fa_df.copy()
    projection_df["In Service Date"] = projection_df["Date In Service"]

    # Generate projection summary
    print("\n" + "=" * 80)
    print(f"GENERATING {projection_years}-YEAR DEPRECIATION PROJECTION")
    print("=" * 80)

    summary_df = project_portfolio_depreciation(
        df=projection_df,
        current_tax_year=tax_year,
        projection_years=projection_years
    )

    # Print summary
    print(f"\nProjection Summary ({projection_years} years):")
    print("-" * 80)

    for _, row in summary_df.iterrows():
        year = int(row["Tax Year"])
        total_dep = row["Total Depreciation"]
        count = int(row["Assets Depreciating"])

        print(f"  {year}: ${total_dep:>12,.2f}  ({count} assets)")

    total_all_years = summary_df["Total Depreciation"].sum()
    print("-" * 80)
    print(f"  Total ({projection_years} years): ${total_all_years:>12,.2f}")
    print("=" * 80 + "\n")

    # Export to Excel if path provided
    if output_path:
        export_projection_to_excel(
            df=projection_df,
            current_tax_year=tax_year,
            output_path=output_path,
            projection_years=projection_years
        )

    return summary_df


def generate_comprehensive_depreciation_report(
    fa_df: pd.DataFrame,
    tax_year: int,
    output_dir: str = ".",
    projection_years: int = 10
) -> dict:
    """
    Generate comprehensive depreciation report with all Phase 4 features.

    Creates multiple Excel files:
    1. Fixed Asset Register (standard export)
    2. Multi-Year Depreciation Projection
    3. Section 179 Carryforward Schedule (if applicable)

    Args:
        fa_df: Fixed asset dataframe from build_fa()
        tax_year: Current tax year
        output_dir: Directory to save output files
        projection_years: Number of years to project

    Returns:
        Dict with paths to generated files
    """
    import os
    from .depreciation_projection import export_projection_to_excel
    from .section_179_carryforward import Section179CarryforwardTracker

    output_files = {}

    # 1. Fixed Asset Register
    fa_register_path = os.path.join(output_dir, f"Fixed_Asset_Register_{tax_year}.xlsx")
    fa_bytes = export_fa_excel(fa_df)
    with open(fa_register_path, "wb") as f:
        f.write(fa_bytes)
    output_files["fixed_asset_register"] = fa_register_path
    print(f"✓ Fixed Asset Register saved: {fa_register_path}")

    # 2. Multi-Year Depreciation Projection
    projection_path = os.path.join(output_dir, f"Depreciation_Projection_{tax_year}_{projection_years}yr.xlsx")

    # Prepare dataframe
    projection_df = fa_df.copy()
    projection_df["In Service Date"] = projection_df["Date In Service"]

    export_projection_to_excel(
        df=projection_df,
        current_tax_year=tax_year,
        output_path=projection_path,
        projection_years=projection_years
    )
    output_files["depreciation_projection"] = projection_path

    # 3. Section 179 Carryforward Schedule (if applicable)
    if "Section 179 Carryforward" in fa_df.columns:
        total_carryforward = fa_df["Section 179 Carryforward"].sum()

        if total_carryforward > 0:
            carryforward_path = os.path.join(output_dir, f"Section_179_Carryforward_{tax_year}.xlsx")

            # Create carryforward dataframe
            carryforward_df = fa_df[fa_df["Section 179 Carryforward"] > 0][[
                "Asset ID",
                "Property Description",
                "Date In Service",
                "Cost/Basis",
                "Section 179 Amount",
                "Section 179 Allowed",
                "Section 179 Carryforward"
            ]].copy()

            carryforward_df.to_excel(carryforward_path, index=False, sheet_name="Section 179 Carryforward")
            output_files["section_179_carryforward"] = carryforward_path
            print(f"✓ Section 179 Carryforward Schedule saved: {carryforward_path}")
            print(f"  Total carryforward to {tax_year + 1}: ${total_carryforward:,.2f}")

    print("\n" + "=" * 80)
    print(f"COMPREHENSIVE DEPRECIATION REPORT COMPLETE")
    print("=" * 80)
    print(f"Files generated: {len(output_files)}")
    for report_type, path in output_files.items():
        print(f"  - {report_type}: {path}")
    print("=" * 80 + "\n")

    return output_files
