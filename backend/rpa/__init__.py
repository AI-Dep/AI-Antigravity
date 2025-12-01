# backend/rpa/__init__.py
"""
RPA Integration Module for FA CS Automator

Supports multiple automation backends:
- Desktop (Windows): pywinauto/pyautogui for FA CS desktop application
- Web (Cross-platform): Playwright for web-based accounting systems
- Import: Excel import for bulk data entry (fastest method)

Modules:
- rpa_fa_cs: Desktop automation for FA CS (Windows only)
- rpa_fa_cs_import: Import workflow automation
- ai_rpa_orchestrator: AI-driven RPA orchestration
- playwright_automation: Web-based automation (cross-platform)
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

# Playwright-based web automation (cross-platform alternative)
from .playwright_automation import (
    PlaywrightConfig,
    PlaywrightFAAutomation,
    AutomationResult,
    is_playwright_available,
    run_automation_sync,
)

__all__ = [
    # rpa_fa_cs (Desktop - Windows)
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
    # playwright_automation (Web - Cross-platform)
    "PlaywrightConfig",
    "PlaywrightFAAutomation",
    "AutomationResult",
    "is_playwright_available",
    "run_automation_sync",
]
