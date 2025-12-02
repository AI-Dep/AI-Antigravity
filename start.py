#!/usr/bin/env python
"""Railway startup script - handles PYTHONPATH properly."""
import os
import sys

# Add /app to Python path
sys.path.insert(0, '/app')

# Import and run
from backend.api import app
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
