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

# Add project root to sys.path to allow imports
# This must happen BEFORE importing services that depend on backend.logic
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.importer import ImporterService
from backend.services.classifier import ClassifierService
from backend.services.auditor import AuditorService
from backend.services.exporter import ExporterService
from backend.models.asset import Asset

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
ASSET_STORE: Dict[int, Asset] = {}
APPROVED_ASSETS: set = set()  # Track CPA-approved row_indexes

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
        bonus_info = tax_year_config.get_bonus_depreciation_rate(tax_year)
        config["bonus_rate"] = bonus_info.get("rate", 0) if isinstance(bonus_info, dict) else bonus_info
        config["section_179_limit"] = tax_year_config.get_section_179_limit(tax_year)
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
    if ASSET_STORE:
        assets = list(ASSET_STORE.values())
        classifier._classify_transaction_types(assets, tax_year)

        # Count reclassified assets
        trans_types = {}
        for a in assets:
            tt = a.transaction_type or 'unknown'
            trans_types[tt] = trans_types.get(tt, 0) + 1

    return {
        "status": "updated",
        "tax_year": tax_year,
        "de_minimis_threshold": de_minimis_threshold,
        "has_afs": has_afs,
        "assets_reclassified": len(ASSET_STORE),
        "transaction_type_breakdown": trans_types if ASSET_STORE else {}
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

    # 2. Check for assets missing cost
    zero_cost = [a for a in assets if a.cost <= 0]
    if zero_cost:
        critical_warnings.append({
            "type": "MISSING_COST",
            "message": f"{len(zero_cost)} assets have $0 or missing cost",
            "impact": "Cannot calculate depreciation without cost basis",
            "action": "Enter cost for each asset",
            "affected_count": len(zero_cost)
        })

    # ===== REGULAR WARNINGS =====

    # 3. Check for assets missing dates
    missing_dates = [a for a in assets if not a.in_service_date and not a.acquisition_date]
    if missing_dates:
        warnings.append({
            "type": "MISSING_DATES",
            "message": f"{len(missing_dates)} assets have no in-service or acquisition date",
            "impact": "Cannot determine if current year addition or existing asset",
            "action": "Add in-service dates for proper classification",
            "affected_count": len(missing_dates)
        })

    # 4. Transaction type breakdown check
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

    # 5. De minimis candidates
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

    # 6. Unclassified assets
    unclassified = [a for a in assets if a.macrs_class in ["Unclassified", "Unknown", None, ""]]
    if unclassified:
        warnings.append({
            "type": "UNCLASSIFIED_ASSETS",
            "message": f"{len(unclassified)} assets could not be automatically classified",
            "impact": "Manual MACRS class assignment required before export",
            "action": "Review and assign MACRS class to each unclassified asset",
            "affected_count": len(unclassified)
        })

    # ===== INFO MESSAGES =====

    # 7. Transaction type summary
    info_messages.append({
        "type": "TRANSACTION_SUMMARY",
        "message": "Asset classification summary",
        "breakdown": trans_types,
        "tax_year": tax_year
    })

    # 8. OBBBA 2025 info
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
    temp_file = f"temp_{file.filename}"
    try:
        # Save uploaded file temporarily
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 1. Parse Excel
        assets = importer.parse_excel(temp_file)

        # 2. Classify Assets (MACRS + Transaction Types)
        # Uses the configured tax year for proper classification
        tax_year = TAX_CONFIG["tax_year"]
        classified_assets = classifier.classify_batch(assets, tax_year=tax_year)

        # 3. Store in Memory
        ASSET_STORE.clear()  # Clear previous upload for now
        APPROVED_ASSETS.clear()  # Clear approvals too
        for asset in classified_assets:
            ASSET_STORE[asset.row_index] = asset

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
            
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as cleanup_error:
                print(f"Warning: Failed to delete temp file {temp_file}: {cleanup_error}")

@app.post("/assets/{row_index}/update", response_model=Asset)
def update_asset(row_index: int, update_data: Dict = Body(...)):
    """
    Updates a specific asset and logs the change in the audit trail.
    """
    if row_index not in ASSET_STORE:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset = ASSET_STORE[row_index]

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

@app.post("/assets/{row_index}/approve")
def approve_asset(row_index: int):
    """
    CPA approves a single asset for export.
    """
    if row_index not in ASSET_STORE:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset = ASSET_STORE[row_index]

    # Can't approve assets with validation errors
    if getattr(asset, 'validation_errors', None):
        raise HTTPException(status_code=400, detail="Cannot approve asset with validation errors")

    APPROVED_ASSETS.add(row_index)
    return {"approved": True, "row_index": row_index}

@app.post("/assets/approve-batch")
def approve_batch(row_indexes: List[int] = Body(...)):
    """
    CPA approves multiple assets at once (e.g., all high-confidence items).
    """
    approved = []
    errors = []

    for row_index in row_indexes:
        if row_index not in ASSET_STORE:
            errors.append({"row_index": row_index, "error": "Not found"})
            continue

        asset = ASSET_STORE[row_index]
        if getattr(asset, 'validation_errors', None):
            errors.append({"row_index": row_index, "error": "Has validation errors"})
            continue

        APPROVED_ASSETS.add(row_index)
        approved.append(row_index)

    return {"approved": approved, "errors": errors, "total_approved": len(approved)}

@app.delete("/assets/{row_index}/approve")
def unapprove_asset(row_index: int):
    """
    Remove approval from an asset.
    """
    if row_index in APPROVED_ASSETS:
        APPROVED_ASSETS.discard(row_index)
        return {"approved": False, "row_index": row_index}
    return {"approved": False, "row_index": row_index, "message": "Was not approved"}

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
    
    # Generate Excel
    excel_file = exporter.generate_fa_cs_export(assets)

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
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=FA_CS_Import.xlsx"}
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)