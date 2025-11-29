"""
Fixed Asset AI - Mapping Configuration Schema Validation

JSON Schema definitions and validation for mapping configuration files.
Provides type safety and validation for client and FA CS mappings.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ====================================================================================
# JSON SCHEMA DEFINITIONS
# ====================================================================================

# Schema for client input column mappings
CLIENT_INPUT_MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "_description": {"type": "string"},
        "_notes": {"type": "array", "items": {"type": "string"}},
        "_usage": {"type": "array", "items": {"type": "string"}},
        "default": {
            "type": "object",
            "properties": {
                "additional_keywords": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                }
            }
        },
        "clients": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string"},
                    "header_row": {"type": "integer", "minimum": 1},
                    "sheet_patterns": {"type": "array", "items": {"type": "string"}},
                    "column_mappings": {
                        "type": "object",
                        "properties": {
                            "asset_id": {"type": "string"},
                            "description": {"type": "string"},
                            "cost": {"type": "string"},
                            "acquisition_date": {"type": "string"},
                            "in_service_date": {"type": "string"},
                            "category": {"type": "string"},
                            "location": {"type": "string"},
                            "department": {"type": "string"},
                            "disposal_date": {"type": "string"},
                            "proceeds": {"type": "string"},
                        }
                    },
                    "skip_sheets": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"}
                }
            }
        }
    }
}

# Schema for FA CS import field mappings
FA_CS_IMPORT_MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "_description": {"type": "string"},
        "_notes": {"type": "array", "items": {"type": "string"}},
        "default": {
            "type": "object",
            "required": ["mapping_name", "field_mappings"],
            "properties": {
                "mapping_name": {"type": "string"},
                "description": {"type": "string"},
                "field_mappings": {
                    "type": "object",
                    "additionalProperties": {"type": "string"}
                },
                "import_settings": {
                    "type": "object",
                    "properties": {
                        "skip_header_rows": {"type": "integer", "minimum": 0},
                        "update_existing_assets": {"type": "boolean"},
                        "validate_before_import": {"type": "boolean"},
                        "create_backup": {"type": "boolean"}
                    }
                }
            }
        }
    }
}

# Schema for firm-specific sheet naming conventions
FIRM_SHEET_NAMING_SCHEMA = {
    "type": "object",
    "properties": {
        "firm_id": {"type": "string"},
        "firm_name": {"type": "string"},
        "sheet_naming_convention": {
            "type": "object",
            "properties": {
                "additions_patterns": {"type": "array", "items": {"type": "string"}},
                "disposals_patterns": {"type": "array", "items": {"type": "string"}},
                "transfers_patterns": {"type": "array", "items": {"type": "string"}},
                "summary_patterns": {"type": "array", "items": {"type": "string"}},
                "skip_patterns": {"type": "array", "items": {"type": "string"}}
            }
        },
        "column_preferences": {
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}}
        }
    }
}


# ====================================================================================
# VALIDATION FUNCTIONS
# ====================================================================================

@dataclass
class ValidationResult:
    """Result of schema validation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def validate_json_schema(data: dict, schema: dict) -> ValidationResult:
    """
    Validate data against a JSON schema.

    Simple validation without external dependencies.
    For full JSON Schema validation, install jsonschema package.

    Args:
        data: Data dictionary to validate
        schema: JSON Schema dictionary

    Returns:
        ValidationResult with errors and warnings
    """
    errors = []
    warnings = []

    try:
        # Try to use jsonschema if available
        from jsonschema import validate, ValidationError as JsonSchemaError
        try:
            validate(instance=data, schema=schema)
        except JsonSchemaError as e:
            errors.append(f"Schema validation failed: {e.message}")
    except ImportError:
        # Fallback to basic validation
        errors, warnings = _basic_validate(data, schema)

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def _basic_validate(data: dict, schema: dict, path: str = "") -> Tuple[List[str], List[str]]:
    """
    Basic schema validation without jsonschema package.

    Args:
        data: Data to validate
        schema: Schema to validate against
        path: Current path for error messages

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(data, dict):
            errors.append(f"{path}: Expected object, got {type(data).__name__}")
            return errors, warnings

        # Check required properties
        required = schema.get("required", [])
        for prop in required:
            if prop not in data:
                errors.append(f"{path}: Missing required property '{prop}'")

        # Validate properties
        properties = schema.get("properties", {})
        for prop, prop_schema in properties.items():
            if prop in data:
                prop_path = f"{path}.{prop}" if path else prop
                prop_errors, prop_warnings = _basic_validate(data[prop], prop_schema, prop_path)
                errors.extend(prop_errors)
                warnings.extend(prop_warnings)

    elif schema_type == "array":
        if not isinstance(data, list):
            errors.append(f"{path}: Expected array, got {type(data).__name__}")
            return errors, warnings

        items_schema = schema.get("items", {})
        for i, item in enumerate(data):
            item_path = f"{path}[{i}]"
            item_errors, item_warnings = _basic_validate(item, items_schema, item_path)
            errors.extend(item_errors)
            warnings.extend(item_warnings)

    elif schema_type == "string":
        if not isinstance(data, str):
            errors.append(f"{path}: Expected string, got {type(data).__name__}")

    elif schema_type == "integer":
        if not isinstance(data, int):
            errors.append(f"{path}: Expected integer, got {type(data).__name__}")
        # Check minimum
        if isinstance(data, int) and "minimum" in schema:
            if data < schema["minimum"]:
                errors.append(f"{path}: Value {data} is below minimum {schema['minimum']}")

    elif schema_type == "boolean":
        if not isinstance(data, bool):
            errors.append(f"{path}: Expected boolean, got {type(data).__name__}")

    return errors, warnings


def validate_client_mapping(mapping_data: dict) -> ValidationResult:
    """Validate client input mapping configuration."""
    return validate_json_schema(mapping_data, CLIENT_INPUT_MAPPING_SCHEMA)


def validate_fa_cs_mapping(mapping_data: dict) -> ValidationResult:
    """Validate FA CS import mapping configuration."""
    return validate_json_schema(mapping_data, FA_CS_IMPORT_MAPPING_SCHEMA)


def validate_firm_sheet_naming(config_data: dict) -> ValidationResult:
    """Validate firm sheet naming configuration."""
    return validate_json_schema(config_data, FIRM_SHEET_NAMING_SCHEMA)


# ====================================================================================
# CONFIGURATION LOADING WITH VALIDATION
# ====================================================================================

def load_and_validate_config(
    file_path: str,
    schema: dict,
    strict: bool = False
) -> Tuple[Optional[dict], ValidationResult]:
    """
    Load and validate a JSON configuration file.

    Args:
        file_path: Path to JSON file
        schema: Schema to validate against
        strict: If True, raise exception on validation errors

    Returns:
        Tuple of (config data, validation result)
    """
    errors = []
    warnings = []

    # Load file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, ValidationResult(False, [f"File not found: {file_path}"], [])
    except json.JSONDecodeError as e:
        return None, ValidationResult(False, [f"Invalid JSON: {e}"], [])

    # Validate
    result = validate_json_schema(data, schema)

    if strict and result.has_errors:
        raise ValueError(f"Configuration validation failed: {result.errors}")

    return data, result


def save_config_with_validation(
    data: dict,
    file_path: str,
    schema: dict
) -> ValidationResult:
    """
    Validate and save configuration to JSON file.

    Args:
        data: Configuration data to save
        file_path: Output file path
        schema: Schema to validate against

    Returns:
        ValidationResult
    """
    # Validate first
    result = validate_json_schema(data, schema)

    if result.has_errors:
        logger.error(f"Cannot save invalid configuration: {result.errors}")
        return result

    # Save
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Configuration saved to {file_path}")
    except Exception as e:
        result.errors.append(f"Save failed: {e}")
        result.is_valid = False

    return result


# ====================================================================================
# CONFIGURATION MERGER
# ====================================================================================

def merge_mapping_configs(
    base_config: dict,
    override_config: dict
) -> dict:
    """
    Merge two mapping configurations (base + overrides).

    Override config takes precedence for conflicting values.

    Args:
        base_config: Base configuration
        override_config: Override configuration

    Returns:
        Merged configuration
    """
    result = dict(base_config)

    for key, value in override_config.items():
        if key.startswith("_"):
            # Skip metadata fields
            continue

        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge dictionaries
            result[key] = merge_mapping_configs(result[key], value)
        else:
            # Override value
            result[key] = value

    return result


def get_effective_client_config(
    client_id: str,
    mapping_config: dict
) -> dict:
    """
    Get effective configuration for a specific client.

    Merges default settings with client-specific overrides.

    Args:
        client_id: Client identifier
        mapping_config: Full mapping configuration

    Returns:
        Effective configuration for the client
    """
    default_config = mapping_config.get("default", {})
    clients = mapping_config.get("clients", {})

    if client_id not in clients:
        return default_config

    client_config = clients[client_id]
    return merge_mapping_configs(default_config, client_config)
