# fixed_asset_ai/logic/ai_rpa_orchestrator.py
"""
AI + RPA Orchestration Layer
Coordinates AI classification and RPA automation for end-to-end workflow

Supports Two RPA Approaches:
- Tier 1: Import-based automation (fast, for bulk imports)
- Tier 2: UI automation (slower, more reliable fallback)
"""

import pandas as pd
from typing import Dict, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path

from .logging_utils import get_logger
from .fa_export import build_fa, export_fa_excel
from .rpa_fa_cs import FARobotOrchestrator, RPAConfig
from .rpa_fa_cs_import import HybridFACSAutomation

logger = get_logger(__name__)


class AIRPAOrchestrator:
    """
    Orchestrates the complete AI + RPA workflow:
    1. AI Classification
    2. Data Export Preparation
    3. RPA Automation into FA CS

    Supports hybrid automation:
    - Tier 1: Import-based (fast, recommended for 100+ assets)
    - Tier 2: UI automation (fallback, works for all scenarios)
    """

    def __init__(self, config: Optional[RPAConfig] = None, use_import_automation: bool = True):
        """
        Initialize orchestrator

        Args:
            config: RPA configuration
            use_import_automation: If True, use import-based automation (Tier 1) with UI fallback (Tier 2)
                                   If False, use only UI automation (Tier 2)
        """
        self.config = config or RPAConfig()
        self.use_import_automation = use_import_automation

        # Initialize appropriate automation system
        if use_import_automation:
            logger.info("Using Hybrid Automation (Import + UI fallback)")
            self.hybrid_orchestrator = HybridFACSAutomation(self.config)
        else:
            logger.info("Using UI-only Automation")
            self.hybrid_orchestrator = None

        self.rpa_orchestrator = FARobotOrchestrator(self.config)
        self.execution_log = []

    def run_full_workflow(
        self,
        classified_df: pd.DataFrame,
        tax_year: int,
        strategy: str,
        taxable_income: float,
        use_acq_if_missing: bool = True,
        preview_mode: bool = False,
        auto_run_rpa: bool = False,
        client_id: str = "default",
        force_ui_automation: bool = False,
    ) -> Dict:
        """
        Run the complete workflow from classified data to FA CS input

        Args:
            classified_df: DataFrame with AI-classified assets
            tax_year: Tax year for depreciation
            strategy: Tax strategy (Aggressive/Balanced/Conservative)
            taxable_income: Taxable income for Section 179 limits
            use_acq_if_missing: Use acquisition date when in-service date missing
            preview_mode: If True, only process first 3 assets
            auto_run_rpa: If True, automatically run RPA (otherwise just prepare data)
            client_id: Client identifier for field mapping (default: "default")
            force_ui_automation: If True, skip import and use UI automation directly

        Returns:
            Dictionary with workflow results and statistics
        """
        workflow_start = datetime.now()
        self.execution_log = []

        results = {
            "workflow_id": f"fa_workflow_{workflow_start.strftime('%Y%m%d_%H%M%S')}",
            "start_time": workflow_start.isoformat(),
            "steps": {},
            "success": False,
        }

        try:
            # ================================================================
            # STEP 1: Prepare FA CS Export Data
            # ================================================================
            self._log("Starting FA CS data preparation")

            fa_df = build_fa(
                df=classified_df,
                tax_year=tax_year,
                strategy=strategy,
                taxable_income=taxable_income,
                use_acq_if_missing=use_acq_if_missing,
            )

            results["steps"]["data_preparation"] = {
                "status": "success",
                "asset_count": len(fa_df),
                "columns": fa_df.columns.tolist(),
            }

            self._log(f"Prepared {len(fa_df)} assets for FA CS import")

            # ================================================================
            # STEP 2: Generate Excel Export (Backup)
            # ================================================================
            self._log("Generating Excel backup file")

            excel_bytes = export_fa_excel(fa_df)
            backup_filename = f"FA_CS_Export_{workflow_start.strftime('%Y%m%d_%H%M%S')}.xlsx"

            # Save backup locally
            backup_path = Path(backup_filename)
            with open(backup_path, "wb") as f:
                f.write(excel_bytes)

            results["steps"]["excel_export"] = {
                "status": "success",
                "filename": backup_filename,
                "file_size": len(excel_bytes),
            }

            self._log(f"Excel backup saved: {backup_filename}")

            # ================================================================
            # STEP 3: RPA Automation (if enabled)
            # ================================================================
            if auto_run_rpa:
                self._log("Initiating RPA automation")

                # Choose automation method based on settings
                if self.use_import_automation and not force_ui_automation:
                    # Tier 1: Import-based automation (with UI fallback)
                    self._log("Using Tier 1: Import-based automation (with UI fallback)")

                    rpa_stats = self.hybrid_orchestrator.process_assets(
                        excel_file_path=str(backup_path),
                        df=fa_df if preview_mode else fa_df,  # Provide DataFrame for UI fallback
                        client_id=client_id,
                        force_ui_automation=False
                    )

                    results["steps"]["rpa_automation"] = {
                        "status": "success" if rpa_stats.get("failed", 0) == 0 else "partial",
                        "method": rpa_stats.get("method_used", "unknown"),
                        "statistics": rpa_stats,
                        "total_assets": rpa_stats.get("total_assets", 0),
                        "succeeded": rpa_stats.get("succeeded", 0),
                        "failed": rpa_stats.get("failed", 0),
                    }

                    self._log(
                        f"RPA automation complete ({rpa_stats.get('method_used', 'unknown')}): "
                        f"{rpa_stats.get('succeeded', 0)} succeeded, {rpa_stats.get('failed', 0)} failed"
                    )

                else:
                    # Tier 2: UI automation only
                    self._log("Using Tier 2: UI automation (field-by-field entry)")

                    # Initialize RPA
                    if not self.rpa_orchestrator.initialize():
                        results["steps"]["rpa_automation"] = {
                            "status": "failed",
                            "error": "Failed to connect to Fixed Asset CS",
                        }
                        self._log("RPA initialization failed", level="error")
                    else:
                        # Run UI automation
                        rpa_stats = self.rpa_orchestrator.run_automation(
                            df=fa_df,
                            preview_mode=preview_mode,
                        )

                        results["steps"]["rpa_automation"] = {
                            "status": "success" if rpa_stats["failed"] == 0 else "partial",
                            "method": "ui_automation",
                            "statistics": rpa_stats,
                            "processed": rpa_stats["processed"],
                            "succeeded": rpa_stats["succeeded"],
                            "failed": rpa_stats["failed"],
                        }

                        self._log(
                            f"RPA automation complete (UI): {rpa_stats['succeeded']} succeeded, "
                            f"{rpa_stats['failed']} failed"
                        )

            else:
                results["steps"]["rpa_automation"] = {
                    "status": "skipped",
                    "note": "Auto-run RPA was disabled",
                }
                self._log("RPA automation skipped (auto_run_rpa=False)")

            # ================================================================
            # WORKFLOW COMPLETE
            # ================================================================
            workflow_end = datetime.now()
            duration = (workflow_end - workflow_start).total_seconds()

            results["success"] = True
            results["end_time"] = workflow_end.isoformat()
            results["duration_seconds"] = duration
            results["execution_log"] = self.execution_log

            self._log(f"Workflow complete in {duration:.2f} seconds")

            # Save execution log
            self._save_execution_log(results)

            return results

        except Exception as e:
            self._log(f"Workflow error: {e}", level="error")
            results["success"] = False
            results["error"] = str(e)
            results["execution_log"] = self.execution_log
            return results

    def run_rpa_only(
        self,
        fa_df: pd.DataFrame,
        preview_mode: bool = False,
    ) -> Dict:
        """
        Run only the RPA automation step (data already prepared)

        Args:
            fa_df: Pre-formatted FA CS DataFrame
            preview_mode: If True, only process first 3 assets

        Returns:
            RPA statistics
        """
        self._log("Running RPA-only mode")

        if not self.rpa_orchestrator.initialize():
            return {
                "success": False,
                "error": "Failed to initialize RPA connection to Fixed Asset CS",
            }

        stats = self.rpa_orchestrator.run_automation(
            df=fa_df,
            preview_mode=preview_mode,
        )

        return {
            "success": stats["failed"] == 0,
            "statistics": stats,
        }

    def validate_fa_cs_connection(self) -> Tuple[bool, str]:
        """
        Validate connection to Fixed Asset CS

        Returns:
            (success, message) tuple
        """
        try:
            if not self.rpa_orchestrator.window_manager.is_fa_cs_running():
                return False, "Fixed Asset CS is not running. Please start the application."

            if not self.rpa_orchestrator.window_manager.connect_to_fa_cs():
                return False, "Failed to connect to Fixed Asset CS window."

            return True, "Successfully connected to Fixed Asset CS"

        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def _log(self, message: str, level: str = "info"):
        """Add entry to execution log"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
        }
        self.execution_log.append(log_entry)

        # Also log to standard logger
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def _save_execution_log(self, results: Dict):
        """Save execution log to file"""
        try:
            log_filename = f"workflow_log_{results['workflow_id']}.json"
            with open(log_filename, "w") as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"Execution log saved: {log_filename}")
        except Exception as e:
            logger.error(f"Failed to save execution log: {e}")


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def run_ai_to_rpa_workflow(
    classified_df: pd.DataFrame,
    tax_year: int,
    strategy: str,
    taxable_income: float,
    preview_mode: bool = False,
    auto_run_rpa: bool = True,
) -> Dict:
    """
    Convenience function to run complete AI to RPA workflow

    Args:
        classified_df: DataFrame with AI-classified assets
        tax_year: Tax year
        strategy: Tax strategy
        taxable_income: Taxable income for Section 179
        preview_mode: Test mode (first 3 assets only)
        auto_run_rpa: Whether to automatically run RPA

    Returns:
        Results dictionary
    """
    orchestrator = AIRPAOrchestrator()
    return orchestrator.run_full_workflow(
        classified_df=classified_df,
        tax_year=tax_year,
        strategy=strategy,
        taxable_income=taxable_income,
        preview_mode=preview_mode,
        auto_run_rpa=auto_run_rpa,
    )
