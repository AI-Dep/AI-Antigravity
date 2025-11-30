/**
 * FA CS Automator API Type Definitions
 *
 * These JSDoc type definitions provide IDE support and documentation
 * for the API contract between frontend and backend.
 *
 * @fileoverview API types matching backend/models/asset.py and backend/api.py
 */

// =============================================================================
// CORE ASSET TYPES
// =============================================================================

/**
 * @typedef {Object} Asset
 * @property {number} row_index - Original row number in Excel
 * @property {number} [unique_id] - Unique ID for storage (set by API)
 * @property {string} [asset_id] - Unique Asset Identifier from client data
 * @property {string} description - Asset Description
 * @property {number} cost - Acquisition Cost (0 if unknown)
 * @property {string} [acquisition_date] - Date Acquired (ISO format)
 * @property {string} [in_service_date] - Date Placed in Service (ISO format)
 * @property {string} [macrs_class] - AI-predicted MACRS class
 * @property {number} [macrs_life] - Recovery period in years
 * @property {string} [macrs_method] - Depreciation method (200DB, 150DB, SL)
 * @property {string} [macrs_convention] - Convention (HY, MQ, MM)
 * @property {string} [fa_cs_wizard_category] - FA CS dropdown category text
 * @property {number} confidence_score - Classification confidence (0.0-1.0)
 * @property {boolean} is_qualified_improvement - QIP flag
 * @property {boolean} is_bonus_eligible - Bonus depreciation eligible
 * @property {string} [source_sheet] - Source Excel sheet name
 * @property {string} [transaction_type] - "Current Year Addition" | "Existing Asset" | "Disposal" | "Transfer"
 * @property {string} [classification_reason] - Reason for transaction type
 * @property {AuditEvent[]} audit_trail - Change history
 * @property {string[]} validation_errors - Critical errors (block export)
 * @property {string[]} validation_warnings - Non-critical warnings
 */

/**
 * @typedef {Object} AuditEvent
 * @property {string} timestamp - ISO timestamp
 * @property {string} user - User who made change
 * @property {string} action - "override" | "approve"
 * @property {string} [field] - Field that was changed
 * @property {string} [old_value] - Previous value
 * @property {string} [new_value] - New value
 * @property {string} [reason] - Reason for change
 */

// =============================================================================
// API RESPONSE TYPES
// =============================================================================

/**
 * @typedef {Object} APIError
 * @property {string} error - Machine-readable error code (e.g., "ASSET_NOT_FOUND")
 * @property {string} message - Human-readable error message
 * @property {Object} [details] - Additional context
 */

/**
 * @typedef {Object} StatsResponse
 * @property {number} total - Total asset count
 * @property {number} errors - Assets with validation errors
 * @property {number} needs_review - Assets needing manual review
 * @property {number} high_confidence - High confidence count
 * @property {number} approved - Approved asset count
 * @property {boolean} ready_for_export - Export readiness flag
 * @property {Object} transaction_types - Count by transaction type
 * @property {number} tax_year - Current tax year
 * @property {string} session_id - Session identifier
 */

/**
 * @typedef {Object} ExportStatusResponse
 * @property {boolean} ready - Can export now
 * @property {string} reason - Explanation if not ready
 * @property {number} total_assets - Total assets
 * @property {number} actionable_assets - Actionable (non-existing) count
 * @property {number} approved_assets - Approved count
 * @property {number} unapproved_assets - Unapproved count
 * @property {number} errors - Assets with errors
 * @property {number} low_confidence_unreviewed - Low confidence not reviewed
 * @property {number[]} approved_ids - Array of approved unique_ids
 */

/**
 * @typedef {Object} TaxConfigResponse
 * @property {number} tax_year - Current tax year
 * @property {number} de_minimis_threshold - De minimis threshold
 * @property {boolean} has_afs - Has audited financial statements
 * @property {number} [bonus_rate] - Bonus depreciation rate
 * @property {number} [section_179_limit] - Section 179 limit
 * @property {boolean} [obbba_effective] - OBBBA effective flag
 * @property {Object} [obbba_info] - OBBBA details
 */

/**
 * @typedef {Object} QualityResponse
 * @property {string} grade - Letter grade (A-F)
 * @property {number} score - Numeric score (0-100)
 * @property {boolean} is_export_ready - Ready for export
 * @property {Object[]} checks - Individual quality checks
 * @property {string[]} critical_issues - Critical issues found
 * @property {string[]} recommendations - Improvement suggestions
 */

/**
 * @typedef {Object} WarningsResponse
 * @property {string[]} critical - Critical warnings
 * @property {string[]} warnings - Standard warnings
 * @property {string[]} info - Informational messages
 * @property {Object} summary - Summary statistics
 */

/**
 * @typedef {Object} ApproveResponse
 * @property {boolean} approved - Success flag
 * @property {number} unique_id - Asset ID that was approved
 * @property {string} [message] - Optional message
 */

/**
 * @typedef {Object} BatchApproveResponse
 * @property {number[]} approved - Successfully approved IDs
 * @property {Array<{unique_id: number, error: string}>} errors - Failed approvals
 * @property {number} total_approved - Total approved count
 */

// =============================================================================
// TRANSACTION TYPES (Constants for comparison)
// =============================================================================

/**
 * Transaction type constants - USE THESE instead of hardcoded strings
 * @readonly
 * @enum {string}
 */
export const TRANSACTION_TYPES = {
  ADDITION: "Current Year Addition",
  EXISTING: "Existing Asset",
  DISPOSAL: "Disposal",
  TRANSFER: "Transfer"
};

/**
 * API error codes - USE THESE for error handling
 * @readonly
 * @enum {string}
 */
export const API_ERROR_CODES = {
  ASSET_NOT_FOUND: "ASSET_NOT_FOUND",
  VALIDATION_ERRORS: "VALIDATION_ERRORS",
  NO_ASSETS: "NO_ASSETS",
  ASSETS_NOT_APPROVED: "ASSETS_NOT_APPROVED",
  LOW_CONFIDENCE_NOT_REVIEWED: "LOW_CONFIDENCE_NOT_REVIEWED",
  FILE_PROCESSING_FAILED: "FILE_PROCESSING_FAILED",
  INVALID_UPDATE_FIELDS: "INVALID_UPDATE_FIELDS"
};

// =============================================================================
// API ENDPOINT PATHS
// =============================================================================

/**
 * API endpoint paths
 * @readonly
 */
export const API_ENDPOINTS = {
  // System
  ROOT: "/",
  CHECK_FACS: "/check-facs",
  SYSTEM_STATUS: "/system-status",

  // File Operations
  UPLOAD: "/upload",
  TABS: "/tabs",

  // Assets
  ASSETS: "/assets",
  UPDATE_ASSET: (id) => `/assets/${id}/update`,
  APPROVE_ASSET: (id) => `/assets/${id}/approve`,
  APPROVE_BATCH: "/assets/approve-batch",

  // Export
  EXPORT: "/export",
  EXPORT_STATUS: "/export/status",
  EXPORT_AUDIT: "/export/audit",

  // Config
  TAX_CONFIG: "/config/tax",

  // Analysis
  STATS: "/stats",
  QUALITY: "/quality",
  WARNINGS: "/warnings",
  ROLLFORWARD: "/rollforward",
  PROJECTION: "/projection",
  CONFIDENCE: "/confidence"
};

// Default export for convenience
export default {
  TRANSACTION_TYPES,
  API_ERROR_CODES,
  API_ENDPOINTS
};
