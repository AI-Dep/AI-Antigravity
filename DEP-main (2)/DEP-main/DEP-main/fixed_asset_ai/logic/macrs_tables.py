"""
MACRS Depreciation Tables (IRS Publication 946)

Official IRS depreciation percentage tables for Modified Accelerated Cost Recovery System (MACRS).
Tables are from IRS Publication 946, Appendix A.

Conventions:
- HY: Half-Year (6 months assumed for first and last year)
- MQ: Mid-Quarter (different tables for Q1, Q2, Q3, Q4)
- MM: Mid-Month (for real property)

Methods:
- 200DB: 200% Declining Balance (5, 7, 10, 15, 20 year property)
- 150DB: 150% Declining Balance (3 year property, some other property)
- SL: Straight Line (real property, ADS property)
"""

from typing import List, Optional

# ==============================================================================
# 200% DECLINING BALANCE - HALF-YEAR CONVENTION
# ==============================================================================

# 3-Year Property (200% DB, HY) - Actually uses 200% DB
MACRS_200DB_3Y_HY = [
    0.3333,  # Year 1
    0.4445,  # Year 2
    0.1481,  # Year 3
    0.0741,  # Year 4
]

# 5-Year Property (200% DB, HY)
MACRS_200DB_5Y_HY = [
    0.2000,  # Year 1
    0.3200,  # Year 2
    0.1920,  # Year 3
    0.1152,  # Year 4
    0.1152,  # Year 5
    0.0576,  # Year 6
]

# 7-Year Property (200% DB, HY)
MACRS_200DB_7Y_HY = [
    0.1429,  # Year 1
    0.2449,  # Year 2
    0.1749,  # Year 3
    0.1249,  # Year 4
    0.0893,  # Year 5
    0.0892,  # Year 6
    0.0893,  # Year 7
    0.0446,  # Year 8
]

# 10-Year Property (200% DB, HY)
MACRS_200DB_10Y_HY = [
    0.1000,  # Year 1
    0.1800,  # Year 2
    0.1440,  # Year 3
    0.1152,  # Year 4
    0.0922,  # Year 5
    0.0737,  # Year 6
    0.0655,  # Year 7
    0.0655,  # Year 8
    0.0656,  # Year 9
    0.0655,  # Year 10
    0.0328,  # Year 11
]

# 15-Year Property (200% DB, HY) -> Actually 150% DB
MACRS_150DB_15Y_HY = [
    0.0500,  # Year 1
    0.0950,  # Year 2
    0.0855,  # Year 3
    0.0770,  # Year 4
    0.0693,  # Year 5
    0.0623,  # Year 6
    0.0590,  # Year 7
    0.0590,  # Year 8
    0.0591,  # Year 9
    0.0590,  # Year 10
    0.0591,  # Year 11
    0.0590,  # Year 12
    0.0591,  # Year 13
    0.0590,  # Year 14
    0.0591,  # Year 15
    0.0295,  # Year 16
]

# 20-Year Property (200% DB, HY) -> Actually 150% DB
MACRS_150DB_20Y_HY = [
    0.03750,  # Year 1
    0.07219,  # Year 2
    0.06677,  # Year 3
    0.06177,  # Year 4
    0.05713,  # Year 5
    0.05285,  # Year 6
    0.04888,  # Year 7
    0.04522,  # Year 8
    0.04462,  # Year 9
    0.04461,  # Year 10
    0.04462,  # Year 11
    0.04461,  # Year 12
    0.04462,  # Year 13
    0.04461,  # Year 14
    0.04462,  # Year 15
    0.04461,  # Year 16
    0.04462,  # Year 17
    0.04461,  # Year 18
    0.04462,  # Year 19
    0.04461,  # Year 20
    0.02231,  # Year 21
]

# ==============================================================================
# 200% DECLINING BALANCE - MID-QUARTER CONVENTION
# ==============================================================================

# 5-Year Property - Mid-Quarter Q1 (Property placed in service in Q1)
MACRS_200DB_5Y_MQ_Q1 = [
    0.3500,  # Year 1 (87.5% of year)
    0.2600,  # Year 2
    0.1560,  # Year 3
    0.1104,  # Year 4
    0.1104,  # Year 5
    0.0232,  # Year 6
]

# 5-Year Property - Mid-Quarter Q2
MACRS_200DB_5Y_MQ_Q2 = [
    0.2500,  # Year 1 (62.5% of year)
    0.3000,  # Year 2
    0.1800,  # Year 3
    0.1080,  # Year 4
    0.1080,  # Year 5
    0.0540,  # Year 6
]

# 5-Year Property - Mid-Quarter Q3
MACRS_200DB_5Y_MQ_Q3 = [
    0.1500,  # Year 1 (37.5% of year)
    0.3400,  # Year 2
    0.2040,  # Year 3
    0.1224,  # Year 4
    0.1130,  # Year 5
    0.0706,  # Year 6
]

# 5-Year Property - Mid-Quarter Q4
MACRS_200DB_5Y_MQ_Q4 = [
    0.0500,  # Year 1 (12.5% of year)
    0.3800,  # Year 2
    0.2280,  # Year 3
    0.1368,  # Year 4
    0.1179,  # Year 5
    0.0873,  # Year 6
]

# 7-Year Property - Mid-Quarter Q1
MACRS_200DB_7Y_MQ_Q1 = [
    0.2500,  # Year 1
    0.2143,  # Year 2
    0.1531,  # Year 3
    0.1094,  # Year 4
    0.0781,  # Year 5
    0.0715,  # Year 6
    0.0715,  # Year 7
    0.0521,  # Year 8
]

# 7-Year Property - Mid-Quarter Q2
MACRS_200DB_7Y_MQ_Q2 = [
    0.1786,  # Year 1
    0.2321,  # Year 2
    0.1658,  # Year 3
    0.1184,  # Year 4
    0.0845,  # Year 5
    0.0772,  # Year 6
    0.0772,  # Year 7
    0.0662,  # Year 8
]

# 7-Year Property - Mid-Quarter Q3
MACRS_200DB_7Y_MQ_Q3 = [
    0.1071,  # Year 1
    0.2500,  # Year 2
    0.1786,  # Year 3
    0.1276,  # Year 4
    0.0911,  # Year 5
    0.0830,  # Year 6
    0.0830,  # Year 7
    0.0796,  # Year 8
]

# 7-Year Property - Mid-Quarter Q4
MACRS_200DB_7Y_MQ_Q4 = [
    0.0357,  # Year 1
    0.2679,  # Year 2
    0.1913,  # Year 3
    0.1367,  # Year 4
    0.0976,  # Year 5
    0.0887,  # Year 6
    0.0887,  # Year 7
    0.0934,  # Year 8
]

# ==============================================================================
# STRAIGHT LINE - REAL PROPERTY (MID-MONTH CONVENTION)
# ==============================================================================

def get_sl_mm_table(recovery_period: float, month: int) -> List[float]:
    """
    Generate Straight-Line Mid-Month table for real property.

    For 27.5-year residential or 39-year nonresidential property.
    Month = month placed in service (1-12)

    Args:
        recovery_period: 27.5 or 39 years
        month: Month placed in service (1=Jan, 12=Dec)

    Returns:
        List of depreciation percentages for each year
    """
    # First year: Mid-month convention
    # Months of depreciation in first year = (12 - month + 1) - 0.5
    # Examples: Jan (month 1) = 11.5 months, Dec (month 12) = 0.5 months

    months_year_1 = (12 - month + 1) - 0.5
    first_year_pct = (months_year_1 / 12) / recovery_period

    # Full years: 1 / recovery_period
    full_year_pct = 1.0 / recovery_period

    # Last year: Remainder
    # Months in last year = 12 - months_year_1 = month - 0.5
    months_last_year = month - 0.5
    last_year_pct = (months_last_year / 12) / recovery_period

    # Build table
    table = [first_year_pct]

    # Add full years
    num_full_years = int(recovery_period)
    for _ in range(num_full_years - 1):
        table.append(full_year_pct)

    # Add last year
    table.append(last_year_pct)

    return table


# Pre-calculated 39-year SL MM tables for common months
MACRS_SL_39Y_MM_JAN = get_sl_mm_table(39, 1)   # January
MACRS_SL_39Y_MM_JUL = get_sl_mm_table(39, 7)   # July
MACRS_SL_39Y_MM_DEC = get_sl_mm_table(39, 12)  # December

# Pre-calculated 27.5-year SL MM tables
MACRS_SL_27_5Y_MM_JAN = get_sl_mm_table(27.5, 1)
MACRS_SL_27_5Y_MM_JUL = get_sl_mm_table(27.5, 7)
MACRS_SL_27_5Y_MM_DEC = get_sl_mm_table(27.5, 12)

# ==============================================================================
# STRAIGHT LINE - PERSONAL PROPERTY (HALF-YEAR CONVENTION)
# ==============================================================================

def get_sl_hy_table(recovery_period: int) -> List[float]:
    """
    Generate Straight-Line Half-Year table.

    Used for personal property electing straight-line or ADS.

    Args:
        recovery_period: Recovery period in years

    Returns:
        List of depreciation percentages
    """
    # First year: Half year
    first_year_pct = 0.5 / recovery_period

    # Full years
    full_year_pct = 1.0 / recovery_period

    # Last year: Half year
    last_year_pct = 0.5 / recovery_period

    # Build table
    table = [first_year_pct]
    for _ in range(recovery_period - 1):
        table.append(full_year_pct)
    table.append(last_year_pct)

    return table


# Pre-calculated SL HY tables for common lives
MACRS_SL_5Y_HY = get_sl_hy_table(5)
MACRS_SL_7Y_HY = get_sl_hy_table(7)
MACRS_SL_12Y_HY = get_sl_hy_table(12)  # ADS for 7-year property
MACRS_SL_39Y_HY = get_sl_hy_table(39)

# ==============================================================================
# TABLE LOOKUP FUNCTION
# ==============================================================================

def get_macrs_table(
    recovery_period: int,
    method: str = "200DB",
    convention: str = "HY",
    quarter: Optional[int] = None,
    month: Optional[int] = None
) -> List[float]:
    """
    Get the appropriate MACRS depreciation table.

    Args:
        recovery_period: Recovery period in years (3, 5, 7, 10, 15, 20, 27.5, 39)
        method: Depreciation method ("200DB", "150DB", "SL")
        convention: Convention ("HY", "MQ", "MM")
        quarter: Quarter if MQ convention (1, 2, 3, 4)
        month: Month if MM convention (1-12)

    Returns:
        List of depreciation percentages for each year
    """
    # Map to table based on parameters
    if convention == "HY":
        if method == "200DB" or method == "DB":
            if recovery_period == 3:
                return MACRS_200DB_3Y_HY
            elif recovery_period == 5:
                return MACRS_200DB_5Y_HY
            elif recovery_period == 7:
                return MACRS_200DB_7Y_HY
            elif recovery_period == 10:
                return MACRS_200DB_10Y_HY

        if method == "150DB":
            if recovery_period == 15:
                return MACRS_150DB_15Y_HY
            elif recovery_period == 20:
                return MACRS_150DB_20Y_HY

        if method == "SL":
            return get_sl_hy_table(recovery_period)

    elif convention == "MQ":
        if not quarter or quarter not in [1, 2, 3, 4]:
            raise ValueError(f"Mid-quarter convention requires quarter (1-4), got: {quarter}")

        if method == "200DB" or method == "DB":
            if recovery_period == 5:
                if quarter == 1:
                    return MACRS_200DB_5Y_MQ_Q1
                elif quarter == 2:
                    return MACRS_200DB_5Y_MQ_Q2
                elif quarter == 3:
                    return MACRS_200DB_5Y_MQ_Q3
                elif quarter == 4:
                    return MACRS_200DB_5Y_MQ_Q4
            elif recovery_period == 7:
                if quarter == 1:
                    return MACRS_200DB_7Y_MQ_Q1
                elif quarter == 2:
                    return MACRS_200DB_7Y_MQ_Q2
                elif quarter == 3:
                    return MACRS_200DB_7Y_MQ_Q3
                elif quarter == 4:
                    return MACRS_200DB_7Y_MQ_Q4

    elif convention == "MM":
        if not month or month not in range(1, 13):
            raise ValueError(f"Mid-month convention requires month (1-12), got: {month}")

        if method == "SL":
            if recovery_period == 27.5:
                return get_sl_mm_table(27.5, month)
            elif recovery_period == 39:
                return get_sl_mm_table(39, month)

    # If no table found, generate SL table as fallback
    print(f"WARNING: No exact table for {recovery_period}Y {method} {convention}. Using SL.")
    return get_sl_hy_table(int(recovery_period))


def calculate_macrs_depreciation(
    basis: float,
    recovery_period: int,
    method: str,
    convention: str,
    year: int,
    quarter: Optional[int] = None,
    month: Optional[int] = None
) -> float:
    """
    Calculate MACRS depreciation for a specific year.

    Args:
        basis: Depreciable basis (cost - Section 179 - bonus)
        recovery_period: Recovery period in years
        method: Depreciation method ("200DB", "150DB", "SL")
        convention: Convention ("HY", "MQ", "MM")
        year: Year number (1, 2, 3, ...)
        quarter: Quarter if MQ (1-4)
        month: Month if MM (1-12)

    Returns:
        Depreciation amount for the specified year
    """
    if basis <= 0:
        return 0.0

    # Get table
    table = get_macrs_table(recovery_period, method, convention, quarter, month)

    # Year is 1-indexed
    if year < 1 or year > len(table):
        return 0.0

    # Get percentage for this year
    percentage = table[year - 1]

    return basis * percentage
