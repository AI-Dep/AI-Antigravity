# fixed_asset_ai/logic/client_mapping_manager.py
"""
Client-Specific Input Mapping Manager

Handles loading, saving, and applying client-specific column mappings
for Excel asset schedules with varying formats.

Key Features:
- Load client-specific column mappings from JSON config
- Apply mappings to override auto-detection
- Learn and save new mappings from user corrections
- Preview detected mappings before processing

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import os
import json
import logging
import re
import fnmatch
from typing import Dict, Optional, List, Any, Tuple
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Path to the client mappings configuration file
CONFIG_DIR = Path(__file__).parent
CLIENT_MAPPINGS_FILE = CONFIG_DIR / "client_input_mappings.json"


class ClientMappingManager:
    """
    Manages client-specific column mappings for Excel parsing.

    Provides:
    - Loading client mappings from config
    - Matching clients by ID or filename patterns
    - Applying mappings to override detection
    - Learning and saving new mappings
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the mapping manager.

        Args:
            config_path: Optional path to config file. Defaults to client_input_mappings.json
        """
        self.config_path = config_path or CLIENT_MAPPINGS_FILE
        self.config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from JSON file."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info(f"Loaded client mappings from {self.config_path}")
            else:
                logger.warning(f"Client mappings file not found: {self.config_path}")
                self.config = {"clients": {}, "default": {"additional_keywords": {}}}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing client mappings JSON: {e}")
            self.config = {"clients": {}, "default": {"additional_keywords": {}}}
        except Exception as e:
            logger.error(f"Error loading client mappings: {e}")
            self.config = {"clients": {}, "default": {"additional_keywords": {}}}

    def _save_config(self) -> bool:
        """
        Save configuration back to JSON file.

        Returns:
            True if save was successful, False otherwise
        """
        try:
            # Create backup first
            if self.config_path.exists():
                backup_path = self.config_path.with_suffix('.json.bak')
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(backup_content)

            # Save new config
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved client mappings to {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving client mappings: {e}")
            return False

    def get_client_mapping(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get mapping configuration for a specific client.

        Args:
            client_id: The client identifier

        Returns:
            Client mapping dict or None if not found
        """
        clients = self.config.get("clients", {})
        return clients.get(client_id)

    def get_client_by_filename(self, filename: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Find a client mapping that matches the filename pattern.

        Args:
            filename: The Excel filename being processed

        Returns:
            Tuple of (client_id, mapping) or None if no match
        """
        filename_lower = filename.lower()
        clients = self.config.get("clients", {})

        for client_id, mapping in clients.items():
            if client_id.startswith("_"):  # Skip internal keys
                continue

            # Check filename patterns
            patterns = mapping.get("filename_patterns", [])
            for pattern in patterns:
                if fnmatch.fnmatch(filename_lower, pattern.lower()):
                    logger.info(f"Matched client '{client_id}' by filename pattern: {pattern}")
                    return client_id, mapping

            # Check if client name appears in filename
            client_name = mapping.get("client_name", "")
            if client_name and client_name.lower() in filename_lower:
                logger.info(f"Matched client '{client_id}' by client name in filename")
                return client_id, mapping

        return None

    def get_column_mapping(self, client_id: Optional[str] = None) -> Dict[str, str]:
        """
        Get column mappings for a client (or default).

        Args:
            client_id: Optional client ID. If None, returns empty dict.

        Returns:
            Dict mapping logical field names to Excel column names
        """
        if not client_id:
            return {}

        mapping = self.get_client_mapping(client_id)
        if mapping:
            return mapping.get("column_mappings", {})

        return {}

    def get_header_row(self, client_id: Optional[str] = None) -> Optional[int]:
        """
        Get the header row setting for a client.

        Args:
            client_id: Optional client ID

        Returns:
            1-indexed header row number, or None for auto-detection
        """
        if not client_id:
            return None

        mapping = self.get_client_mapping(client_id)
        if mapping:
            return mapping.get("header_row")

        return None

    def get_skip_sheets(self, client_id: Optional[str] = None) -> List[str]:
        """
        Get list of sheets to skip for a client.

        Args:
            client_id: Optional client ID

        Returns:
            List of sheet name patterns to skip
        """
        if not client_id:
            return []

        mapping = self.get_client_mapping(client_id)
        if mapping:
            return mapping.get("skip_sheets", [])

        return []

    def get_additional_keywords(self) -> Dict[str, List[str]]:
        """
        Get additional keywords from default config to extend built-in detection.

        Returns:
            Dict mapping logical field names to additional keyword lists
        """
        default = self.config.get("default", {})
        return default.get("additional_keywords", {})

    def list_clients(self) -> List[Dict[str, str]]:
        """
        List all configured clients.

        Returns:
            List of dicts with client_id and client_name
        """
        clients = self.config.get("clients", {})
        result = []

        for client_id, mapping in clients.items():
            if client_id.startswith("_"):
                continue
            result.append({
                "client_id": client_id,
                "client_name": mapping.get("client_name", client_id),
                "notes": mapping.get("notes", "")
            })

        return result

    def save_client_mapping(
        self,
        client_id: str,
        column_mappings: Dict[str, str],
        client_name: Optional[str] = None,
        header_row: Optional[int] = None,
        skip_sheets: Optional[List[str]] = None,
        filename_patterns: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        Save or update a client mapping configuration.

        This is the "learning" mechanism - when a user corrects mappings,
        save them for future use.

        Args:
            client_id: Unique identifier for this client
            column_mappings: Dict of logical_field -> excel_column_name
            client_name: Human-readable client name
            header_row: 1-indexed row number for headers (None for auto-detect)
            skip_sheets: List of sheet name patterns to skip
            filename_patterns: List of filename patterns to auto-match this client
            notes: Optional notes about this mapping

        Returns:
            True if save was successful
        """
        if "clients" not in self.config:
            self.config["clients"] = {}

        # Build the mapping entry
        mapping_entry = {
            "client_name": client_name or client_id,
            "column_mappings": column_mappings,
            "created": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }

        # Add optional fields
        if header_row is not None:
            mapping_entry["header_row"] = header_row

        if skip_sheets:
            mapping_entry["skip_sheets"] = skip_sheets

        if filename_patterns:
            mapping_entry["filename_patterns"] = filename_patterns

        if notes:
            mapping_entry["notes"] = notes

        # If updating existing, preserve creation date
        existing = self.config["clients"].get(client_id)
        if existing and "created" in existing:
            mapping_entry["created"] = existing["created"]

        self.config["clients"][client_id] = mapping_entry

        logger.info(f"Saving client mapping for '{client_id}' with {len(column_mappings)} column mappings")
        return self._save_config()

    def delete_client_mapping(self, client_id: str) -> bool:
        """
        Delete a client mapping.

        Args:
            client_id: The client ID to delete

        Returns:
            True if deletion was successful
        """
        clients = self.config.get("clients", {})
        if client_id in clients:
            del clients[client_id]
            logger.info(f"Deleted client mapping for '{client_id}'")
            return self._save_config()
        return False

    def add_additional_keyword(self, field: str, keyword: str) -> bool:
        """
        Add a new keyword to the default additional keywords.

        This extends the built-in column detection for all clients.

        Args:
            field: The logical field name (e.g., "asset_id", "description")
            keyword: The new keyword to add

        Returns:
            True if save was successful
        """
        if "default" not in self.config:
            self.config["default"] = {"additional_keywords": {}}

        additional = self.config["default"].setdefault("additional_keywords", {})
        keywords = additional.setdefault(field, [])

        keyword_lower = keyword.lower().strip()
        if keyword_lower not in [k.lower() for k in keywords]:
            keywords.append(keyword_lower)
            logger.info(f"Added keyword '{keyword}' for field '{field}'")
            return self._save_config()

        return True  # Already exists


class MappingPreview:
    """
    Represents a preview of detected column mappings for user review.
    """

    def __init__(
        self,
        sheet_name: str,
        header_row: int,
        all_columns: List[str],
        detected_mappings: Dict[str, str],
        unmatched_columns: List[str],
        missing_fields: List[str],
        warnings: List[str]
    ):
        self.sheet_name = sheet_name
        self.header_row = header_row  # 1-indexed
        self.all_columns = all_columns
        self.detected_mappings = detected_mappings  # logical -> excel_col
        self.unmatched_columns = unmatched_columns  # Excel cols not matched
        self.missing_fields = missing_fields  # Critical fields not found
        self.warnings = warnings

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sheet_name": self.sheet_name,
            "header_row": self.header_row,
            "all_columns": self.all_columns,
            "detected_mappings": self.detected_mappings,
            "unmatched_columns": self.unmatched_columns,
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "is_valid": len(self.missing_fields) == 0
        }

    def __repr__(self) -> str:
        valid = "VALID" if not self.missing_fields else "INCOMPLETE"
        return f"MappingPreview({self.sheet_name}, row={self.header_row}, {valid}, {len(self.detected_mappings)} mapped)"


def generate_mapping_preview(
    sheets: Dict[str, Any],
    client_id: Optional[str] = None,
    manager: Optional[ClientMappingManager] = None
) -> List[MappingPreview]:
    """
    Generate a preview of column mappings for all sheets.

    This allows users to review and correct mappings before processing.

    Args:
        sheets: Dict of sheet_name -> DataFrame (header=None)
        client_id: Optional client ID for pre-configured mappings
        manager: Optional ClientMappingManager instance

    Returns:
        List of MappingPreview objects for each sheet
    """
    # Import here to avoid circular imports
    from .sheet_loader import (
        _detect_header_row,
        _normalize_header,
        _map_columns_with_validation,
        CRITICAL_FIELDS,
        IMPORTANT_FIELDS
    )

    if manager is None:
        manager = ClientMappingManager()

    previews = []
    client_mappings = manager.get_column_mapping(client_id) if client_id else {}

    for sheet_name, df_raw in sheets.items():
        if df_raw is None or df_raw.empty:
            continue

        try:
            # Detect header row
            header_idx = _detect_header_row(df_raw)

            # Extract headers
            df = df_raw.iloc[header_idx:].copy()
            headers = [_normalize_header(x) for x in df.iloc[0]]
            df.columns = headers

            # Get all original column names (before normalization)
            original_columns = [str(x) for x in df_raw.iloc[header_idx] if not pd.isna(x)]

            # Apply client-specific mappings first (if any)
            col_map = {}
            if client_mappings:
                for logical, excel_col in client_mappings.items():
                    excel_col_norm = _normalize_header(excel_col)
                    if excel_col_norm in headers:
                        col_map[logical] = excel_col_norm

            # Then do auto-detection for remaining fields
            auto_col_map, column_mappings, warnings = _map_columns_with_validation(df, sheet_name)

            # Merge (client mappings take priority)
            for logical, excel_col in auto_col_map.items():
                if logical not in col_map:
                    col_map[logical] = excel_col

            # Identify unmatched columns
            mapped_cols = set(col_map.values())
            unmatched = [c for c in headers if c and c not in mapped_cols]

            # Identify missing critical fields
            missing = []
            for field in CRITICAL_FIELDS:
                if field not in col_map:
                    missing.append(field)

            # Add important fields with warnings
            for field in IMPORTANT_FIELDS:
                if field not in col_map and field not in missing:
                    warnings.append(f"Optional field '{field}' not detected")

            preview = MappingPreview(
                sheet_name=sheet_name,
                header_row=header_idx + 1,  # 1-indexed
                all_columns=original_columns,
                detected_mappings=col_map,
                unmatched_columns=unmatched,
                missing_fields=missing,
                warnings=warnings
            )

            previews.append(preview)

        except Exception as e:
            logger.error(f"Error generating preview for sheet {sheet_name}: {e}")
            previews.append(MappingPreview(
                sheet_name=sheet_name,
                header_row=0,
                all_columns=[],
                detected_mappings={},
                unmatched_columns=[],
                missing_fields=["ERROR: Could not analyze sheet"],
                warnings=[str(e)]
            ))

    return previews


# Singleton instance for convenience
_manager_instance: Optional[ClientMappingManager] = None


def get_manager() -> ClientMappingManager:
    """Get the singleton ClientMappingManager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ClientMappingManager()
    return _manager_instance


def reload_manager() -> ClientMappingManager:
    """Reload the manager from disk (useful after config changes)."""
    global _manager_instance
    _manager_instance = ClientMappingManager()
    return _manager_instance
