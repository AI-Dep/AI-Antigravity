# fixed_asset_ai/logic/outlier_detector.py

import pandas as pd
import numpy as np
from typing import Optional


def detect_outliers(
    df: pd.DataFrame,
    additions_only: bool = True,
    transaction_type_col: str = "Transaction Type"
) -> pd.DataFrame:
    """
    Detect cost-based outliers using IQR method.
    Always returns a DataFrame (never None) to guarantee safety.

    Args:
        df: DataFrame with asset data
        additions_only: If True, only analyze Current Year Additions (recommended).
                       If False, analyze all assets.
        transaction_type_col: Column name containing transaction type

    Returns:
        DataFrame of outlier assets with 'reason' column added

    Why additions_only=True is recommended:
    - Existing assets were validated in prior tax years
    - New data (additions) is where errors most likely occur
    - Comparing new equipment to old buildings isn't statistically meaningful
    - Reduces noise and makes results more actionable
    """

    if df is None or df.empty:
        return pd.DataFrame()

    if "Cost" not in df.columns:
        return pd.DataFrame()

    try:
        # Filter to additions only if requested
        if additions_only and transaction_type_col in df.columns:
            trans_type = df[transaction_type_col].astype(str)
            is_addition = trans_type.str.contains("Current Year Addition", case=False, na=False)
            analysis_df = df[is_addition].copy()

            if analysis_df.empty:
                return pd.DataFrame()
        else:
            analysis_df = df.copy()

        cost_series = pd.to_numeric(analysis_df["Cost"], errors="coerce")

        # Need at least 4 data points for meaningful IQR analysis
        valid_costs = cost_series.dropna()
        if len(valid_costs) < 4:
            return pd.DataFrame()

        q1 = cost_series.quantile(0.25)
        q3 = cost_series.quantile(0.75)
        iqr = q3 - q1

        # Handle case where IQR is 0 or very small (all same values or minimal variation)
        # Use epsilon comparison for floating-point safety
        if abs(iqr) < 1e-10:
            return pd.DataFrame()

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        # Find outliers
        is_low_outlier = cost_series < lower
        is_high_outlier = cost_series > upper
        mask = is_low_outlier | is_high_outlier

        outliers_df = analysis_df[mask].copy()

        if outliers_df.empty:
            return pd.DataFrame()

        # Add reason column for clarity
        outliers_df["reason"] = outliers_df.apply(
            lambda row: _get_outlier_reason(row, lower, upper, q1, q3),
            axis=1
        )

        # Add Asset ID column if available for better identification
        if "Asset ID" not in outliers_df.columns and "Asset #" in outliers_df.columns:
            outliers_df["Asset ID"] = outliers_df["Asset #"]

        return outliers_df

    except Exception:
        # If something unexpected happens → return empty DataFrame safely
        return pd.DataFrame()


def _get_outlier_reason(row, lower: float, upper: float, q1: float, q3: float) -> str:
    """Generate human-readable reason for outlier flag."""
    try:
        cost = float(row.get("Cost", 0))

        if cost < lower:
            return f"Unusually low cost (${cost:,.0f}) - below ${lower:,.0f} threshold"
        elif cost > upper:
            return f"Unusually high cost (${cost:,.0f}) - above ${upper:,.0f} threshold"
        else:
            return "Statistical outlier detected"
    except Exception:
        return "Statistical outlier detected"


def get_outlier_summary(df: pd.DataFrame, additions_only: bool = True) -> dict:
    """
    Get summary statistics about outliers for display.

    Returns dict with:
    - outlier_count: Number of outliers found
    - total_analyzed: Total assets analyzed
    - scope: "additions" or "all"
    - thresholds: Lower and upper bounds used
    """
    if df is None or df.empty or "Cost" not in df.columns:
        return {
            "outlier_count": 0,
            "total_analyzed": 0,
            "scope": "additions" if additions_only else "all",
            "thresholds": {"lower": 0, "upper": 0}
        }

    try:
        # Filter if needed
        if additions_only and "Transaction Type" in df.columns:
            trans_type = df["Transaction Type"].astype(str)
            is_addition = trans_type.str.contains("Current Year Addition", case=False, na=False)
            analysis_df = df[is_addition]
        else:
            analysis_df = df

        cost_series = pd.to_numeric(analysis_df["Cost"], errors="coerce").dropna()

        if len(cost_series) < 4:
            return {
                "outlier_count": 0,
                "total_analyzed": len(analysis_df),
                "scope": "additions" if additions_only else "all",
                "thresholds": {"lower": 0, "upper": 0},
                "note": "Insufficient data for outlier analysis (need 4+ assets)"
            }

        q1 = cost_series.quantile(0.25)
        q3 = cost_series.quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outlier_count = ((cost_series < lower) | (cost_series > upper)).sum()

        return {
            "outlier_count": int(outlier_count),
            "total_analyzed": len(analysis_df),
            "scope": "additions" if additions_only else "all",
            "thresholds": {
                "lower": float(lower),
                "upper": float(upper)
            }
        }

    except Exception:
        return {
            "outlier_count": 0,
            "total_analyzed": 0,
            "scope": "additions" if additions_only else "all",
            "thresholds": {"lower": 0, "upper": 0}
        }
