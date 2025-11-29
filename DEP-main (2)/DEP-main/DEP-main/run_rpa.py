#!/usr/bin/env python3
"""
Standalone RPA Automation Script
Run Fixed Asset CS automation from command line without Streamlit UI
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

# Add fixed_asset_ai to path
sys.path.insert(0, str(Path(__file__).parent / "fixed_asset_ai"))

from logic.ai_rpa_orchestrator import AIRPAOrchestrator
from logic.sheet_loader import build_unified_dataframe
from logic.macrs_classification import load_rules, load_overrides, classify_asset
from logic.sanitizer import sanitize_asset_description

from openai import OpenAI


def classify_assets_cli(df, client_key="DefaultClient"):
    """Classify assets using AI"""
    print(f"🤖 Classifying {len(df)} assets...")

    client = OpenAI()
    rules = load_rules()
    overrides = load_overrides()

    # Add classification columns
    df["Sanitized Description"] = df["description"].apply(
        lambda x: sanitize_asset_description(str(x)) if pd.notna(x) else ""
    )
    df["Final Category"] = ""
    df["MACRS Life"] = ""
    df["Method"] = ""
    df["Convention"] = ""
    df["Source"] = ""
    df["Confidence"] = ""

    for idx, row in df.iterrows():
        try:
            result = classify_asset(
                row,
                client=client,
                model="gpt-4.1-mini",
                rules=rules,
                overrides=overrides,
                strategy="rule_then_gpt",
            )

            df.at[idx, "Final Category"] = result.get("final_class")
            df.at[idx, "MACRS Life"] = result.get("final_life")
            df.at[idx, "Method"] = result.get("final_method")
            df.at[idx, "Convention"] = result.get("final_convention")
            df.at[idx, "Source"] = result.get("source")
            df.at[idx, "Confidence"] = result.get("confidence")

            # Progress indicator
            if (idx + 1) % 10 == 0:
                print(f"  Progress: {idx + 1}/{len(df)} assets classified")

        except Exception as e:
            print(f"  ⚠️  Error classifying row {idx}: {e}")
            df.at[idx, "Source"] = "error"

    print(f"✓ Classification complete")
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Run Fixed Asset CS RPA automation from command line"
    )

    parser.add_argument(
        "excel_file",
        help="Path to Excel file with asset data"
    )

    parser.add_argument(
        "--tax-year",
        type=int,
        default=datetime.now().year,
        help="Tax year (default: current year)"
    )

    parser.add_argument(
        "--strategy",
        choices=["aggressive", "balanced", "conservative"],
        default="balanced",
        help="Tax strategy (default: balanced)"
    )

    parser.add_argument(
        "--taxable-income",
        type=float,
        default=200000,
        help="Taxable income for Section 179 limit (default: 200000)"
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: only process first 3 assets"
    )

    parser.add_argument(
        "--no-rpa",
        action="store_true",
        help="Skip RPA automation (only classify and export)"
    )

    parser.add_argument(
        "--client",
        default="DefaultClient",
        help="Client identifier"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Fixed Asset CS - AI + RPA Automation")
    print("=" * 70)
    print()

    # =========================================================================
    # STEP 1: Load Excel File
    # =========================================================================
    print(f"📂 Loading: {args.excel_file}")

    try:
        excel_path = Path(args.excel_file)
        if not excel_path.exists():
            print(f"❌ Error: File not found: {excel_path}")
            sys.exit(1)

        xls = pd.ExcelFile(excel_path)
        sheets = {name: xls.parse(name, header=None) for name in xls.sheet_names}

        df_raw = build_unified_dataframe(sheets)

        # Rename columns
        df_raw = df_raw.rename(columns={
            "asset_id": "Asset ID",
            "description": "Description",
            "client_category": "Client Category",
            "cost": "Cost",
            "acquisition_date": "Acquisition Date",
            "in_service_date": "In Service Date",
            "location": "Location",
            "transaction_type": "Transaction Type",
        })

        print(f"✓ Loaded {len(df_raw)} assets from {len(sheets)} sheets")
        print()

    except Exception as e:
        print(f"❌ Error loading file: {e}")
        sys.exit(1)

    # =========================================================================
    # STEP 2: AI Classification
    # =========================================================================
    print("🤖 Starting AI Classification")
    print(f"   Tax Year: {args.tax_year}")
    print(f"   Strategy: {args.strategy.title()}")
    print(f"   Taxable Income: ${args.taxable_income:,.2f}")
    print()

    try:
        classified_df = classify_assets_cli(df_raw, client_key=args.client)
        print()
    except Exception as e:
        print(f"❌ Classification error: {e}")
        sys.exit(1)

    # =========================================================================
    # STEP 3: RPA Automation
    # =========================================================================
    if args.no_rpa:
        print("⏭️  Skipping RPA automation (--no-rpa flag)")
        print()
    else:
        print("🤖 Starting RPA Automation")
        print()

        if args.preview:
            print("⚠️  PREVIEW MODE: Processing first 3 assets only")
            print()

        # Map strategy names
        strategy_map = {
            "aggressive": "Aggressive (179 + Bonus)",
            "balanced": "Balanced (Bonus Only)",
            "conservative": "Conservative (MACRS Only)",
        }

        try:
            orchestrator = AIRPAOrchestrator()

            # Check FA CS connection
            print("🔍 Testing Fixed Asset CS connection...")
            success, message = orchestrator.validate_fa_cs_connection()

            if not success:
                print(f"❌ {message}")
                print()
                print("Make sure:")
                print("  1. Fixed Asset CS is running")
                print("  2. Window is visible (not minimized)")
                print("  3. You have the correct FA CS version")
                sys.exit(1)

            print(f"✓ {message}")
            print()

            # Run automation
            print("▶️  Running automation...")
            print()
            print("⚠️  WARNING: Do not touch keyboard or mouse during automation!")
            print()

            input("Press Enter to continue (Ctrl+C to cancel)...")
            print()

            results = orchestrator.run_full_workflow(
                classified_df=classified_df,
                tax_year=args.tax_year,
                strategy=strategy_map[args.strategy],
                taxable_income=args.taxable_income,
                use_acq_if_missing=True,
                preview_mode=args.preview,
                auto_run_rpa=True,
            )

            # Display results
            print()
            print("=" * 70)
            print("RESULTS")
            print("=" * 70)
            print()

            if results.get("success"):
                print("✓ Automation completed successfully!")
                print()

                rpa_stats = results["steps"].get("rpa_automation", {})
                if "statistics" in rpa_stats:
                    stats = rpa_stats["statistics"]
                    print(f"  Processed: {stats.get('processed', 0)}")
                    print(f"  Succeeded: {stats.get('succeeded', 0)}")
                    print(f"  Failed:    {stats.get('failed', 0)}")
                    print()

                    if stats.get("errors"):
                        print("Errors:")
                        for err in stats["errors"]:
                            print(f"  - {err}")
                        print()

                print(f"Duration: {results.get('duration_seconds', 0):.1f} seconds")
                print()
                print(f"Logs saved to: workflow_log_{results['workflow_id']}.json")

            else:
                print(f"❌ Automation failed: {results.get('error', 'Unknown error')}")
                sys.exit(1)

        except KeyboardInterrupt:
            print()
            print("⏸️  Automation cancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"❌ RPA error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
