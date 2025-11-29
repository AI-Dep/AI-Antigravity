# fixed_asset_ai/logic/outlier_detector.py

import pandas as pd
import numpy as np


def detect_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect cost-based outliers using IQR method.
    Always returns a DataFrame (never None) to guarantee safety.
    """

    if "Cost" not in df.columns:
        return pd.DataFrame()  # safe empty return

    try:
        cost_series = pd.to_numeric(df["Cost"], errors="coerce")
        q1 = cost_series.quantile(0.25)
        q3 = cost_series.quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        mask = (cost_series < lower) | (cost_series > upper)
        outliers_df = df[mask].copy()

        return outliers_df if not outliers_df.empty else pd.DataFrame()

    except Exception:
        # If something unexpected happens → return empty DataFrame safely
        return pd.DataFrame()
