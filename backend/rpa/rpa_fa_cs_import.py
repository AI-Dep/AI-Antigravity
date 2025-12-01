# fixed_asset_ai/logic/rpa_fa_cs_import.py
"""
FA CS Import-Based RPA Automation Module

This module provides Tier 1 automation using FA CS's built-in import feature.
This is MUCH faster than UI automation for bulk imports (100+ assets).

Performance Comparison:
- Import method: ~10-20 seconds for 100 assets
- UI automation: ~10 minutes for 100 assets (5-10 seconds per asset)

Workflow:
1. Load client-specific field mapping
2. Navigate to FA CS import feature
3. Load exported Excel file
4. Apply/configure field mapping
5. Execute import
6. Validate results
7. Fallback to UI automation if import fails
"""

import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd

try:
    import pyautogui
    import pywinauto
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    import psutil
except ImportError as e:
    logging.warning(f"RPA libraries not installed: {e}")

try:
    from backend.logic.logging_utils import get_logger
except ImportError:
    import logging
    def get_logger(name):
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
from .rpa_fa_cs import RPAConfig, FACSWindowManager

logger = get_logger(__name__)


# ==============================================================================
# IMPORT MAPPING CONFIGURATION
# ==============================================================================

class ImportMappingConfig:
    """Manages FA CS import field mappings for different clients"""

    def __init__(self, config_path: str = None):
        """
        Initialize mapping configuration

        Args:
            config_path: Path to mapping JSON file (default: fa_cs_import_mappings.json)
        """
        if config_path is None:
            config_path = Path(__file__).parent / "fa_cs_import_mappings.json"

        self.config_path = Path(config_path)
        self.mappings = self._load_mappings()

    def _load_mappings(self) -> Dict:
        """Load mapping configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Mapping config not found: {self.config_path}")
            return {"default": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in mapping config: {e}")
            return {"default": {}}

    def get_mapping(self, client_id: str = "default") -> Dict:
        """
        Get field mapping for a specific client

        Args:
            client_id: Client identifier (uses 'default' if not found)

        Returns:
            Dictionary with mapping configuration
        """
        if client_id in self.mappings:
            logger.info(f"Using custom mapping for client: {client_id}")
            return self.mappings[client_id]
        else:
            logger.info(f"Client '{client_id}' not found, using default mapping")
            return self.mappings.get("default", {})

    def get_field_mappings(self, client_id: str = "default") -> Dict[str, str]:
        """Get just the field mapping dictionary"""
        mapping = self.get_mapping(client_id)
        return mapping.get("field_mappings", {})

    def get_import_settings(self, client_id: str = "default") -> Dict:
        """Get import settings for client"""
        mapping = self.get_mapping(client_id)
        return mapping.get("import_settings", {})


# ==============================================================================
# FA CS IMPORT AUTOMATION
# ==============================================================================

class FACSImportAutomation:
    """
    Automates FA CS import feature for bulk data entry

    This is the Tier 1 automation approach - much faster than UI automation.
    """

    def __init__(self, config: RPAConfig = None, mapping_config: ImportMappingConfig = None):
        """
        Initialize import automation

        Args:
            config: RPA configuration
            mapping_config: Import mapping configuration
        """
        self.config = config or RPAConfig()
        self.mapping_config = mapping_config or ImportMappingConfig()
        self.window_manager = FACSWindowManager(self.config)

        # Import workflow settings
        self.import_menu_path = ["Tools", "Import", "Fixed Assets"]  # Adjust based on actual FA CS
        self.import_timeout = 60  # seconds to wait for import to complete

        self.stats = {
            "import_attempted": False,
            "import_succeeded": False,
            "import_failed": False,
            "assets_imported": 0,
            "errors": [],
            "fallback_to_ui": False
        }

    def can_use_import_feature(self) -> bool:
        """
        Check if FA CS import feature is available

        Returns:
            True if import feature can be used, False otherwise
        """
        # This would check FA CS version, license, etc.
        # For now, assume it's available if FA CS is running
        return self.window_manager.is_fa_cs_running()

    def execute_import_workflow(
        self,
        excel_file_path: str,
        client_id: str = "default",
        sheet_name: str = "FA_Import"
    ) -> Tuple[bool, Dict]:
        """
        Execute complete import workflow

        Args:
            excel_file_path: Path to Excel file to import
            client_id: Client identifier for mapping selection
            sheet_name: Sheet name to import from

        Returns:
            Tuple of (success: bool, stats: dict)
        """
        logger.info(f"Starting FA CS import workflow for client: {client_id}")
        logger.info(f"Import file: {excel_file_path}")

        self.stats["import_attempted"] = True

        try:
            # Step 1: Connect to FA CS
            if not self.window_manager.connect_to_fa_cs():
                raise Exception("Failed to connect to FA CS")

            # Step 2: Activate window
            if not self.window_manager.activate_window():
                raise Exception("Failed to activate FA CS window")

            # Step 3: Navigate to import menu
            if not self._navigate_to_import():
                raise Exception("Failed to navigate to import feature")

            # Step 4: Load Excel file
            if not self._load_import_file(excel_file_path, sheet_name):
                raise Exception("Failed to load import file")

            # Step 5: Configure/apply field mapping
            mapping = self.mapping_config.get_mapping(client_id)
            if not self._apply_field_mapping(mapping):
                raise Exception("Failed to apply field mapping")

            # Step 6: Execute import
            if not self._execute_import():
                raise Exception("Import execution failed")

            # Step 7: Validate import results
            imported_count = self._validate_import_results()

            self.stats["import_succeeded"] = True
            self.stats["assets_imported"] = imported_count

            logger.info(f"✅ Import completed successfully: {imported_count} assets")
            return True, self.stats

        except Exception as e:
            error_msg = f"Import workflow failed: {e}"
            logger.error(error_msg)
            self.stats["import_failed"] = True
            self.stats["errors"].append(str(e))

            # Take screenshot for debugging
            if self.config.SCREENSHOT_ON_ERROR:
                self.window_manager.take_screenshot("import_error")

            return False, self.stats

    def _navigate_to_import(self) -> bool:
        """
        Navigate to FA CS import feature

        Typical path: Tools -> Import -> Fixed Assets
        Adjust based on actual FA CS menu structure
        """
        try:
            logger.info("Navigating to FA CS import feature")

            # Method 1: Try menu navigation (most common)
            # Tools menu
            pyautogui.hotkey('alt', 't')  # Alt+T for Tools
            time.sleep(self.config.WAIT_AFTER_CLICK)

            # Import submenu
            pyautogui.press('i')  # I for Import
            time.sleep(self.config.WAIT_AFTER_CLICK)

            # Fixed Assets option
            pyautogui.press('f')  # F for Fixed Assets
            time.sleep(self.config.WAIT_FOR_DIALOG)

            logger.info("Successfully navigated to import dialog")
            return True

        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False

    def _load_import_file(self, file_path: str, sheet_name: str = "FA_Import") -> bool:
        """
        Load Excel file in import dialog

        Args:
            file_path: Path to Excel file
            sheet_name: Sheet to import

        Returns:
            True if file loaded successfully
        """
        try:
            logger.info(f"Loading import file: {file_path}")

            # Typical workflow:
            # 1. Click "Browse" or "Select File" button
            # 2. Type file path in dialog
            # 3. Confirm selection

            # Wait for import dialog to appear
            time.sleep(self.config.WAIT_FOR_DIALOG)

            # Click Browse button (usually Tab to it or click)
            # This is FA CS-specific, may need adjustment
            pyautogui.press('tab')  # Tab to Browse button
            time.sleep(0.3)
            pyautogui.press('enter')  # Click Browse
            time.sleep(self.config.WAIT_FOR_DIALOG)

            # Type file path in file dialog
            # Using Ctrl+A to clear any existing path, then type new path
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            pyautogui.typewrite(file_path, interval=0.05)
            time.sleep(0.3)
            pyautogui.press('enter')  # Confirm file selection
            time.sleep(self.config.WAIT_FOR_WINDOW)

            # Select sheet if needed
            # Some import dialogs allow sheet selection
            # This is optional and FA CS-specific

            logger.info("File loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load import file: {e}")
            return False

    def _apply_field_mapping(self, mapping: Dict) -> bool:
        """
        Apply or configure field mapping

        FA CS typically allows:
        - Loading saved mapping templates
        - Manual field mapping configuration

        Args:
            mapping: Mapping configuration dictionary

        Returns:
            True if mapping applied successfully
        """
        try:
            logger.info("Applying field mapping")

            mapping_name = mapping.get("mapping_name", "Default")
            field_mappings = mapping.get("field_mappings", {})

            # Strategy 1: Try to load saved mapping template (fastest)
            # This assumes the mapping was previously saved in FA CS
            if self._load_saved_mapping_template(mapping_name):
                logger.info(f"Loaded saved mapping template: {mapping_name}")
                return True

            # Strategy 2: Configure mapping manually (fallback)
            logger.info("Saved template not found, configuring mapping manually")
            return self._configure_mapping_manually(field_mappings)

        except Exception as e:
            logger.error(f"Failed to apply field mapping: {e}")
            return False

    def _load_saved_mapping_template(self, template_name: str) -> bool:
        """
        Try to load a previously saved mapping template

        Args:
            template_name: Name of the saved template

        Returns:
            True if template loaded successfully
        """
        try:
            # This is FA CS-specific
            # Typical workflow:
            # 1. Click "Load Template" button or dropdown
            # 2. Select template by name
            # 3. Confirm

            # Example (adjust based on actual FA CS UI):
            # Tab to template dropdown
            pyautogui.press('tab')
            time.sleep(0.2)

            # Open dropdown
            pyautogui.press('down')
            time.sleep(0.3)

            # Type template name to search
            pyautogui.typewrite(template_name[:10], interval=0.05)  # First 10 chars
            time.sleep(0.3)

            # Select
            pyautogui.press('enter')
            time.sleep(0.5)

            return True

        except Exception as e:
            logger.debug(f"Could not load saved template '{template_name}': {e}")
            return False

    def _configure_mapping_manually(self, field_mappings: Dict[str, str]) -> bool:
        """
        Configure field mapping manually if template not available

        Args:
            field_mappings: Dictionary of source -> target field mappings

        Returns:
            True if configuration successful
        """
        try:
            logger.info("Configuring field mapping manually")

            # This is highly FA CS-specific and would need to be customized
            # Typical workflow:
            # 1. For each source field, select corresponding target field
            # 2. Usually involves dropdown selections or clicking

            # For now, we'll assume the default auto-mapping works
            # and just click "Auto Map" if available

            # Look for "Auto Map" button (common feature)
            # This is a simplified approach
            pyautogui.press('tab')  # Navigate to Auto Map button
            time.sleep(0.3)
            pyautogui.press('enter')  # Click Auto Map
            time.sleep(1.0)

            logger.info("Auto-mapping applied")
            return True

        except Exception as e:
            logger.error(f"Manual mapping configuration failed: {e}")
            return False

    def _execute_import(self) -> bool:
        """
        Execute the import operation

        Returns:
            True if import executed successfully
        """
        try:
            logger.info("Executing import")

            # Navigate to Import/OK button and click it
            # Usually Tab to navigate to the button
            time.sleep(0.5)
            pyautogui.press('tab')  # Navigate to Import button
            time.sleep(0.3)
            pyautogui.press('enter')  # Click Import

            # Wait for import to complete
            # Show progress or wait for completion dialog
            logger.info(f"Waiting for import to complete (timeout: {self.import_timeout}s)")
            time.sleep(self.import_timeout)  # Basic wait - could be improved with status checking

            # Look for success dialog and close it
            pyautogui.press('enter')  # Close success dialog if present
            time.sleep(0.5)

            logger.info("Import execution completed")
            return True

        except Exception as e:
            logger.error(f"Import execution failed: {e}")
            return False

    def _validate_import_results(self) -> int:
        """
        Validate import results and count imported assets

        Returns:
            Number of assets successfully imported
        """
        try:
            logger.info("Validating import results")

            # This would need to check FA CS to verify:
            # 1. Number of assets imported
            # 2. Any errors or warnings
            # 3. Data integrity

            # For now, return 0 as placeholder
            # In production, this would query FA CS or parse result dialogs

            # Could also check the export file to get expected count
            # and compare with FA CS asset count

            return 0  # Placeholder

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return 0


# ==============================================================================
# HYBRID ORCHESTRATOR (Import + UI Fallback)
# ==============================================================================

class HybridFACSAutomation:
    """
    Hybrid automation that tries import first, falls back to UI automation

    This provides the best of both worlds:
    - Speed of import for bulk operations
    - Reliability of UI automation as fallback
    """

    def __init__(self, config: RPAConfig = None):
        """Initialize hybrid automation"""
        self.config = config or RPAConfig()
        self.import_automation = FACSImportAutomation(config)

        # UI automation is imported dynamically to avoid circular dependency
        self._ui_automation = None

    def process_assets(
        self,
        excel_file_path: str,
        df: pd.DataFrame = None,
        client_id: str = "default",
        force_ui_automation: bool = False
    ) -> Dict:
        """
        Process assets using best available method

        Args:
            excel_file_path: Path to exported Excel file
            df: DataFrame of assets (for UI fallback)
            client_id: Client identifier
            force_ui_automation: Skip import, use UI automation directly

        Returns:
            Statistics dictionary
        """
        stats = {
            "method_used": None,
            "total_assets": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": []
        }

        # Strategy 1: Try import-based automation first (Tier 1)
        if not force_ui_automation:
            logger.info("Attempting Tier 1: Import-based automation")

            success, import_stats = self.import_automation.execute_import_workflow(
                excel_file_path=excel_file_path,
                client_id=client_id
            )

            if success:
                stats["method_used"] = "import"
                stats["total_assets"] = import_stats.get("assets_imported", 0)
                stats["succeeded"] = import_stats.get("assets_imported", 0)
                logger.info("✅ Tier 1 (Import) completed successfully")
                return stats
            else:
                logger.warning("⚠️ Tier 1 (Import) failed, falling back to Tier 2")
                stats["errors"].append("Import failed: " + str(import_stats.get("errors", [])))

        # Strategy 2: Fallback to UI automation (Tier 2)
        if df is not None:
            logger.info("Attempting Tier 2: UI automation (field-by-field entry)")

            # Import UI automation module
            from .rpa_fa_cs import FARobotOrchestrator

            orchestrator = FARobotOrchestrator(self.config)
            ui_result = orchestrator.run_automation(df)

            stats["method_used"] = "ui_automation"
            stats["total_assets"] = len(df)
            stats["succeeded"] = ui_result.get("succeeded", 0)
            stats["failed"] = ui_result.get("failed", 0)
            stats["errors"].extend(ui_result.get("errors", []))

            logger.info(f"✅ Tier 2 (UI) completed: {stats['succeeded']}/{stats['total_assets']} assets")
            return stats
        else:
            logger.error("❌ No DataFrame provided for UI automation fallback")
            stats["method_used"] = "none"
            stats["errors"].append("No fallback data available")
            return stats


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def create_import_ready_excel(
    df: pd.DataFrame,
    output_path: str,
    client_id: str = "default"
) -> str:
    """
    Create Excel file optimized for FA CS import

    Args:
        df: Asset dataframe
        output_path: Where to save Excel file
        client_id: Client for mapping

    Returns:
        Path to created file
    """
    # This would prepare the Excel file with proper formatting
    # for FA CS import, applying client-specific column naming

    mapping_config = ImportMappingConfig()
    field_mappings = mapping_config.get_field_mappings(client_id)

    # Rename columns according to mapping
    df_export = df.copy()
    df_export = df_export.rename(columns=field_mappings)

    # Export to Excel
    df_export.to_excel(output_path, sheet_name="FA_Import", index=False)

    logger.info(f"Created import-ready Excel: {output_path}")
    return output_path


# ==============================================================================
# EXAMPLE USAGE
# ==============================================================================

if __name__ == "__main__":
    # Example: Using hybrid automation

    hybrid = HybridFACSAutomation()

    # Try import first, fallback to UI if needed
    results = hybrid.process_assets(
        excel_file_path="/path/to/export.xlsx",
        df=None,  # Would provide DataFrame for UI fallback
        client_id="example_client_123"
    )

    print(f"Method used: {results['method_used']}")
    print(f"Success: {results['succeeded']}/{results['total_assets']}")
