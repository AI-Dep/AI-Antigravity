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

# Add project root to sys.path to allow imports from backend.logic
# This must happen BEFORE importing services that depend on backend.logic
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.importer import ImporterService
from services.classifier import ClassifierService
from services.auditor import AuditorService
from services.exporter import ExporterService
from models.asset import Asset

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

@app.get("/")
def read_root():
    return {"status": "Backend Online", "version": "1.0.0"}

@app.get("/check-facs")
def check_facs():
    # SAFETY CHECK: Is Fixed Assets CS running?
    running = "FAwin.exe" in (p.name() for p in psutil.process_iter())
    return {"running": running}

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
        ASSET_STORE.clear() # Clear previous upload for now
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
    
    # Generate Excel
    excel_file = exporter.generate_fa_cs_export(assets)
    
    # Save to Bot Handoff Folder
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