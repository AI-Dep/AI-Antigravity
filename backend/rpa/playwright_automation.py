"""
Playwright-Based Web Automation Module for Fixed Asset Entry

Cross-platform alternative to pywinauto/UiPath for web-based accounting systems.
Supports Thomson Reuters CS Professional Suite Online, QuickBooks Online,
and other web-based fixed asset management systems.

Benefits over UiPath/pywinauto:
- No license costs (open source)
- Cross-platform (Windows, Mac, Linux)
- Easier to maintain (Python-native)
- Headless mode for server deployment
- Better debugging tools

Usage:
    from backend.rpa.playwright_automation import PlaywrightFAAutomation

    async with PlaywrightFAAutomation() as automation:
        await automation.login(url, username, password)
        results = await automation.enter_assets(assets_df)
"""

import asyncio
import logging
import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

# Check if Playwright is available
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning(
        "Playwright not installed. Install with: pip install playwright && playwright install"
    )
    # Define dummy types for type hints
    Page = Any
    Browser = Any
    BrowserContext = Any
    PlaywrightTimeout = TimeoutError


# ==============================================================================
# CONFIGURATION
# ==============================================================================

@dataclass
class PlaywrightConfig:
    """Configuration for Playwright automation."""

    # Browser settings
    browser_type: str = "chromium"  # chromium, firefox, webkit
    headless: bool = False  # Set True for server/CI environments
    slow_mo: int = 100  # Milliseconds between actions (for debugging)

    # Timeouts (milliseconds)
    default_timeout: int = 30000
    navigation_timeout: int = 60000
    element_timeout: int = 10000

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    # Screenshot settings
    screenshot_on_error: bool = True
    screenshot_dir: str = "rpa_screenshots"

    # Logging
    trace_enabled: bool = False  # Enable Playwright trace for debugging
    video_enabled: bool = False  # Record video of automation

    # Target system (determines selectors and workflow)
    target_system: str = "generic"  # generic, thomson_cloud, quickbooks

    # Credentials (loaded from environment or config)
    credentials_env_prefix: str = "FA_RPA_"


@dataclass
class AutomationResult:
    """Result of an automation operation."""
    success: bool
    message: str
    assets_processed: int = 0
    assets_succeeded: int = 0
    assets_failed: int = 0
    errors: List[Dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    screenshots: List[str] = field(default_factory=list)


# ==============================================================================
# SELECTOR DEFINITIONS
# ==============================================================================

# Selectors for different target systems
# These can be customized per client or system

SELECTORS = {
    "generic": {
        "login_username": 'input[name="username"], input[type="email"], #username',
        "login_password": 'input[name="password"], input[type="password"], #password',
        "login_button": 'button[type="submit"], input[type="submit"], .login-button',
        "asset_form": 'form.asset-form, #asset-entry, .fixed-asset-form',
        "asset_id": 'input[name="asset_id"], #asset-id, .asset-number',
        "description": 'input[name="description"], #description, textarea[name="description"]',
        "cost": 'input[name="cost"], #cost, .cost-field',
        "date_in_service": 'input[name="date_in_service"], #date-in-service, input[type="date"]',
        "life_years": 'input[name="life"], #life-years, select[name="recovery_period"]',
        "method": 'select[name="method"], #depreciation-method',
        "save_button": 'button[type="submit"], .save-button, #save-asset',
        "new_asset_button": '.new-asset, #add-asset, button:has-text("New Asset")',
        "success_indicator": '.success-message, .toast-success, [data-status="saved"]',
        "error_indicator": '.error-message, .toast-error, .validation-error',
    },
    "thomson_cloud": {
        # Thomson Reuters CS Professional Suite Online selectors
        # These would need to be updated based on actual application
        "login_username": '#Username, input[name="UserName"]',
        "login_password": '#Password, input[name="Password"]',
        "login_button": '#LoginButton, button[type="submit"]',
        "asset_module": 'a[href*="FixedAssets"], .fa-module-link',
        "asset_form": '.asset-entry-form',
        "asset_id": '#AssetNumber',
        "description": '#Description',
        "cost": '#Cost',
        "date_in_service": '#DateInService',
        "life_years": '#RecoveryPeriod',
        "method": '#DepreciationMethod',
        "convention": '#Convention',
        "save_button": '#SaveAsset',
        "new_asset_button": '#NewAsset',
        "success_indicator": '.save-success, .notification-success',
        "error_indicator": '.validation-error, .save-error',
    },
    "quickbooks": {
        # QuickBooks Online Fixed Asset Manager selectors
        "login_username": '#ius-userid',
        "login_password": '#ius-password',
        "login_button": '#ius-sign-in-submit-btn',
        "asset_form": '.asset-form',
        "asset_id": 'input[data-field="assetNumber"]',
        "description": 'input[data-field="name"]',
        "cost": 'input[data-field="originalCost"]',
        "date_in_service": 'input[data-field="purchaseDate"]',
        "save_button": 'button[data-cy="save-button"]',
    },
}


# ==============================================================================
# PLAYWRIGHT AUTOMATION CLASS
# ==============================================================================

class PlaywrightFAAutomation:
    """
    Playwright-based fixed asset automation.

    Cross-platform web automation for entering assets into accounting systems.
    """

    def __init__(self, config: Optional[PlaywrightConfig] = None):
        """
        Initialize the automation.

        Args:
            config: Playwright configuration. Uses defaults if not provided.
        """
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed. "
                "Install with: pip install playwright && playwright install chromium"
            )

        self.config = config or PlaywrightConfig()
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Get selectors for target system
        self.selectors = SELECTORS.get(
            self.config.target_system,
            SELECTORS["generic"]
        )

        # Ensure screenshot directory exists
        if self.config.screenshot_on_error:
            Path(self.config.screenshot_dir).mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            "total_processed": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": [],
        }

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()

    async def start(self) -> None:
        """Start the browser and create a new page."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()

        # Select browser type
        browser_launchers = {
            "chromium": self.playwright.chromium,
            "firefox": self.playwright.firefox,
            "webkit": self.playwright.webkit,
        }
        launcher = browser_launchers.get(
            self.config.browser_type,
            self.playwright.chromium
        )

        # Launch browser
        self.browser = await launcher.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )

        # Create context with optional video recording
        context_options = {}
        if self.config.video_enabled:
            context_options["record_video_dir"] = self.config.screenshot_dir

        self.context = await self.browser.new_context(**context_options)

        # Set default timeout
        self.context.set_default_timeout(self.config.default_timeout)

        # Enable tracing if configured
        if self.config.trace_enabled:
            await self.context.tracing.start(screenshots=True, snapshots=True)

        # Create page
        self.page = await self.context.new_page()

        logger.info(f"Browser started: {self.config.browser_type} (headless={self.config.headless})")

    async def stop(self) -> None:
        """Close browser and cleanup."""
        if self.config.trace_enabled and self.context:
            trace_path = Path(self.config.screenshot_dir) / f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            await self.context.tracing.stop(path=str(trace_path))
            logger.info(f"Trace saved to: {trace_path}")

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        logger.info("Browser closed")

    async def take_screenshot(self, name: str = "screenshot") -> str:
        """Take a screenshot and return the path."""
        if not self.page:
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = Path(self.config.screenshot_dir) / filename

        await self.page.screenshot(path=str(filepath))
        logger.info(f"Screenshot saved: {filepath}")

        return str(filepath)

    async def login(
        self,
        url: str,
        username: str,
        password: str,
    ) -> bool:
        """
        Log in to the target accounting system.

        Args:
            url: Login URL
            username: Username/email
            password: Password

        Returns:
            True if login succeeded
        """
        try:
            logger.info(f"Navigating to: {url}")
            await self.page.goto(url, timeout=self.config.navigation_timeout)

            # Wait for login form
            await self.page.wait_for_selector(
                self.selectors["login_username"],
                timeout=self.config.element_timeout
            )

            # Fill credentials
            await self.page.fill(self.selectors["login_username"], username)
            await self.page.fill(self.selectors["login_password"], password)

            # Click login button
            await self.page.click(self.selectors["login_button"])

            # Wait for navigation (login completion)
            await self.page.wait_for_load_state("networkidle")

            # Check if still on login page (login failed)
            try:
                await self.page.wait_for_selector(
                    self.selectors["login_username"],
                    timeout=2000
                )
                logger.error("Login failed - still on login page")
                await self.take_screenshot("login_failed")
                return False
            except PlaywrightTimeout:
                # Login page is gone, which means we logged in successfully
                logger.info("Login successful")
                return True

        except Exception as e:
            logger.error(f"Login error: {e}")
            await self.take_screenshot("login_error")
            return False

    async def navigate_to_assets(self) -> bool:
        """Navigate to the fixed assets module."""
        try:
            # Click on asset module link if available
            if "asset_module" in self.selectors:
                await self.page.click(self.selectors["asset_module"])
                await self.page.wait_for_load_state("networkidle")

            # Wait for asset form or new asset button
            await self.page.wait_for_selector(
                f'{self.selectors.get("asset_form", "body")}, {self.selectors["new_asset_button"]}',
                timeout=self.config.element_timeout
            )

            logger.info("Navigated to asset module")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to assets: {e}")
            await self.take_screenshot("navigation_error")
            return False

    async def enter_single_asset(self, asset: Dict[str, Any]) -> bool:
        """
        Enter a single asset into the system.

        Args:
            asset: Dictionary with asset data

        Returns:
            True if asset was entered successfully
        """
        try:
            # Click new asset button if needed
            try:
                new_btn = self.page.locator(self.selectors["new_asset_button"])
                if await new_btn.is_visible():
                    await new_btn.click()
                    await self.page.wait_for_timeout(500)
            except Exception:
                pass  # Form might already be ready

            # Fill asset fields
            field_mappings = [
                ("asset_id", str(asset.get("asset_id", asset.get("fa_cs_asset_no", "")))),
                ("description", str(asset.get("description", ""))),
                ("cost", str(asset.get("cost", ""))),
                ("date_in_service", str(asset.get("date_in_service", asset.get("in_service_date", "")))),
                ("life_years", str(asset.get("life_years", asset.get("recovery_period", "")))),
            ]

            for field_name, value in field_mappings:
                if value and field_name in self.selectors:
                    selector = self.selectors[field_name]
                    try:
                        element = self.page.locator(selector).first
                        if await element.is_visible():
                            # Clear existing value first
                            await element.fill("")
                            await element.fill(value)
                    except Exception as e:
                        logger.debug(f"Could not fill {field_name}: {e}")

            # Handle method dropdown if present
            if "method" in self.selectors and asset.get("method"):
                try:
                    await self.page.select_option(
                        self.selectors["method"],
                        label=str(asset.get("method"))
                    )
                except Exception:
                    pass  # Method might be auto-set

            # Save the asset
            await self.page.click(self.selectors["save_button"])

            # Wait for success or error indicator
            try:
                await self.page.wait_for_selector(
                    self.selectors["success_indicator"],
                    timeout=5000
                )
                logger.info(f"Asset saved: {asset.get('description', 'Unknown')}")
                return True
            except PlaywrightTimeout:
                # Check for error
                error_visible = await self.page.locator(
                    self.selectors["error_indicator"]
                ).first.is_visible()

                if error_visible:
                    error_text = await self.page.locator(
                        self.selectors["error_indicator"]
                    ).first.text_content()
                    logger.error(f"Save error: {error_text}")
                    return False

                # No explicit success/error, assume success
                logger.info(f"Asset saved (no confirmation): {asset.get('description', 'Unknown')}")
                return True

        except Exception as e:
            logger.error(f"Error entering asset: {e}")
            await self.take_screenshot(f"asset_error_{asset.get('asset_id', 'unknown')}")
            return False

    async def enter_assets(
        self,
        assets: pd.DataFrame,
        progress_callback: Optional[callable] = None,
    ) -> AutomationResult:
        """
        Enter multiple assets into the accounting system.

        Args:
            assets: DataFrame with asset data
            progress_callback: Optional callback(current, total, message)

        Returns:
            AutomationResult with statistics
        """
        start_time = datetime.now()
        result = AutomationResult(
            success=True,
            message="",
            assets_processed=0,
            assets_succeeded=0,
            assets_failed=0,
        )

        total = len(assets)
        logger.info(f"Starting to enter {total} assets")

        for idx, row in assets.iterrows():
            asset = row.to_dict()
            result.assets_processed += 1

            # Progress callback
            if progress_callback:
                progress_callback(
                    result.assets_processed,
                    total,
                    f"Entering asset {result.assets_processed}/{total}"
                )

            # Retry logic
            success = False
            for attempt in range(self.config.max_retries):
                try:
                    success = await self.enter_single_asset(asset)
                    if success:
                        break

                    # Retry delay
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)

                except Exception as e:
                    logger.error(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)

            if success:
                result.assets_succeeded += 1
            else:
                result.assets_failed += 1
                result.errors.append({
                    "asset_id": asset.get("asset_id"),
                    "description": asset.get("description"),
                    "error": "Failed after max retries",
                })

                if self.config.screenshot_on_error:
                    screenshot = await self.take_screenshot(f"failed_{asset.get('asset_id', idx)}")
                    result.screenshots.append(screenshot)

        # Calculate duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        # Set final status
        if result.assets_failed == 0:
            result.message = f"Successfully entered all {result.assets_succeeded} assets"
        else:
            result.success = result.assets_failed < result.assets_processed
            result.message = (
                f"Completed with {result.assets_failed} failures out of {result.assets_processed} assets"
            )

        logger.info(result.message)
        return result


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def is_playwright_available() -> bool:
    """Check if Playwright is installed and ready."""
    return _PLAYWRIGHT_AVAILABLE


async def run_automation(
    url: str,
    username: str,
    password: str,
    assets_df: pd.DataFrame,
    config: Optional[PlaywrightConfig] = None,
    progress_callback: Optional[callable] = None,
) -> AutomationResult:
    """
    Convenience function to run the full automation workflow.

    Args:
        url: Login URL
        username: Username
        password: Password
        assets_df: DataFrame with assets to enter
        config: Optional configuration
        progress_callback: Optional progress callback

    Returns:
        AutomationResult
    """
    async with PlaywrightFAAutomation(config) as automation:
        # Login
        if not await automation.login(url, username, password):
            return AutomationResult(
                success=False,
                message="Login failed",
            )

        # Navigate to assets
        if not await automation.navigate_to_assets():
            return AutomationResult(
                success=False,
                message="Failed to navigate to asset module",
            )

        # Enter assets
        return await automation.enter_assets(assets_df, progress_callback)


def run_automation_sync(
    url: str,
    username: str,
    password: str,
    assets_df: pd.DataFrame,
    config: Optional[PlaywrightConfig] = None,
    progress_callback: Optional[callable] = None,
) -> AutomationResult:
    """
    Synchronous wrapper for run_automation.

    Use this when calling from non-async code.
    """
    return asyncio.run(run_automation(
        url, username, password, assets_df, config, progress_callback
    ))
