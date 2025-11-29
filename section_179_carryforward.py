"""
Section 179 Carryforward Tracking (IRC §179(b)(3))

Handles the taxable income limitation and carryforward of disallowed Section 179 deductions.

CRITICAL TAX RULE (IRC §179(b)(3)):
Section 179 deduction cannot exceed taxable business income for the year.
Any disallowed amount carries forward INDEFINITELY to future years.

Example:
- 2024: $100k Section 179 elected, but only $60k taxable income
- 2024: $60k deducted, $40k carried forward
- 2025: $40k carryforward + new Section 179 (subject to current year limits)

This is one of the most commonly missed tax compliance issues.
"""

from typing import Dict, List, Optional, Tuple
from datetime import date
import pandas as pd


# ==============================================================================
# TAXABLE INCOME LIMITATION (IRC §179(b)(3))
# ==============================================================================

def calculate_section_179_with_income_limit(
    section_179_elected: float,
    taxable_business_income: float,
    carryforward_from_prior_years: float = 0.0
) -> Dict[str, float]:
    """
    Calculate Section 179 deduction considering taxable income limitation.

    IRC §179(b)(3): Section 179 deduction cannot exceed taxable business income.
    Disallowed amounts carry forward indefinitely.

    Args:
        section_179_elected: Section 179 elected for current year assets
        taxable_business_income: Taxable business income (from Schedule C, 1065, 1120S, etc.)
        carryforward_from_prior_years: Section 179 carryforward from prior years

    Returns:
        Dict with:
        - current_year_deduction: Section 179 deduction allowed in current year
        - carryforward_to_next_year: Amount carried forward to next year
        - total_elected: Total Section 179 elected (current + carryforward)
        - limitation_applied: Whether income limitation was triggered
    """
    # Total Section 179 available = current year + carryforward
    total_section_179_available = section_179_elected + carryforward_from_prior_years

    # Deduction limited to taxable business income
    current_year_deduction = min(total_section_179_available, taxable_business_income)

    # Any excess carries forward
    carryforward_to_next_year = max(total_section_179_available - taxable_business_income, 0.0)

    limitation_applied = carryforward_to_next_year > 0

    return {
        "current_year_deduction": current_year_deduction,
        "carryforward_to_next_year": carryforward_to_next_year,
        "total_elected": total_section_179_available,
        "section_179_elected_this_year": section_179_elected,
        "carryforward_from_prior_years": carryforward_from_prior_years,
        "taxable_business_income": taxable_business_income,
        "limitation_applied": limitation_applied,
    }


# ==============================================================================
# ASSET-LEVEL CARRYFORWARD ALLOCATION
# ==============================================================================

def allocate_section_179_limitation(
    assets: List[Dict],
    taxable_business_income: float,
    carryforward_from_prior_years: float = 0.0
) -> Tuple[List[Dict], float]:
    """
    Allocate Section 179 deduction across assets when income limitation applies.

    When taxable income is insufficient to deduct all Section 179:
    1. Apply carryforward from prior years first (FIFO)
    2. Apply current year Section 179 pro-rata across assets
    3. Calculate per-asset carryforward

    Args:
        assets: List of asset dicts with "Section 179 Elected" amounts
        taxable_business_income: Taxable business income
        carryforward_from_prior_years: Total carryforward from prior years

    Returns:
        Tuple of (updated_assets, total_carryforward_to_next_year)
    """
    # Calculate total Section 179 elected this year
    total_elected_this_year = sum(a.get("Section 179 Elected", 0.0) for a in assets)

    # Total available = current + carryforward
    total_available = total_elected_this_year + carryforward_from_prior_years

    # Check if limitation applies
    if total_available <= taxable_business_income:
        # No limitation - all Section 179 allowed
        for asset in assets:
            asset["Section 179 Allowed"] = asset.get("Section 179 Elected", 0.0)
            asset["Section 179 Carryforward"] = 0.0

        return assets, 0.0

    # Limitation applies - need to allocate
    remaining_income = taxable_business_income

    # Step 1: Apply carryforward from prior years first
    carryforward_used = min(carryforward_from_prior_years, remaining_income)
    remaining_income -= carryforward_used
    carryforward_remaining = carryforward_from_prior_years - carryforward_used

    # Step 2: Allocate remaining income to current year assets (pro-rata)
    if total_elected_this_year > 0 and remaining_income > 0:
        allocation_ratio = min(remaining_income / total_elected_this_year, 1.0)
    else:
        allocation_ratio = 0.0

    # Update each asset
    total_carryforward_this_year = 0.0

    for asset in assets:
        elected = asset.get("Section 179 Elected", 0.0)

        # Allowed = allocated portion of current year Section 179
        allowed = elected * allocation_ratio

        # Carryforward = elected - allowed
        carryforward = elected - allowed

        asset["Section 179 Allowed"] = allowed
        asset["Section 179 Carryforward"] = carryforward

        total_carryforward_this_year += carryforward

    # Total carryforward to next year = prior carryforward remaining + current year carryforward
    total_carryforward_to_next_year = carryforward_remaining + total_carryforward_this_year

    return assets, total_carryforward_to_next_year


# ==============================================================================
# CARRYFORWARD TRACKING ACROSS YEARS
# ==============================================================================

class Section179CarryforwardTracker:
    """
    Track Section 179 carryforwards across multiple tax years.

    Maintains carryforward balance and applies it in future years.
    """

    def __init__(self, initial_carryforward: float = 0.0):
        """
        Initialize tracker.

        Args:
            initial_carryforward: Beginning carryforward balance (from prior tax returns)
        """
        self.carryforward_balance = initial_carryforward
        self.history = []

    def process_year(
        self,
        tax_year: int,
        section_179_elected: float,
        taxable_business_income: float
    ) -> Dict[str, float]:
        """
        Process Section 179 for a tax year, considering carryforward.

        Args:
            tax_year: Tax year
            section_179_elected: Section 179 elected for current year
            taxable_business_income: Taxable business income

        Returns:
            Dict with year results and updated carryforward
        """
        result = calculate_section_179_with_income_limit(
            section_179_elected=section_179_elected,
            taxable_business_income=taxable_business_income,
            carryforward_from_prior_years=self.carryforward_balance
        )

        # Update carryforward balance
        self.carryforward_balance = result["carryforward_to_next_year"]

        # Record history
        self.history.append({
            "tax_year": tax_year,
            **result
        })

        return result

    def get_carryforward_balance(self) -> float:
        """Get current carryforward balance."""
        return self.carryforward_balance

    def get_history(self) -> List[Dict]:
        """Get full history of Section 179 calculations."""
        return self.history

    def generate_carryforward_schedule(self) -> pd.DataFrame:
        """
        Generate carryforward schedule for tax return disclosure.

        Returns DataFrame with:
        - Tax Year
        - Section 179 Elected
        - Carryforward from Prior Years
        - Total Available
        - Current Year Deduction
        - Carryforward to Next Year
        """
        if not self.history:
            return pd.DataFrame()

        df = pd.DataFrame(self.history)

        # Rename columns for clarity
        df = df.rename(columns={
            "current_year_deduction": "Current Year Deduction",
            "carryforward_to_next_year": "Carryforward to Next Year",
            "section_179_elected_this_year": "Section 179 Elected",
            "carryforward_from_prior_years": "Carryforward from Prior Years",
            "total_elected": "Total Available",
            "taxable_business_income": "Taxable Business Income",
        })

        # Select and order columns
        columns = [
            "tax_year",
            "Section 179 Elected",
            "Carryforward from Prior Years",
            "Total Available",
            "Taxable Business Income",
            "Current Year Deduction",
            "Carryforward to Next Year",
        ]

        df = df[[col for col in columns if col in df.columns]]

        return df


# ==============================================================================
# INTEGRATION WITH ASSET DATAFRAME
# ==============================================================================

def apply_section_179_carryforward_to_dataframe(
    df: pd.DataFrame,
    taxable_business_income: float,
    carryforward_from_prior_years: float = 0.0
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Apply Section 179 income limitation to asset dataframe.

    Updates dataframe with:
    - Section 179 Allowed (actual deduction)
    - Section 179 Carryforward (disallowed amount)

    Args:
        df: Asset dataframe with "Section 179" column
        taxable_business_income: Taxable business income
        carryforward_from_prior_years: Carryforward from prior years

    Returns:
        Tuple of (updated_dataframe, summary_dict)
    """
    # Extract assets with Section 179
    assets_with_179 = []

    for idx, row in df.iterrows():
        section_179 = float(row.get("Section 179") or 0.0)

        if section_179 > 0:
            assets_with_179.append({
                "index": idx,
                "Section 179 Elected": section_179,
            })

    # Allocate Section 179 across assets
    if assets_with_179:
        updated_assets, total_carryforward = allocate_section_179_limitation(
            assets_with_179,
            taxable_business_income,
            carryforward_from_prior_years
        )

        # Update dataframe
        section_179_allowed = []
        section_179_carryforward = []

        for idx, row in df.iterrows():
            # Find this asset in updated_assets
            matching_asset = next(
                (a for a in updated_assets if a["index"] == idx),
                None
            )

            if matching_asset:
                allowed = matching_asset["Section 179 Allowed"]
                carryforward = matching_asset["Section 179 Carryforward"]
            else:
                allowed = 0.0
                carryforward = 0.0

            section_179_allowed.append(allowed)
            section_179_carryforward.append(carryforward)

        df["Section 179 Allowed"] = section_179_allowed
        df["Section 179 Carryforward"] = section_179_carryforward

    else:
        # No Section 179 - just handle carryforward passthrough
        df["Section 179 Allowed"] = 0.0
        df["Section 179 Carryforward"] = 0.0
        total_carryforward = carryforward_from_prior_years

    # Calculate summary
    total_elected = df["Section 179"].sum() if "Section 179" in df.columns else 0.0
    total_allowed = df["Section 179 Allowed"].sum()

    summary = {
        "section_179_elected": total_elected,
        "carryforward_from_prior_years": carryforward_from_prior_years,
        "total_available": total_elected + carryforward_from_prior_years,
        "taxable_business_income": taxable_business_income,
        "section_179_allowed": total_allowed,
        "carryforward_to_next_year": total_carryforward,
        "limitation_applied": total_carryforward > 0,
    }

    return df, summary


# ==============================================================================
# REPORTING AND VALIDATION
# ==============================================================================

def generate_section_179_report(summary: Dict[str, float]) -> str:
    """
    Generate Section 179 report with carryforward disclosure.

    Args:
        summary: Summary dict from apply_section_179_carryforward_to_dataframe()

    Returns:
        Formatted report string
    """
    report = []
    report.append("=" * 80)
    report.append("SECTION 179 DEDUCTION SUMMARY (IRC §179)")
    report.append("=" * 80)
    report.append("")

    report.append(f"Section 179 Elected (Current Year):    ${summary['section_179_elected']:>15,.2f}")
    report.append(f"Carryforward from Prior Years:         ${summary['carryforward_from_prior_years']:>15,.2f}")
    report.append(f"{'─' * 80}")
    report.append(f"Total Section 179 Available:           ${summary['total_available']:>15,.2f}")
    report.append("")

    report.append(f"Taxable Business Income (Limitation):  ${summary['taxable_business_income']:>15,.2f}")
    report.append("")

    report.append(f"Section 179 Deduction Allowed:         ${summary['section_179_allowed']:>15,.2f}")
    report.append(f"Carryforward to Next Year:             ${summary['carryforward_to_next_year']:>15,.2f}")
    report.append("")

    if summary["limitation_applied"]:
        report.append("⚠️  TAXABLE INCOME LIMITATION APPLIED")
        report.append("")
        report.append("CRITICAL: Section 179 deduction was limited by taxable business income.")
        report.append(f"Carryforward of ${summary['carryforward_to_next_year']:,.2f} must be tracked")
        report.append("and disclosed on next year's tax return (Form 4562, Part I, Line 13).")
    else:
        report.append("✓ No income limitation - all Section 179 deducted in current year")

    report.append("")
    report.append("=" * 80)

    return "\n".join(report)


def validate_section_179_carryforward(
    df: pd.DataFrame,
    verbose: bool = True
) -> Tuple[bool, List[str]]:
    """
    Validate Section 179 carryforward calculations.

    Args:
        df: Asset dataframe with Section 179 columns
        verbose: Print validation results

    Returns:
        Tuple of (is_valid, warnings)
    """
    warnings = []

    # Check if carryforward columns exist
    if "Section 179 Allowed" not in df.columns:
        warnings.append("Missing 'Section 179 Allowed' column")
        return False, warnings

    # Validate: Allowed ≤ Elected
    if "Section 179" in df.columns:
        for idx, row in df.iterrows():
            elected = float(row.get("Section 179") or 0.0)
            allowed = float(row.get("Section 179 Allowed") or 0.0)

            if allowed > elected + 0.01:  # Allow 1 cent rounding
                warnings.append(
                    f"Asset {row.get('Asset ID', idx)}: "
                    f"Section 179 Allowed (${allowed:,.2f}) exceeds Elected (${elected:,.2f})"
                )

    # Validate: Carryforward = Elected - Allowed
    if "Section 179 Carryforward" in df.columns:
        for idx, row in df.iterrows():
            elected = float(row.get("Section 179") or 0.0)
            allowed = float(row.get("Section 179 Allowed") or 0.0)
            carryforward = float(row.get("Section 179 Carryforward") or 0.0)

            expected_carryforward = elected - allowed

            if abs(carryforward - expected_carryforward) > 0.01:
                warnings.append(
                    f"Asset {row.get('Asset ID', idx)}: "
                    f"Carryforward mismatch. Expected ${expected_carryforward:,.2f}, "
                    f"got ${carryforward:,.2f}"
                )

    is_valid = len(warnings) == 0

    if verbose:
        if is_valid:
            print("✓ Section 179 carryforward validation PASSED")
        else:
            print("✗ Section 179 carryforward validation FAILED")
            for warning in warnings:
                print(f"  - {warning}")

    return is_valid, warnings
