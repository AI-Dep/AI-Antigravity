# backend/rpa/__init__.py
"""
RPA Integration Module for FA CS Automator

UiPath integration for Fixed Asset CS automation:
- rpa_fa_cs: Core RPA functions for FA CS interaction
- rpa_fa_cs_import: Import workflow automation
- ai_rpa_orchestrator: AI-driven RPA orchestration
"""

# Explicit imports instead of wildcard imports for better clarity and IDE support
from .rpa_fa_cs import (
    RPAConfig,
    FACSWindowManager,
    FACSDataEntry,
    FARobotOrchestrator,
    run_fa_cs_automation,
    test_fa_cs_connection,
)

from .rpa_fa_cs_import import (
    ImportMappingConfig,
    FACSImportAutomation,
    HybridFACSAutomation,
    create_import_ready_excel,
)

from .ai_rpa_orchestrator import (
    AIRPAOrchestrator,
    run_ai_to_rpa_workflow,
)

__all__ = [
    # rpa_fa_cs
    "RPAConfig",
    "FACSWindowManager",
    "FACSDataEntry",
    "FARobotOrchestrator",
    "run_fa_cs_automation",
    "test_fa_cs_connection",
    # rpa_fa_cs_import
    "ImportMappingConfig",
    "FACSImportAutomation",
    "HybridFACSAutomation",
    "create_import_ready_excel",
    # ai_rpa_orchestrator
    "AIRPAOrchestrator",
    "run_ai_to_rpa_workflow",
]
