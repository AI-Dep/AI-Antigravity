# backend/rpa/__init__.py
"""
RPA Integration Module for FA CS Automator

UiPath integration for Fixed Asset CS automation:
- rpa_fa_cs: Core RPA functions for FA CS interaction
- rpa_fa_cs_import: Import workflow automation
- ai_rpa_orchestrator: AI-driven RPA orchestration
"""

from .rpa_fa_cs import *
from .rpa_fa_cs_import import *
from .ai_rpa_orchestrator import *
