# fixed_asset_ai/logic/__init__.py
"""
Fixed Asset AI Logic Module

Core processing logic for fixed asset classification, depreciation calculation,
and FA CS export.

Module Structure (refactored):
- fa_export.py: Main export builder (uses supporting modules below)
- fa_export_validation.py: Data quality, NBV reconciliation, materiality
- fa_export_audit.py: Classification explanations, audit trail
- fa_export_vehicles.py: Luxury auto rules, vehicle detection
- fa_export_formatters.py: Excel formatting utilities
- fa_cs_mappings.py: FA CS wizard category mappings
- sheet_loader.py: Excel parsing (uses supporting modules below)
- column_detector.py: Header keys, fuzzy matching
- sheet_analyzer.py: Sheet skip, role detection, fiscal year
- firm_sheet_naming.py: Firm-specific sheet naming conventions
- encryption.py: Database encryption utilities
- mapping_schema.py: JSON schema validation for configs
- circuit_breaker.py: API resilience with fallback support
"""

# Data Quality & Validation
from .data_validator import (
    AssetDataValidator,
    ValidationError,
    validate_asset_data,
)

from .data_quality_score import (
    DataQualityScore,
    QualityCheckResult,
    calculate_data_quality_score,
    generate_quality_report,
    get_quality_badge,
)

from .rollforward_reconciliation import (
    RollforwardResult,
    reconcile_rollforward,
    reconcile_by_category,
    validate_period_to_period,
    generate_rollforward_report,
    add_rollforward_to_export,
)

from .export_qa_validator import (
    validate_fixed_asset_cs_export,
    export_validation_report,
)

# Firm-specific sheet naming support
from .firm_sheet_naming import (
    FirmConfigManager,
    SheetNamingConfig,
    SheetDetectionResult,
    detect_sheet_role_with_firm_config,
    detect_sheet_roles_for_workbook,
    get_processable_sheets,
    suggest_firm_config,
)

# Mapping schema validation
from .mapping_schema import (
    ValidationResult,
    validate_client_mapping,
    validate_fa_cs_mapping,
    validate_firm_sheet_naming,
    load_and_validate_config,
)

# Circuit breaker for API resilience
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStats,
    openai_breaker,
    external_api_breaker,
    classify_with_fallback,
    get_circuit_status,
    reset_all_circuits,
)

__all__ = [
    # Data Validator
    "AssetDataValidator",
    "ValidationError",
    "validate_asset_data",
    # Data Quality Score
    "DataQualityScore",
    "QualityCheckResult",
    "calculate_data_quality_score",
    "generate_quality_report",
    "get_quality_badge",
    # Rollforward Reconciliation
    "RollforwardResult",
    "reconcile_rollforward",
    "reconcile_by_category",
    "validate_period_to_period",
    "generate_rollforward_report",
    "add_rollforward_to_export",
    # Export QA
    "validate_fixed_asset_cs_export",
    "export_validation_report",
    # Firm Sheet Naming
    "FirmConfigManager",
    "SheetNamingConfig",
    "SheetDetectionResult",
    "detect_sheet_role_with_firm_config",
    "detect_sheet_roles_for_workbook",
    "get_processable_sheets",
    "suggest_firm_config",
    # Mapping Schema Validation
    "ValidationResult",
    "validate_client_mapping",
    "validate_fa_cs_mapping",
    "validate_firm_sheet_naming",
    "load_and_validate_config",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitStats",
    "openai_breaker",
    "external_api_breaker",
    "classify_with_fallback",
    "get_circuit_status",
    "reset_all_circuits",
]
