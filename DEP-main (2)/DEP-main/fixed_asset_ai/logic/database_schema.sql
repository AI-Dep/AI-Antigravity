-- ============================================================================
-- Fixed Asset AI - SQLite Database Schema
-- Full SQLite Solution with Management UI Support
-- ============================================================================
-- This schema consolidates all JSON-based storage into a unified database
-- with support for audit trails, multi-client management, and analytics.
-- ============================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================================
-- CLIENTS & CONFIGURATION
-- ============================================================================

-- Clients table: Multi-tenant support
CREATE TABLE IF NOT EXISTS clients (
    client_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL UNIQUE,
    client_code TEXT UNIQUE,
    contact_name TEXT,
    contact_email TEXT,
    phone TEXT,
    active BOOLEAN DEFAULT 1,
    rpa_enabled BOOLEAN DEFAULT 0,
    use_import_automation BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

-- Client field mappings: Replaces fa_cs_import_mappings.json
CREATE TABLE IF NOT EXISTS client_field_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    mapping_name TEXT NOT NULL,
    description TEXT,
    source_field TEXT NOT NULL,
    target_field TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE,
    UNIQUE(client_id, source_field, is_active)
);

-- Import settings per client
CREATE TABLE IF NOT EXISTS client_import_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    skip_header_rows INTEGER DEFAULT 0,
    update_existing_assets BOOLEAN DEFAULT 0,
    validate_before_import BOOLEAN DEFAULT 1,
    create_backup BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE,
    UNIQUE(client_id)
);

-- ============================================================================
-- ASSETS & CLASSIFICATIONS
-- ============================================================================

-- Master assets table
CREATE TABLE IF NOT EXISTS assets (
    asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER,
    external_asset_id TEXT,
    asset_number TEXT,
    description TEXT NOT NULL,
    category TEXT,
    cost REAL,
    acquisition_date DATE,
    date_in_service DATE,
    disposal_date DATE,
    current_classification TEXT,
    current_life INTEGER,
    current_method TEXT,
    current_convention TEXT,
    is_bonus_eligible BOOLEAN DEFAULT 0,
    is_qip BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE SET NULL,
    UNIQUE(client_id, external_asset_id)
);

CREATE INDEX idx_assets_client ON assets(client_id);
CREATE INDEX idx_assets_external_id ON assets(external_asset_id);
CREATE INDEX idx_assets_classification ON assets(current_classification);

-- Classification history: Replaces classification_memory.json
CREATE TABLE IF NOT EXISTS classifications (
    classification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER,
    asset_id INTEGER,
    asset_text TEXT NOT NULL,
    asset_description TEXT,
    classification_class TEXT NOT NULL,
    classification_life INTEGER NOT NULL,
    classification_method TEXT NOT NULL,
    classification_convention TEXT NOT NULL,
    is_bonus_eligible BOOLEAN DEFAULT 0,
    is_qip BOOLEAN DEFAULT 0,
    confidence_score REAL,
    source TEXT, -- 'rules', 'gpt', 'manual', 'override'
    rule_triggered TEXT,
    similarity_score REAL,
    similar_asset_id INTEGER,
    classification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    classified_by TEXT,
    notes TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE SET NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
    FOREIGN KEY (similar_asset_id) REFERENCES assets(asset_id) ON DELETE SET NULL
);

CREATE INDEX idx_classifications_client ON classifications(client_id);
CREATE INDEX idx_classifications_asset ON classifications(asset_id);
CREATE INDEX idx_classifications_date ON classifications(classification_date);
CREATE INDEX idx_classifications_source ON classifications(source);

-- Classification embeddings: Store vector embeddings separately
CREATE TABLE IF NOT EXISTS classification_embeddings (
    embedding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    classification_id INTEGER NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_vector BLOB NOT NULL, -- Store as binary
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (classification_id) REFERENCES classifications(classification_id) ON DELETE CASCADE,
    UNIQUE(classification_id)
);

CREATE INDEX idx_embeddings_classification ON classification_embeddings(classification_id);

-- Overrides: Replaces overrides.json
CREATE TABLE IF NOT EXISTS overrides (
    override_id INTEGER PRIMARY KEY AUTOINCREMENT,
    override_type TEXT NOT NULL, -- 'asset_id', 'client_category', 'description_pattern'
    client_id INTEGER,
    asset_id INTEGER,
    external_asset_id TEXT,
    category_name TEXT,
    description_pattern TEXT,
    override_class TEXT NOT NULL,
    override_life INTEGER NOT NULL,
    override_method TEXT NOT NULL,
    override_convention TEXT NOT NULL,
    is_bonus_eligible BOOLEAN DEFAULT 0,
    is_qip BOOLEAN DEFAULT 0,
    priority INTEGER DEFAULT 0, -- Higher priority overrides win
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    notes TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE
);

CREATE INDEX idx_overrides_type ON overrides(override_type);
CREATE INDEX idx_overrides_client ON overrides(client_id);
CREATE INDEX idx_overrides_asset ON overrides(external_asset_id);
CREATE INDEX idx_overrides_category ON overrides(category_name);

-- ============================================================================
-- EXPORTS & TAX CALCULATIONS
-- ============================================================================

-- Export records: Track all generated exports
CREATE TABLE IF NOT EXISTS exports (
    export_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER,
    tax_year INTEGER NOT NULL,
    export_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    export_filename TEXT,
    export_path TEXT,
    total_assets INTEGER,
    additions_count INTEGER,
    disposals_count INTEGER,
    transfers_count INTEGER,
    total_cost REAL,
    total_section_179 REAL,
    total_bonus REAL,
    total_depreciable_basis REAL,
    total_macrs_year1 REAL,
    total_de_minimis REAL,
    total_sec179_carryforward REAL,
    year1_total_deduction REAL,
    approval_status TEXT, -- 'PENDING', 'APPROVED', 'REJECTED'
    approval_id INTEGER,
    rpa_status TEXT, -- 'NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED'
    rpa_method TEXT, -- 'TIER1_IMPORT', 'TIER2_UI', 'TIER3_MANUAL'
    rpa_completed_at TIMESTAMP,
    audit_hash TEXT,
    created_by TEXT,
    notes TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE SET NULL,
    FOREIGN KEY (approval_id) REFERENCES approvals(approval_id) ON DELETE SET NULL
);

CREATE INDEX idx_exports_client ON exports(client_id);
CREATE INDEX idx_exports_tax_year ON exports(tax_year);
CREATE INDEX idx_exports_date ON exports(export_date);
CREATE INDEX idx_exports_approval ON exports(approval_id);

-- Export assets: Junction table linking exports to assets
CREATE TABLE IF NOT EXISTS export_assets (
    export_asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_id INTEGER NOT NULL,
    asset_id INTEGER,
    asset_number TEXT,
    description TEXT,
    transaction_type TEXT,
    cost REAL,
    classification TEXT,
    life INTEGER,
    method TEXT,
    convention TEXT,
    section_179_amount REAL,
    bonus_amount REAL,
    macrs_depreciation REAL,
    de_minimis_amount REAL,
    FOREIGN KEY (export_id) REFERENCES exports(export_id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE SET NULL
);

CREATE INDEX idx_export_assets_export ON export_assets(export_id);
CREATE INDEX idx_export_assets_asset ON export_assets(asset_id);

-- ============================================================================
-- APPROVAL WORKFLOW
-- ============================================================================

-- Approvals: Master approval records
CREATE TABLE IF NOT EXISTS approvals (
    approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_id INTEGER,
    client_id INTEGER,
    approval_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approver_name TEXT NOT NULL,
    approver_email TEXT,
    approval_status TEXT NOT NULL, -- 'PENDING_REVIEW', 'QUALITY_APPROVED', 'TAX_APPROVED', 'FINAL_APPROVED', 'REJECTED', 'RPA_READY'
    checkpoint_1_status TEXT, -- 'PASSED', 'FAILED', 'WARNING'
    checkpoint_2_status TEXT,
    checkpoint_3_status TEXT,
    all_checkpoints_passed BOOLEAN DEFAULT 0,
    rpa_ready BOOLEAN DEFAULT 0,
    approval_notes TEXT,
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (export_id) REFERENCES exports(export_id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE SET NULL
);

CREATE INDEX idx_approvals_export ON approvals(export_id);
CREATE INDEX idx_approvals_client ON approvals(client_id);
CREATE INDEX idx_approvals_timestamp ON approvals(approval_timestamp);
CREATE INDEX idx_approvals_status ON approvals(approval_status);
CREATE INDEX idx_approvals_approver ON approvals(approver_email);

-- Approval checkpoints: Detailed checkpoint data
CREATE TABLE IF NOT EXISTS approval_checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id INTEGER NOT NULL,
    checkpoint_number INTEGER NOT NULL, -- 1, 2, 3
    checkpoint_name TEXT NOT NULL, -- 'QUALITY_REVIEW', 'TAX_REVIEW', 'PRE_RPA_CHECKLIST'
    checkpoint_status TEXT NOT NULL, -- 'PASSED', 'FAILED', 'WARNING'
    checkpoint_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_valid BOOLEAN,
    critical_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    total_issues INTEGER DEFAULT 0,
    validation_details TEXT, -- JSON string with detailed results
    tax_summary TEXT, -- JSON string with tax calculation summary
    checklist_results TEXT, -- JSON string with checklist results
    reviewer_notes TEXT,
    FOREIGN KEY (approval_id) REFERENCES approvals(approval_id) ON DELETE CASCADE,
    UNIQUE(approval_id, checkpoint_number)
);

CREATE INDEX idx_checkpoints_approval ON approval_checkpoints(approval_id);
CREATE INDEX idx_checkpoints_number ON approval_checkpoints(checkpoint_number);
CREATE INDEX idx_checkpoints_status ON approval_checkpoints(checkpoint_status);

-- ============================================================================
-- AUDIT & SESSION TRACKING
-- ============================================================================

-- Audit log: General audit trail for all operations
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_name TEXT,
    user_email TEXT,
    action_type TEXT NOT NULL, -- 'CREATE', 'UPDATE', 'DELETE', 'EXPORT', 'APPROVE', 'REJECT', etc.
    entity_type TEXT NOT NULL, -- 'asset', 'classification', 'export', 'approval', etc.
    entity_id INTEGER,
    client_id INTEGER,
    description TEXT,
    old_values TEXT, -- JSON string
    new_values TEXT, -- JSON string
    ip_address TEXT,
    session_id TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_user ON audit_log(user_email);
CREATE INDEX idx_audit_action ON audit_log(action_type);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_client ON audit_log(client_id);

-- User sessions: Track Streamlit sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_name TEXT,
    user_email TEXT,
    client_id INTEGER,
    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_end TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT,
    is_active BOOLEAN DEFAULT 1,
    session_data TEXT, -- JSON string for session state
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE SET NULL
);

CREATE INDEX idx_sessions_user ON sessions(user_email);
CREATE INDEX idx_sessions_client ON sessions(client_id);
CREATE INDEX idx_sessions_active ON sessions(is_active);

-- ============================================================================
-- ANALYTICS & REPORTING VIEWS
-- ============================================================================

-- View: Classification accuracy over time
CREATE VIEW IF NOT EXISTS v_classification_accuracy AS
SELECT
    date(classification_date) as classification_day,
    source,
    COUNT(*) as total_classifications,
    AVG(confidence_score) as avg_confidence,
    COUNT(CASE WHEN confidence_score >= 0.9 THEN 1 END) as high_confidence_count,
    COUNT(CASE WHEN confidence_score < 0.7 THEN 1 END) as low_confidence_count
FROM classifications
WHERE classification_date >= date('now', '-30 days')
GROUP BY classification_day, source
ORDER BY classification_day DESC;

-- View: Export history summary
CREATE VIEW IF NOT EXISTS v_export_summary AS
SELECT
    e.export_id,
    e.export_date,
    c.client_name,
    e.tax_year,
    e.total_assets,
    e.total_cost,
    e.year1_total_deduction,
    e.approval_status,
    e.rpa_status,
    a.approver_name,
    a.approval_timestamp
FROM exports e
LEFT JOIN clients c ON e.client_id = c.client_id
LEFT JOIN approvals a ON e.approval_id = a.approval_id
ORDER BY e.export_date DESC;

-- View: Approval workflow metrics
CREATE VIEW IF NOT EXISTS v_approval_metrics AS
SELECT
    date(approval_timestamp) as approval_day,
    approval_status,
    COUNT(*) as approval_count,
    AVG(CASE
        WHEN approval_status = 'FINAL_APPROVED'
        THEN julianday(approval_timestamp) - julianday(created_at)
    END) as avg_approval_time_days,
    COUNT(CASE WHEN rpa_ready = 1 THEN 1 END) as rpa_ready_count
FROM approvals
WHERE approval_timestamp >= date('now', '-90 days')
GROUP BY approval_day, approval_status
ORDER BY approval_day DESC;

-- View: Client activity summary
CREATE VIEW IF NOT EXISTS v_client_activity AS
SELECT
    c.client_id,
    c.client_name,
    c.active,
    COUNT(DISTINCT e.export_id) as total_exports,
    COUNT(DISTINCT a.approval_id) as total_approvals,
    COUNT(DISTINCT ast.asset_id) as total_assets,
    MAX(e.export_date) as last_export_date,
    MAX(a.approval_timestamp) as last_approval_date
FROM clients c
LEFT JOIN exports e ON c.client_id = e.client_id
LEFT JOIN approvals a ON c.client_id = a.client_id
LEFT JOIN assets ast ON c.client_id = ast.client_id
GROUP BY c.client_id, c.client_name, c.active
ORDER BY last_export_date DESC;

-- View: Asset classification history
CREATE VIEW IF NOT EXISTS v_asset_history AS
SELECT
    a.asset_id,
    a.asset_number,
    a.description,
    c.classification_date,
    c.classification_class,
    c.classification_life,
    c.source,
    c.confidence_score,
    c.classified_by,
    ROW_NUMBER() OVER (PARTITION BY a.asset_id ORDER BY c.classification_date DESC) as version
FROM assets a
LEFT JOIN classifications c ON a.asset_id = c.asset_id
ORDER BY a.asset_id, c.classification_date DESC;

-- ============================================================================
-- TRIGGERS FOR AUTO-UPDATE TIMESTAMPS
-- ============================================================================

-- Update clients timestamp
CREATE TRIGGER IF NOT EXISTS update_clients_timestamp
AFTER UPDATE ON clients
BEGIN
    UPDATE clients SET updated_at = CURRENT_TIMESTAMP WHERE client_id = NEW.client_id;
END;

-- Update assets timestamp
CREATE TRIGGER IF NOT EXISTS update_assets_timestamp
AFTER UPDATE ON assets
BEGIN
    UPDATE assets SET updated_at = CURRENT_TIMESTAMP WHERE asset_id = NEW.asset_id;
END;

-- Update approvals timestamp
CREATE TRIGGER IF NOT EXISTS update_approvals_timestamp
AFTER UPDATE ON approvals
BEGIN
    UPDATE approvals SET updated_at = CURRENT_TIMESTAMP WHERE approval_id = NEW.approval_id;
END;

-- ============================================================================
-- INITIAL DATA SETUP
-- ============================================================================

-- Insert default client for existing data migration
INSERT OR IGNORE INTO clients (client_id, client_name, client_code, active, notes)
VALUES (1, 'Default Client', 'DEFAULT', 1, 'Default client for data migration from JSON files');

-- ============================================================================
-- SCHEMA VERSION TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT OR IGNORE INTO schema_version (version, description)
VALUES (1, 'Initial schema - Full SQLite solution with management UI support');

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
