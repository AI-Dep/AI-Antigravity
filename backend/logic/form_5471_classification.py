"""
Form 5471 Classification Engine

Maps Trial Balance accounts to Form 5471 schedules and line items.

Form 5471 Schedules:
- Schedule C: Income Statement (P&L accounts)
- Schedule E: Income, War Profits, and Excess Profits Taxes
- Schedule F: Balance Sheet (Assets and Liabilities)
- Schedule H: Current Earnings and Profits
- Schedule I: Summary of Shareholder's Income

This module replaces the MACRS classification for 5471 workflows.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class Form5471Schedule(Enum):
    """Form 5471 Schedule Types"""
    SCHEDULE_C = "Sch C"  # Income Statement
    SCHEDULE_E = "Sch E"  # Tax on Income
    SCHEDULE_F = "Sch F"  # Balance Sheet
    SCHEDULE_H = "Sch H"  # Current E&P
    SCHEDULE_I = "Sch I"  # Shareholder Summary
    UNKNOWN = "Unknown"


@dataclass
class Form5471LineMapping:
    """Mapping result for a single account"""
    schedule: str
    line: str
    line_description: str
    confidence: float
    match_reason: str
    account_type: str  # "asset", "liability", "equity", "income", "expense"


# =============================================================================
# FORM 5471 SCHEDULE F - BALANCE SHEET MAPPINGS
# =============================================================================

# Schedule F Line Definitions (Balance Sheet)
SCHEDULE_F_ASSETS = {
    # Current Assets
    "1": {"description": "Cash", "keywords": ["cash", "bank", "banco", "checking", "savings", "money market", "petty cash", "caja"]},
    "2a": {"description": "Trade notes and accounts receivable", "keywords": ["accounts receivable", "a/r", "ar", "trade receivable", "customer receivable", "cuentas por cobrar"]},
    "2b": {"description": "Less allowance for bad debts", "keywords": ["allowance", "bad debt", "doubtful", "provision for bad"]},
    "3": {"description": "Inventories", "keywords": ["inventory", "inventories", "stock", "merchandise", "raw material", "wip", "work in process", "finished goods", "inventario", "existencias"]},
    "4": {"description": "Other current assets", "keywords": ["prepaid", "prepayment", "advance", "deposit", "other current", "deferred expense", "gastos anticipados", "anticipos"]},

    # Non-Current Assets
    "5": {"description": "Loans to shareholders", "keywords": ["loan to shareholder", "shareholder loan", "due from shareholder", "related party receivable", "intercompany receivable"]},
    "6": {"description": "Other investments", "keywords": ["investment", "securities", "marketable", "equity investment", "bond", "inversiones"]},
    "7a": {"description": "Buildings and other depreciable assets", "keywords": ["building", "property", "plant", "equipment", "ppe", "fixed asset", "machinery", "furniture", "vehicle", "computer", "activo fijo", "inmueble", "maquinaria"]},
    "7b": {"description": "Less accumulated depreciation", "keywords": ["accumulated depreciation", "accum depreciation", "depreciation accumulated", "depreciacion acumulada"]},
    "8": {"description": "Depletable assets", "keywords": ["depletion", "mineral", "oil", "gas", "timber", "natural resource"]},
    "9": {"description": "Land", "keywords": ["land", "terreno", "tierra"]},
    "10": {"description": "Intangible assets", "keywords": ["intangible", "goodwill", "patent", "trademark", "copyright", "license", "software", "activo intangible"]},
    "11": {"description": "Other assets", "keywords": ["other asset", "miscellaneous asset", "otros activos", "deferred tax asset"]},
}

SCHEDULE_F_LIABILITIES = {
    # Current Liabilities
    "14": {"description": "Accounts payable", "keywords": ["accounts payable", "a/p", "ap", "trade payable", "supplier payable", "vendor payable", "cuentas por pagar", "proveedores"]},
    "15": {"description": "Other current liabilities", "keywords": ["accrued", "accrual", "other current liab", "withholding", "payroll payable", "tax payable", "vat payable", "iva", "pasivo corriente", "provision"]},
    "16": {"description": "Loans from shareholders", "keywords": ["loan from shareholder", "shareholder loan payable", "due to shareholder", "related party payable", "intercompany payable"]},
    "17": {"description": "Other liabilities", "keywords": ["long term", "long-term", "deferred", "other liab", "lease liability", "pension", "severance", "retirement", "otros pasivos"]},
}

SCHEDULE_F_EQUITY = {
    # Equity section
    "18": {"description": "Capital stock", "keywords": ["capital stock", "common stock", "preferred stock", "share capital", "paid in capital", "capital social", "acciones"]},
    "19": {"description": "Paid-in or capital surplus", "keywords": ["paid-in surplus", "capital surplus", "additional paid", "agio", "prima", "aporte"]},
    "20": {"description": "Retained earnings", "keywords": ["retained earnings", "accumulated earnings", "accumulated profit", "accumulated deficit", "utilidades retenidas", "resultados acumulados"]},
    "21": {"description": "Less cost of treasury stock", "keywords": ["treasury stock", "treasury shares", "acciones en tesoreria"]},
}

# =============================================================================
# FORM 5471 SCHEDULE C - INCOME STATEMENT MAPPINGS
# =============================================================================

SCHEDULE_C_INCOME = {
    "1a": {"description": "Gross receipts or sales", "keywords": ["sales", "revenue", "income", "gross receipts", "ventas", "ingresos"]},
    "1b": {"description": "Less returns and allowances", "keywords": ["return", "allowance", "discount", "rebate", "devoluciones"]},
    "2": {"description": "Cost of goods sold", "keywords": ["cost of goods", "cogs", "cost of sales", "costo de ventas"]},
    "4": {"description": "Dividends", "keywords": ["dividend income", "dividends received", "dividendos"]},
    "5": {"description": "Interest", "keywords": ["interest income", "interest received", "intereses ganados"]},
    "6": {"description": "Gross rents", "keywords": ["rent income", "rental income", "lease income", "arriendo", "alquiler"]},
    "7": {"description": "Gross royalties", "keywords": ["royalty income", "royalties", "regalias"]},
    "8": {"description": "Net gain or loss on sale of capital assets", "keywords": ["gain on sale", "loss on sale", "capital gain", "capital loss", "ganancia", "perdida"]},
    "9": {"description": "Other income", "keywords": ["other income", "miscellaneous income", "otros ingresos"]},
}

SCHEDULE_C_DEDUCTIONS = {
    "11": {"description": "Compensation not deducted elsewhere", "keywords": ["compensation", "salary", "wages", "bonus", "salario", "sueldo", "remuneracion"]},
    "12a": {"description": "Rents", "keywords": ["rent expense", "lease expense", "rental expense", "arriendo", "alquiler"]},
    "12b": {"description": "Royalties", "keywords": ["royalty expense", "royalties paid", "regalias"]},
    "13": {"description": "Interest", "keywords": ["interest expense", "interest paid", "intereses pagados"]},
    "14": {"description": "Depreciation", "keywords": ["depreciation", "amortization", "depreciacion", "amortizacion"]},
    "15": {"description": "Depletion", "keywords": ["depletion expense", "agotamiento"]},
    "16": {"description": "Taxes", "keywords": ["tax expense", "taxes paid", "income tax", "impuestos"]},
    "17": {"description": "Other deductions", "keywords": ["other expense", "general expense", "administrative", "professional fee", "otros gastos", "gastos generales"]},
}

# =============================================================================
# FORM 5471 SCHEDULE E - TAX MAPPINGS
# =============================================================================

SCHEDULE_E_LINES = {
    "1": {"description": "Foreign income taxes paid", "keywords": ["foreign tax", "income tax paid", "impuesto a la renta"]},
    "2": {"description": "Foreign income taxes accrued", "keywords": ["tax accrued", "tax provision", "provision impuesto"]},
}


# =============================================================================
# ACCOUNT NUMBER PATTERN MATCHING
# =============================================================================

# Common Chart of Accounts patterns (account number ranges)
# These are typical for many accounting systems
ACCOUNT_NUMBER_PATTERNS = {
    # Assets (1xxx)
    r"^1[0-2]\d{2}": ("asset", "current_asset"),      # 1000-1299 Current Assets
    r"^1[3-4]\d{2}": ("asset", "fixed_asset"),        # 1300-1499 Fixed Assets
    r"^1[5-9]\d{2}": ("asset", "other_asset"),        # 1500-1999 Other Assets

    # Liabilities (2xxx)
    r"^2[0-2]\d{2}": ("liability", "current_liability"),  # 2000-2299 Current Liabilities
    r"^2[3-9]\d{2}": ("liability", "long_term_liability"), # 2300-2999 Long-term Liabilities

    # Equity (3xxx)
    r"^3\d{3}": ("equity", "equity"),                 # 3000-3999 Equity

    # Revenue (4xxx)
    r"^4\d{3}": ("income", "revenue"),                # 4000-4999 Revenue

    # COGS (5xxx)
    r"^5\d{3}": ("expense", "cogs"),                  # 5000-5999 Cost of Goods Sold

    # Operating Expenses (6xxx-7xxx)
    r"^[67]\d{3}": ("expense", "operating_expense"),  # 6000-7999 Operating Expenses

    # Other Income/Expense (8xxx)
    r"^8\d{3}": ("income", "other_income"),           # 8000-8999 Other Income/Expense

    # Taxes (9xxx)
    r"^9\d{3}": ("expense", "tax_expense"),           # 9000-9999 Taxes
}


# =============================================================================
# CLASSIFICATION ENGINE
# =============================================================================

def _normalize_text(text: str) -> str:
    """Normalize text for matching"""
    if not text:
        return ""
    return str(text).lower().strip()


def _calculate_keyword_score(description: str, keywords: List[str]) -> float:
    """
    Calculate how well a description matches a set of keywords.
    Returns score between 0.0 and 1.0
    """
    if not description or not keywords:
        return 0.0

    desc_lower = _normalize_text(description)
    desc_words = set(desc_lower.split())

    max_score = 0.0

    for keyword in keywords:
        kw_lower = _normalize_text(keyword)

        # Exact match (highest score)
        if kw_lower == desc_lower:
            return 1.0

        # Keyword contained in description
        if kw_lower in desc_lower:
            # Longer keyword matches are more specific
            score = 0.7 + (len(kw_lower) / len(desc_lower)) * 0.3
            max_score = max(max_score, min(score, 0.95))

        # Word-level matching
        kw_words = set(kw_lower.split())
        common_words = desc_words & kw_words
        if common_words:
            score = len(common_words) / max(len(kw_words), len(desc_words)) * 0.8
            max_score = max(max_score, score)

    return max_score


def _classify_by_account_number(account_number: str) -> Optional[Tuple[str, str]]:
    """
    Classify account by its number using standard chart of accounts patterns.

    Returns:
        Tuple of (account_type, sub_type) or None if no match
    """
    if not account_number:
        return None

    # Clean account number
    acct_clean = re.sub(r'[^0-9]', '', str(account_number))

    if not acct_clean:
        return None

    for pattern, (account_type, sub_type) in ACCOUNT_NUMBER_PATTERNS.items():
        if re.match(pattern, acct_clean):
            return (account_type, sub_type)

    return None


def classify_for_5471(
    account_number: Optional[str],
    description: str,
    balance: float = 0.0,
    account_type_hint: Optional[str] = None
) -> Form5471LineMapping:
    """
    Classify a trial balance account for Form 5471 schedules.

    Args:
        account_number: GL account number (e.g., "1100", "121001")
        description: Account description (e.g., "Cash - Operating", "Banco Santiago")
        balance: Account balance (positive = debit, negative = credit for most)
        account_type_hint: Optional hint about account type from source data

    Returns:
        Form5471LineMapping with schedule, line, and confidence
    """
    desc_normalized = _normalize_text(description)

    # Step 1: Try to determine account type from account number
    acct_type_from_number = _classify_by_account_number(account_number)

    # Step 2: Search all line mappings for best match
    best_match = None
    best_score = 0.0

    # Define search order based on account number hint
    if acct_type_from_number:
        acct_type, sub_type = acct_type_from_number

        if acct_type == "asset":
            search_order = [
                (SCHEDULE_F_ASSETS, Form5471Schedule.SCHEDULE_F, "asset"),
            ]
        elif acct_type == "liability":
            search_order = [
                (SCHEDULE_F_LIABILITIES, Form5471Schedule.SCHEDULE_F, "liability"),
            ]
        elif acct_type == "equity":
            search_order = [
                (SCHEDULE_F_EQUITY, Form5471Schedule.SCHEDULE_F, "equity"),
            ]
        elif acct_type == "income":
            search_order = [
                (SCHEDULE_C_INCOME, Form5471Schedule.SCHEDULE_C, "income"),
            ]
        elif acct_type == "expense":
            if sub_type == "tax_expense":
                search_order = [
                    (SCHEDULE_E_LINES, Form5471Schedule.SCHEDULE_E, "expense"),
                    (SCHEDULE_C_DEDUCTIONS, Form5471Schedule.SCHEDULE_C, "expense"),
                ]
            else:
                search_order = [
                    (SCHEDULE_C_DEDUCTIONS, Form5471Schedule.SCHEDULE_C, "expense"),
                ]
        else:
            search_order = []
    else:
        # No account number hint - search all
        search_order = [
            (SCHEDULE_F_ASSETS, Form5471Schedule.SCHEDULE_F, "asset"),
            (SCHEDULE_F_LIABILITIES, Form5471Schedule.SCHEDULE_F, "liability"),
            (SCHEDULE_F_EQUITY, Form5471Schedule.SCHEDULE_F, "equity"),
            (SCHEDULE_C_INCOME, Form5471Schedule.SCHEDULE_C, "income"),
            (SCHEDULE_C_DEDUCTIONS, Form5471Schedule.SCHEDULE_C, "expense"),
            (SCHEDULE_E_LINES, Form5471Schedule.SCHEDULE_E, "expense"),
        ]

    # Search each mapping
    for line_mappings, schedule, acct_type in search_order:
        for line_num, line_info in line_mappings.items():
            score = _calculate_keyword_score(description, line_info["keywords"])

            # Boost score if account number pattern matches
            if acct_type_from_number and acct_type_from_number[0] == acct_type:
                score = min(score + 0.15, 1.0)

            if score > best_score:
                best_score = score
                best_match = Form5471LineMapping(
                    schedule=schedule.value,
                    line=line_num,
                    line_description=line_info["description"],
                    confidence=score,
                    match_reason=f"Matched keywords for {line_info['description']}",
                    account_type=acct_type
                )

    # If no good match found, use fallback based on account number
    if not best_match or best_score < 0.3:
        if acct_type_from_number:
            acct_type, sub_type = acct_type_from_number

            # Default line mappings for unmatched accounts
            fallback_lines = {
                ("asset", "current_asset"): ("4", "Other current assets"),
                ("asset", "fixed_asset"): ("7a", "Buildings and other depreciable assets"),
                ("asset", "other_asset"): ("11", "Other assets"),
                ("liability", "current_liability"): ("15", "Other current liabilities"),
                ("liability", "long_term_liability"): ("17", "Other liabilities"),
                ("equity", "equity"): ("20", "Retained earnings"),
                ("income", "revenue"): ("9", "Other income"),
                ("income", "other_income"): ("9", "Other income"),
                ("expense", "cogs"): ("2", "Cost of goods sold"),
                ("expense", "operating_expense"): ("17", "Other deductions"),
                ("expense", "tax_expense"): ("16", "Taxes"),
            }

            if (acct_type, sub_type) in fallback_lines:
                line_num, line_desc = fallback_lines[(acct_type, sub_type)]
                schedule = Form5471Schedule.SCHEDULE_F if acct_type in ("asset", "liability", "equity") else Form5471Schedule.SCHEDULE_C

                best_match = Form5471LineMapping(
                    schedule=schedule.value,
                    line=line_num,
                    line_description=line_desc,
                    confidence=0.35,  # Low confidence for fallback
                    match_reason=f"Fallback based on account number pattern ({acct_type})",
                    account_type=acct_type
                )

    # Ultimate fallback - unknown
    if not best_match:
        # Try to guess based on description keywords
        if any(kw in desc_normalized for kw in ["asset", "receivable", "inventory", "cash", "equipment"]):
            best_match = Form5471LineMapping(
                schedule=Form5471Schedule.SCHEDULE_F.value,
                line="11",
                line_description="Other assets",
                confidence=0.20,
                match_reason="Low confidence - description suggests asset",
                account_type="asset"
            )
        elif any(kw in desc_normalized for kw in ["payable", "liability", "accrued", "provision"]):
            best_match = Form5471LineMapping(
                schedule=Form5471Schedule.SCHEDULE_F.value,
                line="17",
                line_description="Other liabilities",
                confidence=0.20,
                match_reason="Low confidence - description suggests liability",
                account_type="liability"
            )
        elif any(kw in desc_normalized for kw in ["income", "revenue", "sales", "gain"]):
            best_match = Form5471LineMapping(
                schedule=Form5471Schedule.SCHEDULE_C.value,
                line="9",
                line_description="Other income",
                confidence=0.20,
                match_reason="Low confidence - description suggests income",
                account_type="income"
            )
        elif any(kw in desc_normalized for kw in ["expense", "cost", "loss"]):
            best_match = Form5471LineMapping(
                schedule=Form5471Schedule.SCHEDULE_C.value,
                line="17",
                line_description="Other deductions",
                confidence=0.20,
                match_reason="Low confidence - description suggests expense",
                account_type="expense"
            )
        else:
            best_match = Form5471LineMapping(
                schedule=Form5471Schedule.UNKNOWN.value,
                line="",
                line_description="Unable to classify",
                confidence=0.0,
                match_reason="No matching keywords or account pattern found",
                account_type="unknown"
            )

    return best_match


def classify_trial_balance_batch(
    accounts: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Classify a batch of trial balance accounts for Form 5471.

    Args:
        accounts: List of dicts with keys:
            - account_number (optional)
            - description (required)
            - balance (optional)

    Returns:
        List of dicts with original data plus:
            - schedule
            - line
            - line_description
            - confidence
            - account_type
    """
    results = []

    for account in accounts:
        mapping = classify_for_5471(
            account_number=account.get("account_number") or account.get("account") or account.get("acct"),
            description=account.get("description", ""),
            balance=float(account.get("balance", 0) or 0),
        )

        result = {
            **account,
            "schedule": mapping.schedule,
            "line": mapping.line,
            "line_description": mapping.line_description,
            "confidence": mapping.confidence,
            "account_type": mapping.account_type,
            "classification_reason": mapping.match_reason,
        }
        results.append(result)

    return results


# =============================================================================
# CONFIDENCE THRESHOLDS
# =============================================================================

# Confidence thresholds for auto-approval
HIGH_CONFIDENCE_THRESHOLD = 0.70
LOW_CONFIDENCE_THRESHOLD = 0.40


def get_low_confidence_accounts(
    classified_accounts: List[Dict[str, Any]],
    threshold: float = LOW_CONFIDENCE_THRESHOLD
) -> List[Dict[str, Any]]:
    """Get accounts that need manual review due to low confidence"""
    return [a for a in classified_accounts if a.get("confidence", 0) < threshold]


def get_schedule_summary(
    classified_accounts: List[Dict[str, Any]]
) -> Dict[str, Dict[str, float]]:
    """
    Summarize classified accounts by schedule and line.

    Returns:
        Dict like {"Sch F": {"1": 50000.0, "2a": 30000.0, ...}, ...}
    """
    summary = {}

    for account in classified_accounts:
        schedule = account.get("schedule", "Unknown")
        line = account.get("line", "")
        balance = float(account.get("balance", 0) or 0)

        if schedule not in summary:
            summary[schedule] = {}

        if line not in summary[schedule]:
            summary[schedule][line] = 0.0

        summary[schedule][line] += balance

    return summary
