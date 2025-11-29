# fixed_asset_ai/logic/rpa_fa_cs.py
"""
RPA Automation Module for Fixed Asset CS
Automates data entry into Thomson Reuters Fixed Asset CS software
"""

import time
import logging
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

from .logging_utils import get_logger

logger = get_logger(__name__)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

class RPAConfig:
    """Configuration for RPA automation"""

    # Timing settings (in seconds)
    WAIT_AFTER_CLICK = 0.5
    WAIT_AFTER_TYPING = 0.3
    WAIT_FOR_WINDOW = 2.0
    WAIT_FOR_DIALOG = 1.5
    RETRY_DELAY = 1.0

    # Application settings
    FA_CS_PROCESS_NAME = "FAwin.exe"
    FA_CS_WINDOW_TITLE = "Fixed Assets CS"

    # Safety settings
    MAX_RETRIES = 3
    ENABLE_FAILSAFE = True  # Move mouse to corner to abort
    SCREENSHOT_ON_ERROR = True

    # Field mapping
    FIELD_TAB_COUNTS = {
        "asset_id": 1,
        "description": 2,
        "date_in_service": 3,
        "cost": 4,
        "method": 5,
        "life": 6,
        "convention": 7,
    }


# ==============================================================================
# WINDOW MANAGER
# ==============================================================================

class FACSWindowManager:
    """Manages Fixed Asset CS window interactions"""

    def __init__(self, config: RPAConfig = None):
        self.config = config or RPAConfig()
        self.app: Optional[Application] = None
        self.main_window = None

        # Configure pyautogui safety
        if self.config.ENABLE_FAILSAFE:
            pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

    def is_fa_cs_running(self) -> bool:
        """Check if FA CS is currently running"""
        for proc in psutil.process_iter(['name']):
            try:
                if self.config.FA_CS_PROCESS_NAME.lower() in proc.info['name'].lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def connect_to_fa_cs(self) -> bool:
        """Connect to running FA CS application"""
        try:
            if not self.is_fa_cs_running():
                logger.error("Fixed Asset CS is not running")
                return False

            # Connect to the application
            self.app = Application(backend="uia").connect(
                path=self.config.FA_CS_PROCESS_NAME,
                timeout=10
            )

            # Find main window
            time.sleep(self.config.WAIT_FOR_WINDOW)
            self.main_window = self.app.window(title_re=f".*{self.config.FA_CS_WINDOW_TITLE}.*")

            logger.info("Successfully connected to Fixed Asset CS")
            return True

        except ElementNotFoundError:
            logger.error("Could not find Fixed Asset CS window")
            return False
        except Exception as e:
            logger.error(f"Error connecting to FA CS: {e}")
            return False

    def activate_window(self) -> bool:
        """Bring FA CS window to front"""
        try:
            if self.main_window:
                self.main_window.set_focus()
                time.sleep(self.config.WAIT_FOR_WINDOW)
                return True
            return False
        except Exception as e:
            logger.error(f"Error activating window: {e}")
            return False

    def take_screenshot(self, name: str = "error") -> Optional[str]:
        """Take screenshot for debugging"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"rpa_screenshot_{name}_{timestamp}.png"
            pyautogui.screenshot(filename)
            logger.info(f"Screenshot saved: {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None


# ==============================================================================
# DATA ENTRY AUTOMATION
# ==============================================================================

class FACSDataEntry:
    """Handles automated data entry into FA CS"""

    def __init__(self, window_manager: FACSWindowManager):
        self.wm = window_manager
        self.config = window_manager.config
        self.stats = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": []
        }

    def navigate_to_asset_entry(self) -> bool:
        """Navigate to new asset entry screen"""
        try:
            logger.info("Navigating to asset entry screen")

            # Typical FA CS navigation: File -> New -> Asset
            # This may need adjustment based on actual FA CS menu structure
            pyautogui.hotkey('alt', 'f')  # File menu
            time.sleep(self.config.WAIT_AFTER_CLICK)

            pyautogui.press('n')  # New
            time.sleep(self.config.WAIT_AFTER_CLICK)

            pyautogui.press('a')  # Asset
            time.sleep(self.config.WAIT_FOR_DIALOG)

            logger.info("Successfully navigated to asset entry")
            return True

        except Exception as e:
            logger.error(f"Error navigating to asset entry: {e}")
            if self.config.SCREENSHOT_ON_ERROR:
                self.wm.take_screenshot("navigation_error")
            return False

    def input_asset_data(self, asset: Dict) -> bool:
        """Input a single asset's data"""
        try:
            # CRITICAL: FA CS requires Asset# to be NUMERIC ONLY
            # Use "Asset #" (numeric) for FA CS input, not "Asset ID" (may be alphanumeric)
            asset_num = asset.get("Asset #", asset.get("Asset ID", ""))
            original_id = asset.get("Original Asset ID", asset.get("Asset ID", ""))
            logger.info(f"Processing asset: {asset_num} (Original ID: {original_id})")

            # Asset # (must be numeric for FA CS)
            if "Asset #" in asset:
                # Validate numeric-only for FA CS
                asset_num_str = str(asset["Asset #"])
                if not asset_num_str.isdigit():
                    logger.warning(f"Asset # '{asset_num_str}' is not numeric. FA CS may reject this.")
                self._type_field(asset_num_str)
                self._tab()
            elif "Asset ID" in asset:
                # Fallback: Try to extract numeric portion or use as-is
                asset_id_str = str(asset["Asset ID"])
                numeric_only = ''.join(filter(str.isdigit, asset_id_str))
                if numeric_only:
                    logger.warning(f"Using numeric portion '{numeric_only}' from Asset ID '{asset_id_str}'")
                    self._type_field(numeric_only)
                else:
                    logger.error(f"Asset ID '{asset_id_str}' has no numeric portion. FA CS will reject this.")
                    self._type_field(asset_id_str)  # Try anyway, will likely fail
                self._tab()

            # Description
            if "Property Description" in asset:
                self._type_field(str(asset["Property Description"]))
                self._tab()

            # Date In Service
            if "Date In Service" in asset and pd.notna(asset["Date In Service"]):
                date_str = self._format_date(asset["Date In Service"])
                self._type_field(date_str)
                self._tab()

            # Cost/Basis
            if "Cost/Basis" in asset:
                cost_str = self._format_currency(asset["Cost/Basis"])
                self._type_field(cost_str)
                self._tab()

            # Method
            if "Method" in asset and asset["Method"]:
                self._type_field(str(asset["Method"]))
                self._tab()

            # Life
            if "Life" in asset and asset["Life"]:
                self._type_field(str(asset["Life"]))
                self._tab()

            # Convention
            if "Convention" in asset and asset["Convention"]:
                self._type_field(str(asset["Convention"]))
                self._tab()

            # Section 179
            if "Section 179 Amount" in asset and asset["Section 179 Amount"]:
                sec179 = float(asset["Section 179 Amount"])
                if sec179 > 0:
                    self._type_field(self._format_currency(sec179))
                self._tab()

            # Bonus Depreciation
            if "Bonus Amount" in asset and asset["Bonus Amount"]:
                bonus = float(asset["Bonus Amount"])
                if bonus > 0:
                    self._type_field(self._format_currency(bonus))
                self._tab()

            # Save the entry
            self._save_asset()

            self.stats["succeeded"] += 1
            logger.info(f"Successfully processed asset: {asset_id}")
            return True

        except Exception as e:
            error_msg = f"Error processing asset {asset.get('Asset ID', 'unknown')}: {e}"
            logger.error(error_msg)
            self.stats["failed"] += 1
            self.stats["errors"].append(error_msg)

            if self.config.SCREENSHOT_ON_ERROR:
                self.wm.take_screenshot(f"asset_error_{asset.get('Asset ID', 'unknown')}")

            return False

    def process_dataframe(self, df: pd.DataFrame, start_index: int = 0) -> Dict:
        """Process entire dataframe of assets"""
        logger.info(f"Starting RPA processing for {len(df)} assets")

        # Ensure FA CS is active
        if not self.wm.activate_window():
            logger.error("Could not activate FA CS window")
            return self.stats

        # Process each asset
        for idx, row in df.iterrows():
            if idx < start_index:
                continue

            self.stats["processed"] += 1

            # Navigate to new asset entry
            if not self.navigate_to_asset_entry():
                logger.error(f"Failed to navigate to asset entry for row {idx}")
                self.stats["failed"] += 1
                continue

            # Input asset data
            asset_dict = row.to_dict()
            self.input_asset_data(asset_dict)

            # Brief pause between assets
            time.sleep(0.5)

            # Log progress every 10 assets
            if self.stats["processed"] % 10 == 0:
                logger.info(
                    f"Progress: {self.stats['processed']}/{len(df)} assets processed "
                    f"({self.stats['succeeded']} succeeded, {self.stats['failed']} failed)"
                )

        logger.info(
            f"RPA processing complete. Total: {self.stats['processed']}, "
            f"Succeeded: {self.stats['succeeded']}, Failed: {self.stats['failed']}"
        )

        return self.stats

    def _type_field(self, text: str):
        """Type text into current field"""
        if pd.notna(text) and str(text).strip():
            pyautogui.write(str(text), interval=0.05)
            time.sleep(self.config.WAIT_AFTER_TYPING)

    def _tab(self):
        """Press tab to move to next field"""
        pyautogui.press('tab')
        time.sleep(self.config.WAIT_AFTER_CLICK)

    def _save_asset(self):
        """Save current asset entry"""
        # Ctrl+S or specific save button
        pyautogui.hotkey('ctrl', 's')
        time.sleep(self.config.WAIT_FOR_DIALOG)

    def _format_date(self, date_val) -> str:
        """Format date for FA CS input (MM/DD/YYYY)"""
        if isinstance(date_val, (datetime, pd.Timestamp)):
            return date_val.strftime("%m/%d/%Y")
        return str(date_val)

    def _format_currency(self, value) -> str:
        """Format currency value"""
        try:
            return f"{float(value):.2f}"
        except (ValueError, TypeError):
            return "0.00"


# ==============================================================================
# MAIN RPA ORCHESTRATOR
# ==============================================================================

class FARobotOrchestrator:
    """Main orchestrator for FA CS RPA automation"""

    def __init__(self, config: RPAConfig = None):
        self.config = config or RPAConfig()
        self.window_manager = FACSWindowManager(self.config)
        self.data_entry: Optional[FACSDataEntry] = None

    def initialize(self) -> bool:
        """Initialize RPA components"""
        logger.info("Initializing FA CS RPA automation")

        logger.warning("=" * 70)
        logger.warning("IMPORTANT: Manual Login Required")
        logger.warning("=" * 70)
        logger.warning("RPA CANNOT automate the FA CS login process.")
        logger.warning("You MUST manually complete these steps BEFORE running RPA:")
        logger.warning("  1. Windows Security credential prompt (OS-level, cannot automate)")
        logger.warning("  2. RemoteApp session configuration (RDP layer, cannot automate)")
        logger.warning("  3. FA CS Sign-In button (fragile, manual click recommended)")
        logger.warning("  4. Thomson Reuters browser login (fragile, manual entry required)")
        logger.warning("  5. Email/Password entry (security risk to automate)")
        logger.warning("  6. MFA verification code (IMPOSSIBLE to automate - on your phone)")
        logger.warning("")
        logger.warning("Please ensure you are FULLY LOGGED IN to FA CS before proceeding.")
        logger.warning("See FA_CS_LOGIN_LIMITATIONS.md for detailed explanation.")
        logger.warning("=" * 70)

        # Check if FA CS is running
        if not self.window_manager.is_fa_cs_running():
            logger.error(
                "Fixed Asset CS is not running. Please start the application and "
                "complete the manual login process first."
            )
            logger.error(
                "Required: Complete Windows Security, RemoteApp, Thomson Reuters login, "
                "and MFA verification BEFORE running RPA."
            )
            return False

        # Connect to FA CS
        if not self.window_manager.connect_to_fa_cs():
            logger.error(
                "Failed to connect to FA CS. Ensure you have completed the manual login "
                "process and FA CS main window is visible."
            )
            return False

        # Initialize data entry handler
        self.data_entry = FACSDataEntry(self.window_manager)

        logger.info("✓ RPA initialization complete")
        logger.info("✓ FA CS connection established")
        logger.info("You may now proceed with automation")
        return True

    def run_automation(
        self,
        df: pd.DataFrame,
        start_index: int = 0,
        preview_mode: bool = False
    ) -> Dict:
        """
        Run the full automation process

        Args:
            df: DataFrame with asset data
            start_index: Index to start from (for resuming)
            preview_mode: If True, only process first 3 assets as test

        Returns:
            Statistics dictionary
        """
        if not self.data_entry:
            if not self.initialize():
                return {"error": "Failed to initialize RPA"}

        # Preview mode - limit to 3 assets
        if preview_mode:
            logger.info("Running in PREVIEW MODE - processing first 3 assets only")
            df = df.head(3)

        # Run the automation
        stats = self.data_entry.process_dataframe(df, start_index)

        return stats

    def resume_automation(self, df: pd.DataFrame, last_successful_index: int) -> Dict:
        """Resume automation from last successful point"""
        logger.info(f"Resuming automation from index {last_successful_index + 1}")
        return self.run_automation(df, start_index=last_successful_index + 1)


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def run_fa_cs_automation(
    df: pd.DataFrame,
    preview_mode: bool = False,
    config: Optional[RPAConfig] = None
) -> Dict:
    """
    Convenience function to run FA CS automation

    Args:
        df: DataFrame with FA CS formatted data
        preview_mode: If True, only process first 3 assets
        config: Optional custom configuration

    Returns:
        Statistics dictionary with results
    """
    orchestrator = FARobotOrchestrator(config)
    return orchestrator.run_automation(df, preview_mode=preview_mode)


def test_fa_cs_connection() -> bool:
    """Test if we can connect to FA CS"""
    config = RPAConfig()
    wm = FACSWindowManager(config)
    return wm.connect_to_fa_cs()
