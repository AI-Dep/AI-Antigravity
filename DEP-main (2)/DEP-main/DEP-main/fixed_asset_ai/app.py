# fixed_asset_ai/app.py
# Version: 2025-01-19.3 - FORCE REDEPLOY: Pandas NA fixes in data_validator + transaction classifier acquisition date fallback
# CRITICAL: This version includes pandas NA handling fixes that prevent TypeError during export

import streamlit as st
import pandas as pd
from datetime import datetime
import traceback

# =====================================================================
# DEBUG IMPORT BLOCK (CRITICAL)
# Shows real errors inside macrs_classification.py
# =====================================================================

try:
    from logic.sheet_loader import build_unified_dataframe, analyze_excel_structure
    from logic.macrs_classification import (
        load_rules,
        load_overrides,
        save_overrides,
        classify_asset,
    )
    from logic.transaction_classifier import (
        classify_all_transactions,
        validate_transaction_classification,
    )
    from logic.fa_export import export_fa_excel, build_fa
    from logic.human_approval_workflow import (
        checkpoint_1_quality_review,
        checkpoint_2_tax_review,
        checkpoint_3_pre_rpa_checklist,
        final_approval_and_signoff,
        save_approval_record,
        ApprovalStatus
    )
except Exception as e:
    st.error("IMPORT ERROR in macrs_classification.py or related modules")
    st.code(traceback.format_exc())
    st.stop()


from logic.validators import validate_assets
from logic.advanced_validations import advanced_validations
from logic.outlier_detector import detect_outliers
from logic.explanations import build_explanation
from logic.sanitizer import sanitize_asset_description

# RPA imports - optional (only work on Windows with FA CS)
RPA_AVAILABLE = False
try:
    from logic.ai_rpa_orchestrator import AIRPAOrchestrator
    from logic.rpa_fa_cs import test_fa_cs_connection
    RPA_AVAILABLE = True
except Exception:
    # RPA libraries not available or failed to load (e.g., on Streamlit Cloud/Linux)
    # This catches ImportError, KeyError (DISPLAY), and any other RPA-related errors
    AIRPAOrchestrator = None
    test_fa_cs_connection = None


# =====================================================================
# STREAMLIT CONFIG
# =====================================================================

st.set_page_config(
    page_title="AI Fixed Asset Automation",
    layout="wide",
)

st.title("AI-Based Fixed Asset Classification Tool")

# =====================================================================
# OPENAI CLIENT
# =====================================================================

from openai import OpenAI

@st.cache_resource
def get_openai_client():
    try:
        return OpenAI()
    except Exception as e:
        st.error("OpenAI Client Initialization FAILED:")
        st.code(str(e))
        return None

client = get_openai_client()
if client is None:
    st.stop()


# =====================================================================
# SAFE HELPERS
# =====================================================================

def safe_desc(row):
    if "description" in row and pd.notna(row["description"]):
        return sanitize_asset_description(str(row["description"]))
    return ""

def safe_cat(row):
    if "client_category" in row and pd.notna(row["client_category"]):
        return str(row["client_category"])
    return ""


# =====================================================================
# STEP 1 — Upload
# =====================================================================

uploaded = st.file_uploader(
    "Upload client's asset schedule (Excel)", type=["xlsx", "xls"]
)

if not uploaded:
    st.info("Please upload an Excel file to begin.")
    st.stop()


# =====================================================================
# STEP 1 — Load & Parse
# =====================================================================

st.subheader("Step 1 — Loading & Parsing File")

try:
    xls = pd.ExcelFile(uploaded)
    xls = pd.ExcelFile(uploaded)
    sheets = {name: xls.parse(name, header=None) for name in xls.sheet_names}

    # =====================================================================
    # STEP 1.5 — Column Mapping Review (NEW)
    # =====================================================================
    st.subheader("Step 1.5 — Column Mapping Review")
    st.info("Verify that Excel columns are correctly mapped to system fields.")

    if "column_overrides" not in st.session_state:
        st.session_state["column_overrides"] = {}

    # Analyze structure
    analysis_results = analyze_excel_structure(sheets)
    
    # Container for overrides
    current_overrides = st.session_state["column_overrides"]
    
    for sheet_name, analysis in analysis_results.items():
        with st.expander(f"Sheet: {sheet_name} (Role: {analysis.sheet_role})", expanded=False):
            st.write(f"**Header Row:** {analysis.header_row}")
            
            # Show warnings
            if analysis.warnings:
                for w in analysis.warnings:
                    st.warning(w)
            
            # Column Mapping Editor
            cols = st.columns(3)
            
            # Critical Fields
            with cols[0]:
                st.markdown("#### Critical Fields")
                for field in ["asset_id", "description"]:
                    current_val = analysis.detected_columns.get(field, "")
                    # Check if overridden
                    if sheet_name in current_overrides and field in current_overrides[sheet_name]:
                        current_val = current_overrides[sheet_name][field]
                        
                    new_val = st.selectbox(
                        f"{field}", 
                        options=[""] + analysis.all_columns,
                        index=analysis.all_columns.index(current_val) + 1 if current_val in analysis.all_columns else 0,
                        key=f"map_{sheet_name}_{field}"
                    )
                    
                    if new_val != current_val:
                        if sheet_name not in current_overrides:
                            current_overrides[sheet_name] = {}
                        current_overrides[sheet_name][field] = new_val
                        st.rerun()

            # Important Fields
            with cols[1]:
                st.markdown("#### Financial Fields")
                for field in ["cost", "acquisition_date", "in_service_date"]:
                    current_val = analysis.detected_columns.get(field, "")
                    if sheet_name in current_overrides and field in current_overrides[sheet_name]:
                        current_val = current_overrides[sheet_name][field]
                        
                    new_val = st.selectbox(
                        f"{field}", 
                        options=[""] + analysis.all_columns,
                        index=analysis.all_columns.index(current_val) + 1 if current_val in analysis.all_columns else 0,
                        key=f"map_{sheet_name}_{field}"
                    )
                    
                    if new_val != current_val:
                        if sheet_name not in current_overrides:
                            current_overrides[sheet_name] = {}
                        current_overrides[sheet_name][field] = new_val
                        st.rerun()

            # Other Fields
            with cols[2]:
                st.markdown("#### Other Fields")
                for field in ["category", "location", "department"]:
                    current_val = analysis.detected_columns.get(field, "")
                    if sheet_name in current_overrides and field in current_overrides[sheet_name]:
                        current_val = current_overrides[sheet_name][field]
                        
                    new_val = st.selectbox(
                        f"{field}", 
                        options=[""] + analysis.all_columns,
                        index=analysis.all_columns.index(current_val) + 1 if current_val in analysis.all_columns else 0,
                        key=f"map_{sheet_name}_{field}"
                    )
                    
                    if new_val != current_val:
                        if sheet_name not in current_overrides:
                            current_overrides[sheet_name] = {}
                        current_overrides[sheet_name][field] = new_val
                        st.rerun()

    # Build unified dataframe with overrides
    df_raw = build_unified_dataframe(sheets, column_mapping_overrides=current_overrides)
    st.write("DEBUG COLUMNS:", df_raw.columns.tolist())

    df_raw = df_raw.rename(columns={
        "asset_id": "Asset ID",
        "description": "Description",
        "client_category": "Client Category",
        "cost": "Cost",
        "acquisition_date": "Acquisition Date",
        "in_service_date": "In Service Date",
        "location": "Location",
        "sheet_role": "Sheet Role",
        "transaction_type": "Transaction Type",
    })

    st.success("File successfully loaded.")
    st.write(df_raw.head())

except Exception as e:
    st.error("Error parsing the file:")
    st.code(traceback.format_exc())
    st.stop()


# =====================================================================
# STEP 2 — Client Identifier
# =====================================================================

st.subheader("Step 2 — Specify Client Identifier")

client_key = st.text_input("Enter client identifier", value="DefaultClient")

if not client_key:
    st.warning("Client identifier required.")
    st.stop()


# =====================================================================
# STEP 3 — Tax Year Settings
# =====================================================================

st.subheader("Step 3 — Tax Year Settings")

col1, col2 = st.columns(2)

with col1:
    tax_year = st.number_input("Enter tax year:", value=datetime.now().year, step=1)

with col2:
    use_acq_if_missing = st.checkbox(
        "Use Acquisition Date when In-Service Date is missing", value=True
    )


# =====================================================================
# STEP 3.5 — Tax Strategy
# =====================================================================

st.subheader("Step 3.5 — Tax Strategy")

strategy = st.selectbox(
    "Select Tax Strategy:",
    [
        "Aggressive (179 + Bonus)",
        "Balanced (Bonus Only)",
        "Conservative (MACRS Only)",
    ],
)

taxable_income = st.number_input(
    "Expected Taxable Income (for §179 limitation):",
    value=200000,
    step=10000,
)


# =====================================================================
# STEP 4 — RUN CLASSIFICATION
# =====================================================================

st.subheader("Step 4 — Classification")

if st.button("Run Full Classification", type="primary"):

    with st.spinner("Classifying assets…"):

        df = df_raw.copy()

        df["Sanitized Description"] = df.apply(lambda r: safe_desc(r), axis=1)
        df["Client Category Original"] = df.apply(lambda r: safe_cat(r), axis=1)

        df["Final Category"] = ""
        df["MACRS Life"] = ""
        df["Method"] = ""
        df["Convention"] = ""
        df["Source"] = ""
        df["Confidence"] = ""
        df["Low Confidence"] = False
        df["Notes"] = ""

        rules = load_rules()
        overrides = load_overrides()

        # DEBUG: show number of rules loaded
        if st.session_state.get("_rules_debug_printed") is None:
            st.write(f"DEBUG: Loaded {len(rules.get('rules', []))} rules from rules.json")
            st.session_state["_rules_debug_printed"] = True

        # Track classification statistics
        additions_classified = 0
        disposals_skipped = 0
        transfers_skipped = 0

        for idx, row in df.iterrows():

            # ===================================================================
            # CRITICAL FIX: Skip classification for disposals and transfers
            # ===================================================================
            # Disposals and transfers don't need new MACRS classification
            # - Disposals: Already depreciated, need recapture calculation (not new classification)
            # - Transfers: Already classified when added, just moving location
            #
            # Only ADDITIONS need classification for depreciation purposes

            sheet_role = str(row.get("Sheet Role", "")).lower()
            trans_type = str(row.get("Transaction Type", "")).lower()

            is_disposal = any(x in sheet_role for x in ["dispos", "disposal"]) or \
                          any(x in trans_type for x in ["dispos", "disposal"])
            is_transfer = any(x in sheet_role for x in ["transfer", "xfer", "reclass"]) or \
                          any(x in trans_type for x in ["transfer", "xfer", "reclass"])

            if is_disposal:
                # Skip classification for disposals
                df.at[idx, "Final Category"] = ""
                df.at[idx, "MACRS Life"] = ""
                df.at[idx, "Method"] = ""
                df.at[idx, "Convention"] = ""
                df.at[idx, "Source"] = "skipped_disposal"
                df.at[idx, "Confidence"] = ""
                df.at[idx, "Low Confidence"] = False
                df.at[idx, "Notes"] = "Disposal - Classification not needed (use historical data for recapture)"
                disposals_skipped += 1
                continue

            if is_transfer:
                # Skip classification for transfers
                df.at[idx, "Final Category"] = ""
                df.at[idx, "MACRS Life"] = ""
                df.at[idx, "Method"] = ""
                df.at[idx, "Convention"] = ""
                df.at[idx, "Source"] = "skipped_transfer"
                df.at[idx, "Confidence"] = ""
                df.at[idx, "Low Confidence"] = False
                df.at[idx, "Notes"] = "Transfer - Classification not needed (already classified)"
                transfers_skipped += 1
                continue

            # CLASSIFY ADDITIONS ONLY
            try:
                final = classify_asset(
                    row,
                    client=client,
                    model="gpt-4.1-mini",
                    rules=rules,
                    overrides=overrides,
                    strategy="rule_then_gpt",
                )
                additions_classified += 1
            except Exception:
                final = {
                    "final_class": None,
                    "final_life": None,
                    "final_method": None,
                    "final_convention": None,
                    "source": "error",
                    "confidence": 0.0,
                    "low_confidence": True,
                    "notes": traceback.format_exc(),
                }

            df.at[idx, "Final Category"] = final.get("final_class")
            df.at[idx, "MACRS Life"] = final.get("final_life")
            df.at[idx, "Method"] = final.get("final_method")
            df.at[idx, "Convention"] = final.get("final_convention")
            df.at[idx, "Source"] = final.get("source")
            df.at[idx, "Confidence"] = final.get("confidence")
            df.at[idx, "Low Confidence"] = final.get("low_confidence")
            df.at[idx, "Notes"] = final.get("notes")

        # Show classification summary
        st.write(f"✓ Additions classified: {additions_classified}")
        if disposals_skipped > 0:
            st.write(f"⏭️  Disposals skipped: {disposals_skipped} (don't need classification)")
        if transfers_skipped > 0:
            st.write(f"⏭️  Transfers skipped: {transfers_skipped} (don't need classification)")

    # =====================================================================
    # CRITICAL: Transaction Type Classification
    # =====================================================================
    # Properly classify assets based on in-service date vs tax year
    # This determines Section 179/Bonus eligibility
    st.write("\n**Classifying transaction types based on in-service dates...**")

    df = classify_all_transactions(df, tax_year, verbose=False)

    # Validate classification
    is_valid, classification_errors = validate_transaction_classification(df, tax_year)

    if not is_valid:
        st.warning(f"⚠️ Found {len(classification_errors)} transaction classification issues")
        for error in classification_errors[:5]:  # Show first 5
            st.write(f"  - {error}")

    # Show summary
    if "Transaction Type" in df.columns:
        trans_counts = df["Transaction Type"].value_counts()
        st.write("\n**Transaction Type Summary:**")
        for trans_type, count in trans_counts.items():
            st.write(f"  • {trans_type}: {count}")

    st.success("Classification complete.")
    st.write(df.head())

    st.session_state["classified_df"] = df


# =====================================================================
# STEP 5 — STRICT HUMAN-IN-THE-LOOP WORKFLOW
# =====================================================================

if "classified_df" in st.session_state:

    df = st.session_state["classified_df"]
    
    st.markdown("---")
    st.header("Step 5 — Human-in-the-Loop Approval Workflow")
    st.info("Strict approval workflow required before RPA automation.")

    # Initialize approval state
    if "approval_status" not in st.session_state:
        st.session_state["approval_status"] = "PENDING"
    if "checkpoint_1_passed" not in st.session_state:
        st.session_state["checkpoint_1_passed"] = False
    if "checkpoint_2_passed" not in st.session_state:
        st.session_state["checkpoint_2_passed"] = False
    if "checkpoint_3_passed" not in st.session_state:
        st.session_state["checkpoint_3_passed"] = False

    # ------------------------------------------------------------------
    # CHECKPOINT 1: QUALITY REVIEW
    # ------------------------------------------------------------------
    st.subheader("Checkpoint 1: Quality Review")
    
    # Always run validation to show current status
    is_valid, errors, summary = validate_fixed_asset_cs_export(df, verbose=False)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Assets", len(df))
    col2.metric("Critical Errors", summary["CRITICAL"], delta_color="inverse")
    col3.metric("Errors", summary["ERROR"], delta_color="inverse")
    col4.metric("Warnings", summary["WARNING"], delta_color="inverse")

    if summary["CRITICAL"] > 0:
        st.error("❌ CRITICAL ERRORS DETECTED. Workflow Blocked.")
        st.session_state["checkpoint_1_passed"] = False
        for err in errors:
            if "CRITICAL" in str(err):
                st.write(f"- {err}")
    elif summary["ERROR"] > 0:
        st.warning("⚠️ ERRORS DETECTED. Human review required.")
        st.session_state["checkpoint_1_passed"] = False
        # Allow override for non-critical errors
        if st.checkbox("I have reviewed the errors and approve this data (Override)", key="cp1_override"):
            st.session_state["checkpoint_1_passed"] = True
            st.success("✓ Checkpoint 1 Approved (Override)")
    else:
        st.success("✓ Quality Check Passed")
        st.session_state["checkpoint_1_passed"] = True

    # ------------------------------------------------------------------
    # CHECKPOINT 2: TAX REVIEW
    # ------------------------------------------------------------------
    if st.session_state["checkpoint_1_passed"]:
        st.markdown("---")
        st.subheader("Checkpoint 2: Tax Calculation Review")
        
        # Calculate totals for display
        total_cost = df["Cost"].sum()
        total_sec179 = df.get("Section 179 Amount", pd.Series([0])).sum()
        total_bonus = df.get("Bonus Amount", pd.Series([0])).sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cost Basis", f"${total_cost:,.2f}")
        c2.metric("Total Sec 179", f"${total_sec179:,.2f}")
        c3.metric("Total Bonus", f"${total_bonus:,.2f}")
        
        st.write("**Review Required:**")
        st.write("1. Verify Section 179 limits ($2.5M max)")
        st.write("2. Confirm Bonus Depreciation eligibility")
        st.write("3. Check MACRS classifications")
        
        if st.checkbox("I have reviewed and approved the tax calculations", key="cp2_approve"):
            st.session_state["checkpoint_2_passed"] = True
            st.success("✓ Checkpoint 2 Approved")
        else:
            st.session_state["checkpoint_2_passed"] = False

    # ------------------------------------------------------------------
    # CHECKPOINT 3: PRE-RPA CHECKLIST
    # ------------------------------------------------------------------
    if st.session_state["checkpoint_2_passed"]:
        st.markdown("---")
        st.subheader("Checkpoint 3: Pre-RPA Checklist")
        
        checklist_items = {
            "File is ready for import": False,
            "No duplicate Asset IDs": not df["Asset ID"].duplicated().any(),
            "Fixed Asset CS is open": False
        }
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("System Checks:")
            if checklist_items["No duplicate Asset IDs"]:
                st.success("✓ No duplicate Asset IDs")
            else:
                st.error("❌ Duplicate Asset IDs found")
                
        with c2:
            st.write("Manual Checks:")
            fa_open = st.checkbox("Fixed Asset CS is open and ready")
            
        if checklist_items["No duplicate Asset IDs"] and fa_open:
            st.session_state["checkpoint_3_passed"] = True
            st.success("✓ Checkpoint 3 Passed")
        else:
            st.session_state["checkpoint_3_passed"] = False

    # ------------------------------------------------------------------
    # FINAL SIGN-OFF & RPA
    # ------------------------------------------------------------------
    if st.session_state["checkpoint_3_passed"]:
        st.markdown("---")
        st.subheader("Final Sign-Off & RPA Execution")
        
        col1, col2 = st.columns(2)
        with col1:
            approver_name = st.text_input("Approver Name")
        with col2:
            approver_email = st.text_input("Approver Email")
            
        if approver_name and approver_email:
            st.success("✓ Final Approval Granted")
            
            # RPA BUTTON
            if RPA_AVAILABLE:
                if st.button("▶️ RUN RPA AUTOMATION", type="primary"):
                    
                    # Create approval record
                    approval_record = final_approval_and_signoff(
                        validation_summary=summary,
                        tax_summary={"total_cost": total_cost}, # Simplified for UI
                        checklist={"passed": True},
                        approver_name=approver_name,
                        approver_email=approver_email,
                        notes="Streamlit UI Approval"
                    )
                    save_approval_record(approval_record)
                    
                    # Run RPA
                    with st.spinner("Running RPA Automation..."):
                        try:
                            # Build FA CS export data first
                            fa_df = build_fa(
                                df=df,
                                tax_year=tax_year,
                                strategy=strategy,
                                taxable_income=taxable_income,
                                use_acq_if_missing=use_acq_if_missing,
                            )
                            
                            orchestrator = AIRPAOrchestrator()
                            results = orchestrator.run_full_workflow(
                                classified_df=df,
                                tax_year=tax_year,
                                strategy=strategy,
                                taxable_income=taxable_income,
                                use_acq_if_missing=use_acq_if_missing,
                                preview_mode=False, # Full run if approved
                                auto_run_rpa=True,
                            )
                            
                            if results.get("success"):
                                st.balloons()
                                st.success("✅ RPA Automation Complete!")
                                st.json(results)
                            else:
                                st.error(f"RPA Failed: {results.get('error')}")
                                
                        except Exception as e:
                            st.error(f"RPA Error: {e}")
            else:
                st.warning("RPA not available in this environment.")
                
                # Allow download instead
                if st.button("Download Import File (Manual)"):
                    fa_df = build_fa(
                        df=df,
                        tax_year=tax_year,
                        strategy=strategy,
                        taxable_income=taxable_income,
                        use_acq_if_missing=use_acq_if_missing,
                    )
                    outfile = export_fa_excel(fa_df)
                    st.download_button(
                        "Download Excel",
                        data=outfile,
                        file_name="FA_CS_Import_Approved.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

