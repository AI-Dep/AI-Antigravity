# fixed_asset_ai/logic/accuracy_metrics.py

"""
Upgraded evaluation suite for the MACRS classification engine.
Use this module to benchmark:
- Rule-only accuracy
- GPT-only accuracy
- Hybrid accuracy (Rule -> GPT)
- Error types (class/life/method/convention mismatches)
- Confusion matrices
- Impact of tokenizer vs. raw descriptions
- Performance on noisy / messy descriptions

Input format must contain:
- Description
- True Class
- True Life
- True Method
- True Convention

Optional:
- Client Category
- Cost
- In Service Date
"""

from __future__ import annotations

import pandas as pd
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
import numpy as np
from collections import Counter

from .macrs_classification import classify_asset, load_rules, load_overrides
from .sanitizer import sanitize_description


# ============================================================
# Result structure
# ============================================================

@dataclass
class RowEval:
    pred_class: str
    true_class: str
    class_match: bool

    pred_life: Optional[float]
    true_life: Optional[float]
    life_match: bool

    pred_method: str
    true_method: str
    method_match: bool

    pred_convention: str
    true_convention: str
    convention_match: bool

    source: str
    confidence: float


# ============================================================
# Utilities
# ============================================================

def _norm_str(x):
    return str(x).strip().lower() if isinstance(x, str) else str(x)


def _safe(val):
    return "" if val is None else val


# ============================================================
# Core row evaluation
# ============================================================

def evaluate_single_row(row, strategy="rule_then_gpt") -> RowEval:
    """
    Evaluate a single row with the chosen strategy:
    - rule_only
    - gpt_only
    - rule_then_gpt (hybrid)
    """
    asset = {
        "Description": row.get("Description", ""),
        "Client Category": row.get("Client Category", ""),
        "Cost": row.get("Cost", None),
        "In Service Date": row.get("In Service Date", None),
    }

    true_class = _safe(row.get("True Class"))
    true_life = row.get("True Life")
    true_method = _norm_str(_safe(row.get("True Method")))
    true_convention = _norm_str(_safe(row.get("True Convention")))

    rules = load_rules()
    overrides = load_overrides()

    result = classify_asset(
        asset,
        client=None,
        model="gpt-4.1-mini",
        rules=rules,
        overrides=overrides,
        strategy=strategy,
    )

    pred_class = _safe(result.get("final_class"))
    pred_life = result.get("final_life")
    pred_method = _norm_str(_safe(result.get("final_method")))
    pred_conv = _norm_str(_safe(result.get("final_convention")))

    return RowEval(
        pred_class=pred_class,
        true_class=true_class,
        class_match=(true_class.lower() == pred_class.lower()) if true_class else True,

        pred_life=pred_life,
        true_life=true_life,
        life_match=(true_life == pred_life) if true_life else True,

        pred_method=pred_method,
        true_method=true_method,
        method_match=(true_method == pred_method) if true_method else True,

        pred_convention=pred_conv,
        true_convention=true_convention,
        convention_match=(true_convention == pred_conv) if true_convention else True,

        source=result.get("source", ""),
        confidence=result.get("confidence") or 0.0
    )


# ============================================================
# Evaluation of entire dataset
# ============================================================

def evaluate_dataset(df: pd.DataFrame, strategy="rule_then_gpt") -> pd.DataFrame:
    """
    Evaluate entire dataset and return DataFrame of results.
    """
    evaluations: List[RowEval] = []
    for _, row in df.iterrows():
        evaluations.append(evaluate_single_row(row, strategy=strategy))

    records = [asdict(e) for e in evaluations]
    results_df = pd.DataFrame(records)

    # Composite match column
    results_df["all_match"] = (
        results_df["class_match"]
        & results_df["life_match"]
        & results_df["method_match"]
        & results_df["convention_match"]
    )

    return results_df


# ============================================================
# Summary statistics
# ============================================================

def summarize_results(df: pd.DataFrame) -> pd.DataFrame:
    """
    Produce a high-level accuracy summary.
    """
    summary = {
        "class_accuracy": df["class_match"].mean(),
        "life_accuracy": df["life_match"].mean(),
        "method_accuracy": df["method_match"].mean(),
        "convention_accuracy": df["convention_match"].mean(),
        "full_accuracy": df["all_match"].mean(),
        "rule_percentage": (df["source"] == "rule").mean(),
        "gpt_percentage": (df["source"] == "gpt").mean(),
        "fallback_percentage": (df["source"] == "fallback").mean(),
        "avg_confidence_gpt": df.loc[df["source"] == "gpt", "confidence"].mean(),
    }

    return pd.DataFrame([summary])


# ============================================================
# Confusion matrices for debugging rules
# ============================================================

def confusion_matrix(df: pd.DataFrame, column="class") -> pd.DataFrame:
    """
    Build a simple confusion matrix for class predictions.
    """
    df_small = df[[f"true_{column}", f"pred_{column}"]].copy()
    df_small.columns = ["true", "pred"]
    pivot = pd.crosstab(df_small["true"], df_small["pred"])
    return pivot


# ============================================================
# Noise / stress testing
# ============================================================

def stress_test(df: pd.DataFrame, noise_level=0.20) -> pd.DataFrame:
    """
    Add artificial noise to descriptions:
    - random capitalization
    - inserted typos
    - repeated words
    - punctuation noise
    Useful to measure engine robustness.
    """

    def add_noise(desc: str) -> str:
        if not isinstance(desc, str):
            return desc

        import random

        s = desc

        # 1. Random capitalization
        if random.random() < noise_level:
            s = s.upper()

        # 2. Insert random typos
        if random.random() < noise_level:
            s = s.replace("e", "3").replace("o", "0")

        # 3. Add repeated word
        if random.random() < noise_level:
            parts = s.split()
            if parts:
                s = s + " " + parts[-1]

        # 4. Insert punctuation noise
        if random.random() < noise_level:
            s = "?? " + s + " ##"

        return s

    df_noisy = df.copy()
    df_noisy["Description"] = df_noisy["Description"].apply(add_noise)
    return df_noisy


# ============================================================
# Master runner for Rule-only / GPT-only / Hybrid comparison
# ============================================================

def evaluate_file(path: str) -> Dict[str, pd.DataFrame]:
    """
    Evaluate Rule-only, GPT-only, and Hybrid side-by-side.
    """
    df = pd.read_csv(path)

    # RUN 1 — Rule-only
    print("\n=== RULE-ONLY EVALUATION ===")
    r1 = evaluate_dataset(df, strategy="rule_only")
    s1 = summarize_results(r1)
    print(s1)

    # RUN 2 — GPT-only
    print("\n=== GPT-ONLY EVALUATION ===")
    r2 = evaluate_dataset(df, strategy="gpt_only")
    s2 = summarize_results(r2)
    print(s2)

    # RUN 3 — Hybrid
    print("\n=== HYBRID (Rule → GPT) EVALUATION ===")
    r3 = evaluate_dataset(df, strategy="rule_then_gpt")
    s3 = summarize_results(r3)
    print(s3)

    return {
        "rule_only_results": r1,
        "rule_only_summary": s1,
        "gpt_only_results": r2,
        "gpt_only_summary": s2,
        "hybrid_results": r3,
        "hybrid_summary": s3
    }
