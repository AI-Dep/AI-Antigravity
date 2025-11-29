# fixed_asset_ai/logic/explanations.py

import pandas as pd
from typing import List


def build_explanation(df: pd.DataFrame) -> str:
    """
    Generates a high-level narrative explaining how classifications
    were determined: rule vs memory vs GPT.
    Always returns a safe string (never errors).
    """

    if df.empty:
        return "No assets were classified."

    total = len(df)

    # Count by source
    source_counts = df["Source"].fillna("unknown").astype(str).value_counts()

    rule_cnt = source_counts.get("rule", 0)
    mem_cnt = source_counts.get("memory", 0)
    gpt_cnt = source_counts.get("gpt", 0)
    err_cnt = source_counts.get("error", 0)
    unk_cnt = source_counts.get("unknown", 0)

    # Confidence statistics
    conf_series = pd.to_numeric(df["Confidence"], errors="coerce")
    avg_conf = round(conf_series.mean(), 3) if conf_series.notna().any() else "N/A"

    # Build narrative
    explanation = []

    explanation.append(f"Total assets classified: {total}")
    explanation.append("")
    explanation.append("Classification Source Breakdown:")
    explanation.append(f" - Rule engine: {rule_cnt}")
    explanation.append(f" - Memory engine: {mem_cnt}")
    explanation.append(f" - GPT model: {gpt_cnt}")
    explanation.append(f" - Errors: {err_cnt}")
    if unk_cnt > 0:
        explanation.append(f" - Unknown source: {unk_cnt}")
    explanation.append("")
    explanation.append(f"Average confidence score: {avg_conf}")
    explanation.append("")

    # Memory similarity insights
    if "memory_match_similarity" in df.columns:
        mem_sims = pd.to_numeric(df["memory_match_similarity"], errors="coerce").dropna()
        if len(mem_sims) > 0:
            explanation.append(
                f"Average memory-match similarity: {round(mem_sims.mean(), 3)}"
            )
            explanation.append(
                f"Highest memory similarity: {round(mem_sims.max(), 3)}"
            )
            explanation.append("")

    # Flag low confidence items
    low_conf = df[df["Confidence"].astype(float) < 0.50] if df["Confidence"].astype(str).str.isnumeric().any() else pd.DataFrame()

    if not low_conf.empty:
        explanation.append(f"Low-confidence items (confidence < 0.50): {len(low_conf)}")
        explanation.append("Consider manually reviewing these items.")
    else:
        explanation.append("No low-confidence items detected.")

    return "\n".join(explanation)
