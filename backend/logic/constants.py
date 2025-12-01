# fixed_asset_ai/logic/constants.py
"""
Centralized Constants Module

This module eliminates magic numbers scattered throughout the codebase.
All configurable thresholds, limits, and defaults should be defined here.

References:
- IRS Publication 946
- IRC Sections 168, 179, 280F
"""

from datetime import date

# ==============================================================================
# DEPRECIATION THRESHOLDS & LIMITS
# ==============================================================================

# Mid-quarter convention threshold (IRC §168(d)(3))
# If >40% of personal property basis is placed in service in Q4,
# mid-quarter convention is REQUIRED
MID_QUARTER_Q4_THRESHOLD = 0.40

# De minimis safe harbor election threshold (IRC §263(a), Reg. 1.263(a)-1(f))
# Taxpayers with audited financial statements: $5,000
# Taxpayers without audited financial statements: $2,500
DE_MINIMIS_WITH_AFS = 5000
DE_MINIMIS_WITHOUT_AFS = 2500

# Small taxpayer safe harbor for repairs (Rev. Proc. 2015-20)
SMALL_TAXPAYER_BUILDING_UBIA_LIMIT = 1_000_000
SMALL_TAXPAYER_REPAIR_LIMIT = 10_000  # Lesser of $10K or 2% of UBIA

# Listed property business use threshold (IRC §280F)
# Below 50% business use = ADS required, no bonus, no 179
LISTED_PROPERTY_BUSINESS_USE_THRESHOLD = 0.50


# ==============================================================================
# AI CLASSIFICATION THRESHOLDS
# ==============================================================================

# GPT confidence threshold for flagging low-confidence classifications
LOW_CONFIDENCE_THRESHOLD = 0.75

# Minimum rule match score to accept a rule-based classification
# Scores typically range from 2.0 (minimum) to 15+ (strong match)
MIN_RULE_SCORE = 2.0

# GPT temperature for consistent results (lower = more deterministic)
GPT_TEMPERATURE = 0.3


# ==============================================================================
# DATA VALIDATION THRESHOLDS
# ==============================================================================

# Tolerance for floating point comparisons (0.01 cents)
# Used to avoid rounding errors in depreciation calculations
FLOAT_TOLERANCE = 0.0001

# Maximum reasonable useful life for any depreciable asset (years)
# Used to detect data errors (e.g., life of 999 years)
MAX_REASONABLE_USEFUL_LIFE = 50

# Maximum reasonable cost for single asset before warning
# (to catch data entry errors like extra zeros)
MAX_SINGLE_ASSET_COST_WARNING = 100_000_000  # $100M

# Minimum cost threshold to flag as potentially material
MATERIALITY_THRESHOLD_DEFAULT = 5000


# ==============================================================================
# DATE VALIDATION
# ==============================================================================

# Earliest reasonable acquisition date (for detecting bad data)
EARLIEST_REASONABLE_DATE = date(1980, 1, 1)

# Maximum years in future for in-service date (for detecting bad data)
MAX_FUTURE_YEARS = 2


# ==============================================================================
# EXCEL/FILE PROCESSING
# ==============================================================================

# Excel serial date base for conversion
EXCEL_SERIAL_DATE_BASE = "1899-12-30"

# Minimum Excel serial date value (anything below is likely not a date)
MIN_EXCEL_SERIAL_DATE = 30000  # ~1982

# Maximum rows to process before warning
MAX_ROWS_WARNING = 10000


# ==============================================================================
# TAX YEAR EFFECTIVE DATES
# ==============================================================================

# TCJA effective date (Tax Cuts and Jobs Act)
TCJA_EFFECTIVE_DATE = date(2017, 12, 22)

# QIP effective date (Qualified Improvement Property - 15 year)
QIP_EFFECTIVE_DATE = date(2018, 1, 1)

# OBBBA effective date for bonus (One Big Beautiful Bill Act)
# Property must be BOTH acquired AND placed in service AFTER this date
OBBBA_BONUS_EFFECTIVE_DATE = date(2025, 1, 19)

# OBBBA effective date for Section 179 increases
# Property placed in service AFTER this date
OBBBA_179_EFFECTIVE_DATE = date(2024, 12, 31)

# Nonresidential real property date cutoff (per IRS Pub 946, Table A-7/A-7a)
# Property placed in service BEFORE May 13, 1993 = 31.5-year (Table A-7a)
# Property placed in service ON OR AFTER May 13, 1993 = 39-year (Table A-7)
NONRESIDENTIAL_31_5_YEAR_CUTOFF = date(1993, 5, 13)


# ==============================================================================
# RECOVERY PERIODS (IRS Publication 946)
# ==============================================================================

# Standard MACRS GDS recovery periods by property type
MACRS_GDS_RECOVERY_PERIODS = {
    "3-year": 3,
    "5-year": 5,
    "7-year": 7,
    "10-year": 10,
    "15-year": 15,
    "20-year": 20,
    "25-year": 25,  # Water utility property
    "27.5-year": 27.5,  # Residential rental
    "31.5-year": 31.5,  # Nonresidential real property (pre-May 13, 1993)
    "39-year": 39,  # Nonresidential real property (post-May 12, 1993)
}

# ADS recovery periods (IRC §168(g))
MACRS_ADS_RECOVERY_PERIODS = {
    "3-year": 4,
    "5-year": 6,
    "7-year": 12,
    "10-year": 16,
    "15-year": 20,
    "20-year": 25,
    "25-year": 35,    # Water utility property under ADS (Pub 946)
    "27.5-year": 30,  # Residential rental under ADS
    "31.5-year": 40,  # Pre-May 1993 nonresidential under ADS
    "39-year": 40,    # Nonresidential under ADS
}


# ==============================================================================
# CONVENTION CODES
# ==============================================================================

# Standard convention codes
CONVENTION_HALF_YEAR = "HY"
CONVENTION_MID_QUARTER = "MQ"
CONVENTION_MID_MONTH = "MM"

# Valid conventions
VALID_CONVENTIONS = [CONVENTION_HALF_YEAR, CONVENTION_MID_QUARTER, CONVENTION_MID_MONTH]


# ==============================================================================
# DEPRECIATION METHODS
# ==============================================================================

# Standard method codes
METHOD_200DB = "200DB"  # 200% Declining Balance
METHOD_150DB = "150DB"  # 150% Declining Balance
METHOD_SL = "SL"        # Straight Line

# Valid methods
VALID_METHODS = [METHOD_200DB, METHOD_150DB, METHOD_SL]


# ==============================================================================
# ERROR MESSAGES
# ==============================================================================

class ErrorMessages:
    """Centralized error messages for consistency."""

    # Data validation errors
    MISSING_COST = "Asset missing required Cost value"
    MISSING_DESCRIPTION = "Asset missing Description"
    MISSING_IN_SERVICE_DATE = "Asset missing In-Service Date"
    NEGATIVE_COST = "Asset has negative cost (data entry error)"
    ACCUM_EXCEEDS_COST = "Accumulated Depreciation exceeds Cost (impossible)"
    FUTURE_IN_SERVICE_DATE = "In-Service Date is in the future"
    DUPLICATE_ASSET_ID = "Duplicate Asset ID detected"
    DATE_CHRONOLOGY_ERROR = "Acquisition Date must be <= In-Service Date <= Disposal Date"

    # Tax calculation warnings
    MID_QUARTER_REQUIRED = "Mid-quarter convention required (>40% Q4 basis)"
    QIP_DATE_WARNING = "QIP classification requires in-service date >= 2018-01-01"
    LISTED_PROPERTY_ADS = "Listed property with ≤50% business use requires ADS"

    # AI classification
    GPT_UNAVAILABLE = "GPT classification unavailable - using fallback rules"
    LOW_CONFIDENCE = "Low confidence classification - review recommended"


# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================

# Log levels
LOG_LEVEL_DEBUG = "DEBUG"
LOG_LEVEL_INFO = "INFO"
LOG_LEVEL_WARNING = "WARNING"
LOG_LEVEL_ERROR = "ERROR"

# Default log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
