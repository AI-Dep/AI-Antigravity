# fixed_asset_ai/app.py
# Version: 2025-11-25.1 - REDEPLOY: Force sync for tax_year_config imports
# DEPLOYED: 2025-11-25 02:10 UTC
# CRITICAL: Fixed pandas NaT comparison in bonus percentage calculation
# Fix commits: 1286c1e (NA handling), e87134d (NaT handling)

import streamlit as st
import pandas as pd
from datetime import datetime
import traceback
import logging
import os
import re
import hashlib
from pathlib import Path

# Tax year configuration imports
from logic.tax_year_config import (
    get_tax_year_status, TaxYearStatus, get_config_info, validate_tax_year_config
)

# =====================================================================
# PAGE CONFIGURATION - Professional Setup
# =====================================================================
st.set_page_config(
    page_title="Fixed Asset AI - Professional Tax Depreciation",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================================
# AUTHENTICATION (Optional - can be disabled for development)
# =====================================================================

# Import authentication module
try:
    from logic.login_ui import (
        require_auth, show_user_menu, show_profile_dialog,
        get_current_user, is_auth_enabled, get_accessible_clients,
        has_client_access, require_permission
    )
    AUTH_MODULE_AVAILABLE = True
except ImportError:
    AUTH_MODULE_AVAILABLE = False

# Check authentication if enabled
if AUTH_MODULE_AVAILABLE and is_auth_enabled():
    current_user = require_auth()
    if current_user is None:
        st.stop()  # Login form is being shown
else:
    current_user = None

# =====================================================================
# SECURE ERROR LOGGING
# =====================================================================

# Configure secure error logging
ERROR_LOG_DIR = Path("logs")
ERROR_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=ERROR_LOG_DIR / "app_errors.log",
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# =====================================================================
# COST & RATE LIMITING CONTROLS
# =====================================================================

# Maximum number of assets that can be processed in a single run
MAX_ASSETS_PER_RUN = 1000

# Estimated cost per GPT API call (approximate, update based on actual pricing)
ESTIMATED_COST_PER_CALL = 0.0001  # ~$0.0001 per call for gpt-4o-mini

def estimate_processing_cost(num_assets: int) -> float:
    """
    Estimate the cost of processing assets.

    Args:
        num_assets: Number of assets to process

    Returns:
        Estimated cost in USD
    """
    # Not all assets call GPT (some use rules), but conservative estimate
    # assumes worst case where 80% require GPT calls
    gpt_calls_estimate = int(num_assets * 0.8)
    return gpt_calls_estimate * ESTIMATED_COST_PER_CALL

def log_error_securely(error: Exception, context: str = "", include_error_id: bool = False) -> str:
    """
    Log detailed error information to file and return a generic user-facing message.

    Args:
        error: The exception that occurred
        context: Description of what was being attempted
        include_error_id: If True, include error ID in message; if False, store in session state

    Returns:
        A generic, user-safe error message
    """
    # Log detailed error to file (not shown to user)
    error_details = traceback.format_exc()
    error_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    logging.error(f"Context: {context} | Error ID: {error_id}\n{error_details}")

    # Store error ID for technical details display
    if 'st' in dir() or 'streamlit' in str(type(st)):
        try:
            st.session_state["last_error_id"] = error_id
        except:
            pass

    # Return user-friendly message (without technical error ID by default)
    if include_error_id:
        return f"An error occurred while {context}. Error ID: {error_id}. Please contact support if the issue persists."
    else:
        return f"An error occurred while {context}. Please contact support if the issue persists."

def sanitize_log_data(log_data: dict) -> dict:
    """
    Sanitize log data before allowing download by removing sensitive information.

    Args:
        log_data: The log data dictionary

    Returns:
        Sanitized log data safe for download
    """
    import copy
    sanitized = copy.deepcopy(log_data)

    # List of sensitive keys to redact
    sensitive_keys = [
        'api_key', 'password', 'token', 'secret', 'credential',
        'authorization', 'auth', 'private_key', 'access_token'
    ]

    def redact_sensitive(obj, path=""):
        """Recursively redact sensitive information from nested structures"""
        if isinstance(obj, dict):
            for key in list(obj.keys()):
                new_path = f"{path}.{key}" if path else key
                # Check if key name suggests sensitive data
                if any(sensitive in key.lower() for sensitive in sensitive_keys):
                    obj[key] = "***REDACTED***"
                else:
                    redact_sensitive(obj[key], new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                redact_sensitive(item, f"{path}[{i}]")
        elif isinstance(obj, str):
            # Redact file paths that might expose internal structure
            if len(obj) > 100 and ('/' in obj or '\\' in obj):
                return "***PATH_REDACTED***"

    redact_sensitive(sanitized)
    return sanitized

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal and other file system attacks.

    Args:
        filename: The filename to sanitize

    Returns:
        A safe filename with no directory components

    Raises:
        ValueError: If the filename is invalid
    """
    import os
    import re

    if not filename:
        raise ValueError("Filename cannot be empty")

    # Remove any directory components (path traversal prevention)
    filename = os.path.basename(filename)

    # Remove or replace unsafe characters (keep only alphanumeric, dash, underscore, dot)
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

    # Prevent hidden files
    if filename.startswith('.'):
        filename = '_' + filename[1:]

    # Ensure filename isn't too long (max 255 chars for most filesystems)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext

    # Prevent empty filename after sanitization
    if not filename or filename == '.':
        raise ValueError("Invalid filename")

    return filename


def sanitize_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitize DataFrame for PyArrow/Streamlit display by converting mixed-type columns to strings.

    PyArrow cannot handle columns with mixed types (e.g., both strings and numbers).
    This function converts all object columns to strings to prevent ArrowInvalid errors.
    """
    df_display = df.copy()
    for col in df_display.columns:
        # Convert object columns (which may have mixed types) to string
        if df_display[col].dtype == 'object':
            df_display[col] = df_display[col].astype(str).replace('nan', '').replace('None', '')
    return df_display


# =====================================================================
# DEBUG IMPORT BLOCK (CRITICAL)
# Shows real errors inside macrs_classification.py
# =====================================================================

try:
    from logic.sheet_loader import (
        build_unified_dataframe,
        analyze_tabs_smart,
        build_unified_dataframe_smart,
        format_tab_analysis_for_display
    )
    # Smart tab analyzer types - optional, with fallback
    try:
        from logic.smart_tab_analyzer import TabRole, TabAnalysis, TabAnalysisResult
        SMART_TAB_ANALYZER_AVAILABLE = True
    except ImportError:
        # Create dummy types for graceful fallback
        TabRole = None
        TabAnalysis = None
        TabAnalysisResult = None
        SMART_TAB_ANALYZER_AVAILABLE = False
    from logic.client_mapping_manager import (
        ClientMappingManager, generate_mapping_preview, get_manager, reload_manager
    )
    from logic.macrs_classification import (
        load_rules,
        load_overrides,
        save_overrides,
        classify_asset,
    )
    # Batch classification is optional (new feature) - graceful fallback if not available
    try:
        from logic.macrs_classification import classify_assets_batch
        BATCH_CLASSIFICATION_AVAILABLE = True
    except ImportError:
        classify_assets_batch = None
        BATCH_CLASSIFICATION_AVAILABLE = False

    from logic.transaction_classifier import (
        classify_all_transactions,
        validate_transaction_classification,
    )
    from logic.fa_export import export_fa_excel, build_fa
except Exception as e:
    st.error("Failed to load required application modules. Please ensure all dependencies are installed.")
    st.error(f"**Actual error:** {type(e).__name__}: {str(e)}")
    error_msg = log_error_securely(e, "loading application modules")
    st.info(error_msg)
    st.code(traceback.format_exc())
    st.stop()


from logic.validators import validate_assets
from logic.advanced_validations import advanced_validations
from logic.outlier_detector import detect_outliers
from logic.explanations import build_explanation
from logic.sanitizer import sanitize_asset_description
from logic.strategy_config import get_strategy_labels, get_strategy_help

# =====================================================================
# ENHANCED VALIDATION MODULES (Phases 1 & 2)
# =====================================================================
# Phase 1: Existing modules now integrated
from logic.data_quality_score import calculate_data_quality_score, generate_quality_report, DataQualityScore
from logic.rollforward_reconciliation import reconcile_rollforward, generate_rollforward_report
from logic.risk_engine import evaluate_asset_risk
from logic.data_validator import AssetDataValidator, ValidationError

# Phase 2: New tax correctness modules
from logic.classification_verifier import verify_classifications, ClassificationIssue
from logic.prior_year_reconciler import reconcile_to_prior_year, reconcile_cost_totals
from logic.spot_checker import select_spot_check_sample, generate_spot_check_report
from logic.confidence_gate import check_confidence_gate, get_assets_requiring_review

# CPA Planning & Analysis modules
from logic.depreciation_projection import (
    project_portfolio_depreciation, create_detailed_projection_table
)
from logic.recapture import recapture_analysis, calculate_section_1245_recapture, determine_recapture_type
from logic.section_179_carryforward import calculate_section_179_with_income_limit
from logic.materiality import compute_materiality

# Database integration for classification persistence
try:
    from logic.workflow_integration import WorkflowIntegration
    DB_AVAILABLE = True
except Exception:
    WorkflowIntegration = None
    DB_AVAILABLE = False

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
# STREAMLIT CONFIG (REMOVED - duplicate, already set above)
# =====================================================================
# NOTE: st.set_page_config() must only be called once and is done above

# =====================================================================
# CLEAN HEADER
# =====================================================================
st.title("Fixed Asset AI")
st.caption("Tax Depreciation & FA CS Export")

# =====================================================================
# OPENAI CLIENT
# =====================================================================

from openai import OpenAI

@st.cache_resource
def get_openai_client():
    try:
        # Get API key from Streamlit Cloud Secrets or environment variable
        # Priority: st.secrets (Streamlit Cloud) > os.getenv (local .env)
        api_key = ""

        # Try Streamlit Cloud Secrets first
        try:
            api_key = st.secrets["OPENAI_API_KEY"]
        except (KeyError, FileNotFoundError):
            # Fall back to environment variable for local development
            api_key = os.getenv("OPENAI_API_KEY", "")

        if api_key:
            # Check for common security mistakes
            if api_key == "sk-your-api-key-here" or api_key == "your_api_key_here":
                st.error("⚠️ Please replace the placeholder API key with your actual OpenAI API key")
                st.stop()
            elif len(api_key) < 20:
                st.warning("⚠️ Your API key looks unusually short. Please verify it's correct.")
        else:
            st.error("""
            **OpenAI API Key Not Found**

            **For Streamlit Cloud:**
            1. Go to your app settings
            2. Click "Secrets"
            3. Add: `OPENAI_API_KEY = "your-key-here"`

            **For Local Development:**
            1. Copy `.env.example` to `.env`
            2. Add your OpenAI API key to the `.env` file
            3. Restart the application

            See SECURITY.md for detailed instructions.
            """)
            st.stop()

        return OpenAI(api_key=api_key)
    except Exception as e:
        st.error("Failed to initialize OpenAI client. Please check your API key configuration.")
        error_msg = log_error_securely(e, "initializing OpenAI client")
        st.info(error_msg)
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
# PAGE SELECTION (must be before any other UI elements)
# =====================================================================

# Initialize page_mode in session state if not present
if 'page_mode' not in st.session_state:
    st.session_state.page_mode = "📊 Processing"

# =====================================================================
# SIDEBAR - MINIMAL & CLEAN
# =====================================================================

with st.sidebar:
    # Clean branding
    st.markdown("### Fixed Asset AI")
    st.caption("Tax depreciation made easy")

    # Show user menu if authenticated
    if AUTH_MODULE_AVAILABLE and current_user:
        show_user_menu()
        show_profile_dialog()

    st.divider()

    # Simple page toggle - pill style
    page_options = ["📊 Process", "⚙️ Manage"]
    selected_page = st.radio(
        "Mode",
        page_options,
        index=0 if st.session_state.page_mode in ["📊 Processing", "Processing", "📊 Process"] else 1,
        horizontal=True,
        label_visibility="collapsed"
    )

    # Check if management mode
    if "Manage" in selected_page:
        st.session_state.page_mode = "Management"
        try:
            from logic.management_ui import render_management_ui
            render_management_ui()
            st.stop()
        except Exception as e:
            st.error(f"Error loading management UI: {str(e)}")
            st.stop()
    else:
        st.session_state.page_mode = "Processing"

    st.divider()

    # Session stats (only when data loaded)
    if "classified_df" in st.session_state:
        df_stats = st.session_state["classified_df"]

        # Calculate totals - use pd.to_numeric for mixed types
        if "Cost" in df_stats.columns:
            if "Transaction Type" in df_stats.columns:
                non_disposal_mask = ~df_stats["Transaction Type"].astype(str).str.contains("Disposal", case=False, na=False)
                total_cost = pd.to_numeric(df_stats.loc[non_disposal_mask, "Cost"], errors='coerce').fillna(0).sum()
            else:
                total_cost = pd.to_numeric(df_stats["Cost"], errors='coerce').fillna(0).sum()
        else:
            total_cost = 0

        st.metric("Total Assets", f"{len(df_stats):,}")
        st.metric("Total Value", f"${total_cost:,.0f}")

        st.divider()

        if st.button("🔄 Start Over", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # Hidden RPA setting
    show_rpa_steps = False
    st.session_state["show_rpa_steps"] = show_rpa_steps

    # Session Persistence
    with st.expander("Save/Load Session"):
        try:
            from logic.session_persistence import (
                save_session, load_session, list_sessions, has_autosave, load_autosave
            )

            # Save current session
            if "classified_df" in st.session_state:
                save_name = st.text_input("Session name", value="", key="session_name")
                if st.button("Save Session", use_container_width=True):
                    if save_name:
                        session_id = save_session(st.session_state, session_id=save_name)
                        st.success(f"Saved as: {session_id}")
                    else:
                        st.warning("Enter a session name")

            # Load previous sessions
            sessions = list_sessions()
            if sessions:
                st.markdown("**Load Previous:**")
                session_options = [""] + [s.get("session_id", "unknown") for s in sessions]
                selected = st.selectbox("Select session", session_options, key="load_session_select")
                if selected and st.button("Load", use_container_width=True):
                    loaded = load_session(selected)
                    if loaded:
                        for key, value in loaded.items():
                            st.session_state[key] = value
                        st.success(f"Loaded: {selected}")
                        st.rerun()

            # Auto-save recovery
            if has_autosave() and "classified_df" not in st.session_state:
                st.info("Autosave found!")
                if st.button("Recover Last Session"):
                    autosave = load_autosave()
                    if autosave:
                        for key, value in autosave.items():
                            st.session_state[key] = value
                        st.rerun()

        except Exception as e:
            st.caption(f"Session persistence unavailable: {e}")

    st.caption("v2.2")


# =====================================================================
# SIMPLE STEP INDICATOR - Clean 3-step flow
# =====================================================================

# Determine current step
current_step = 1  # Upload
if "classified_df" in st.session_state:
    if st.session_state.get("fa_preview") is not None:
        current_step = 3  # Export
    else:
        current_step = 2  # Review

# Simple text-based step indicator
step_col1, step_col2, step_col3 = st.columns(3)
with step_col1:
    if current_step > 1:
        st.success("✓ Upload")
    elif current_step == 1:
        st.info("① Upload")
    else:
        st.caption("① Upload")
with step_col2:
    if current_step > 2:
        st.success("✓ Review")
    elif current_step == 2:
        st.info("② Review")
    else:
        st.caption("② Review")
with step_col3:
    if current_step == 3:
        st.info("③ Export")
    else:
        st.caption("③ Export")


# =====================================================================
# STEP 1: UPLOAD
# =====================================================================

# Minimal info - just what they need to know
with st.expander("ℹ️ About Data Privacy", expanded=False):
    st.caption("Asset descriptions are sent to OpenAI for AI classification. Costs and dates stay local. Session clears when you close this tab.")

uploaded = st.file_uploader("Upload asset schedule", type=["xlsx", "xls"])

if not uploaded:
    st.info("Upload an Excel file to begin.")
    st.stop()

try:
    # HIGH PRIORITY: Better detection of corrupted Excel files
    try:
        xls = pd.ExcelFile(uploaded)
        # Store filename and checksum for audit trail
        st.session_state["uploaded_file_name"] = uploaded.name
        # Calculate file checksum for audit integrity
        uploaded.seek(0)
        file_hash = hashlib.sha256(uploaded.read()).hexdigest()[:16]  # First 16 chars
        st.session_state["uploaded_file_checksum"] = file_hash
        uploaded.seek(0)  # Reset for later reading
    except Exception as excel_err:
        error_type = type(excel_err).__name__
        error_msg = str(excel_err).lower()

        # Detect corrupted file errors
        if any(keyword in error_msg for keyword in ['corrupt', 'invalid', 'damaged', 'bad', 'malformed']):
            st.error("❌ Excel file appears to be corrupted or damaged")
            st.info(
                "**How to fix:**\n"
                "1. Try opening the file in Excel and saving it again\n"
                "2. If Excel can't open it, the file may be permanently corrupted\n"
                "3. Restore from backup if available\n"
                "4. Re-export the data from your source system"
            )
            st.error(f"Technical details: {error_type}: {excel_err}")
            st.stop()
        elif 'zip' in error_msg or 'format' in error_msg:
            st.error("❌ File format error - file may be corrupted or not a valid Excel file")
            st.info(
                "**Common causes:**\n"
                "- File extension is .xlsx but it's not actually an Excel file\n"
                "- File was partially downloaded or transfer was interrupted\n"
                "- File is password-protected (not currently supported)\n"
                "- File uses an old Excel format (.xls) - try saving as .xlsx"
            )
            st.error(f"Technical details: {error_type}: {excel_err}")
            st.stop()
        else:
            # Re-raise for generic error handling below
            raise

    sheets = {name: xls.parse(name, header=None) for name in xls.sheet_names}

    # =====================================================================
    # SMART TAB ANALYSIS - CPA-style file structure detection
    # =====================================================================

    # Store sheets in session state for later use with tax year
    if "uploaded_sheets" not in st.session_state or st.session_state.get("uploaded_file_checksum") != file_hash:
        st.session_state["uploaded_sheets"] = sheets
        # Clear old checkbox states when new file uploaded
        for key in list(st.session_state.keys()):
            if key.startswith("tab_select_"):
                del st.session_state[key]

    # Initialize tab analysis with default tax year (current year)
    # This enables prior year detection on initial load
    default_tax_year = datetime.now().year
    preliminary_analysis = analyze_tabs_smart(sheets, target_tax_year=default_tax_year)

    # Check if smart tab analyzer is available
    if preliminary_analysis is not None:
        # Show smart tab detection UI
        with st.expander("🧠 Smart Tab Detection", expanded=True):
            st.markdown("""
            **How CPAs read fixed asset files:**
            - Summary tabs (FY roll-ups) → Skip, they're just totals
            - Detail tabs (by category) → Process for additions
            - Prior year tabs → Skip unless reconciling
            - Disposal tabs → Track for disposals only
            """)

            # Show detected tabs with their roles
            st.markdown("##### Detected Tab Structure")

            # Create visual tab tree
            for tab in preliminary_analysis.tabs:
                role_icons = {
                    TabRole.SUMMARY: ("📊", "Summary", "yellow"),
                    TabRole.DETAIL: ("📋", "Detail", "green"),
                    TabRole.DISPOSALS: ("🗑️", "Disposals", "blue"),
                    TabRole.ADDITIONS: ("➕", "Additions", "green"),
                    TabRole.TRANSFERS: ("🔄", "Transfers", "blue"),
                    TabRole.PRIOR_YEAR: ("📅", "Prior Year", "gray"),
                    TabRole.WORKING: ("📝", "Working/Draft", "gray"),
                    TabRole.UNKNOWN: ("❓", "Unknown", "orange"),
                }
                icon, role_label, color = role_icons.get(tab.role, ("❓", "Unknown", "gray"))

                # Checkbox for tab selection
                # Default: process recommended tabs, skip others
                default_selected = tab.should_process
                tab_key = f"tab_select_{tab.tab_name}"

                col1, col2, col3 = st.columns([0.5, 3, 2])
                with col1:
                    # Streamlit manages checkbox state via key parameter
                    # Get current state or use default
                    current_value = st.session_state.get(tab_key, default_selected)
                    st.checkbox(
                        "",
                        value=current_value,
                        key=tab_key,
                        label_visibility="collapsed"
                    )
                with col2:
                    st.markdown(f"{icon} **{tab.tab_name}**")
                with col3:
                    if tab.should_process:
                        st.markdown(f":green[{role_label}] ({tab.data_row_count} rows)")
                    else:
                        st.markdown(f":gray[{role_label} - skip] ({tab.data_row_count} rows)")

            # Show warnings if any (e.g., summary has data but details empty)
            if preliminary_analysis.warnings:
                st.markdown("---")
                st.markdown("##### ⚠️ Data Warnings")
                for warning in preliminary_analysis.warnings:
                    st.warning(warning)

            # Show efficiency stats
            stats = preliminary_analysis.get_efficiency_stats()
            if stats["reduction_percent"] > 0:
                st.markdown("---")
                st.info(
                    f"💡 **Efficiency gain:** Processing {stats['process_tabs']}/{stats['total_tabs']} tabs "
                    f"({stats['process_rows']} rows instead of {stats['total_rows']}). "
                    f"**{stats['reduction_percent']:.0f}% reduction** in data to classify."
                )

        # Get selected tabs based on checkboxes
        # Note: Streamlit checkbox with key=X stores value directly in st.session_state[X]
        selected_tabs = [
            tab.tab_name for tab in preliminary_analysis.tabs
            if st.session_state.get(f"tab_select_{tab.tab_name}", tab.should_process)
        ]

        # Store selected tabs in session state for use after tax year selection
        st.session_state["selected_tabs"] = selected_tabs

        # For initial load, use basic processing (will be re-processed after tax year selection)
        filtered_sheets = {name: df for name, df in sheets.items() if name in selected_tabs}

        if not filtered_sheets:
            st.warning("No tabs selected for processing. Please select at least one tab.")
            st.stop()

        df_raw = build_unified_dataframe(filtered_sheets)
    else:
        # Fallback: Smart tab analyzer not available, show basic file structure
        with st.expander("📂 File Structure Detected", expanded=False):
            st.write(f"**Sheets found:** {', '.join(xls.sheet_names)}")
            for sheet_name, df_sheet in sheets.items():
                if df_sheet is not None and not df_sheet.empty:
                    first_row = df_sheet.iloc[0].tolist() if len(df_sheet) > 0 else []
                    st.write(f"**{sheet_name}:** {len(df_sheet)} rows")
                    if first_row:
                        st.caption(f"First row: {', '.join(str(x)[:30] for x in first_row[:6])}")

        # Process all sheets without smart filtering
        df_raw = build_unified_dataframe(sheets)

    if df_raw.empty:
        st.error("❌ No data could be extracted from the selected tabs.")
        st.warning(
            "**Possible causes:**\n"
            "- No 'Description' column found (required)\n"
            "- Headers not in first 20 rows\n"
            "- Column names don't match expected patterns\n\n"
            "**Try:** Open the file and check that column headers include:\n"
            "- Description, Asset Description, or Property Description\n"
            "- Cost, Original Cost, or Tax Cost\n"
            "- In Service Date, Date In Service, or PIS Date"
        )
        st.stop()

    df_raw = df_raw.rename(columns={
        "asset_id": "Asset ID",
        "description": "Description",
        "client_category": "Client Category",
        "cost": "Cost",
        "acquisition_date": "Acquisition Date",
        "in_service_date": "In Service Date",
        "disposal_date": "Disposal Date",
        "location": "Location",
        "sheet_role": "Sheet Role",
        "transaction_type": "Transaction Type",
        "accumulated_depreciation": "Accumulated Depreciation",
        "net_book_value": "NBV",
        "proceeds": "Proceeds",
    })

    # Store detected column mappings for client memory feature
    # Build reverse mapping from standardized names to original columns
    detected_mappings = {}
    for orig_col in df_raw.columns:
        # Map the standardized column back to what we detected
        standardized = orig_col.lower().replace(" ", "_")
        detected_mappings[standardized] = orig_col
    st.session_state["detected_column_mappings"] = detected_mappings

    # Show success with tab filtering info
    tabs_skipped = len(sheets) - len(filtered_sheets)
    if tabs_skipped > 0:
        st.success(f"✅ Loaded {len(df_raw)} assets from {len(filtered_sheets)} tabs (skipped {tabs_skipped} tabs)")
    else:
        st.success(f"✅ Loaded {len(df_raw)} assets")

    # Compact preview
    with st.expander("Preview data"):
        display_cols = [col for col in ['Asset ID', 'Description', 'Cost', 'In Service Date'] if col in df_raw.columns]
        st.dataframe(sanitize_dataframe_for_display(df_raw[display_cols].head(5)), use_container_width=True, hide_index=True)

except Exception as e:
    st.error("❌ Failed to parse the uploaded file.")

    # Provide specific guidance based on error type
    error_str = str(e).lower()
    if "no sheets" in error_str or "empty" in error_str:
        st.warning("The file appears to be empty or has no readable sheets.")
    elif "description" in error_str:
        st.warning(
            "**No Description column found.**\n\n"
            "The tool requires a column named something like:\n"
            "- Description\n"
            "- Asset Description\n"
            "- Property Description\n"
            "- Item Name"
        )
    elif "header" in error_str:
        st.warning(
            "**Could not find column headers.**\n\n"
            "Make sure your headers are in the first 20 rows of the spreadsheet."
        )
    else:
        st.warning(
            "**Common fixes:**\n"
            "1. Open in Excel and re-save as .xlsx\n"
            "2. Make sure headers are in the first row\n"
            "3. Remove any merged cells in the header row\n"
            "4. Check that columns include: Description, Cost, In Service Date"
        )

    error_msg = log_error_securely(e, "parsing uploaded Excel file")
    with st.expander("🔍 Technical Details"):
        st.code(f"Error: {type(e).__name__}: {str(e)[:200]}")
        st.info(error_msg)
    st.stop()


# =====================================================================
# CONFIGURATION (Client + Tax Year in one row)
# =====================================================================

st.markdown("### Configuration")

# =====================================================================
# SIMPLIFIED SETTINGS - Just the essentials
# =====================================================================

# Auto-detect tax year from data if possible
def detect_tax_year_from_data(df):
    """Try to detect tax year from date columns."""
    date_cols = ["In Service Date", "Acquisition Date", "Date", "Placed in Service"]
    for col in date_cols:
        if col in df.columns:
            dates = pd.to_datetime(df[col], errors='coerce').dropna()
            if len(dates) > 0:
                # Use the most common year, defaulting to current year
                years = dates.dt.year
                mode_year = years.mode()
                if len(mode_year) > 0 and 2020 <= mode_year.iloc[0] <= 2030:
                    return int(mode_year.iloc[0])
    return datetime.now().year  # Default to current year

# Detect tax year from uploaded data
detected_tax_year = detect_tax_year_from_data(df_raw)

# Simple 2-column layout: Client Name + Tax Year
col1, col2 = st.columns([2, 1])

with col1:
    client_key = st.text_input("Client Name", value="", placeholder="Enter client name")
    if not client_key:
        client_key = "Client"

with col2:
    # Show detected year as default
    year_options = [2026, 2025, 2024, 2023, 2022]
    default_index = year_options.index(detected_tax_year) if detected_tax_year in year_options else 1
    tax_year = st.selectbox("Tax Year", options=year_options, index=default_index)
    st.session_state["tax_year"] = tax_year

# Validate client key silently
if not re.match(r'^[a-zA-Z0-9_\- ]{1,50}$', client_key):
    st.error("Client name can only contain letters, numbers, spaces, hyphens, underscores.")
    st.stop()

st.session_state["client_key"] = client_key

# Check if this client has saved settings (show subtle indicator)
client_mapping_manager = get_manager()
client_id_normalized = client_key.lower().replace(" ", "_")
existing_client_mapping = client_mapping_manager.get_client_mapping(client_id_normalized)
if existing_client_mapping:
    st.caption(f"✓ Using saved settings for {existing_client_mapping.get('client_name', client_key)}")
    st.session_state["using_saved_client_mapping"] = True
    st.session_state["client_id_normalized"] = client_id_normalized
else:
    st.session_state["using_saved_client_mapping"] = False
    st.session_state["client_id_normalized"] = client_id_normalized

# Tax Year Status - subtle indicator
tax_status, tax_status_msg = get_tax_year_status(tax_year)
if tax_status == TaxYearStatus.ESTIMATED:
    st.caption(f"⚠️ {tax_year} uses estimated values")
elif tax_status == TaxYearStatus.UNSUPPORTED:
    st.error(f"Tax Year {tax_year} is not supported. Please select 2022-2026.")
    st.stop()

# Smart defaults - aggressive strategy for maximum deductions
strategy = get_strategy_labels()[0]  # Aggressive (179 + Bonus)

# All other settings in collapsed expander
with st.expander("⚙️ Settings", expanded=False):
    set_col1, set_col2 = st.columns(2)

    with set_col1:
        strategy = st.selectbox(
            "Depreciation Strategy",
            get_strategy_labels(),
            index=0,
            help="Aggressive: Max §179 + Bonus | Balanced: Bonus only | Conservative: MACRS only"
        )

        taxable_income = st.number_input(
            "Est. Taxable Income",
            value=200000,
            step=10000,
            min_value=0,
            help="For §179 income limitation check"
        )

        de_minimis_limit = st.number_input(
            "De Minimis Limit",
            value=2500,
            min_value=0,
            max_value=5000,
            help="Expense items under this amount"
        )

    with set_col2:
        section_179_carryforward = st.number_input(
            "§179 Carryforward",
            value=0,
            step=1000,
            min_value=0,
            help="Prior year carryforward (Form 4562)"
        )

        asset_number_start = st.number_input(
            "Starting Asset #",
            value=1,
            min_value=1,
            max_value=999999,
            help="Start from last FA CS Asset # + 1"
        )
        st.session_state["asset_number_start"] = asset_number_start

        remember_client = st.checkbox(
            "Remember settings for this client",
            value=True
        )
        st.session_state["remember_client"] = remember_client

    # Fiscal year (rarely changed)
    fy_options = {"Calendar (Jan-Dec)": 1, "Apr-Mar": 4, "Jul-Jun": 7, "Oct-Sep": 10}
    fy_selection = st.selectbox("Fiscal Year End", list(fy_options.keys()), index=0)
    fy_start_month = fy_options[fy_selection]
    st.session_state["fy_start_month"] = fy_start_month

# Hidden settings with smart defaults
use_acq_if_missing = True  # Smart default

# =====================================================================
# PRE-CLASSIFICATION SUMMARY - Show data quality before classification
# =====================================================================
total_cost = pd.to_numeric(df_raw["Cost"], errors='coerce').fillna(0).sum() if "Cost" in df_raw.columns else 0
num_assets = len(df_raw)

st.markdown("---")

# Pre-classification data check summary
st.markdown("### 📋 Pre-Classification Check")

check_col1, check_col2, check_col3, check_col4 = st.columns(4)

# Check 1: Asset count
with check_col1:
    st.metric("Assets Found", f"{num_assets:,}")

# Check 2: Total cost
with check_col2:
    st.metric("Total Cost", f"${total_cost:,.0f}")

# Check 3: Missing descriptions
with check_col3:
    missing_desc = df_raw["Description"].isna().sum() if "Description" in df_raw.columns else num_assets
    if missing_desc == 0:
        st.metric("Descriptions", "✅ Complete")
    else:
        st.metric("Missing Desc.", f"⚠️ {missing_desc}")

# Check 4: Missing dates
with check_col4:
    missing_dates = 0
    if "In Service Date" in df_raw.columns:
        missing_dates = df_raw["In Service Date"].isna().sum()
    elif "Acquisition Date" in df_raw.columns:
        missing_dates = df_raw["Acquisition Date"].isna().sum()
    else:
        missing_dates = num_assets

    if missing_dates == 0:
        st.metric("Dates", "✅ Complete")
    else:
        st.metric("Missing Dates", f"⚠️ {missing_dates}")

# Data quality warnings
with st.expander("📊 Data Quality Details", expanded=False):
    quality_issues = []

    # Check for high-value assets
    if "Cost" in df_raw.columns:
        high_value = df_raw[pd.to_numeric(df_raw["Cost"], errors='coerce') > 100000]
        if len(high_value) > 0:
            quality_issues.append(f"🔍 **{len(high_value)} high-value assets** (>${100000:,}) - will receive extra scrutiny")

    # Check for disposals
    if "Transaction Type" in df_raw.columns:
        disposals = df_raw[df_raw["Transaction Type"].str.lower().str.contains("dispos|sold|retire", na=False)]
        if len(disposals) > 0:
            quality_issues.append(f"📤 **{len(disposals)} disposals detected** - will skip MACRS classification")

    # Check for potential duplicates
    if "Description" in df_raw.columns and "Cost" in df_raw.columns:
        potential_dupes = df_raw.duplicated(subset=["Description", "Cost"], keep=False).sum()
        if potential_dupes > 0:
            quality_issues.append(f"⚠️ **{potential_dupes} potential duplicates** - same description and cost")

    # Check for missing costs
    if "Cost" in df_raw.columns:
        missing_cost = df_raw["Cost"].isna().sum() + (df_raw["Cost"] == 0).sum()
        if missing_cost > 0:
            quality_issues.append(f"⚠️ **{missing_cost} assets with missing/zero cost**")

    if quality_issues:
        for issue in quality_issues:
            st.markdown(issue)
    else:
        st.success("✅ No data quality issues detected")

    # Show column detection summary
    st.markdown("**Columns Detected:**")
    detected = []
    if "Description" in df_raw.columns: detected.append("✅ Description")
    if "Cost" in df_raw.columns: detected.append("✅ Cost")
    if "In Service Date" in df_raw.columns: detected.append("✅ In Service Date")
    if "Asset ID" in df_raw.columns: detected.append("✅ Asset ID")
    if "Client Category" in df_raw.columns: detected.append("✅ Category")
    if "Location" in df_raw.columns: detected.append("✅ Location")
    if "NBV" in df_raw.columns: detected.append("✅ NBV")
    if "Accumulated Depreciation" in df_raw.columns: detected.append("✅ Accum. Depr.")
    st.write(" • ".join(detected) if detected else "No standard columns detected")


# =====================================================================
# CLASSIFICATION - MAIN ACTION
# =====================================================================

# Enforce maximum asset limit
if num_assets > MAX_ASSETS_PER_RUN:
    st.error(f"Too many assets ({num_assets:,}). Maximum is {MAX_ASSETS_PER_RUN:,}. Please split into smaller files.")
    st.stop()

# Privacy setting with smart default
include_location = False
st.session_state["include_location_in_gpt"] = include_location

# Main action button - prominent and clear
st.markdown("")
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    classify_clicked = st.button("🚀 Classify Assets", type="primary", use_container_width=True)

if classify_clicked:

    # Show progress for large files
    total_assets = len(df_raw)
    use_progress_bar = total_assets > 50  # Show progress bar for >50 assets

    if use_progress_bar:
        progress_text = st.empty()
        progress_bar = st.progress(0)
        progress_text.text(f"Classifying 0 of {total_assets} assets...")
    else:
        progress_text = None
        progress_bar = None

    with st.spinner("Classifying assets…"):
        # Track classification time for ROI display
        import time
        classification_start_time = time.time()

        df = df_raw.copy()

        # ===================================================================
        # PRE-CLASSIFICATION DATA CHECK - Single Clean Status Card
        # ===================================================================
        validation_issues = []
        auto_fixes = []
        is_blocked = False

        # Run data validation
        try:
            data_validator = AssetDataValidator(tax_year=tax_year)
            validation_errors = data_validator.validate_dataframe(df)

            if validation_errors:
                critical_errors = [e for e in validation_errors if e.severity == "CRITICAL"]
                other_issues = [e for e in validation_errors if e.severity in ["ERROR", "WARNING"]]

                if critical_errors:
                    is_blocked = True
                    for err in critical_errors:
                        validation_issues.append(f"**{err.field}** ({err.row_id}): {err.message}")

                for err in other_issues:
                    validation_issues.append(f"{err.field} ({err.row_id}): {err.message}")

        except Exception as val_err:
            pass  # Don't block on validator failure

        # Apply auto-fixes: Fill missing In-Service dates
        if use_acq_if_missing and "Acquisition Date" in df.columns and "In Service Date" in df.columns:
            missing_in_service = df["In Service Date"].isna() | (df["In Service Date"] == "")
            filled_count = missing_in_service.sum()
            if filled_count > 0:
                df.loc[missing_in_service, "In Service Date"] = df.loc[missing_in_service, "Acquisition Date"]
                auto_fixes.append(f"{filled_count} missing dates auto-filled")

        # ===================================================================
        # DISPLAY: Single Status Card
        # ===================================================================
        if is_blocked:
            st.error(f"❌ **Cannot proceed** - {len(validation_issues)} critical issues must be fixed")
            with st.expander("View issues", expanded=True):
                for issue in validation_issues[:15]:
                    st.markdown(f"• {issue}")
                if len(validation_issues) > 15:
                    st.caption(f"...and {len(validation_issues) - 15} more")
            st.stop()
        elif validation_issues:
            # Build status line
            status_parts = [f"{len(df)} assets"]
            if auto_fixes:
                status_parts.append(" • ".join(auto_fixes))
            status_parts.append(f"{len(validation_issues)} items to review")

            st.warning(f"⚠️ **Ready** - {' • '.join(status_parts)}")
            with st.expander(f"View {len(validation_issues)} items to review"):
                for issue in validation_issues[:15]:
                    st.markdown(f"• {issue}")
                if len(validation_issues) > 15:
                    st.caption(f"...and {len(validation_issues) - 15} more")
        else:
            # All good
            status_parts = [f"{len(df)} assets"]
            if auto_fixes:
                status_parts.append(" • ".join(auto_fixes))
            st.success(f"✅ **Ready to classify** - {' • '.join(status_parts)}")

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

        # Track classification statistics
        assets_classified = 0  # Assets that went through MACRS classification
        disposals_skipped = 0
        transfers_skipped = 0

        # ===================================================================
        # BATCH CLASSIFICATION - 10x faster than individual calls
        # ===================================================================
        # Step 1: Separate assets needing classification vs disposals/transfers
        # Note: "to_classify" includes both existing assets AND new additions
        # (both need MACRS classification, unlike disposals which use historical data)
        to_classify_indices = []
        to_classify_rows = []

        for idx, row in df.iterrows():
            sheet_role = str(row.get("Sheet Role", "")).lower()
            trans_type = str(row.get("Transaction Type", "")).lower()

            is_disposal = any(x in sheet_role for x in ["dispos", "disposal"]) or \
                          any(x in trans_type for x in ["dispos", "disposal"])
            is_transfer = any(x in sheet_role for x in ["transfer", "xfer", "reclass"]) or \
                          any(x in trans_type for x in ["transfer", "xfer", "reclass"])

            if is_disposal:
                df.at[idx, "Final Category"] = ""
                df.at[idx, "MACRS Life"] = ""
                df.at[idx, "Method"] = ""
                df.at[idx, "Convention"] = ""
                df.at[idx, "Source"] = "skipped_disposal"
                df.at[idx, "Confidence"] = ""
                df.at[idx, "Low Confidence"] = False
                df.at[idx, "Notes"] = "Disposal - Classification not needed (use historical data for recapture)"
                disposals_skipped += 1
            elif is_transfer:
                df.at[idx, "Final Category"] = ""
                df.at[idx, "MACRS Life"] = ""
                df.at[idx, "Method"] = ""
                df.at[idx, "Convention"] = ""
                df.at[idx, "Source"] = "skipped_transfer"
                df.at[idx, "Confidence"] = ""
                df.at[idx, "Low Confidence"] = False
                df.at[idx, "Notes"] = "Transfer - Classification not needed (already classified)"
                transfers_skipped += 1
            else:
                to_classify_indices.append(idx)
                to_classify_rows.append(row.to_dict())

        # Step 2: Classify assets (existing + new additions)
        # Use batch if available (10x faster), otherwise individual classification
        if to_classify_rows:
            use_batch = BATCH_CLASSIFICATION_AVAILABLE and classify_assets_batch is not None

            if use_batch:
                if use_progress_bar:
                    progress_bar.progress(0.1)
                    progress_text.text(f"Batch classifying {len(to_classify_rows)} assets...")

                try:
                    batch_results = classify_assets_batch(
                        to_classify_rows,
                        client=client,
                        model="gpt-4o-mini",
                        rules=rules,
                        overrides=overrides,
                        batch_size=30
                    )

                    for idx, final in zip(to_classify_indices, batch_results):
                        df.at[idx, "Final Category"] = final.get("final_class")
                        df.at[idx, "MACRS Life"] = final.get("final_life")
                        df.at[idx, "Method"] = final.get("final_method")
                        df.at[idx, "Convention"] = final.get("final_convention")
                        df.at[idx, "Source"] = final.get("source")
                        df.at[idx, "Confidence"] = final.get("confidence")
                        df.at[idx, "Low Confidence"] = final.get("low_confidence")
                        df.at[idx, "Notes"] = final.get("notes")
                        assets_classified += 1

                    if use_progress_bar:
                        progress_bar.progress(0.8)
                        progress_text.text(f"Classified {assets_classified} assets")

                except Exception as e:
                    log_error_securely(e, "batch classifying assets")
                    st.warning("Batch classification failed, falling back to individual...")
                    use_batch = False  # Fall through to individual classification

            # Individual classification (fallback or if batch not available)
            if not use_batch or assets_classified == 0:
                for i, (idx, row_dict) in enumerate(zip(to_classify_indices, to_classify_rows)):
                    if use_progress_bar and i % 10 == 0:
                        progress = (i / len(to_classify_rows))
                        progress_bar.progress(progress)
                        progress_text.text(f"Classifying {i + 1} of {len(to_classify_rows)} assets...")
                    try:
                        final = classify_asset(row_dict, client=client, model="gpt-4o-mini",
                                              rules=rules, overrides=overrides, strategy=strategy)
                        assets_classified += 1
                    except Exception as e2:
                        log_error_securely(e2, f"classifying asset at index {idx}")
                        final = {"final_class": None, "final_life": None, "final_method": None,
                                "final_convention": None, "source": "error", "confidence": 0.0,
                                "low_confidence": True, "notes": "Classification failed"}

                    df.at[idx, "Final Category"] = final.get("final_class")
                    df.at[idx, "MACRS Life"] = final.get("final_life")
                    df.at[idx, "Method"] = final.get("final_method")
                    df.at[idx, "Convention"] = final.get("final_convention")
                    df.at[idx, "Source"] = final.get("source")
                    df.at[idx, "Confidence"] = final.get("confidence")
                    df.at[idx, "Low Confidence"] = final.get("low_confidence")
                    df.at[idx, "Notes"] = final.get("notes")

        # Show classification summary
        st.write(f"✓ Assets classified: {assets_classified}")
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

    # Perform actual classification (progress is fast, no need for fake bar)
    df = classify_all_transactions(df, tax_year, verbose=False)
    st.write(f"✓ Transaction classification complete for {len(df)} assets")

    # Validate classification
    is_valid, classification_errors = validate_transaction_classification(df, tax_year)

    if not is_valid:
        st.warning(f"⚠️ Found {len(classification_errors)} transaction classification issues")
        for error in classification_errors[:5]:  # Show first 5
            # Format error nicely instead of raw dictionary
            row_num = error.get('row', '?')
            asset_id = error.get('asset_id', 'Unknown')
            desc = error.get('description', '')[:30]  # Truncate long descriptions
            issue = error.get('issue', 'Unknown issue')
            st.write(f"  • **Row {row_num}** ({asset_id}): {issue}")

    # Show summary
    if "Transaction Type" in df.columns:
        trans_counts = df["Transaction Type"].value_counts()
        st.write("\n**Transaction Type Summary:**")
        for trans_type, count in trans_counts.items():
            st.write(f"  • {trans_type}: {count}")

    # Clear progress bar if it was shown
    if use_progress_bar:
        progress_bar.progress(1.0)
        progress_text.text(f"Classification complete: {total_assets} assets processed")

    # Calculate and display time savings
    classification_end_time = time.time()
    classification_duration = classification_end_time - classification_start_time

    # Estimate manual time: ~30 seconds per asset for experienced CPA
    # (looking up IRS tables, determining class, entering data)
    estimated_manual_seconds = len(df) * 30
    time_saved_seconds = max(estimated_manual_seconds - classification_duration, 0)

    # Format times for display
    def format_time(seconds):
        if seconds < 60:
            return f"{seconds:.0f} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} hours"

    # Show prominent time savings display
    st.success(f"✅ Classification complete: {len(df)} assets classified")

    # Time savings metrics in columns
    time_col1, time_col2, time_col3 = st.columns(3)
    with time_col1:
        st.metric("⏱️ AI Time", format_time(classification_duration))
    with time_col2:
        st.metric("📋 Est. Manual Time", format_time(estimated_manual_seconds))
    with time_col3:
        st.metric("💰 Time Saved", format_time(time_saved_seconds), delta=f"{(time_saved_seconds/60):.0f} min")

    # Store for later reference
    st.session_state["classification_duration"] = classification_duration
    st.session_state["time_saved"] = time_saved_seconds

    # Show deduction summary by MACRS class
    with st.expander("💰 Estimated Deductions by Category", expanded=True):
        if "Final Category" in df.columns and "Cost" in df.columns:
            # Replace empty/blank categories with "Unclassified"
            df_for_summary = df.copy()
            df_for_summary["Final Category"] = df_for_summary["Final Category"].fillna("")
            df_for_summary.loc[
                df_for_summary["Final Category"].astype(str).str.strip().isin(["", "nan"]),
                "Final Category"
            ] = "Unclassified"

            # Group by category and sum costs
            category_summary = df_for_summary.groupby("Final Category").agg({
                "Cost": lambda x: pd.to_numeric(x, errors='coerce').sum()
            }).reset_index()
            category_summary.columns = ["Category", "Total Cost"]
            # Filter out zero costs only
            category_summary = category_summary[category_summary["Total Cost"] > 0]
            category_summary = category_summary.sort_values("Total Cost", ascending=False)

            if not category_summary.empty:
                # Show top categories
                summary_col1, summary_col2 = st.columns(2)
                with summary_col1:
                    st.markdown("**By MACRS Category:**")
                    for _, row in category_summary.head(6).iterrows():
                        st.write(f"• {row['Category']}: ${row['Total Cost']:,.0f}")

                with summary_col2:
                    # Count special items
                    qip_count = len(df[df.get("QIP", pd.Series([False])) == True]) if "QIP" in df.columns else 0
                    bonus_count = len(df[df.get("Bonus Eligible", pd.Series([False])) == True]) if "Bonus Eligible" in df.columns else 0

                    st.markdown("**Special Classifications:**")
                    if qip_count > 0:
                        st.write(f"• QIP (15-year): {qip_count} assets")
                    if bonus_count > 0:
                        st.write(f"• Bonus eligible: {bonus_count} assets")

                    # Show transaction type breakdown
                    if "Transaction Type" in df.columns:
                        additions = len(df[df["Transaction Type"].str.contains("Addition|Current", case=False, na=False)])
                        existing = len(df[df["Transaction Type"].str.contains("Existing|Prior", case=False, na=False)])
                        st.write(f"• Current year additions: {additions}")
                        if existing > 0:
                            st.write(f"• Existing assets: {existing}")
        else:
            st.info("Classification details will appear after export generation")

    # Show classified assets preview
    with st.expander("📊 View Classified Assets (First 10 Rows)", expanded=False):
        display_cols = [col for col in ['Asset ID', 'Description', 'Final Category', 'MACRS Life', 'Method', 'Transaction Type'] if col in df.columns]
        st.dataframe(sanitize_dataframe_for_display(df[display_cols].head(10)), use_container_width=True, hide_index=True)

    st.session_state["classified_df"] = df

    # Save classifications to database for management/search functionality
    if DB_AVAILABLE and WorkflowIntegration:
        try:
            integration = WorkflowIntegration()
            saved_count = 0
            for _, row in df.iterrows():
                asset_text = str(row.get("Description", ""))
                if not asset_text or asset_text == "nan":
                    continue

                classification = {
                    "class": row.get("Final Category", ""),
                    "life": row.get("MACRS Life", 0),
                    "method": row.get("Method", ""),
                    "convention": row.get("Convention", "HY"),
                    "bonus": row.get("Bonus Eligible", False),
                    "qip": row.get("QIP", False),
                }

                # Determine source based on how it was classified
                source = "ai"
                if row.get("Override Category") or row.get("Override MACRS Life"):
                    source = "manual"

                confidence = row.get("Confidence", 0.85)

                integration.save_classification(
                    asset_text=asset_text,
                    classification=classification,
                    source=source,
                    confidence_score=float(confidence) if pd.notna(confidence) else 0.85,
                )
                saved_count += 1

            if saved_count > 0:
                st.caption(f"💾 {saved_count} classifications saved to database")
        except Exception as e:
            # Log the error but don't block the workflow
            log_error_securely(e, "saving classifications to database")
            st.caption("⚠️ Could not save to database (non-blocking)")

    # Save client settings if "Remember client settings" is checked
    if st.session_state.get("remember_client", False):
        try:
            # Get the column mappings that were used for this file
            column_mappings = st.session_state.get("detected_column_mappings", {})
            if column_mappings:
                client_id = st.session_state.get("client_id_normalized", client_key.lower().replace(" ", "_"))
                mapping_manager = get_manager()

                # Build filename patterns from uploaded file
                uploaded_filename = st.session_state.get("uploaded_file_name", "")
                filename_patterns = []
                if uploaded_filename:
                    # Extract patterns from filename (e.g., "ABC_FA_2024.xlsx" -> ["ABC"])
                    name_parts = uploaded_filename.replace(".xlsx", "").replace(".xls", "").split("_")
                    if name_parts:
                        filename_patterns = [name_parts[0]]  # Use first part as pattern

                success = mapping_manager.save_client_mapping(
                    client_id=client_id,
                    column_mappings=column_mappings,
                    client_name=client_key,
                    filename_patterns=filename_patterns if filename_patterns else None,
                    notes=f"Auto-saved from classification on {datetime.now().strftime('%Y-%m-%d')}"
                )
                if success:
                    st.caption(f"💾 Client settings saved for **{client_key}**")
        except Exception as e:
            # Non-blocking - just log
            log_error_securely(e, "saving client mappings")


# =====================================================================
# STEP 2: REVIEW & VALIDATION
# =====================================================================

if "classified_df" in st.session_state:

    df = st.session_state["classified_df"]

    st.markdown("---")
    st.markdown("## Step 2: Review Results")

    # Collect validation issues
    all_issues = []
    critical_count = 0
    warning_count = 0
    info_count = 0

    # Validation issues
    try:
        issues, details = validate_assets(df)  # FIXED: Unpack tuple correctly
        if issues:
            if isinstance(issues, list):
                for issue in issues:
                    issue_str = str(issue)
                    # Classify severity based on issue content
                    # Missing cost or classification for ADDITIONS = CRITICAL
                    # Missing dates for additions = CRITICAL
                    # Date inconsistencies, zero costs = WARNING
                    # Note: Transfers don't need classification (already classified)
                    if any(keyword in issue_str.lower() for keyword in ['missing cost', 'missing macrs classification for additions', 'missing in-service']):
                        severity = "CRITICAL"
                    elif 'missing' in issue_str.lower() and 'classification' in issue_str.lower() and 'addition' in issue_str.lower():
                        severity = "CRITICAL"
                    else:
                        severity = "WARNING"

                    all_issues.append({"Severity": severity, "Type": "Validation", "Message": issue_str})
                    if severity == "CRITICAL":
                        critical_count += 1
                    else:
                        warning_count += 1
    except Exception as e:
        error_msg = log_error_securely(e, "validating assets")
        all_issues.append({"Severity": "CRITICAL", "Type": "System", "Message": f"Validation check failed: {error_msg}"})
        critical_count += 1

    # Advanced validation issues
    try:
        adv = advanced_validations(df)
        if adv:
            if isinstance(adv, list):
                for issue in adv:
                    # Format dict issues nicely instead of raw repr
                    if isinstance(issue, dict):
                        row_num = issue.get('row', '?')
                        issue_text = issue.get('issue', 'Unknown issue')
                        formatted_msg = f"Row {row_num}: {issue_text}"
                    else:
                        formatted_msg = str(issue)
                    all_issues.append({"Severity": "WARNING", "Type": "Advanced", "Message": formatted_msg})
                    warning_count += 1
    except Exception as e:
        error_msg = log_error_securely(e, "running advanced validations")
        all_issues.append({"Severity": "WARNING", "Type": "System", "Message": f"Advanced validation failed: {error_msg}"})
        warning_count += 1

    # Outliers - Default to additions only (existing assets were validated in prior years)
    # Check if there are additions to analyze
    has_additions = False
    if "Transaction Type" in df.columns:
        has_additions = df["Transaction Type"].astype(str).str.contains("Current Year Addition", case=False, na=False).any()

    try:
        # Default: analyze additions only (more actionable, less noise)
        # Falls back to all assets if no Transaction Type column exists
        outliers = detect_outliers(df, additions_only=True)

        if isinstance(outliers, pd.DataFrame) and not outliers.empty:
            for _, row in outliers.iterrows():
                asset_id = row.get('Asset ID', row.get('Asset #', 'Unknown'))
                reason = row.get('reason', 'Outlier detected')
                all_issues.append({
                    "Severity": "INFO",
                    "Type": "Outlier (Additions)",
                    "Message": f"Asset {asset_id}: {reason}"
                })
                info_count += 1
        elif has_additions:
            # No outliers found in additions - this is good news, don't add noise
            pass

    except Exception as e:
        error_msg = log_error_securely(e, "detecting outliers")
        all_issues.append({"Severity": "INFO", "Type": "System", "Message": f"Outlier detection failed: {error_msg}"})
        info_count += 1

    total_issues = len(all_issues)

    # Clean validation summary - simple status
    if total_issues == 0:
        st.success("✓ All validations passed - ready to export")
    else:
        # Simple issue summary
        if critical_count > 0:
            st.error(f"⚠️ {critical_count} critical issue(s) must be resolved before export")
        elif warning_count > 0:
            st.warning(f"ℹ️ {warning_count} warning(s) - review recommended")

        # Collapsible details
        with st.expander(f"View Issues ({total_issues})", expanded=critical_count > 0):
            for issue in all_issues:
                if issue["Severity"] == "CRITICAL":
                    st.error(issue["Message"])
                elif issue["Severity"] == "WARNING":
                    st.warning(issue["Message"])
                else:
                    st.info(issue["Message"])

    # Store critical count in session state for export blocking
    st.session_state["critical_issue_count"] = critical_count

    # =========================================================================
    # SIMPLE DATA QUALITY SUMMARY (replaces 5-tab dashboard)
    # =========================================================================

    # Run validations silently to get status
    quality_grade = "?"
    quality_ready = True
    tax_issues = 0
    confidence_ok = True
    rollforward_balanced = True

    try:
        tax_year = st.session_state.get("tax_year", date.today().year)
        quality_score = calculate_data_quality_score(df, tax_year=tax_year)
        quality_grade = quality_score.grade
        quality_ready = quality_score.is_export_ready
        st.session_state["quality_grade"] = quality_grade
        st.session_state["quality_export_ready"] = quality_ready
    except:
        pass

    try:
        verification_issues, verification_summary = verify_classifications(df, tax_year=tax_year)
        tax_issues = verification_summary.get("critical_count", 0)
        st.session_state["tax_verification_critical"] = tax_issues
    except:
        pass

    try:
        confidence_result = check_confidence_gate(df)
        confidence_ok = confidence_result.passed
        st.session_state["confidence_gate_passed"] = confidence_ok
    except:
        pass

    try:
        rollforward_result = reconcile_rollforward(df)
        rollforward_balanced = rollforward_result.is_balanced
    except:
        pass

    # Single status card
    all_good = quality_ready and tax_issues == 0 and confidence_ok and rollforward_balanced

    if all_good:
        st.success(f"✅ **Ready to export** — Grade: {quality_grade}")
    else:
        issues = []
        if not quality_ready:
            issues.append(f"Quality: {quality_grade}")
        if tax_issues > 0:
            issues.append(f"{tax_issues} tax issues")
        if not confidence_ok:
            issues.append("Low confidence")
        if not rollforward_balanced:
            issues.append("Rollforward imbalance")

        st.warning(f"⚠️ **Review needed** — {', '.join(issues)}")

    # Detailed dashboard hidden by default
    with st.expander("📊 Detailed Quality Analysis", expanded=False):
        detail_tabs = st.tabs(["Quality", "Tax", "Confidence", "Rollforward"])

        with detail_tabs[0]:
            try:
                grade_colors = {"A": "🟢", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"}
                st.metric("Grade", f"{grade_colors.get(quality_grade, '⚪')} {quality_grade}")
                if quality_score and quality_score.recommendations:
                    for rec in quality_score.recommendations[:3]:
                        st.caption(f"• {rec}")
            except:
                st.caption("Quality check unavailable")

        with detail_tabs[1]:
            try:
                if tax_issues > 0:
                    st.error(f"{tax_issues} critical tax issues")
                    for issue in verification_issues[:5]:
                        if issue.severity == "CRITICAL":
                            st.caption(f"• {issue.asset_id}: {issue.message}")
                else:
                    st.success("✓ No tax issues")
            except:
                st.caption("Tax verification unavailable")

        with detail_tabs[2]:
            try:
                if confidence_ok:
                    st.success(f"✓ Avg confidence: {confidence_result.average_confidence:.0%}")
                else:
                    st.warning(f"Low confidence: {confidence_result.low_confidence_count} assets need review")
                    override = st.checkbox("Override (I've reviewed)", key="confidence_override")
                    st.session_state["confidence_gate_override"] = override
            except:
                st.caption("Confidence check unavailable")

        with detail_tabs[3]:
            try:
                existing_count = rollforward_result.details.get('existing_count', 0)
                additions_count = rollforward_result.details.get('additions_count', 0)
                disposals_count = rollforward_result.details.get('disposals_count', 0)

                st.caption(f"{existing_count} existing • {additions_count} additions • {disposals_count} disposals")

                if rollforward_balanced:
                    st.success(f"✓ Balanced — Ending: ${rollforward_result.expected_ending:,.0f}")
                else:
                    st.error(f"Out of balance by ${rollforward_result.variance:,.2f}")
            except:
                st.caption("Rollforward unavailable")

    # =========================================================================
    # END DATA QUALITY SUMMARY
    # =========================================================================

    # Review & Edit Classifications
    # Initialize expander state if not exists (keeps it open when filters change)
    if "edit_classifications_expanded" not in st.session_state:
        st.session_state["edit_classifications_expanded"] = False

    with st.expander("📝 Review & Edit Classifications", expanded=st.session_state["edit_classifications_expanded"]):
        # Mark as expanded once user opens it (so it stays open during filter changes)
        st.session_state["edit_classifications_expanded"] = True
        st.caption("Filter, review, and override AI classifications as needed")
        df_review = st.session_state["classified_df"].copy()

        for col in ["Override Category", "Override MACRS Life", "Override Method", "Override Convention"]:
            if col not in df_review.columns:
                df_review[col] = ""

        # Simple filter
        filter_cols = st.columns(6)
        show_all = filter_cols[0].checkbox("All", value=True, key="filter_all")
        show_additions = filter_cols[1].checkbox("Additions", key="filter_additions")
        show_existing = filter_cols[2].checkbox("Existing", key="filter_existing")
        show_disposals = filter_cols[3].checkbox("Disposals", key="filter_disposals")
        show_transfers = filter_cols[4].checkbox("Transfers", key="filter_transfers")
        show_warnings = filter_cols[5].checkbox("Issues", key="filter_warnings")

        # Apply filters
        display_df = df_review.copy()

        # Format date columns to MM/DD/YYYY for FA CS compatibility
        def parse_flexible_date(val):
            """Parse dates including compact formats like 050225 or 03012025."""
            if pd.isna(val) or val == '' or val is None:
                return ''
            val_str = str(val).strip()
            if val_str == '':
                return ''

            # Try standard pandas parsing first
            try:
                parsed = pd.to_datetime(val, errors='coerce')
                if pd.notna(parsed):
                    return parsed.strftime('%m/%d/%Y')
            except (ValueError, TypeError, AttributeError):
                pass

            # Handle compact formats: MMDDYY or MMDDYYYY (digits only)
            digits_only = ''.join(c for c in val_str if c.isdigit())
            if len(digits_only) == 6:  # MMDDYY format
                try:
                    parsed = pd.to_datetime(digits_only, format='%m%d%y', errors='coerce')
                    if pd.notna(parsed):
                        return parsed.strftime('%m/%d/%Y')
                except (ValueError, TypeError, AttributeError):
                    pass
            elif len(digits_only) == 8:  # MMDDYYYY format
                try:
                    parsed = pd.to_datetime(digits_only, format='%m%d%Y', errors='coerce')
                    if pd.notna(parsed):
                        return parsed.strftime('%m/%d/%Y')
                except (ValueError, TypeError, AttributeError):
                    pass

            # Return original if can't parse
            return val_str

        date_columns = ["Acquisition Date", "In Service Date", "Disposal Date", "Transfer Date", "disposal_date"]
        for col in date_columns:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(parse_flexible_date)

        if not show_all:
            filters = []
            if show_additions and "Transaction Type" in display_df.columns:
                filters.append(display_df["Transaction Type"].str.contains("Addition", case=False, na=False))
            if show_existing and "Transaction Type" in display_df.columns:
                filters.append(display_df["Transaction Type"].str.contains("Existing", case=False, na=False))
            if show_disposals and "Transaction Type" in display_df.columns:
                filters.append(display_df["Transaction Type"].str.contains("Disposal", case=False, na=False))
            if show_transfers and "Transaction Type" in display_df.columns:
                filters.append(display_df["Transaction Type"].str.contains("Transfer", case=False, na=False))
            if show_warnings and "Final Category" in display_df.columns:
                filters.append((display_df["Final Category"].isna()) | (display_df["Final Category"] == ""))
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter | f
                display_df = display_df[combined_filter]

        st.caption(f"{len(display_df)} of {len(df_review)} assets")

        # Quick Rules Section - Apply rules by Client Category
        st.markdown("##### Quick Rules")
        st.caption("Apply classification rules by Client Category (affects ALL matching assets)")

        # Get unique client categories from the data
        client_cats = []
        if "Client Category" in df_review.columns:
            client_cats = sorted(df_review["Client Category"].dropna().unique().tolist())

        if client_cats:
            rule_cols = st.columns([2, 2, 1, 1, 1, 1])

            rule_source_cat = rule_cols[0].selectbox(
                "When Client Category =",
                [""] + client_cats,
                key="rule_source_cat",
                help="Select a client category to reclassify"
            )

            rule_target_cat = rule_cols[1].selectbox(
                "Set MACRS Category to",
                [""] + sorted([
                    "Computer Equipment", "Office Furniture", "Machinery & Equipment",
                    "Passenger Automobile", "Trucks & Trailers", "Leasehold Improvements",
                    "Qualified Improvement Property", "Land Improvements",
                    "Nonresidential Real Property", "Residential Rental Property", "Land", "Software"
                ]),
                key="rule_target_cat"
            )

            rule_life = rule_cols[2].selectbox("Life", ["Auto", 3, 5, 7, 10, 15, 20, 27.5, 39], key="rule_life")
            rule_method = rule_cols[3].selectbox("Method", ["Auto", "200DB", "150DB", "SL"], key="rule_method")

            # Show how many assets would be affected
            if rule_source_cat:
                match_count = len(df_review[df_review["Client Category"] == rule_source_cat])
                rule_cols[4].metric("Matches", match_count)

            if rule_cols[5].button("Apply Rule", type="secondary", key="apply_rule"):
                if rule_source_cat and rule_target_cat:
                    # Define default life/method for each category
                    category_defaults = {
                        "Computer Equipment": (5, "200DB"),
                        "Office Furniture": (7, "200DB"),
                        "Machinery & Equipment": (7, "200DB"),
                        "Passenger Automobile": (5, "200DB"),
                        "Trucks & Trailers": (5, "200DB"),
                        "Leasehold Improvements": (15, "SL"),
                        "Qualified Improvement Property": (15, "SL"),
                        "Land Improvements": (15, "150DB"),
                        "Nonresidential Real Property": (39, "SL"),
                        "Residential Rental Property": (27.5, "SL"),
                        "Land": (None, None),
                        "Software": (3, "SL"),
                    }

                    default_life, default_method = category_defaults.get(rule_target_cat, (7, "200DB"))
                    apply_life = default_life if rule_life == "Auto" else rule_life
                    apply_method = default_method if rule_method == "Auto" else rule_method

                    # Apply to all matching rows
                    mask = df_review["Client Category"] == rule_source_cat
                    affected_count = mask.sum()

                    df_review.loc[mask, "Override Category"] = rule_target_cat
                    if apply_life:
                        df_review.loc[mask, "Override MACRS Life"] = apply_life
                    if apply_method:
                        df_review.loc[mask, "Override Method"] = apply_method
                    df_review.loc[mask, "Override Convention"] = "MM" if rule_target_cat in ["Nonresidential Real Property", "Residential Rental Property"] else "HY"

                    st.session_state["classified_df"] = df_review
                    st.success(f"Applied rule: '{rule_source_cat}' → {rule_target_cat} ({affected_count} assets)")
                    st.rerun()
                else:
                    st.warning("Select both source category and target classification")
        else:
            st.info("No Client Category data available for quick rules")

        st.markdown("---")

        # Bulk Override Section
        st.markdown("##### Bulk Override")
        st.caption("Apply the same classification to all filtered assets at once")

        bulk_cols = st.columns(5)
        bulk_category = bulk_cols[0].selectbox(
            "Category",
            [""] + sorted([
                "Computer Equipment", "Office Furniture", "Machinery & Equipment",
                "Passenger Automobile", "Trucks & Trailers", "Leasehold Improvements",
                "Qualified Improvement Property", "Land Improvements",
                "Nonresidential Real Property", "Residential Rental Property", "Land"
            ]),
            key="bulk_category"
        )
        bulk_life = bulk_cols[1].selectbox(
            "MACRS Life",
            ["", 3, 5, 7, 10, 15, 20, 27.5, 39],
            key="bulk_life"
        )
        bulk_method = bulk_cols[2].selectbox(
            "Method",
            ["", "200DB", "150DB", "SL"],
            key="bulk_method"
        )
        bulk_convention = bulk_cols[3].selectbox(
            "Convention",
            ["", "HY", "MQ", "MM"],
            key="bulk_convention"
        )

        if bulk_cols[4].button("Apply to Filtered", type="secondary"):
            if bulk_category or bulk_life or bulk_method or bulk_convention:
                # Apply bulk override to filtered rows
                for idx in display_df.index:
                    if bulk_category:
                        df_review.at[idx, "Override Category"] = bulk_category
                    if bulk_life:
                        df_review.at[idx, "Override MACRS Life"] = bulk_life
                    if bulk_method:
                        df_review.at[idx, "Override Method"] = bulk_method
                    if bulk_convention:
                        df_review.at[idx, "Override Convention"] = bulk_convention

                st.session_state["classified_df"] = df_review
                st.success(f"Applied bulk override to {len(display_df)} assets")
                st.rerun()
            else:
                st.warning("Select at least one field to override")

        st.markdown("---")

        # Show transfer-specific info when filtering by transfers
        if show_transfers and not show_all:
            transfer_cols = ["Transfer Date", "From Location", "To Location", "From Department", "To Department", "Transfer Type", "Old Category"]
            available_transfer_cols = [c for c in transfer_cols if c in display_df.columns]
            missing_transfer_cols = [c for c in transfer_cols if c not in display_df.columns]

            if available_transfer_cols:
                st.info(f"Transfer columns found: {', '.join(available_transfer_cols)}")
            if missing_transfer_cols:
                st.warning(f"Transfer columns not in data: {', '.join(missing_transfer_cols)}. Consider adding these columns to your source data for complete transfer tracking.")

        # Sanitize for PyArrow display (prevents ArrowInvalid errors with mixed-type columns)
        editor_data = sanitize_dataframe_for_display(display_df if not show_all else df_review)
        edited_df = st.data_editor(editor_data, key="review_editor", use_container_width=True, height=600)

        if st.button("Apply Overrides", type="primary"):
            # CRITICAL: Apply edits to the FULL df_review, not replace with filtered subset
            # Update only the rows that were edited, preserving all other data
            full_df = df_review.copy()

            # Apply edits from the data_editor to the corresponding rows in full_df
            for idx in edited_df.index:
                if idx in full_df.index:
                    for col in edited_df.columns:
                        full_df.at[idx, col] = edited_df.at[idx, col]

            st.session_state["classified_df"] = full_df
            overrides = load_overrides()
            by_id = overrides.get("by_asset_id", {}) or {}
            override_count = 0

            for _, r in edited_df.iterrows():
                asset_id = r.get("Asset ID")
                if not asset_id or pd.isna(asset_id):
                    continue
                oc = (r.get("Override Category") or "").strip()
                olife = r.get("Override MACRS Life")
                omethod = (r.get("Override Method") or "").strip()
                oconv = (r.get("Override Convention") or "").strip()
                if not oc and pd.isna(olife) and not omethod and not oconv:
                    continue
                mapping = {
                    "class": oc or r.get("Final Category"),
                    "life": olife if pd.notna(olife) else r.get("MACRS Life"),
                    "method": omethod or r.get("Method"),
                    "convention": oconv or r.get("Convention"),
                    "bonus": False, "qip": False,
                }
                by_id[str(asset_id)] = mapping
                override_count += 1

            overrides["by_asset_id"] = by_id
            save_overrides(overrides)
            if "fa_preview" in st.session_state:
                del st.session_state["fa_preview"]
            if override_count > 0:
                st.success(f"Applied {override_count} overrides")
            else:
                st.info("No overrides")
            st.rerun()

    # Export Preview
    st.markdown("#### Export Preview")

    # Generate preview if not already cached
    if "fa_preview" not in st.session_state:
        with st.spinner("⏳ Preparing export preview..."):
            try:
                # Validate data before processing
                if df is None or df.empty:
                    st.error("❌ No classified data available. Please complete classification first.")
                    st.session_state["fa_preview"] = None
                else:
                    from logic.fa_export import build_fa
                    asset_number_start = st.session_state.get("asset_number_start", 1)
                    preview_df = build_fa(
                        df=df,
                        tax_year=tax_year,
                        strategy=strategy,
                        taxable_income=taxable_income,
                        use_acq_if_missing=use_acq_if_missing,
                        de_minimis_limit=de_minimis_limit,
                        section_179_carryforward_from_prior_year=section_179_carryforward,
                        asset_number_start=asset_number_start,
                    )

                    # Add materiality scoring for review prioritization
                    try:
                        preview_df = compute_materiality(preview_df)
                    except Exception as mat_err:
                        # Don't block on materiality calculation failure
                        pass

                    st.session_state["fa_preview"] = preview_df
                    st.session_state["fa_preview_generated_at"] = datetime.now()
            except ValueError as e:
                # Data validation errors - show helpful message
                if "CRITICAL data validation errors" in str(e):
                    st.error("❌ Cannot generate export due to data validation errors")
                    st.warning("""
                    **Common issues:**
                    - Missing required column: "Final Category" - Run classification first (Step 4)
                    - Missing required column: "Transaction Type" - Classification incomplete
                    - Missing dates or costs
                    - Invalid data formats

                    **To fix:**
                    1. Make sure you completed Step 4 (Classification) successfully
                    2. Check Step 5 (Validation) for data quality issues
                    3. Fix any critical issues in your data
                    """)
                    with st.expander("🔍 Technical Details", expanded=False):
                        st.code(f"Error: {str(e)}", language="text")
                else:
                    error_msg = log_error_securely(e, "generating export preview")
                    st.error(f"Failed to generate export preview: {error_msg}")
                    with st.expander("🔍 Technical Details", expanded=False):
                        error_id = st.session_state.get("last_error_id", "N/A")
                        st.code(f"Error ID: {error_id}\nError type: {type(e).__name__}\nError message: {str(e)}", language="text")
                st.session_state["fa_preview"] = None
            except Exception as e:
                error_msg = log_error_securely(e, "generating export preview")
                st.error(f"Failed to generate export preview: {error_msg}")
                # Show detailed error for debugging
                with st.expander("🔍 Technical Details", expanded=False):
                    error_id = st.session_state.get("last_error_id", "N/A")
                    st.code(f"Error ID: {error_id}\nError type: {type(e).__name__}\nError message: {str(e)}", language="text")
                st.session_state["fa_preview"] = None

    if st.session_state.get("fa_preview") is not None:
        preview_df = st.session_state["fa_preview"]

        st.markdown("---")
        st.markdown("## Step 3: Export")

        # =====================================================================
        # CALCULATE ALL METRICS UPFRONT
        # =====================================================================
        has_trans_type = "Transaction Type" in preview_df.columns
        if has_trans_type:
            trans_type_col = preview_df["Transaction Type"].astype(str)
            is_disposal = trans_type_col.str.contains("Disposal", case=False, na=False)
            is_addition = trans_type_col.str.contains("Current Year Addition", case=False, na=False)
            addition_cost = pd.to_numeric(preview_df.loc[is_addition, "Tax Cost"], errors='coerce').fillna(0).sum() if "Tax Cost" in preview_df.columns else 0
            addition_count = is_addition.sum()
        else:
            addition_cost = pd.to_numeric(preview_df.get("Tax Cost", pd.Series([0.0])), errors='coerce').fillna(0).sum()
            addition_count = len(preview_df)

        total_sec179 = pd.to_numeric(preview_df.get("Tax Sec 179 Expensed", pd.Series([0.0])), errors='coerce').fillna(0).sum()
        total_year1_depr = pd.to_numeric(preview_df.get("Tax Cur Depreciation", pd.Series([0.0])), errors='coerce').fillna(0).sum()
        total_bonus = pd.to_numeric(preview_df.get("Bonus Amount", pd.Series([0.0])), errors='coerce').fillna(0).sum()
        total_de_minimis = pd.to_numeric(preview_df.get("De Minimis Expensed", pd.Series([0.0])), errors='coerce').fillna(0).sum()
        total_year1_deduction = total_sec179 + total_bonus + total_year1_depr + total_de_minimis

        # Count review items
        nbv_issues = len(preview_df[preview_df.get("NBV_Reco", "") == "CHECK"]) if "NBV_Reco" in preview_df.columns else 0
        high_priority = len(preview_df[preview_df.get("ReviewPriority", "") == "High"]) if "ReviewPriority" in preview_df.columns else 0
        low_confidence = len(preview_df[preview_df.get("ConfidenceGrade", "") == "C"]) if "ConfidenceGrade" in preview_df.columns else 0
        total_review_items = nbv_issues + high_priority + low_confidence

        # Calculate confidence breakdown
        total_assets = len(preview_df)
        if "ConfidenceGrade" in preview_df.columns:
            grade_a = len(preview_df[preview_df["ConfidenceGrade"] == "A"])
            grade_b = len(preview_df[preview_df["ConfidenceGrade"] == "B"])
            grade_c = len(preview_df[preview_df["ConfidenceGrade"] == "C"])
            pct_high = ((grade_a + grade_b) / total_assets * 100) if total_assets > 0 else 0
        else:
            grade_a, grade_b, grade_c = 0, 0, 0
            pct_high = 0

        # =====================================================================
        # STATUS CARD - Clear visual indicator
        # =====================================================================
        if total_review_items == 0:
            st.success(f"**Ready to Export** — {len(preview_df)} assets, ${total_year1_deduction:,.0f} total deduction")
        elif total_review_items <= 3:
            st.warning(f"**Review Recommended** — {total_review_items} item(s) to check before export")
        else:
            st.error(f"**Review Required** — {total_review_items} items need attention")

        # =====================================================================
        # KEY METRICS - 2 rows for clarity
        # =====================================================================
        col1, col2, col3 = st.columns(3)
        col1.metric("Assets", f"{len(preview_df)}", help=f"Additions: {addition_count}")
        col2.metric("Additions Cost", f"${addition_cost:,.0f}")
        col3.metric(f"**{tax_year} Deduction**", f"${total_year1_deduction:,.0f}", help="§179 + Bonus + MACRS + De Minimis")

        # Deduction breakdown (small text)
        if total_de_minimis > 0 or total_sec179 > 0 or total_bonus > 0:
            breakdown_parts = []
            if total_sec179 > 0:
                breakdown_parts.append(f"§179: ${total_sec179:,.0f}")
            if total_bonus > 0:
                breakdown_parts.append(f"Bonus: ${total_bonus:,.0f}")
            if total_year1_depr > 0:
                breakdown_parts.append(f"MACRS: ${total_year1_depr:,.0f}")
            if total_de_minimis > 0:
                breakdown_parts.append(f"De Minimis: ${total_de_minimis:,.0f}")
            st.caption(" | ".join(breakdown_parts))

        # Confidence summary (help CPAs understand classification quality)
        if "ConfidenceGrade" in preview_df.columns and total_assets > 0:
            conf_color = "green" if pct_high >= 90 else ("orange" if pct_high >= 70 else "red")
            st.caption(f"Classification Confidence: **{pct_high:.0f}%** high (A: {grade_a}, B: {grade_b}, C: {grade_c})")

        # =====================================================================
        # ACTION ITEMS - Show only if there are issues
        # =====================================================================
        if total_review_items > 0:
            st.markdown("#### Items to Review")
            review_items = []
            if nbv_issues > 0:
                review_items.append(f"• **{nbv_issues}** NBV out of balance")
            if high_priority > 0:
                review_items.append(f"• **{high_priority}** high materiality assets")
            if low_confidence > 0:
                review_items.append(f"• **{low_confidence}** low confidence classifications")

            for item in review_items:
                st.markdown(item)

            # Show the actual items needing review
            with st.expander("View Items Needing Review"):
                review_mask = pd.Series([False] * len(preview_df))
                if "NBV_Reco" in preview_df.columns:
                    review_mask |= (preview_df["NBV_Reco"] == "CHECK")
                if "ReviewPriority" in preview_df.columns:
                    review_mask |= (preview_df["ReviewPriority"] == "High")
                if "ConfidenceGrade" in preview_df.columns:
                    review_mask |= (preview_df["ConfidenceGrade"] == "C")

                if review_mask.any():
                    review_cols = [c for c in ["Asset #", "Description", "Tax Cost", "NBV_Reco", "ReviewPriority", "ConfidenceGrade", "ClassificationExplanation"] if c in preview_df.columns]
                    st.dataframe(sanitize_dataframe_for_display(preview_df.loc[review_mask, review_cols]), use_container_width=True, hide_index=True)
                    st.caption("ClassificationExplanation shows why each asset was classified - helps identify potential issues.")

        # =====================================================================
        # DATA PREVIEW - Collapsed
        # =====================================================================
        with st.expander("View All Export Data"):
            # Core fields plus incentive amounts (helps CPAs verify deductions)
            preview_cols = [c for c in [
                "Asset #", "Description", "Tax Cost", "Tax Life", "Tax Method", "Transaction Type",
                "Tax Sec 179 Expensed", "Bonus Amount", "Tax Cur Depreciation", "De Minimis Expensed"
            ] if c in preview_df.columns]
            st.dataframe(sanitize_dataframe_for_display(preview_df[preview_cols]), use_container_width=True, hide_index=True)
            st.caption(f"Total: {len(preview_df)} assets | §179: ${total_sec179:,.0f} | Bonus: ${total_bonus:,.0f} | MACRS: ${total_year1_depr:,.0f}")


# =====================================================================
# EXPORT
# =====================================================================

if "classified_df" in st.session_state:

    st.markdown("### Export")

    # Comprehensive pre-export validation using export_qa_validator
    from logic.export_qa_validator import validate_fixed_asset_cs_export

    validation_passed = True
    validation_errors = []
    validation_summary = {}

    if "fa_preview" in st.session_state and st.session_state["fa_preview"] is not None:
        preview_df = st.session_state["fa_preview"]
        validation_passed, validation_errors, validation_summary = validate_fixed_asset_cs_export(
            preview_df, verbose=False
        )

        critical_count = validation_summary.get("CRITICAL", 0)
        error_count = validation_summary.get("ERROR", 0)
        warning_count = validation_summary.get("WARNING", 0)

        if validation_passed:
            if warning_count > 0:
                st.success(f"**FA CS Compatible** — {warning_count} warning(s) to review")
            else:
                st.success("**FA CS Compatible** — Ready for export")
        else:
            st.error(f"**Validation Failed** — {critical_count} critical, {error_count} error(s)")

            # Show validation errors in expander
            with st.expander("View Validation Issues", expanded=True):
                critical_errors = [e for e in validation_errors if e.severity == "CRITICAL"]
                other_errors = [e for e in validation_errors if e.severity == "ERROR"]
                warnings = [e for e in validation_errors if e.severity == "WARNING"]

                if critical_errors:
                    st.markdown("**🔴 Critical (must fix):**")
                    for e in critical_errors[:5]:
                        st.markdown(f"- {e.message}" + (f" [Row {e.row_index + 2}]" if e.row_index is not None else ""))
                    if len(critical_errors) > 5:
                        st.caption(f"... and {len(critical_errors) - 5} more")

                if other_errors:
                    st.markdown("**❌ Errors (should fix):**")
                    for e in other_errors[:5]:
                        st.markdown(f"- {e.message}" + (f" [Row {e.row_index + 2}]" if e.row_index is not None else ""))
                    if len(other_errors) > 5:
                        st.caption(f"... and {len(other_errors) - 5} more")

                if warnings:
                    st.markdown("**⚠️ Warnings (review):**")
                    for e in warnings[:3]:
                        st.markdown(f"- {e.message}" + (f" [Row {e.row_index + 2}]" if e.row_index is not None else ""))
                    if len(warnings) > 3:
                        st.caption(f"... and {len(warnings) - 3} more")
    else:
        st.warning("Generate preview first")
        validation_passed = False

    # =========================================================================
    # PRIOR YEAR COMPARISON (Optional but recommended)
    # =========================================================================
    with st.expander("📅 Prior Year Comparison (Recommended)", expanded=False):
        st.caption("Upload prior year FA CS export to reconcile and catch missing assets")

        prior_year_file = st.file_uploader(
            "Upload Prior Year FA CS Export",
            type=["xlsx", "xls"],
            key="prior_year_upload",
            help="Upload the prior year Fixed Asset CS export to reconcile against current year"
        )

        if prior_year_file:
            try:
                prior_df = pd.read_excel(prior_year_file)
                st.success(f"✅ Loaded {len(prior_df)} prior year assets")

                # Run reconciliation
                current_df = st.session_state.get("fa_preview", st.session_state.get("classified_df"))

                if current_df is not None:
                    recon_issues, recon_summary = reconcile_to_prior_year(current_df, prior_df)

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Matched", recon_summary["matched_count"])
                    col2.metric("Missing", recon_summary["missing_count"],
                               delta_color="inverse" if recon_summary["missing_count"] > 0 else "off")
                    col3.metric("New", recon_summary["new_count"])
                    col4.metric("Changed", recon_summary["changed_count"],
                               delta_color="inverse" if recon_summary["changed_count"] > 0 else "off")

                    if recon_summary["reconciled"]:
                        st.success("✅ Prior year reconciled successfully")
                    else:
                        st.error("❌ Prior year reconciliation has issues")

                    # Show critical issues
                    critical_recon = [i for i in recon_issues if i.severity == "CRITICAL"]
                    if critical_recon:
                        st.error(f"**{len(critical_recon)} Critical Issues:**")
                        for issue in critical_recon[:5]:
                            st.markdown(f"- **{issue.asset_id}**: {issue.message}")
                            st.caption(f"  Prior: {issue.prior_value} → Current: {issue.current_value}")

                    # Cost reconciliation
                    is_reconciled, cost_details = reconcile_cost_totals(current_df, prior_df)
                    if not is_reconciled:
                        st.warning(
                            f"Cost variance: ${cost_details['variance']:,.2f}\n"
                            f"Prior ending: ${cost_details['prior_ending']:,.2f} + "
                            f"Additions: ${cost_details['additions']:,.2f} - "
                            f"Disposals: ${cost_details['disposals']:,.2f} = "
                            f"Expected: ${cost_details['expected_current']:,.2f} vs "
                            f"Actual: ${cost_details['actual_current']:,.2f}"
                        )

                    st.session_state["prior_year_reconciled"] = recon_summary["reconciled"]
                    st.session_state["prior_year_critical"] = len(critical_recon)

            except Exception as e:
                st.error(f"Error loading prior year file: {str(e)[:100]}")
        else:
            st.info("💡 Upload prior year FA CS export to verify no assets are missing")
            st.session_state["prior_year_reconciled"] = True  # No file = no comparison
            st.session_state["prior_year_critical"] = 0

    # =========================================================================
    # SECTION 179 INCOME LIMITATION WARNING
    # =========================================================================
    if "fa_preview" in st.session_state and st.session_state["fa_preview"] is not None:
        preview_df = st.session_state["fa_preview"]

        # Calculate total Section 179 elected
        section_179_col = None
        for col in ["Tax Sec 179 Expensed", "Section 179", "Sec 179"]:
            if col in preview_df.columns:
                section_179_col = col
                break

        if section_179_col:
            total_179_elected = pd.to_numeric(preview_df[section_179_col], errors='coerce').fillna(0).sum()

            if total_179_elected > 0:
                # Check income limitation
                sec_179_result = calculate_section_179_with_income_limit(
                    section_179_elected=total_179_elected,
                    taxable_business_income=taxable_income,
                    carryforward_from_prior_years=section_179_carryforward
                )

                if sec_179_result["limitation_applied"]:
                    st.warning(f"""
**⚠️ Section 179 Income Limitation Warning**

§179 deduction is limited by taxable business income (IRC §179(b)(3)):

| | Amount |
|---|---:|
| §179 Elected This Year | ${total_179_elected:,.0f} |
| + Prior Year Carryforward | ${section_179_carryforward:,.0f} |
| = Total Available | ${sec_179_result['total_elected']:,.0f} |
| Taxable Business Income | ${taxable_income:,.0f} |
| **Allowed Deduction** | **${sec_179_result['current_year_deduction']:,.0f}** |
| **Carryforward to Next Year** | **${sec_179_result['carryforward_to_next_year']:,.0f}** |

💡 *Track this carryforward for next year's Form 4562, Part I, Line 13*
                    """)
                    st.session_state["sec_179_carryforward_warning"] = True
                else:
                    st.success(f"✓ §179 deduction (${total_179_elected:,.0f}) within taxable income limit")
                    st.session_state["sec_179_carryforward_warning"] = False

    # Audit info (collapsed)
    with st.expander("Audit Info"):
        col1, col2 = st.columns(2)
        preparer_name = col1.text_input("Preparer", key="preparer_input")
        reviewer_name = col2.text_input("Reviewer", key="reviewer_input")
        st.session_state["audit_info"] = {"preparer_name": preparer_name, "reviewer_name": reviewer_name}

    # =========================================================================
    # ENHANCED EXPORT BLOCKING (Uses all validation systems)
    # =========================================================================
    critical_count = st.session_state.get("critical_issue_count", 0)
    tax_critical = st.session_state.get("tax_verification_critical", 0)
    prior_year_critical = st.session_state.get("prior_year_critical", 0)
    confidence_passed = st.session_state.get("confidence_gate_passed", True)
    confidence_override = st.session_state.get("confidence_gate_override", False)
    quality_export_ready = st.session_state.get("quality_export_ready", True)

    # Calculate total blocking issues
    total_blocking = critical_count + tax_critical + prior_year_critical
    confidence_blocked = not confidence_passed and not confidence_override

    has_blocking_issues = total_blocking > 0 or not validation_passed or confidence_blocked or not quality_export_ready

    if has_blocking_issues:
        # Build detailed blocking message
        blocking_reasons = []
        if not validation_passed:
            blocking_reasons.append("FA CS format validation failed")
        if critical_count > 0:
            blocking_reasons.append(f"{critical_count} data validation issue(s)")
        if tax_critical > 0:
            blocking_reasons.append(f"{tax_critical} tax verification issue(s)")
        if prior_year_critical > 0:
            blocking_reasons.append(f"{prior_year_critical} prior year reconciliation issue(s)")
        if confidence_blocked:
            blocking_reasons.append("Low classification confidence (override or review required)")
        if not quality_export_ready:
            blocking_reasons.append(f"Quality grade not export-ready (Grade: {st.session_state.get('quality_grade', '?')})")

        st.error("**EXPORT BLOCKED**")
        for reason in blocking_reasons:
            st.markdown(f"- {reason}")
        st.caption("Expand 'Detailed Quality Analysis' above for more info")
        export_disabled = True
    else:
        export_disabled = False
        # Show validation summary
        quality_grade = st.session_state.get("quality_grade", "?")
        st.success(f"✅ All validations passed | Quality Grade: {quality_grade}")

    # Simple confirmation checkbox
    ready_to_export = st.checkbox("Reviewed and ready to export", value=False, disabled=export_disabled)

    # Generate button
    force_regenerate = st.checkbox("Regenerate from current data", value=False, disabled=export_disabled)

    if st.button("📊 Generate Depreciation Report", type="primary", disabled=(not ready_to_export or export_disabled)):
        df = st.session_state["classified_df"]

        try:
            if df is None or df.empty:
                st.error("No classified data available")
            else:
                use_cache = ("fa_preview" in st.session_state and st.session_state["fa_preview"] is not None and not force_regenerate)

                if use_cache:
                    fa_df = st.session_state["fa_preview"]
                else:
                    with st.spinner("Generating..."):
                        from logic.fa_export import build_fa
                        asset_number_start = st.session_state.get("asset_number_start", 1)
                        fa_df = build_fa(df=df, tax_year=tax_year, strategy=strategy, taxable_income=taxable_income,
                                        use_acq_if_missing=use_acq_if_missing, de_minimis_limit=de_minimis_limit,
                                        section_179_carryforward_from_prior_year=section_179_carryforward,
                                        asset_number_start=asset_number_start)

                from logic.fa_export import export_fa_excel
                audit_info = st.session_state.get("audit_info", {})
                # Add processing metadata for audit trail
                audit_info.update({
                    "source_file": st.session_state.get("uploaded_file_name", ""),
                    "source_file_checksum": st.session_state.get("uploaded_file_checksum", ""),
                    "tool_version": "1.0.0",
                    "processing_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "tax_year": str(tax_year),
                    "strategy": strategy,
                })
                outfile = export_fa_excel(fa_df, audit_info=audit_info)

                # Generate descriptive filename
                client_key_safe = st.session_state.get("client_key", "Client").replace(" ", "_")
                filename = f"Depreciation_Report_{client_key_safe}_{tax_year}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

                # Calculate totals for summary (use pd.to_numeric to handle mixed types)
                total_cost = pd.to_numeric(fa_df.get("Tax Cost", pd.Series([0.0])), errors='coerce').fillna(0).sum()
                total_deduction = (
                    pd.to_numeric(fa_df.get("Tax Sec 179 Expensed", pd.Series([0.0])), errors='coerce').fillna(0).sum() +
                    pd.to_numeric(fa_df.get("Bonus Amount", pd.Series([0.0])), errors='coerce').fillna(0).sum() +
                    pd.to_numeric(fa_df.get("Tax Cur Depreciation", pd.Series([0.0])), errors='coerce').fillna(0).sum()
                )

                # Simple success message and download
                st.markdown("---")
                st.success(f"✅ Report generated for **{len(fa_df):,} assets**")

                # Download buttons - FA CS Export and Workpaper
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "📥 Download FA CS Export",
                        data=outfile,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )
                    st.caption(f"📁 {filename}")

                # Generate CPA Workpaper
                with col2:
                    # Build workpaper content
                    workpaper_buffer = io.BytesIO()
                    with pd.ExcelWriter(workpaper_buffer, engine='openpyxl') as writer:
                        # Summary sheet
                        audit_info = st.session_state.get("audit_info", {})
                        summary_data = {
                            "Field": [
                                "Client Name",
                                "Tax Year",
                                "Prepared By",
                                "Reviewed By",
                                "Date Prepared",
                                "Total Assets",
                                "Total Cost",
                                "Total Year 1 Deduction",
                                "Classification Method",
                                "Source File",
                                "Processing Time",
                                "Est. Manual Time",
                                "Time Saved"
                            ],
                            "Value": [
                                client_key,
                                str(tax_year),
                                audit_info.get("preparer_name", ""),
                                audit_info.get("reviewer_name", ""),
                                datetime.now().strftime("%m/%d/%Y"),
                                f"{len(fa_df):,}",
                                f"${pd.to_numeric(fa_df.get('Tax Cost', pd.Series([0])), errors='coerce').fillna(0).sum():,.2f}",
                                f"${total_year1_deduction:,.2f}",
                                f"AI-Assisted ({strategy})",
                                st.session_state.get("uploaded_file_name", ""),
                                f"{st.session_state.get('classification_duration', 0):.1f} seconds",
                                f"{st.session_state.get('time_saved', 0)/60:.1f} minutes",
                                f"{st.session_state.get('time_saved', 0)/60:.1f} minutes"
                            ]
                        }
                        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

                        # Classification detail sheet with rationale
                        workpaper_cols = ["Asset #", "Original Asset ID", "Description", "Tax Cost",
                                         "Final Category Used", "Recovery Period", "Tax Method", "Convention",
                                         "ClassificationExplanation", "ConfidenceGrade", "Source"]
                        available_cols = [c for c in workpaper_cols if c in fa_df.columns]
                        workpaper_df = fa_df[available_cols].copy()
                        workpaper_df.to_excel(writer, sheet_name="Classification Detail", index=False)

                        # Deduction summary by category
                        if "Final Category Used" in fa_df.columns:
                            deduction_summary = fa_df.groupby("Final Category Used").agg({
                                "Tax Cost": lambda x: pd.to_numeric(x, errors='coerce').sum(),
                            }).reset_index()
                            deduction_summary.columns = ["Category", "Total Cost"]
                            deduction_summary = deduction_summary.sort_values("Total Cost", ascending=False)
                            deduction_summary.to_excel(writer, sheet_name="By Category", index=False)

                    workpaper_buffer.seek(0)
                    workpaper_filename = f"Workpaper_{client_key_safe}_{tax_year}_{datetime.now().strftime('%Y%m%d')}.xlsx"

                    st.download_button(
                        "📋 Download Workpaper",
                        data=workpaper_buffer,
                        file_name=workpaper_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    st.caption("For CPA file documentation")

                # =========================================================================
                # DEPRECIATION FORECAST EXPORT (5-Year View)
                # =========================================================================
                st.markdown("---")
                st.markdown("#### 📊 Tax Planning Exports")

                forecast_col1, forecast_col2 = st.columns(2)

                with forecast_col1:
                    # 5-Year Depreciation Forecast
                    try:
                        # Build forecast data
                        forecast_buffer = io.BytesIO()

                        # Get summary projection (5 years)
                        summary_projection = project_portfolio_depreciation(
                            fa_df,
                            current_tax_year=tax_year,
                            projection_years=5
                        )

                        # Get detailed asset-by-year projection
                        detail_projection = create_detailed_projection_table(
                            fa_df,
                            current_tax_year=tax_year,
                            projection_years=5
                        )

                        with pd.ExcelWriter(forecast_buffer, engine='openpyxl') as writer:
                            # Summary by year
                            summary_projection.to_excel(writer, sheet_name='Annual Summary', index=False)

                            # Detail by asset
                            detail_projection.to_excel(writer, sheet_name='By Asset', index=False)

                            # Format summary for display
                            summary_display = summary_projection.copy()
                            summary_display["Total Depreciation"] = summary_display["Total Depreciation"].apply(lambda x: f"${x:,.0f}")
                            summary_display["Average Per Asset"] = summary_display["Average Per Asset"].apply(lambda x: f"${x:,.0f}")

                        forecast_buffer.seek(0)
                        forecast_filename = f"Depreciation_Forecast_{client_key_safe}_{tax_year}_5yr.xlsx"

                        st.download_button(
                            "📈 5-Year Forecast",
                            data=forecast_buffer,
                            file_name=forecast_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                        st.caption("Tax planning projection")

                        # Show quick preview
                        with st.expander("Preview Forecast"):
                            st.dataframe(summary_display, use_container_width=True)
                            total_5yr = summary_projection["Total Depreciation"].sum()
                            st.info(f"**Total 5-Year Depreciation:** ${total_5yr:,.0f}")

                    except Exception as forecast_err:
                        st.caption(f"Forecast unavailable: {forecast_err}")

                with forecast_col2:
                    # Disposal Recapture Preview
                    try:
                        # Check for disposals with gain potential
                        if "Transaction Type" in fa_df.columns:
                            disposals = fa_df[fa_df["Transaction Type"].astype(str).str.contains("Disposal", case=False, na=False)]

                            if len(disposals) > 0:
                                # Run recapture analysis
                                recapture_msgs, recapture_details = recapture_analysis(fa_df)

                                if recapture_msgs:
                                    st.markdown("**⚠️ Recapture Analysis**")
                                    for msg in recapture_msgs:
                                        st.warning(msg)

                                    # Show affected assets
                                    for key, detail_df in recapture_details.items():
                                        if len(detail_df) > 0:
                                            with st.expander(f"View {key.replace('_', ' ').title()} ({len(detail_df)} assets)"):
                                                st.dataframe(detail_df, use_container_width=True)
                                else:
                                    st.success(f"✓ {len(disposals)} disposals - no recapture issues detected")
                            else:
                                st.caption("No disposals in this batch")
                        else:
                            st.caption("Transaction Type not available")
                    except Exception as recapture_err:
                        st.caption(f"Recapture analysis unavailable: {recapture_err}")

        except ValueError as e:
            # Data validation errors - show helpful message
            if "CRITICAL data validation errors" in str(e):
                st.error("❌ Cannot generate export due to data validation errors")
                st.warning("""
                **Common issues:**
                - Missing required column: "Final Category" - Run classification first (Step 4)
                - Missing required column: "Transaction Type" - Classification incomplete
                - Missing dates or costs
                - Invalid data formats

                **To fix:**
                1. Make sure you completed Step 4 (Classification) successfully
                2. Check Step 5 (Validation) for data quality issues
                3. Fix any critical issues in your data
                """)
                with st.expander("🔍 Technical Details", expanded=False):
                    st.code(f"Error: {str(e)}", language="text")
            else:
                st.error("Failed to generate FA CS export file.")
                error_msg = log_error_securely(e, "exporting to FA CS format")
                st.info(error_msg)
                with st.expander("🔍 Technical Details", expanded=False):
                    st.code(f"Error type: {type(e).__name__}\nError message: {str(e)}", language="text")
        except Exception as e:
            st.error("Failed to generate FA CS export file.")
            error_msg = log_error_securely(e, "exporting to FA CS format")
            st.info(error_msg)
            # Show detailed error for debugging
            with st.expander("🔍 Technical Details (for debugging)", expanded=False):
                st.code(f"Error type: {type(e).__name__}\nError message: {str(e)}", language="text")


# =====================================================================
# STEP 7 — RPA AUTOMATION (Experimental - Windows Only)
# Hidden by default, toggle in sidebar under "Advanced Settings"
# =====================================================================

if "classified_df" in st.session_state and st.session_state.get("show_rpa_steps", False):

    st.subheader("Step 7 — RPA Automation (Experimental)")
    st.caption("⚠️ Beta feature: Windows desktop only. Not available on Streamlit Cloud.")

    if not RPA_AVAILABLE:
        st.warning("""
        **RPA Automation Not Available**

        RPA automation requires Windows with Fixed Asset CS desktop application installed.

        This feature is not available on Streamlit Cloud (web version).

        **To use RPA:**
        1. Download this app to run locally on Windows
        2. Install RPA dependencies: `pip install pyautogui pywinauto`
        3. Run Fixed Asset CS on your Windows computer
        4. Run the app locally: `streamlit run fixed_asset_ai/app.py`

        **You can still:**
        - ✓ Upload Excel files
        - ✓ AI classification
        - ✓ Export to Excel for manual import into FA CS
        """)
    else:
        st.info("""
        **RPA Automation Feature**

        This feature will automatically input your classified assets directly into
        Fixed Asset CS software using Robotic Process Automation (RPA).

        **Requirements:**
        - Fixed Asset CS must be running on your computer
        - The application window must be visible
        - You should not use keyboard/mouse during automation
        """)

        # Test connection
        col1, col2 = st.columns(2)

        with col1:
            if st.button("🔍 Test FA CS Connection"):
                with st.spinner("Testing connection to Fixed Asset CS..."):
                    try:
                        orchestrator = AIRPAOrchestrator()
                        success, message = orchestrator.validate_fa_cs_connection()

                        if success:
                            st.success(f"✓ {message}")
                            st.session_state["fa_cs_connected"] = True
                        else:
                            st.error(f"✗ {message}")
                            st.session_state["fa_cs_connected"] = False
                    except Exception as e:
                        st.error(f"Connection test failed: {e}")
                        st.session_state["fa_cs_connected"] = False

        with col2:
            preview_mode = st.checkbox(
                "Preview Mode (First 3 Assets Only)",
                value=True,
                help="Test with only 3 assets before running full automation"
            )

        # RPA Execution
        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("▶️ Run RPA Automation", type="primary"):

                df = st.session_state["classified_df"]

                # Build FA CS export data
                try:
                    asset_number_start = st.session_state.get("asset_number_start", 1)
                    fa_df = build_fa(
                        df=df,
                        tax_year=tax_year,
                        strategy=strategy,
                        taxable_income=taxable_income,
                        use_acq_if_missing=use_acq_if_missing,
                        de_minimis_limit=de_minimis_limit,
                        section_179_carryforward_from_prior_year=section_179_carryforward,
                        asset_number_start=asset_number_start,
                    )
                except Exception as e:
                    st.error(f"Error preparing data: {e}")
                    st.stop()

                # Show what will be processed
                asset_count = 3 if preview_mode else len(fa_df)
                st.warning(f"""
                **About to process {asset_count} assets**

                Please:
                - Do NOT touch keyboard or mouse
                - Keep Fixed Asset CS window visible
                - Move mouse to screen corner to emergency stop (if enabled)
                """)

                # Run RPA
                with st.spinner(f"Running RPA automation for {asset_count} assets..."):
                    try:
                        orchestrator = AIRPAOrchestrator()

                        results = orchestrator.run_full_workflow(
                            classified_df=df,
                            tax_year=tax_year,
                            strategy=strategy,
                            taxable_income=taxable_income,
                            use_acq_if_missing=use_acq_if_missing,
                            preview_mode=preview_mode,
                            auto_run_rpa=True,
                        )

                        if results.get("success"):
                            st.success("✓ RPA Automation Complete!")

                            # Display results
                            rpa_stats = results["steps"].get("rpa_automation", {})
                            if "statistics" in rpa_stats:
                                stats = rpa_stats["statistics"]

                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Processed", stats.get("processed", 0))
                                with col2:
                                    st.metric("Succeeded", stats.get("succeeded", 0))
                                with col3:
                                    st.metric("Failed", stats.get("failed", 0))

                                if stats.get("errors"):
                                    st.error("Errors encountered:")
                                    for err in stats["errors"]:
                                        st.write(f"- {err}")

                            # Show execution log
                            with st.expander("View Execution Log"):
                                st.json(results["execution_log"])

                            st.session_state["rpa_results"] = results

                        else:
                            st.error(f"RPA automation failed: {results.get('error', 'Unknown error')}")

                    except Exception as e:
                        st.error("RPA automation encountered an error.")
                        error_msg = log_error_securely(e, "running RPA automation")
                        st.info(error_msg)

        with col2:
            if st.button("📊 View RPA Status"):
                if "rpa_results" in st.session_state:
                    results = st.session_state["rpa_results"]
                    st.json(results)
                else:
                    st.info("No RPA execution results yet")


# =====================================================================
# STEP 8 — RPA MONITORING & LOGS (Experimental)
# =====================================================================

if "classified_df" in st.session_state and RPA_AVAILABLE and st.session_state.get("show_rpa_steps", False):

    st.subheader("Step 8 — RPA Monitoring & Logs")

    if "rpa_results" in st.session_state:
        results = st.session_state["rpa_results"]

        # Summary card
        st.markdown("### Execution Summary")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Workflow ID", results.get("workflow_id", "N/A"))

        with col2:
            duration = results.get("duration_seconds", 0)
            st.metric("Duration", f"{duration:.1f}s")

        with col3:
            status = "✓ Success" if results.get("success") else "✗ Failed"
            st.metric("Status", status)

        # Step-by-step breakdown
        st.markdown("### Step Results")

        steps = results.get("steps", {})
        for step_name, step_data in steps.items():
            with st.expander(f"{step_name.replace('_', ' ').title()}"):
                st.json(step_data)

        # Download logs
        st.markdown("### Download Logs")

        import json
        # Sanitize log data before download to remove sensitive information
        sanitized_results = sanitize_log_data(results)
        log_json = json.dumps(sanitized_results, indent=2, default=str)
        st.download_button(
            "Download Execution Log (JSON)",
            data=log_json,
            file_name=f"rpa_log_{results.get('workflow_id', 'unknown')}.json",
            mime="application/json",
        )

    else:
        st.info("Run RPA automation to see monitoring data")
