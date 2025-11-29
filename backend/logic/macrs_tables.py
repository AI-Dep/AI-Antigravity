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

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

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

# 3-Year Property - Mid-Quarter Q1
MACRS_200DB_3Y_MQ_Q1 = [
    0.5833,  # Year 1
    0.3889,  # Year 2
    0.0278,  # Year 3
    0.0000,  # Year 4
]

# 3-Year Property - Mid-Quarter Q2
MACRS_200DB_3Y_MQ_Q2 = [
    0.4167,  # Year 1
    0.4444,  # Year 2
    0.1389,  # Year 3
    0.0000,  # Year 4
]

# 3-Year Property - Mid-Quarter Q3
MACRS_200DB_3Y_MQ_Q3 = [
    0.2500,  # Year 1
    0.5000,  # Year 2
    0.2500,  # Year 3
    0.0000,  # Year 4
]

# 3-Year Property - Mid-Quarter Q4
MACRS_200DB_3Y_MQ_Q4 = [
    0.0833,  # Year 1
    0.5556,  # Year 2
    0.3611,  # Year 3
    0.0000,  # Year 4
]

# 5-Year Property - Mid-Quarter Q1 (Property placed in service in Q1)
# Per IRS Publication 946 Table A-2
MACRS_200DB_5Y_MQ_Q1 = [
    0.3500,  # Year 1 (87.5% of year)
    0.2600,  # Year 2
    0.1560,  # Year 3
    0.1104,  # Year 4
    0.1104,  # Year 5
    0.0132,  # Year 6 (Fixed: was 0.0232, correct is 0.0132 per Pub 946)
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

# 10-Year Property - Mid-Quarter Q1
MACRS_200DB_10Y_MQ_Q1 = [
    0.1750,  # Year 1
    0.1650,  # Year 2
    0.1320,  # Year 3
    0.1056,  # Year 4
    0.0845,  # Year 5
    0.0676,  # Year 6
    0.0597,  # Year 7
    0.0597,  # Year 8
    0.0597,  # Year 9
    0.0597,  # Year 10
    0.0313,  # Year 11
]

# 10-Year Property - Mid-Quarter Q2
MACRS_200DB_10Y_MQ_Q2 = [
    0.1250,  # Year 1
    0.1750,  # Year 2
    0.1400,  # Year 3
    0.1120,  # Year 4
    0.0896,  # Year 5
    0.0717,  # Year 6
    0.0634,  # Year 7
    0.0634,  # Year 8
    0.0634,  # Year 9
    0.0634,  # Year 10
    0.0397,  # Year 11
]

# 10-Year Property - Mid-Quarter Q3
MACRS_200DB_10Y_MQ_Q3 = [
    0.0750,  # Year 1
    0.1850,  # Year 2
    0.1480,  # Year 3
    0.1184,  # Year 4
    0.0947,  # Year 5
    0.0758,  # Year 6
    0.0670,  # Year 7
    0.0670,  # Year 8
    0.0670,  # Year 9
    0.0671,  # Year 10
    0.0480,  # Year 11
]

# 10-Year Property - Mid-Quarter Q4
MACRS_200DB_10Y_MQ_Q4 = [
    0.0250,  # Year 1
    0.1950,  # Year 2
    0.1560,  # Year 3
    0.1248,  # Year 4
    0.0998,  # Year 5
    0.0799,  # Year 6
    0.0706,  # Year 7
    0.0706,  # Year 8
    0.0706,  # Year 9
    0.0707,  # Year 10
    0.0563,  # Year 11
]

# 15-Year Property - Mid-Quarter Q1 (150% DB)
MACRS_150DB_15Y_MQ_Q1 = [
    0.0875,  # Year 1
    0.0938,  # Year 2
    0.0844,  # Year 3
    0.0760,  # Year 4
    0.0683,  # Year 5
    0.0615,  # Year 6
    0.0554,  # Year 7
    0.0554,  # Year 8
    0.0554,  # Year 9
    0.0554,  # Year 10
    0.0554,  # Year 11
    0.0554,  # Year 12
    0.0554,  # Year 13
    0.0554,  # Year 14
    0.0554,  # Year 15
    0.0347,  # Year 16
]

# 15-Year Property - Mid-Quarter Q2 (150% DB)
MACRS_150DB_15Y_MQ_Q2 = [
    0.0625,  # Year 1
    0.0969,  # Year 2
    0.0872,  # Year 3
    0.0785,  # Year 4
    0.0706,  # Year 5
    0.0635,  # Year 6
    0.0572,  # Year 7
    0.0572,  # Year 8
    0.0572,  # Year 9
    0.0572,  # Year 10
    0.0572,  # Year 11
    0.0572,  # Year 12
    0.0572,  # Year 13
    0.0572,  # Year 14
    0.0572,  # Year 15
    0.0417,  # Year 16
]

# 15-Year Property - Mid-Quarter Q3 (150% DB)
MACRS_150DB_15Y_MQ_Q3 = [
    0.0375,  # Year 1
    0.1000,  # Year 2
    0.0900,  # Year 3
    0.0810,  # Year 4
    0.0728,  # Year 5
    0.0656,  # Year 6
    0.0590,  # Year 7
    0.0590,  # Year 8
    0.0591,  # Year 9
    0.0590,  # Year 10
    0.0591,  # Year 11
    0.0590,  # Year 12
    0.0591,  # Year 13
    0.0590,  # Year 14
    0.0591,  # Year 15
    0.0486,  # Year 16
]

# 15-Year Property - Mid-Quarter Q4 (150% DB)
MACRS_150DB_15Y_MQ_Q4 = [
    0.0125,  # Year 1
    0.1031,  # Year 2
    0.0928,  # Year 3
    0.0835,  # Year 4
    0.0751,  # Year 5
    0.0676,  # Year 6
    0.0608,  # Year 7
    0.0608,  # Year 8
    0.0609,  # Year 9
    0.0608,  # Year 10
    0.0609,  # Year 11
    0.0608,  # Year 12
    0.0609,  # Year 13
    0.0608,  # Year 14
    0.0609,  # Year 15
    0.0555,  # Year 16
]

# 20-Year Property - Mid-Quarter Q1 (150% DB)
# Per IRS Publication 946 Table A-5
MACRS_150DB_20Y_MQ_Q1 = [
    0.06563,  # Year 1
    0.07000,  # Year 2
    0.06475,  # Year 3
    0.05990,  # Year 4
    0.05540,  # Year 5
    0.05125,  # Year 6
    0.04741,  # Year 7
    0.04385,  # Year 8
    0.04385,  # Year 9
    0.04386,  # Year 10
    0.04385,  # Year 11
    0.04386,  # Year 12
    0.04385,  # Year 13
    0.04386,  # Year 14
    0.04385,  # Year 15
    0.04386,  # Year 16
    0.04385,  # Year 17
    0.04386,  # Year 18
    0.04385,  # Year 19
    0.04386,  # Year 20
    0.02741,  # Year 21
]

# 20-Year Property - Mid-Quarter Q2 (150% DB)
# Per IRS Publication 946 Table A-5
MACRS_150DB_20Y_MQ_Q2 = [
    0.04688,  # Year 1
    0.07148,  # Year 2
    0.06612,  # Year 3
    0.06116,  # Year 4
    0.05658,  # Year 5
    0.05233,  # Year 6
    0.04841,  # Year 7
    0.04478,  # Year 8
    0.04463,  # Year 9
    0.04463,  # Year 10
    0.04463,  # Year 11
    0.04463,  # Year 12
    0.04463,  # Year 13
    0.04463,  # Year 14
    0.04463,  # Year 15
    0.04463,  # Year 16
    0.04463,  # Year 17
    0.04462,  # Year 18
    0.04463,  # Year 19
    0.04462,  # Year 20
    0.03116,  # Year 21
]

# 20-Year Property - Mid-Quarter Q3 (150% DB)
# Per IRS Publication 946 Table A-5
MACRS_150DB_20Y_MQ_Q3 = [
    0.02813,  # Year 1
    0.07289,  # Year 2
    0.06742,  # Year 3
    0.06237,  # Year 4
    0.05769,  # Year 5
    0.05336,  # Year 6
    0.04936,  # Year 7
    0.04566,  # Year 8
    0.04529,  # Year 9
    0.04529,  # Year 10
    0.04530,  # Year 11
    0.04529,  # Year 12
    0.04530,  # Year 13
    0.04529,  # Year 14
    0.04530,  # Year 15
    0.04529,  # Year 16
    0.04530,  # Year 17
    0.04529,  # Year 18
    0.04530,  # Year 19
    0.04529,  # Year 20
    0.03490,  # Year 21
]

# 20-Year Property - Mid-Quarter Q4 (150% DB)
# Per IRS Publication 946 Table A-5
MACRS_150DB_20Y_MQ_Q4 = [
    0.00938,  # Year 1
    0.07430,  # Year 2
    0.06872,  # Year 3
    0.06357,  # Year 4
    0.05880,  # Year 5
    0.05439,  # Year 6
    0.05031,  # Year 7
    0.04654,  # Year 8
    0.04594,  # Year 9
    0.04594,  # Year 10
    0.04594,  # Year 11
    0.04594,  # Year 12
    0.04594,  # Year 13
    0.04594,  # Year 14
    0.04594,  # Year 15
    0.04594,  # Year 16
    0.04595,  # Year 17
    0.04594,  # Year 18
    0.04595,  # Year 19
    0.04594,  # Year 20
    0.03863,  # Year 21
]

# ==============================================================================
# STRAIGHT LINE - REAL PROPERTY (MID-MONTH CONVENTION)
# ==============================================================================

def get_sl_mm_table(recovery_period: float, month: int) -> List[float]:
    """
    Generate Straight-Line Mid-Month table for real property.

    For 27.5-year residential or 39-year nonresidential property.
    Month = month placed in service (1-12)

    Per IRS Publication 946 Tables A-6 (27.5-year) and A-7a (39-year).

    Args:
        recovery_period: 27.5 or 39 years
        month: Month placed in service (1=Jan, 12=Dec)

    Returns:
        List of depreciation percentages for each year
    """
    # Total months of depreciation
    total_months = recovery_period * 12  # 330 for 27.5yr, 468 for 39yr

    # First year: Mid-month convention
    # Months of depreciation in first year = (12 - month + 1) - 0.5
    # Examples: Jan (month 1) = 11.5 months, Dec (month 12) = 0.5 months
    months_year_1 = (12 - month + 1) - 0.5
    first_year_pct = (months_year_1 / 12) / recovery_period

    # Full years: 1 / recovery_period
    full_year_pct = 1.0 / recovery_period

    # Calculate remaining months after first year
    remaining_months = total_months - months_year_1

    # Number of full 12-month years
    num_full_years = int(remaining_months / 12)

    # Last year: Remainder (not a mirror of first year!)
    # For 27.5yr Jan: remaining = 330 - 11.5 = 318.5, full_years = 26, last = 6.5 months
    months_last_year = remaining_months - (num_full_years * 12)
    last_year_pct = (months_last_year / 12) / recovery_period

    # Build table
    table = [first_year_pct]

    # Add full years
    for _ in range(num_full_years):
        table.append(full_year_pct)

    # Add last year (only if there are remaining months)
    if months_last_year > 0:
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
            if recovery_period == 3:
                if quarter == 1:
                    return MACRS_200DB_3Y_MQ_Q1
                elif quarter == 2:
                    return MACRS_200DB_3Y_MQ_Q2
                elif quarter == 3:
                    return MACRS_200DB_3Y_MQ_Q3
                elif quarter == 4:
                    return MACRS_200DB_3Y_MQ_Q4
            elif recovery_period == 5:
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
            elif recovery_period == 10:
                if quarter == 1:
                    return MACRS_200DB_10Y_MQ_Q1
                elif quarter == 2:
                    return MACRS_200DB_10Y_MQ_Q2
                elif quarter == 3:
                    return MACRS_200DB_10Y_MQ_Q3
                elif quarter == 4:
                    return MACRS_200DB_10Y_MQ_Q4

        if method == "150DB":
            if recovery_period == 15:
                if quarter == 1:
                    return MACRS_150DB_15Y_MQ_Q1
                elif quarter == 2:
                    return MACRS_150DB_15Y_MQ_Q2
                elif quarter == 3:
                    return MACRS_150DB_15Y_MQ_Q3
                elif quarter == 4:
                    return MACRS_150DB_15Y_MQ_Q4
            elif recovery_period == 20:
                if quarter == 1:
                    return MACRS_150DB_20Y_MQ_Q1
                elif quarter == 2:
                    return MACRS_150DB_20Y_MQ_Q2
                elif quarter == 3:
                    return MACRS_150DB_20Y_MQ_Q3
                elif quarter == 4:
                    return MACRS_150DB_20Y_MQ_Q4

    elif convention == "MM":
        if not month or month not in range(1, 13):
            raise ValueError(f"Mid-month convention requires month (1-12), got: {month}")

        if method == "SL":
            if recovery_period == 27.5:
                return get_sl_mm_table(27.5, month)
            elif recovery_period == 39:
                return get_sl_mm_table(39, month)

    # =========================================================================
    # SMART FALLBACK: Handle invalid method/recovery period combinations
    # =========================================================================
    # Per IRS rules:
    # - 3, 5, 7, 10-year property can use 200DB
    # - 15, 20-year property MUST use 150DB (no 200DB tables exist)
    # - 27.5, 39-year property MUST use SL
    #
    # If user specifies 200DB for 15/20-year, auto-correct to 150DB
    # This is more accurate than silently falling back to SL

    if recovery_period in (15, 20) and method == "200DB":
        logger.warning(
            f"MACRS Correction: {recovery_period}-year property cannot use 200DB per IRS rules. "
            f"Using 150DB instead (convention: {convention})."
        )
        # Recursively call with corrected method
        return get_macrs_table(recovery_period, "150DB", convention, quarter, month)

    if recovery_period in (27.5, 39) and method in ("200DB", "150DB"):
        logger.warning(
            f"MACRS Correction: {recovery_period}-year real property must use SL per IRS rules. "
            f"Using SL instead (convention: {convention or 'MM'})."
        )
        # Real property MUST use Mid-Month (MM) convention per IRC §168(d)(2)
        # If month is not provided, default to month 7 (July) as a reasonable midpoint
        # but log a warning since month should always be provided for real property
        if not month:
            logger.error(
                f"CRITICAL: Real property ({recovery_period}Y) requires month parameter for MM convention. "
                f"Defaulting to month 7, but this may be incorrect. Please provide actual in-service month."
            )
            month = 7  # Default to July if not provided
        if recovery_period == 27.5:
            return get_sl_mm_table(27.5, month)
        elif recovery_period == 39:
            return get_sl_mm_table(39, month)

    # Final fallback: generate SL table
    logger.warning(
        f"MACRS Fallback: No exact table for {recovery_period}Y {method} {convention}. "
        f"Using straight-line approximation. Review for accuracy."
    )
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


def calculate_disposal_year_depreciation(
    basis: float,
    recovery_period: int,
    method: str,
    convention: str,
    year_of_recovery: int,
    disposal_quarter: Optional[int] = None,
    disposal_month: Optional[int] = None,
    placed_in_service_quarter: Optional[int] = None,
    placed_in_service_month: Optional[int] = None
) -> float:
    """
    Calculate depreciation for the year of disposal.

    Per IRS Publication 946:
    - HY Convention: Disposal year gets half-year depreciation (same as year 1)
    - MQ Convention: Depreciation based on quarter of disposal
    - MM Convention: Depreciation based on month of disposal

    CRITICAL: The disposal year depreciation is NOT simply half of normal.
    It depends on the convention used AND when the asset was disposed.

    Args:
        basis: Depreciable basis (cost - Section 179 - bonus)
        recovery_period: Recovery period in years
        method: Depreciation method ("200DB", "150DB", "SL")
        convention: Convention ("HY", "MQ", "MM")
        year_of_recovery: Which year of the recovery period (1, 2, 3...)
        disposal_quarter: Quarter of disposal (1-4) for MQ
        disposal_month: Month of disposal (1-12) for MM
        placed_in_service_quarter: Original quarter placed in service (for MQ)
        placed_in_service_month: Original month placed in service (for MM)

    Returns:
        Depreciation amount for disposal year
    """
    if basis <= 0:
        return 0.0

    # Get the FULL year depreciation first
    if convention == "HY":
        full_year_depr = calculate_macrs_depreciation(
            basis, recovery_period, method, convention, year_of_recovery
        )
        # HY Convention: Disposal year = half year regardless of when disposed
        # This is the same treatment as year 1
        return full_year_depr * 0.5

    elif convention == "MQ":
        # MQ Convention: Depreciation depends on quarter of disposal
        # Use the original placed-in-service quarter for table lookup
        full_year_depr = calculate_macrs_depreciation(
            basis, recovery_period, method, convention, year_of_recovery,
            quarter=placed_in_service_quarter
        )

        # Disposal quarter determines fraction per IRS Pub 946, Table A-6a
        # MQ disposal uses midpoint of quarter for calculation:
        # Q1: 1.5 months / 12 = 12.5%
        # Q2: 4.5 months / 12 = 37.5%
        # Q3: 7.5 months / 12 = 62.5%
        # Q4: 10.5 months / 12 = 87.5%
        disposal_fractions = {
            1: 0.125,   # Q1: 1.5 months / 12 months = 12.5%
            2: 0.375,   # Q2: 4.5 months / 12 months = 37.5%
            3: 0.625,   # Q3: 7.5 months / 12 months = 62.5%
            4: 0.875,   # Q4: 10.5 months / 12 months = 87.5%
        }
        fraction = disposal_fractions.get(disposal_quarter, 0.5)
        return full_year_depr * fraction

    elif convention == "MM":
        # MM Convention: Depreciation based on month of disposal
        # Get the monthly rate
        if recovery_period == 27.5:
            monthly_rate = 1 / 27.5 / 12  # Monthly SL rate
        elif recovery_period == 39:
            monthly_rate = 1 / 39 / 12
        else:
            monthly_rate = 1 / recovery_period / 12

        # Disposal month gets half-month convention
        # Months in year = (disposal_month - 0.5)
        months_in_year = disposal_month - 0.5 if disposal_month else 6
        return basis * monthly_rate * months_in_year

    else:
        # Unknown convention - use half year as fallback
        full_year_depr = calculate_macrs_depreciation(
            basis, recovery_period, method, "HY", year_of_recovery
        )
        return full_year_depr * 0.5
