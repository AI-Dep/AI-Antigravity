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

    return {
        "total": total,
        "errors": errors,
        "needs_review": needs_review,
        "high_confidence": high_confidence,
        "approved": approved,
        "ready_for_export": errors == 0 and total > 0
    }

@app.post("/upload", response_model=List[Asset])
async def upload_file(file: UploadFile = File(...)):
    """
    Uploads an Excel file, parses it, and returns classified assets.
    """
    temp_file = f"temp_{file.filename}"
    try:
        # Save uploaded file temporarily
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 1. Parse Excel
        assets = importer.parse_excel(temp_file)
        
        # 2. Classify Assets
        classified_assets = classifier.classify_batch(assets)
        
        # 3. Store in Memory
        ASSET_STORE.clear()  # Clear previous upload for now
        APPROVED_ASSETS.clear()  # Clear approvals too
        for asset in classified_assets:
            ASSET_STORE[asset.row_index] = asset

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