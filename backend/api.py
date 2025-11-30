from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
import psutil
import os
import shutil
import sys
from typing import List, Dict
from datetime import datetime
import traceback
import io

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add project root to sys.path to allow imports
# This must happen BEFORE importing services that depend on backend.logic
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.importer import ImporterService
from backend.services.classifier import ClassifierService
from backend.services.auditor import AuditorService
from backend.services.exporter import ExporterService
from backend.models.asset import Asset

# Import logic modules for new features
from backend.logic.data_quality_score import calculate_data_quality_score, DataQualityScore
from backend.logic.smart_tab_analyzer import analyze_tabs, TabAnalysisResult
from backend.logic.rollforward_reconciliation import reconcile_rollforward, RollforwardResult
from backend.logic.depreciation_projection import project_portfolio_depreciation
import pandas as pd

app = FastAPI()

# ==============================================================================
# CORS CONFIGURATION (Issue 6.2 from IRS Audit Report - Security)
# ==============================================================================
# Configure allowed origins via CORS_ALLOWED_ORIGINS environment variable.
# For production, set to specific domains (comma-separated):
#   CORS_ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
#
# For development, leave unset to use localhost defaults.

def get_cors_origins():
    """Get CORS allowed origins from environment or use development defaults."""
    env_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    if env_origins:
        # Production: use configured origins
        return [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    else:
        # Development: allow localhost
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173"
        ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
importer = ImporterService()
classifier = ClassifierService()
auditor = AuditorService()
exporter = ExporterService()

# In-Memory Store (Replace with DB later)
# IMPORTANT: Use unique_id (not row_index) as key to prevent overwrites
# when assets from different sheets have the same row numbers
ASSET_STORE: Dict[int, Asset] = {}
ASSET_ID_COUNTER = 0  # Global counter for unique asset IDs
APPROVED_ASSETS: set = set()  # Track CPA-approved unique_ids
TAB_ANALYSIS_RESULT = None  # Store latest tab analysis for UI
LAST_UPLOAD_FILENAME = None  # Track filename for display

# Remote FA CS Configuration
FACS_CONFIG = {
    "remote_mode": True,  # FA CS runs on remote server
    "user_confirmed_connected": False,  # User manually confirms connection
    "export_path": None  # Custom export path (e.g., shared network folder)
}

# Tax Configuration - CRITICAL for proper classification
from datetime import date
TAX_CONFIG = {
    "tax_year": date.today().year,  # Default to current year
    "de_minimis_threshold": 2500,   # Default to non-AFS threshold ($2,500)
    "has_afs": False,               # Audited Financial Statement status
    "bonus_rate": None,             # Will be calculated based on tax year
    "section_179_limit": None,      # Will be set based on tax year
}

# Import tax year config for bonus rates
try:
    from backend.logic import tax_year_config
    TAX_YEAR_CONFIG_AVAILABLE = True
except ImportError:
    TAX_YEAR_CONFIG_AVAILABLE = False

@app.get("/")
def read_root():
    return {"status": "Backend Online", "version": "1.0.0"}

@app.get("/check-facs")
def check_facs():
    """
    Check FA CS connection status.
    Remote mode: relies on user confirmation (can't auto-detect remote app)
    Local mode: checks if FAwin.exe is running
    """
    if FACS_CONFIG["remote_mode"]:
        return {
            "running": FACS_CONFIG["user_confirmed_connected"],
            "remote_mode": True,
            "message": "Remote FA CS - Please confirm you are connected" if not FACS_CONFIG["user_confirmed_connected"] else "Connected to remote FA CS",
            "export_path": FACS_CONFIG["export_path"]
        }
    else:
        # Local mode - auto-detect
        running = "FAwin.exe" in (p.name() for p in psutil.process_iter())
        return {"running": running, "remote_mode": False}

@app.post("/facs/confirm-connected")
def confirm_facs_connected():
    """User confirms they are connected to remote FA CS session."""
    FACS_CONFIG["user_confirmed_connected"] = True
    return {"confirmed": True, "message": "FA CS connection confirmed"}

@app.post("/facs/disconnect")
def disconnect_facs():
    """User indicates they disconnected from FA CS."""
    FACS_CONFIG["user_confirmed_connected"] = False
    return {"confirmed": False, "message": "FA CS disconnected"}

@app.post("/facs/set-export-path")
def set_export_path(path: str = Body(..., embed=True)):
    """
    Set custom export path (e.g., shared network folder accessible from remote session).
    Example: "\\\\server\\shared\\FA_Imports" or "Z:\\FA_Imports"
    """
    FACS_CONFIG["export_path"] = path
    return {"export_path": path, "message": f"Export path set to: {path}"}

@app.get("/facs/config")
def get_facs_config():
    """Get current FA CS configuration."""
    return FACS_CONFIG

@app.get("/stats")
def get_stats():
    """
    Returns statistics for the Dashboard.
    """
    assets = list(ASSET_STORE.values())
    total = len(assets)

    errors = sum(1 for a in assets if getattr(a, 'validation_errors', None))
    needs_review = sum(1 for a in assets if not getattr(a, 'validation_errors', None)
                       and getattr(a, 'confidence_score', 1.0) <= 0.8)
    high_confidence = sum(1 for a in assets if not getattr(a, 'validation_errors', None)
                          and getattr(a, 'confidence_score', 1.0) > 0.8)
    approved = len(APPROVED_ASSETS)

    # Transaction type breakdown
    trans_types = {}
    for a in assets:
        tt = getattr(a, 'transaction_type', 'addition') or 'addition'
        trans_types[tt] = trans_types.get(tt, 0) + 1

    return {
        "total": total,
        "errors": errors,
        "needs_review": needs_review,
        "high_confidence": high_confidence,
        "approved": approved,
        "ready_for_export": errors == 0 and total > 0,
        "transaction_types": trans_types,
        "tax_year": TAX_CONFIG["tax_year"]
    }


@app.get("/assets")
def get_assets():
    """
    Returns all currently loaded assets.
    Useful for refreshing the frontend after tax year changes.
    """
    return list(ASSET_STORE.values())


# ==============================================================================
# TAX CONFIGURATION ENDPOINTS
# ==============================================================================

@app.get("/config/tax")
def get_tax_config():
    """
    Get current tax configuration including:
    - Tax year
    - De minimis threshold
    - Bonus depreciation rate
    - Section 179 limits
    """
    config = dict(TAX_CONFIG)
    tax_year = config["tax_year"]

    # Calculate bonus rate based on tax year
    if TAX_YEAR_CONFIG_AVAILABLE:
        # get_bonus_percentage returns a float (e.g., 1.0 for 100%, 0.6 for 60%)
        bonus_rate = tax_year_config.get_bonus_percentage(tax_year)
        config["bonus_rate"] = int(bonus_rate * 100)  # Convert to percentage (e.g., 100, 60)
        # get_section_179_limits returns a dict with 'max_deduction' and 'phaseout_threshold'
        section_179_info = tax_year_config.get_section_179_limits(tax_year)
        config["section_179_limit"] = section_179_info.get("max_deduction", 0)
        config["obbba_effective"] = tax_year >= 2025  # OBBBA passed in 2025
        config["obbba_info"] = {
            "name": "One Big Beautiful Bill Act (OBBBA) 2025",
            "effective_date": "2025-01-19",
            "bonus_rate_post_obbba": 100 if tax_year >= 2025 else None,
            "section_179_limit_increase": "$2.5M (up from $1.2M)" if tax_year >= 2025 else None
        }
    else:
        # Fallback defaults
        config["bonus_rate"] = 60 if tax_year == 2024 else 40 if tax_year == 2025 else 0
        config["section_179_limit"] = 1220000 if tax_year < 2025 else 2500000

    return config


@app.post("/config/tax")
def set_tax_config(
    tax_year: int = Body(..., embed=True, ge=2020, le=2030),
    de_minimis_threshold: int = Body(2500, ge=0, le=5000),
    has_afs: bool = Body(False)
):
    """
    Set tax configuration for the session.

    Args:
        tax_year: Tax year for depreciation calculations (2020-2030)
        de_minimis_threshold: De minimis safe harbor threshold ($0-$5000)
                             - $2,500 for taxpayers WITHOUT audited financial statements
                             - $5,000 for taxpayers WITH audited financial statements
        has_afs: Whether taxpayer has Audited Financial Statements

    IMPORTANT: Setting tax year will RECLASSIFY all loaded assets!
    """
    global TAX_CONFIG

    TAX_CONFIG["tax_year"] = tax_year
    TAX_CONFIG["de_minimis_threshold"] = de_minimis_threshold
    TAX_CONFIG["has_afs"] = has_afs

    # Update classifier's tax year
    classifier.set_tax_year(tax_year)

    # Reclassify loaded assets with new tax year
    # CRITICAL: We must preserve ALL assets - never filter or remove any
    trans_types = {}
    errors_count = 0
    reclassified_assets = []

    if ASSET_STORE:
        # Get all assets from store
        asset_count_before = len(ASSET_STORE)
        assets = list(ASSET_STORE.values())
        print(f"[Tax Year Change] Starting with {asset_count_before} assets in ASSET_STORE")
        print(f"[Tax Year Change] Reclassifying {len(assets)} assets for tax year {tax_year}")

        # Reclassify transaction types
        classifier._classify_transaction_types(assets, tax_year)

        # Re-run validation for each asset with new tax year
        # This will flag assets with dates after the tax year as errors
        # BUT it should NEVER remove assets from the list
        for a in assets:
            a.check_validity(tax_year=tax_year)
            tt = a.transaction_type or 'unknown'
            trans_types[tt] = trans_types.get(tt, 0) + 1
            if a.validation_errors:
                errors_count += 1
            reclassified_assets.append(a)

        asset_count_after = len(reclassified_assets)
        print(f"[Tax Year Change] Reclassification complete: {trans_types}")
        print(f"[Tax Year Change] Asset count after reclassification: {asset_count_after}")
        if asset_count_before != asset_count_after:
            print(f"[Tax Year Change] WARNING: Asset count changed from {asset_count_before} to {asset_count_after}!")
        if errors_count > 0:
            print(f"[Tax Year Change] {errors_count} assets have validation errors (may include future dates)")
    else:
        print(f"[Tax Year Change] No assets in ASSET_STORE to reclassify")
        reclassified_assets = []

    return {
        "status": "updated",
        "tax_year": tax_year,
        "de_minimis_threshold": de_minimis_threshold,
        "has_afs": has_afs,
        "assets_reclassified": len(ASSET_STORE),
        "transaction_type_breakdown": trans_types,
        "assets": list(ASSET_STORE.values()) if ASSET_STORE else []
    }


# ==============================================================================
# DATA WARNINGS & COMPLETENESS ENDPOINTS
# ==============================================================================

@app.get("/warnings")
def get_warnings():
    """
    Get comprehensive warnings about the loaded data including:
    - Missing asset detection warnings
    - Transaction type classification issues
    - De minimis candidates
    - Tax compliance warnings
    """
    assets = list(ASSET_STORE.values())
    if not assets:
        return {"warnings": [], "critical": [], "info": []}

    critical_warnings = []
    warnings = []
    info_messages = []
    tax_year = TAX_CONFIG["tax_year"]

    # ===== CRITICAL WARNINGS =====

    # 1. Check for existing assets incorrectly classified as additions
    existing_as_additions = []
    for a in assets:
        if a.in_service_date:
            asset_year = a.in_service_date.year
            if asset_year < tax_year and "addition" in (a.transaction_type or "").lower():
                existing_as_additions.append({
                    "asset_id": a.asset_id,
                    "description": a.description[:50],
                    "in_service_year": asset_year,
                    "tax_year": tax_year
                })

    if existing_as_additions:
        critical_warnings.append({
            "type": "MISCLASSIFIED_EXISTING_ASSETS",
            "message": f"{len(existing_as_additions)} existing assets may be incorrectly classified as additions",
            "impact": "Section 179 and Bonus depreciation NOT allowed on existing assets",
            "action": "Review transaction type classification and set correct tax year",
            "affected_count": len(existing_as_additions),
            "examples": existing_as_additions[:5]
        })

    # 2. Check for assets missing cost (exclude transfers - they don't require cost)
    # Transfers just move assets between departments/locations, cost is already recorded
    zero_cost = [
        a for a in assets
        if a.cost <= 0 and not (a.transaction_type and a.transaction_type.lower() == "transfer")
    ]
    if zero_cost:
        critical_warnings.append({
            "type": "MISSING_COST",
            "message": f"{len(zero_cost)} assets have $0 or missing cost",
            "impact": "Cannot calculate depreciation without cost basis",
            "action": "Enter cost for each asset",
            "affected_count": len(zero_cost)
        })

    # 3. Check for assets with Unknown (Missing Date) transaction type - CRITICAL
    unknown_trans_type = [
        a for a in assets
        if a.transaction_type and "unknown" in a.transaction_type.lower()
    ]
    if unknown_trans_type:
        critical_warnings.append({
            "type": "UNKNOWN_TRANSACTION_TYPE",
            "message": f"{len(unknown_trans_type)} assets have unknown transaction type due to missing dates",
            "impact": "Cannot determine if Section 179/Bonus eligible - potential tax compliance issue",
            "action": "Add in-service dates to properly classify as Current Year Addition or Existing Asset",
            "affected_count": len(unknown_trans_type)
        })

    # ===== REGULAR WARNINGS =====

    # 4. Check for assets missing dates (informational - already covered by Unknown transaction type)
    missing_dates = [a for a in assets if not a.in_service_date and not a.acquisition_date]
    if missing_dates:
        warnings.append({
            "type": "MISSING_DATES",
            "message": f"{len(missing_dates)} assets have no in-service or acquisition date",
            "impact": "Classified as 'Unknown (Missing Date)' - requires manual review",
            "action": "Add in-service dates for proper classification",
            "affected_count": len(missing_dates)
        })

    # 5. Transaction type breakdown check
    trans_types = {}
    for a in assets:
        tt = a.transaction_type or "unknown"
        trans_types[tt] = trans_types.get(tt, 0) + 1

    # Check if ALL assets are additions (suspicious)
    additions_count = trans_types.get("Current Year Addition", 0) + trans_types.get("addition", 0)
    if additions_count == len(assets) and len(assets) > 10:
        warnings.append({
            "type": "ALL_ADDITIONS_SUSPICIOUS",
            "message": f"All {len(assets)} assets classified as additions - this may indicate missing data",
            "impact": "Typical asset schedules include existing assets, disposals, and transfers",
            "action": "Verify data includes complete asset schedule with all transaction types",
            "affected_count": len(assets)
        })

    # 6. De minimis candidates
    de_minimis_threshold = TAX_CONFIG["de_minimis_threshold"]
    de_minimis_candidates = [
        a for a in assets
        if 0 < a.cost <= de_minimis_threshold and "Current Year Addition" in (a.transaction_type or "")
    ]
    if de_minimis_candidates:
        info_messages.append({
            "type": "DE_MINIMIS_CANDIDATES",
            "message": f"{len(de_minimis_candidates)} current year additions qualify for de minimis safe harbor",
            "threshold": de_minimis_threshold,
            "total_value": sum(a.cost for a in de_minimis_candidates),
            "benefit": "Can expense immediately instead of capitalizing and depreciating",
            "affected_count": len(de_minimis_candidates)
        })

    # 7. Unclassified assets (exclude transfers - they don't need classification)
    unclassified = [
        a for a in assets
        if a.macrs_class in ["Unclassified", "Unknown", None, ""]
        and not (a.transaction_type and a.transaction_type.lower() == "transfer")
    ]
    if unclassified:
        warnings.append({
            "type": "UNCLASSIFIED_ASSETS",
            "message": f"{len(unclassified)} assets could not be automatically classified",
            "impact": "Manual MACRS class assignment required before export",
            "action": "Review and assign MACRS class to each unclassified asset",
            "affected_count": len(unclassified)
        })

    # ===== INFO MESSAGES =====

    # 8. Transfer assets info (they don't require cost)
    transfer_assets = [
        a for a in assets
        if a.transaction_type and a.transaction_type.lower() == "transfer"
    ]
    if transfer_assets:
        transfer_with_cost = [a for a in transfer_assets if a.cost > 0]
        transfer_no_cost = [a for a in transfer_assets if a.cost <= 0]
        info_messages.append({
            "type": "TRANSFER_ASSETS_INFO",
            "message": f"{len(transfer_assets)} transfer records detected",
            "details": {
                "with_cost": len(transfer_with_cost),
                "without_cost": len(transfer_no_cost),
                "note": "Transfers track asset movement between departments/locations - cost field is optional"
            },
            "affected_count": len(transfer_assets)
        })

    # 9. Transaction type summary
    info_messages.append({
        "type": "TRANSACTION_SUMMARY",
        "message": "Asset classification summary",
        "breakdown": trans_types,
        "tax_year": tax_year
    })

    # 10. OBBBA 2025 info
    if tax_year >= 2025:
        info_messages.append({
            "type": "OBBBA_2025_EFFECTIVE",
            "message": "One Big Beautiful Bill Act (OBBBA) 2025 provisions apply",
            "details": {
                "bonus_depreciation": "100% for assets acquired AND placed in service after 1/19/2025",
                "section_179_limit": "$2.5 million (increased from $1.2 million)",
                "phase_out_threshold": "$4 million"
            }
        })

    return {
        "critical": critical_warnings,
        "warnings": warnings,
        "info": info_messages,
        "summary": {
            "total_assets": len(assets),
            "critical_issues": len(critical_warnings),
            "warnings": len(warnings),
            "tax_year": tax_year
        }
    }

@app.post("/upload", response_model=List[Asset])
async def upload_file(file: UploadFile = File(...)):
    """
    Uploads an Excel file, parses it, and returns classified assets.

    Uses the configured tax year for proper transaction classification:
    - Current Year Additions (eligible for Section 179/Bonus)
    - Existing Assets (NOT eligible for Section 179/Bonus)
    - Disposals
    - Transfers
    """
    global TAB_ANALYSIS_RESULT, LAST_UPLOAD_FILENAME

    temp_file = f"temp_{file.filename}"
    LAST_UPLOAD_FILENAME = file.filename

    try:
        # Save uploaded file temporarily
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Perform tab analysis before processing
        try:
            import openpyxl
            wb = openpyxl.load_workbook(temp_file, data_only=True)
            sheets = {}
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                data = []
                for row in ws.iter_rows(values_only=True):
                    data.append(row)
                sheets[sheet_name] = pd.DataFrame(data)
            wb.close()

            # Run tab analysis
            TAB_ANALYSIS_RESULT = analyze_tabs(sheets, TAX_CONFIG["tax_year"])
            print(f"Tab analysis: {len(TAB_ANALYSIS_RESULT.tabs)} tabs detected")
        except Exception as tab_err:
            print(f"Tab analysis error (non-fatal): {tab_err}")
            TAB_ANALYSIS_RESULT = None

        # 1. Parse Excel
        assets = importer.parse_excel(temp_file)

        # 2. Classify Assets (MACRS + Transaction Types)
        # Uses the configured tax year for proper classification
        tax_year = TAX_CONFIG["tax_year"]
        classified_assets = classifier.classify_batch(assets, tax_year=tax_year)

        # 3. Store in Memory using unique IDs to prevent overwrites
        # CRITICAL FIX: Use global counter instead of row_index as key
        # Assets from different sheets can have the same row_index (e.g., row 5)
        # which would cause overwrites and data loss
        global ASSET_ID_COUNTER
        ASSET_STORE.clear()  # Clear previous upload for now
        APPROVED_ASSETS.clear()  # Clear approvals too
        ASSET_ID_COUNTER = 0  # Reset counter for new upload
        for asset in classified_assets:
            # Store asset's original row_index for reference, use unique_id as key
            asset.unique_id = ASSET_ID_COUNTER
            ASSET_STORE[ASSET_ID_COUNTER] = asset
            ASSET_ID_COUNTER += 1

        print(f"[Upload] Stored {len(ASSET_STORE)} assets in ASSET_STORE (counter={ASSET_ID_COUNTER})")

        # Log transaction type summary
        trans_types = {}
        for a in classified_assets:
            tt = a.transaction_type or "unknown"
            trans_types[tt] = trans_types.get(tt, 0) + 1
        print(f"Classification Summary (Tax Year {tax_year}): {trans_types}")

        return classified_assets
        
    except Exception as e:
        # Print to console for debugging
        print(f"Upload Error: {e}")
        traceback.print_exc()
        
        try:
            with open("backend_error.log", "w") as f:
                f.write(str(e))
                f.write("\n")
                f.write(traceback.format_exc())
        except Exception as log_error:
            print(f"Failed to write to backend_error.log: {log_error}")
            
        # Don't expose internal error details to client
        raise HTTPException(status_code=500, detail="File processing failed. Please check the file format and try again.")
    finally:
        # Cleanup
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as cleanup_error:
                print(f"Warning: Failed to delete temp file {temp_file}: {cleanup_error}")

@app.post("/assets/{asset_id}/update", response_model=Asset)
def update_asset(asset_id: int, update_data: Dict = Body(...)):
    """
    Updates a specific asset and logs the change in the audit trail.
    Note: asset_id here is the unique_id, not the original row_index.
    """
    if asset_id not in ASSET_STORE:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset = ASSET_STORE[asset_id]

    # Check for changes and log them
    for field, new_value in update_data.items():
        if hasattr(asset, field):
            old_value = getattr(asset, field)
            if str(old_value) != str(new_value):
                # Update the field
                setattr(asset, field, new_value)
                # Log the change
                auditor.log_override(asset, field, str(old_value), str(new_value))

    return asset

@app.post("/assets/{asset_id}/approve")
def approve_asset(asset_id: int):
    """
    CPA approves a single asset for export.
    Note: asset_id here is the unique_id, not the original row_index.
    """
    if asset_id not in ASSET_STORE:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset = ASSET_STORE[asset_id]

    # Can't approve assets with validation errors
    if getattr(asset, 'validation_errors', None):
        raise HTTPException(status_code=400, detail="Cannot approve asset with validation errors")

    APPROVED_ASSETS.add(asset_id)
    return {"approved": True, "unique_id": asset_id}

@app.post("/assets/approve-batch")
def approve_batch(asset_ids: List[int] = Body(...)):
    """
    CPA approves multiple assets at once (e.g., all high-confidence items).
    Note: asset_ids are unique_ids, not row_indexes.
    """
    approved = []
    errors = []

    for asset_id in asset_ids:
        if asset_id not in ASSET_STORE:
            errors.append({"unique_id": asset_id, "error": "Not found"})
            continue

        asset = ASSET_STORE[asset_id]
        if getattr(asset, 'validation_errors', None):
            errors.append({"unique_id": asset_id, "error": "Has validation errors"})
            continue

        APPROVED_ASSETS.add(asset_id)
        approved.append(asset_id)

    return {"approved": approved, "errors": errors, "total_approved": len(approved)}

@app.delete("/assets/{asset_id}/approve")
def unapprove_asset(asset_id: int):
    """
    Remove approval from an asset.
    Note: asset_id here is the unique_id, not the original row_index.
    """
    if asset_id in APPROVED_ASSETS:
        APPROVED_ASSETS.discard(asset_id)
        return {"approved": False, "unique_id": asset_id}
    return {"approved": False, "unique_id": asset_id, "message": "Was not approved"}

@app.get("/export")
def export_assets():
    """
    Generates an Excel file for Fixed Assets CS import.
    Saves a copy to 'bot_handoff' folder for UiPath to pick up.
    """
    if not ASSET_STORE:
        raise HTTPException(status_code=400, detail="No assets to export")

    # Get all assets from store
    assets = list(ASSET_STORE.values())

    # Validate: Block export if any asset has validation errors
    assets_with_errors = [a for a in assets if getattr(a, 'validation_errors', None)]
    if assets_with_errors:
        error_count = len(assets_with_errors)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot export: {error_count} asset(s) have validation errors. Fix all errors before exporting."
        )
    
    # Generate Excel with tax configuration
    excel_file = exporter.generate_fa_cs_export(
        assets,
        tax_year=TAX_CONFIG["tax_year"],
        de_minimis_limit=TAX_CONFIG["de_minimis_threshold"]
    )

    # Save to Bot Handoff Folder (use custom path if set)
    if FACS_CONFIG["export_path"]:
        handoff_dir = FACS_CONFIG["export_path"]
    else:
        handoff_dir = os.path.join(os.getcwd(), "bot_handoff")

    os.makedirs(handoff_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"FA_Import_{timestamp}.xlsx"
    filepath = os.path.join(handoff_dir, filename)
    
    with open(filepath, "wb") as f:
        f.write(excel_file.getvalue())

    print(f"Saved export to: {filepath}")

    # Reset stream position for StreamingResponse
    excel_file.seek(0)

    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=FA_CS_Import.xlsx"}
    )


@app.get("/export/audit")
def export_audit_documentation():
    """
    Generates a comprehensive audit documentation Excel file.
    Includes ALL assets (additions, disposals, transfers, AND existing assets)
    with full classification details, confidence scores, and reasoning.

    This is separate from the FA CS export and is meant for:
    - IRS audit documentation
    - Internal compliance records
    - Year-over-year reconciliation
    """
    if not ASSET_STORE:
        raise HTTPException(status_code=400, detail="No assets to export")

    assets = list(ASSET_STORE.values())
    tax_year = TAX_CONFIG["tax_year"]

    # Create comprehensive audit DataFrame
    audit_data = []
    for a in assets:
        audit_data.append({
            "Asset ID": a.asset_id or "",
            "Description": a.description,
            "Cost": a.cost,
            "Acquisition Date": a.acquisition_date.isoformat() if a.acquisition_date else "",
            "In Service Date": a.in_service_date.isoformat() if a.in_service_date else "",
            "Transaction Type": a.transaction_type or "",
            "Classification Reason": a.classification_reason or "",
            "MACRS Class": a.macrs_class or "",
            "MACRS Life": a.macrs_life or "",
            "MACRS Method": a.macrs_method or "",
            "MACRS Convention": a.macrs_convention or "",
            "Classification Confidence": f"{(a.confidence_score or 0) * 100:.0f}%",
            "Bonus Eligible": "Yes" if a.is_bonus_eligible else "No",
            "Qualified Improvement": "Yes" if a.is_qualified_improvement else "No",
            "Validation Errors": "; ".join(a.validation_errors) if a.validation_errors else "",
            "Validation Warnings": "; ".join(a.validation_warnings) if a.validation_warnings else "",
            "Source Sheet": a.source_sheet or "",
            "Row Index": a.row_index
        })

    df = pd.DataFrame(audit_data)

    # Create summary statistics
    summary_data = {
        "Metric": [
            "Tax Year",
            "Total Assets",
            "Total Cost",
            "Current Year Additions",
            "Existing Assets",
            "Disposals",
            "Transfers",
            "Unknown (Missing Date)",
            "Assets with Errors",
            "High Confidence (>80%)",
            "Low Confidence (<80%)",
            "Export Generated"
        ],
        "Value": [
            str(tax_year),
            str(len(assets)),
            f"${sum(a.cost or 0 for a in assets):,.2f}",
            str(len([a for a in assets if a.transaction_type == "Current Year Addition"])),
            str(len([a for a in assets if a.transaction_type == "Existing Asset"])),
            str(len([a for a in assets if a.transaction_type == "Disposal"])),
            str(len([a for a in assets if a.transaction_type == "Transfer"])),
            str(len([a for a in assets if a.transaction_type and "Unknown" in a.transaction_type])),
            str(len([a for a in assets if a.validation_errors])),
            str(len([a for a in assets if (a.confidence_score or 0) > 0.8])),
            str(len([a for a in assets if (a.confidence_score or 0) <= 0.8])),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
    }
    summary_df = pd.DataFrame(summary_data)

    # Create Excel file with multiple sheets
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Summary sheet first
        summary_df.to_excel(writer, sheet_name='Summary', index=False)

        # All assets - sorted by transaction type
        df_sorted = df.sort_values(['Transaction Type', 'Asset ID'])
        df_sorted.to_excel(writer, sheet_name='All Assets', index=False)

        # Separate sheets by transaction type for easier navigation
        for trans_type in ['Current Year Addition', 'Existing Asset', 'Disposal', 'Transfer']:
            type_df = df[df['Transaction Type'] == trans_type]
            if len(type_df) > 0:
                sheet_name = trans_type.replace(' ', '_')[:31]  # Excel sheet name limit
                type_df.to_excel(writer, sheet_name=sheet_name, index=False)

        # Errors sheet (if any)
        errors_df = df[df['Validation Errors'] != '']
        if len(errors_df) > 0:
            errors_df.to_excel(writer, sheet_name='Validation_Errors', index=False)

    output.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Audit_Documentation_{tax_year}_{timestamp}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==============================================================================
# DATA QUALITY & ANALYSIS ENDPOINTS
# ==============================================================================

@app.get("/quality")
def get_data_quality():
    """
    Get data quality score with A-F grade and detailed breakdown.
    Returns a comprehensive quality assessment for the loaded assets.
    """
    if not ASSET_STORE:
        return {
            "grade": "-",
            "score": 0,
            "is_export_ready": False,
            "summary": "No assets loaded",
            "checks": [],
            "critical_issues": [],
            "recommendations": ["Upload an asset schedule to begin"]
        }

    # Convert assets to DataFrame for quality scoring
    assets = list(ASSET_STORE.values())
    df_data = []
    for a in assets:
        df_data.append({
            "Asset ID": a.asset_id,
            "Description": a.description,
            "Cost": a.cost,
            "In Service Date": a.in_service_date,
            "Final Category": a.macrs_class,
            "MACRS Life": a.macrs_life,
            "Method": a.macrs_method,
            "Transaction Type": a.transaction_type,
        })

    df = pd.DataFrame(df_data)

    try:
        quality_result = calculate_data_quality_score(df, TAX_CONFIG["tax_year"])

        # Convert checks to serializable format
        checks_data = []
        for check in quality_result.checks:
            checks_data.append({
                "name": check.name,
                "passed": check.passed,
                "score": round(check.score, 1),
                "max_score": check.max_score,
                "weight": check.weight,
                "details": check.details,
                "fix_suggestion": check.fix_suggestion
            })

        return {
            "grade": quality_result.grade,
            "score": round(quality_result.score, 1),
            "is_export_ready": quality_result.is_export_ready,
            "summary": quality_result.summary,
            "checks": checks_data,
            "critical_issues": quality_result.critical_issues,
            "recommendations": quality_result.recommendations
        }
    except Exception as e:
        print(f"Quality score error: {e}")
        return {
            "grade": "?",
            "score": 0,
            "is_export_ready": False,
            "summary": f"Error calculating quality: {str(e)}",
            "checks": [],
            "critical_issues": [str(e)],
            "recommendations": []
        }


@app.get("/tabs")
def get_tab_analysis():
    """
    Get the tab analysis results from the last upload.
    Shows which tabs were detected and their roles.
    """
    global TAB_ANALYSIS_RESULT

    if TAB_ANALYSIS_RESULT is None:
        return {
            "tabs": [],
            "target_fiscal_year": TAX_CONFIG["tax_year"],
            "warnings": [],
            "summary": "No file uploaded yet",
            "efficiency": {}
        }

    # Convert tab analysis to serializable format
    tabs_data = []
    for tab in TAB_ANALYSIS_RESULT.tabs:
        tabs_data.append({
            "tab_name": tab.tab_name,
            "role": tab.role.value,
            "role_label": tab.role_label,
            "icon": tab.icon,
            "fiscal_year": tab.fiscal_year,
            "row_count": tab.row_count,
            "data_row_count": tab.data_row_count,
            "has_cost_data": tab.has_cost_data,
            "has_date_data": tab.has_date_data,
            "should_process": tab.should_process,
            "skip_reason": tab.skip_reason,
            "confidence": round(tab.confidence, 2),
            "detection_notes": tab.detection_notes
        })

    efficiency = TAB_ANALYSIS_RESULT.get_efficiency_stats()

    return {
        "tabs": tabs_data,
        "target_fiscal_year": TAB_ANALYSIS_RESULT.target_fiscal_year,
        "warnings": TAB_ANALYSIS_RESULT.warnings,
        "summary_tabs": TAB_ANALYSIS_RESULT.summary_tabs,
        "detail_tabs": TAB_ANALYSIS_RESULT.detail_tabs,
        "disposal_tabs": TAB_ANALYSIS_RESULT.disposal_tabs,
        "efficiency": efficiency,
        "filename": LAST_UPLOAD_FILENAME
    }


@app.get("/rollforward")
def get_rollforward_status():
    """
    Get rollforward reconciliation status for loaded assets.
    Shows beginning balance, additions, disposals, and ending balance.
    """
    if not ASSET_STORE:
        return {
            "is_balanced": True,
            "beginning_balance": 0,
            "additions": 0,
            "disposals": 0,
            "transfers_in": 0,
            "transfers_out": 0,
            "expected_ending": 0,
            "variance": 0,
            "details": {},
            "warnings": ["No assets loaded"],
            "status_label": "No Data"
        }

    # Convert assets to DataFrame
    assets = list(ASSET_STORE.values())
    df_data = []
    for a in assets:
        df_data.append({
            "Cost": a.cost,
            "Transaction Type": a.transaction_type or "",
        })

    df = pd.DataFrame(df_data)

    try:
        result = reconcile_rollforward(df, cost_column="Cost", trans_type_column="Transaction Type")

        status_label = "Balanced" if result.is_balanced else f"Out of Balance (${result.variance:,.2f})"

        return {
            "is_balanced": result.is_balanced,
            "beginning_balance": round(result.beginning_balance, 2),
            "additions": round(result.additions, 2),
            "disposals": round(result.disposals, 2),
            "transfers_in": round(result.transfers_in, 2),
            "transfers_out": round(result.transfers_out, 2),
            "expected_ending": round(result.expected_ending, 2),
            "actual_ending": round(result.actual_ending, 2),
            "variance": round(result.variance, 2),
            "details": result.details,
            "warnings": result.warnings,
            "status_label": status_label
        }
    except Exception as e:
        print(f"Rollforward error: {e}")
        return {
            "is_balanced": False,
            "beginning_balance": 0,
            "additions": 0,
            "disposals": 0,
            "transfers_in": 0,
            "transfers_out": 0,
            "expected_ending": 0,
            "variance": 0,
            "details": {},
            "warnings": [f"Error: {str(e)}"],
            "status_label": "Error"
        }


@app.get("/projection")
def get_depreciation_projection():
    """
    Get 10-year depreciation projection for loaded assets.
    Shows year-by-year tax depreciation forecast.
    """
    if not ASSET_STORE:
        return {
            "years": [],
            "depreciation": [],
            "total_10_year": 0,
            "current_year": 0,
            "summary": "No assets loaded"
        }

    # Convert assets to DataFrame with required columns
    assets = list(ASSET_STORE.values())
    df_data = []
    for a in assets:
        # Calculate depreciable basis (simplified - full calc in export)
        depreciable_basis = a.cost or 0

        df_data.append({
            "Depreciable Basis": depreciable_basis,
            "Recovery Period": a.macrs_life or 7,
            "Method": a.macrs_method or "200DB",
            "Convention": a.macrs_convention or "HY",
            "In Service Date": a.in_service_date,
        })

    df = pd.DataFrame(df_data)
    current_year = TAX_CONFIG["tax_year"]

    try:
        projection_df = project_portfolio_depreciation(df, current_year, projection_years=10)

        years = projection_df["Tax Year"].tolist()
        depreciation = [round(d, 2) for d in projection_df["Total Depreciation"].tolist()]

        total_10_year = sum(depreciation)
        current_year_dep = depreciation[0] if depreciation else 0

        return {
            "years": years,
            "depreciation": depreciation,
            "total_10_year": round(total_10_year, 2),
            "current_year": round(current_year_dep, 2),
            "asset_count": len(assets),
            "summary": f"${total_10_year:,.0f} total depreciation over 10 years"
        }
    except Exception as e:
        print(f"Projection error: {e}")
        traceback.print_exc()
        return {
            "years": [],
            "depreciation": [],
            "total_10_year": 0,
            "current_year": 0,
            "summary": f"Error calculating projection: {str(e)}"
        }


@app.get("/confidence")
def get_confidence_breakdown():
    """
    Get breakdown of assets by confidence level.
    Helps CPAs prioritize review time.
    """
    if not ASSET_STORE:
        return {
            "high": {"count": 0, "pct": 0},
            "medium": {"count": 0, "pct": 0},
            "low": {"count": 0, "pct": 0},
            "total": 0,
            "auto_approve_eligible": 0
        }

    assets = list(ASSET_STORE.values())
    total = len(assets)

    # Count by confidence tier
    high = sum(1 for a in assets if a.confidence_score > 0.8)
    medium = sum(1 for a in assets if 0.5 < a.confidence_score <= 0.8)
    low = sum(1 for a in assets if a.confidence_score <= 0.5)

    # Count auto-approve eligible (high confidence + no errors)
    auto_approve = sum(1 for a in assets
                       if a.confidence_score > 0.8
                       and not getattr(a, 'validation_errors', None))

    return {
        "high": {
            "count": high,
            "pct": round(high / total * 100, 1) if total > 0 else 0,
            "label": "High (80%+)"
        },
        "medium": {
            "count": medium,
            "pct": round(medium / total * 100, 1) if total > 0 else 0,
            "label": "Medium (50-80%)"
        },
        "low": {
            "count": low,
            "pct": round(low / total * 100, 1) if total > 0 else 0,
            "label": "Low (<50%)"
        },
        "total": total,
        "auto_approve_eligible": auto_approve
    }


@app.get("/system-status")
def get_system_status():
    """
    Get system status including AI availability, memory patterns, etc.
    """
    # Check OpenAI API availability
    ai_available = True
    ai_status = "Online"
    try:
        import os
        if not os.getenv("OPENAI_API_KEY"):
            ai_available = False
            ai_status = "No API Key"
    except Exception:
        ai_available = False
        ai_status = "Error"

    # Check memory engine patterns
    memory_patterns = 0
    try:
        from pathlib import Path
        memory_path = Path(__file__).resolve().parent / "logic" / "classification_memory.json"
        if memory_path.exists():
            import json
            with open(memory_path, "r") as f:
                memory_data = json.load(f)
                memory_patterns = len(memory_data.get("assets", []))
    except Exception:
        pass

    # Count classification rules
    rules_count = 0
    try:
        rules_path = Path(__file__).resolve().parent / "logic" / "config" / "rules.json"
        if rules_path.exists():
            import json
            with open(rules_path, "r") as f:
                rules_data = json.load(f)
                rules_count = len(rules_data.get("rules", []))
    except Exception:
        pass

    return {
        "ai": {
            "available": ai_available,
            "status": ai_status,
            "model": "GPT-4o-mini" if ai_available else "Rules Only"
        },
        "memory": {
            "patterns_learned": memory_patterns,
            "status": "Active" if memory_patterns > 0 else "Empty"
        },
        "rules": {
            "count": rules_count,
            "status": "Loaded" if rules_count > 0 else "Not Found"
        },
        "backend": {
            "status": "Online",
            "version": "1.0.0"
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)