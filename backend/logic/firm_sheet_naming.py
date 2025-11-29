"""
Fixed Asset AI - Firm-Specific Sheet Naming Support

Enhanced sheet role detection based on firm-specific naming conventions.
Supports multiple accounting firm formats and custom configurations.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import json
import fnmatch
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .sheet_analyzer import SheetRole


logger = logging.getLogger(__name__)


# ====================================================================================
# CONFIGURATION
# ====================================================================================

UNIFIED_MAPPINGS_PATH = Path(__file__).parent / "unified_mappings.json"


# ====================================================================================
# DATA CLASSES
# ====================================================================================

@dataclass
class SheetNamingConfig:
    """Configuration for sheet naming conventions"""
    firm_id: str
    firm_name: str
    additions_patterns: List[str]
    disposals_patterns: List[str]
    transfers_patterns: List[str]
    summary_patterns: List[str]
    skip_patterns: List[str]
    column_preferences: Dict[str, List[str]]

    @classmethod
    def from_dict(cls, firm_id: str, data: dict) -> "SheetNamingConfig":
        """Create from dictionary configuration"""
        naming = data.get("sheet_naming_convention", {})
        return cls(
            firm_id=firm_id,
            firm_name=data.get("firm_name", firm_id),
            additions_patterns=naming.get("additions_patterns", []),
            disposals_patterns=naming.get("disposals_patterns", []),
            transfers_patterns=naming.get("transfers_patterns", []),
            summary_patterns=naming.get("summary_patterns", []),
            skip_patterns=naming.get("skip_patterns", []),
            column_preferences=data.get("column_preferences", {})
        )


@dataclass
class SheetDetectionResult:
    """Result of sheet role detection"""
    sheet_name: str
    role: SheetRole
    confidence: float
    matched_pattern: Optional[str]
    should_skip: bool
    skip_reason: Optional[str]


# ====================================================================================
# FIRM CONFIGURATION MANAGEMENT
# ====================================================================================

class FirmConfigManager:
    """
    Manages firm-specific sheet naming configurations.

    Loads configurations from unified_mappings.json and provides
    methods for detecting sheet roles based on firm conventions.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to configuration file (defaults to unified_mappings.json)
        """
        self.config_path = config_path or UNIFIED_MAPPINGS_PATH
        self._configs: Dict[str, SheetNamingConfig] = {}
        self._load_configs()

    def _load_configs(self):
        """Load configurations from JSON file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            firm_configs = data.get("firm_configurations", {})

            for firm_id, firm_data in firm_configs.items():
                if firm_id.startswith("_"):
                    continue  # Skip metadata fields

                try:
                    self._configs[firm_id] = SheetNamingConfig.from_dict(firm_id, firm_data)
                except Exception as e:
                    logger.warning(f"Failed to load config for {firm_id}: {e}")

            logger.info(f"Loaded {len(self._configs)} firm configurations")

        except FileNotFoundError:
            logger.warning(f"Configuration file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")

    def get_config(self, firm_id: str) -> Optional[SheetNamingConfig]:
        """Get configuration for a specific firm."""
        return self._configs.get(firm_id)

    def get_default_config(self) -> SheetNamingConfig:
        """Get default configuration."""
        return self._configs.get("default", SheetNamingConfig(
            firm_id="default",
            firm_name="Default",
            additions_patterns=["*addition*", "*new*", "*purchase*"],
            disposals_patterns=["*disposal*", "*sold*", "*retired*"],
            transfers_patterns=["*transfer*", "*reclass*"],
            summary_patterns=["*summary*", "*total*"],
            skip_patterns=["*instructions*", "*notes*", "*draft*"],
            column_preferences={}
        ))

    def list_firms(self) -> List[str]:
        """List all available firm IDs."""
        return list(self._configs.keys())

    def add_custom_config(self, config: SheetNamingConfig):
        """Add a custom firm configuration."""
        self._configs[config.firm_id] = config


# ====================================================================================
# PATTERN MATCHING
# ====================================================================================

def _matches_patterns(sheet_name: str, patterns: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Check if sheet name matches any of the given patterns.

    Supports glob-style wildcards (* for any characters).

    Args:
        sheet_name: Name of the sheet to check
        patterns: List of patterns to match against

    Returns:
        Tuple of (matches, matched_pattern)
    """
    name_lower = sheet_name.lower().strip()

    for pattern in patterns:
        pattern_lower = pattern.lower()

        # Try glob-style match
        if fnmatch.fnmatch(name_lower, pattern_lower):
            return True, pattern

        # Try substring match if no wildcards
        if "*" not in pattern_lower and pattern_lower in name_lower:
            return True, pattern

    return False, None


def _calculate_match_confidence(
    sheet_name: str,
    matched_pattern: str,
    all_patterns: List[str]
) -> float:
    """
    Calculate confidence score for a pattern match.

    Args:
        sheet_name: Sheet name that was matched
        matched_pattern: Pattern that matched
        all_patterns: All patterns in the category

    Returns:
        Confidence score between 0.0 and 1.0
    """
    name_lower = sheet_name.lower()
    pattern_lower = matched_pattern.lower().replace("*", "")

    # Base confidence
    confidence = 0.7

    # Boost for exact match (after removing wildcards)
    if pattern_lower and name_lower == pattern_lower:
        confidence = 1.0
    # Boost for pattern at start of name
    elif pattern_lower and name_lower.startswith(pattern_lower):
        confidence = 0.9
    # Boost for pattern at end of name
    elif pattern_lower and name_lower.endswith(pattern_lower):
        confidence = 0.85

    # Reduce confidence if multiple patterns could match
    matching_patterns = sum(
        1 for p in all_patterns
        if fnmatch.fnmatch(name_lower, p.lower()) or p.lower().replace("*", "") in name_lower
    )
    if matching_patterns > 1:
        confidence *= 0.9

    return min(confidence, 1.0)


# ====================================================================================
# SHEET ROLE DETECTION
# ====================================================================================

def detect_sheet_role_with_firm_config(
    sheet_name: str,
    config: SheetNamingConfig
) -> SheetDetectionResult:
    """
    Detect sheet role using firm-specific configuration.

    Priority order:
    1. Skip patterns (if matches, sheet should be skipped)
    2. Disposals patterns
    3. Transfers patterns
    4. Additions patterns
    5. Summary patterns (treated as skip)
    6. Default to main role

    Args:
        sheet_name: Name of the Excel sheet
        config: Firm-specific naming configuration

    Returns:
        SheetDetectionResult with role and confidence
    """
    # Check skip patterns first
    matches, pattern = _matches_patterns(sheet_name, config.skip_patterns)
    if matches:
        return SheetDetectionResult(
            sheet_name=sheet_name,
            role=SheetRole.MAIN,
            confidence=0.0,
            matched_pattern=pattern,
            should_skip=True,
            skip_reason=f"Matches skip pattern: {pattern}"
        )

    # Check summary patterns (usually skip)
    matches, pattern = _matches_patterns(sheet_name, config.summary_patterns)
    if matches:
        return SheetDetectionResult(
            sheet_name=sheet_name,
            role=SheetRole.MAIN,
            confidence=0.5,
            matched_pattern=pattern,
            should_skip=True,
            skip_reason=f"Summary sheet: {pattern}"
        )

    # Check disposals
    matches, pattern = _matches_patterns(sheet_name, config.disposals_patterns)
    if matches:
        confidence = _calculate_match_confidence(
            sheet_name, pattern, config.disposals_patterns
        )
        return SheetDetectionResult(
            sheet_name=sheet_name,
            role=SheetRole.DISPOSALS,
            confidence=confidence,
            matched_pattern=pattern,
            should_skip=False,
            skip_reason=None
        )

    # Check transfers
    matches, pattern = _matches_patterns(sheet_name, config.transfers_patterns)
    if matches:
        confidence = _calculate_match_confidence(
            sheet_name, pattern, config.transfers_patterns
        )
        return SheetDetectionResult(
            sheet_name=sheet_name,
            role=SheetRole.TRANSFERS,
            confidence=confidence,
            matched_pattern=pattern,
            should_skip=False,
            skip_reason=None
        )

    # Check additions
    matches, pattern = _matches_patterns(sheet_name, config.additions_patterns)
    if matches:
        confidence = _calculate_match_confidence(
            sheet_name, pattern, config.additions_patterns
        )
        return SheetDetectionResult(
            sheet_name=sheet_name,
            role=SheetRole.ADDITIONS,
            confidence=confidence,
            matched_pattern=pattern,
            should_skip=False,
            skip_reason=None
        )

    # Default to main
    return SheetDetectionResult(
        sheet_name=sheet_name,
        role=SheetRole.MAIN,
        confidence=0.5,
        matched_pattern=None,
        should_skip=False,
        skip_reason=None
    )


def detect_sheet_roles_for_workbook(
    sheet_names: List[str],
    firm_id: Optional[str] = None,
    config_manager: Optional[FirmConfigManager] = None
) -> Dict[str, SheetDetectionResult]:
    """
    Detect roles for all sheets in a workbook.

    Args:
        sheet_names: List of sheet names
        firm_id: Optional firm ID for firm-specific patterns
        config_manager: Optional pre-initialized config manager

    Returns:
        Dict mapping sheet names to detection results
    """
    manager = config_manager or FirmConfigManager()

    if firm_id:
        config = manager.get_config(firm_id) or manager.get_default_config()
    else:
        config = manager.get_default_config()

    results = {}
    for sheet_name in sheet_names:
        results[sheet_name] = detect_sheet_role_with_firm_config(sheet_name, config)

    return results


def get_processable_sheets(
    sheet_names: List[str],
    firm_id: Optional[str] = None
) -> List[str]:
    """
    Get list of sheets that should be processed (not skipped).

    Args:
        sheet_names: All sheet names in workbook
        firm_id: Optional firm ID for firm-specific patterns

    Returns:
        List of sheet names to process
    """
    results = detect_sheet_roles_for_workbook(sheet_names, firm_id)
    return [name for name, result in results.items() if not result.should_skip]


def get_sheets_by_role(
    sheet_names: List[str],
    role: SheetRole,
    firm_id: Optional[str] = None
) -> List[str]:
    """
    Get sheets matching a specific role.

    Args:
        sheet_names: All sheet names in workbook
        role: SheetRole to filter by
        firm_id: Optional firm ID for firm-specific patterns

    Returns:
        List of sheet names matching the role
    """
    results = detect_sheet_roles_for_workbook(sheet_names, firm_id)
    return [
        name for name, result in results.items()
        if result.role == role and not result.should_skip
    ]


# ====================================================================================
# UTILITY FUNCTIONS
# ====================================================================================

def suggest_firm_config(sheet_names: List[str]) -> Optional[str]:
    """
    Suggest the best firm configuration based on sheet names.

    Analyzes sheet naming patterns to recommend which firm
    configuration would work best.

    Args:
        sheet_names: List of sheet names to analyze

    Returns:
        Recommended firm_id or None if no clear match
    """
    manager = FirmConfigManager()

    best_match = None
    best_score = 0

    for firm_id in manager.list_firms():
        if firm_id == "default":
            continue

        config = manager.get_config(firm_id)
        if not config:
            continue

        # Score based on pattern matches
        score = 0
        all_patterns = (
            config.additions_patterns +
            config.disposals_patterns +
            config.transfers_patterns +
            config.summary_patterns
        )

        for sheet_name in sheet_names:
            matches, _ = _matches_patterns(sheet_name, all_patterns)
            if matches:
                score += 1

        if score > best_score:
            best_score = score
            best_match = firm_id

    # Only suggest if we have a significant match (at least 2 sheets)
    if best_score >= 2:
        return best_match

    return None


def format_detection_report(results: Dict[str, SheetDetectionResult]) -> str:
    """
    Format detection results as a human-readable report.

    Args:
        results: Dict of detection results

    Returns:
        Formatted report string
    """
    lines = ["Sheet Role Detection Report", "=" * 40]

    # Group by role
    by_role = {}
    skipped = []

    for name, result in results.items():
        if result.should_skip:
            skipped.append((name, result))
        else:
            role_name = result.role.value
            if role_name not in by_role:
                by_role[role_name] = []
            by_role[role_name].append((name, result))

    # Report by role
    for role_name in ["additions", "disposals", "transfers", "main"]:
        if role_name in by_role:
            lines.append(f"\n{role_name.upper()}:")
            for name, result in by_role[role_name]:
                conf_str = f"({result.confidence:.0%})" if result.confidence < 1.0 else ""
                pattern_str = f" [{result.matched_pattern}]" if result.matched_pattern else ""
                lines.append(f"  - {name} {conf_str}{pattern_str}")

    # Skipped sheets
    if skipped:
        lines.append("\nSKIPPED:")
        for name, result in skipped:
            lines.append(f"  - {name}: {result.skip_reason}")

    return "\n".join(lines)
