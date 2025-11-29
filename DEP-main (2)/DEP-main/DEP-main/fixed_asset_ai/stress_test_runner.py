# stress_test_runner.py
#
# Batch test loader + classifier against a folder of Excel asset schedules.
# Usage:
#   python stress_test_runner.py /path/to/asset_stress_suite

import sys
import pathlib
import pandas as pd
from openai import OpenAI

from logic.sheet_loader import build_unified_dataframe
from logic.macrs_classification import (
    load_rules,
    load_overrides,
    classify_rule,
    classify_with_gpt,
)


def run_for_file(path: pathlib.Path, client: OpenAI, rules, overrides):
    """
    Return a dict with summary stats for one Excel file.
    """
    record = {
        "file": path.name,
        "load_ok": False,
        "classify_ok": False,
        "rows": 0,
        "num_rule": 0,
        "num_override": 0,
        "num_memory": 0,
        "num_gpt": 0,
        "num_client_category": 0,
        "num_unclassified": 0,
        "num_error_source": 0,
        "num_low_confidence": 0,
        "notes": "",
    }

    # Load + unify
    try:
        xls = pd.ExcelFile(path)
        sheets = {name: xls.parse(name) for name in xls.sheet_names}
        df = build_unified_dataframe(sheets)
        record["load_ok"] = True
        record["rows"] = len(df)
    except Exception as e:
        record["notes"] = f"Load error: {e}"
        return record

    # Classification
    try:
        for _, row in df.iterrows():
            base = classify_rule(row, rules=rules, overrides=overrides)
            if base["source"] in ("override", "rule"):
                final = base
            else:
                final = classify_with_gpt(
                    row,
                    client=client,
                    rules=rules,
                    overrides=overrides,
                    use_fallback_to_client_category=True,
                )

            src = final.get("source")
            low_conf = bool(final.get("low_confidence"))

            if src == "rule":
                record["num_rule"] += 1
            elif src == "override":
                record["num_override"] += 1
            elif src == "memory":
                record["num_memory"] += 1
            elif src == "gpt":
                record["num_gpt"] += 1
            elif src == "client_category":
                record["num_client_category"] += 1
            elif src == "unclassified":
                record["num_unclassified"] += 1
            elif src == "error":
                record["num_error_source"] += 1

            if low_conf:
                record["num_low_confidence"] += 1

        record["classify_ok"] = True
    except Exception as e:
        record["notes"] = f"Classification error: {e}"

    return record


def main():
    if len(sys.argv) < 2:
        print("Usage: python stress_test_runner.py /path/to/asset_stress_suite")
        sys.exit(1)

    folder = pathlib.Path(sys.argv[1]).expanduser().resolve()
    if not folder.exists():
        print(f"Folder not found: {folder}")
        sys.exit(1)

    client = OpenAI()
    rules = load_rules()
    overrides = load_overrides()

    records = []
    for path in sorted(folder.glob("*.xlsx")):
        print(f"Testing {path.name} ...")
        rec = run_for_file(path, client, rules, overrides)
        records.append(rec)

    summary_df = pd.DataFrame(records)
    out_path = folder / "stress_test_results.csv"
    summary_df.to_csv(out_path, index=False)
    print(f"\nDone. Results written to: {out_path}")


if __name__ == "__main__":
    main()
