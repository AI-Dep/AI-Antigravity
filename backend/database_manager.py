"""
Fixed Asset AI - Database Manager
Comprehensive SQLite database manager with ORM-like functionality

This module provides:
- Database connection management
- CRUD operations for all tables
- Transaction support
- Audit logging
- Helper methods for common queries
- Data migration utilities
- Field-level encryption for sensitive data

Security Features:
- Optional AES-256-GCM encryption for sensitive fields
- Key derivation using PBKDF2
- SQL injection prevention via parameterized queries
- Audit logging for all operations
"""

import sqlite3
import json
import pickle
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from contextlib import contextmanager
import hashlib
import os

# Import encryption support
try:
    from .encryption import (
        DatabaseEncryptionMixin,
        FieldEncryptor,
        EncryptionKeyManager,
        CRYPTO_AVAILABLE,
        is_sensitive_field,
        mask_sensitive_value
    )
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False
    CRYPTO_AVAILABLE = False
    DatabaseEncryptionMixin = object  # Fallback to empty base


logger = logging.getLogger(__name__)


# Database path
DB_PATH = Path(__file__).resolve().parent / "fixed_asset_ai.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "database_schema.sql"

# Columns to encrypt by table (configure as needed)
DEFAULT_ENCRYPTED_COLUMNS = {
    "clients": {"contact_email", "phone", "notes"},
    "assets": {"notes"},
    "approvals": {"approver_email"},
}


class DatabaseManager(DatabaseEncryptionMixin):
    """
    Unified database manager for Fixed Asset AI system.

    Features:
    - Connection pooling and management
    - Automatic audit logging
    - Transaction support
    - Type-safe CRUD operations
    - Migration utilities
    - Optional field-level encryption for sensitive data

    Encryption:
    - Set FA_ENCRYPTION_KEY environment variable to enable
    - Sensitive fields (emails, phone, notes) are encrypted at rest
    - Encrypted data uses AES-256-GCM (authenticated encryption)
    """

    def __init__(self, db_path: Optional[str] = None, enable_encryption: bool = True):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file (defaults to fixed_asset_ai.db)
            enable_encryption: Whether to enable field-level encryption
        """
        self.db_path = db_path or str(DB_PATH)
        self._encryption_enabled = False

        # Initialize encryption if available and requested
        if enable_encryption and ENCRYPTION_AVAILABLE and CRYPTO_AVAILABLE:
            if os.environ.get("FA_ENCRYPTION_KEY"):
                try:
                    self.configure_encryption(DEFAULT_ENCRYPTED_COLUMNS)
                    self._encryption_enabled = True
                    logger.info("Database encryption enabled for sensitive fields")
                except Exception as e:
                    logger.warning(f"Failed to initialize encryption: {e}")
            else:
                logger.debug("FA_ENCRYPTION_KEY not set - encryption disabled")

        self._ensure_database_exists()

    def _ensure_database_exists(self):
        """Create database and schema if it doesn't exist."""
        if not os.path.exists(self.db_path):
            self._create_database()

    def _create_database(self):
        """Create database with schema from SQL file."""
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

        with open(SCHEMA_PATH, 'r') as f:
            schema_sql = f.read()

        conn = sqlite3.connect(self.db_path)
        conn.executescript(schema_sql)
        conn.commit()
        conn.close()

    @contextmanager
    def get_connection(self):
        """
        Get database connection with automatic commit/rollback.

        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM assets")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign keys
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """
        Execute SELECT query and return results as list of dicts.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of dictionaries (one per row)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute_update(self, query: str, params: tuple = ()) -> int:
        """
        Execute INSERT/UPDATE/DELETE and return affected rows.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Number of affected rows
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.rowcount

    def execute_insert(self, query: str, params: tuple = ()) -> int:
        """
        Execute INSERT and return last inserted ID.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Last inserted row ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.lastrowid

    # ========================================================================
    # CLIENT OPERATIONS
    # ========================================================================

    def create_client(self, client_name: str, **kwargs) -> int:
        """
        Create new client.

        Args:
            client_name: Client name (required)
            **kwargs: Additional client fields

        Returns:
            New client_id
        """
        fields = ['client_name'] + list(kwargs.keys())
        values = [client_name] + list(kwargs.values())
        placeholders = ', '.join(['?'] * len(fields))

        query = f"""
            INSERT INTO clients ({', '.join(fields)})
            VALUES ({placeholders})
        """

        client_id = self.execute_insert(query, tuple(values))
        self.log_audit(
            action_type='CREATE',
            entity_type='client',
            entity_id=client_id,
            description=f"Created client: {client_name}"
        )
        return client_id

    def get_client(self, client_id: int) -> Optional[Dict]:
        """Get client by ID."""
        query = "SELECT * FROM clients WHERE client_id = ?"
        results = self.execute_query(query, (client_id,))
        return results[0] if results else None

    def get_all_clients(self, active_only: bool = True) -> List[Dict]:
        """Get all clients."""
        query = "SELECT * FROM clients"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY client_name"
        return self.execute_query(query)

    # Whitelist of allowed fields for each table to prevent SQL injection via column names
    ALLOWED_CLIENT_FIELDS = {'client_name', 'contact_name', 'contact_email', 'phone', 'address', 'active', 'notes', 'fiscal_year_end', 'industry'}
    ALLOWED_ASSET_FIELDS = {'description', 'cost', 'acquisition_date', 'in_service_date', 'disposal_date', 'category', 'macrs_life', 'method', 'convention', 'section_179', 'bonus_amount', 'depreciable_basis', 'accumulated_depreciation', 'classification_status', 'client_id', 'notes'}
    ALLOWED_APPROVAL_FIELDS = {'approval_status', 'reviewer_notes', 'reviewed_by', 'reviewed_at', 'priority', 'flags'}

    def update_client(self, client_id: int, **kwargs) -> bool:
        """Update client fields."""
        if not kwargs:
            return False

        # Filter to only allowed fields to prevent SQL injection via column names
        safe_kwargs = {k: v for k, v in kwargs.items() if k in self.ALLOWED_CLIENT_FIELDS}
        if not safe_kwargs:
            return False

        set_clause = ', '.join([f"{k} = ?" for k in safe_kwargs.keys()])
        query = f"UPDATE clients SET {set_clause} WHERE client_id = ?"
        params = tuple(safe_kwargs.values()) + (client_id,)

        affected = self.execute_update(query, params)
        if affected > 0:
            self.log_audit(
                action_type='UPDATE',
                entity_type='client',
                entity_id=client_id,
                description=f"Updated client {client_id}",
                new_values=json.dumps(kwargs)
            )
        return affected > 0

    # ========================================================================
    # ASSET OPERATIONS
    # ========================================================================

    def create_asset(self, description: str, **kwargs) -> int:
        """
        Create new asset.

        Args:
            description: Asset description (required)
            **kwargs: Additional asset fields

        Returns:
            New asset_id
        """
        fields = ['description'] + list(kwargs.keys())
        values = [description] + list(kwargs.values())
        placeholders = ', '.join(['?'] * len(fields))

        query = f"""
            INSERT INTO assets ({', '.join(fields)})
            VALUES ({placeholders})
        """

        asset_id = self.execute_insert(query, tuple(values))
        self.log_audit(
            action_type='CREATE',
            entity_type='asset',
            entity_id=asset_id,
            client_id=kwargs.get('client_id'),
            description=f"Created asset: {description}"
        )
        return asset_id

    def get_asset(self, asset_id: int) -> Optional[Dict]:
        """Get asset by ID."""
        query = "SELECT * FROM assets WHERE asset_id = ?"
        results = self.execute_query(query, (asset_id,))
        return results[0] if results else None

    def get_assets_by_client(self, client_id: int) -> List[Dict]:
        """Get all assets for a client."""
        query = "SELECT * FROM assets WHERE client_id = ? ORDER BY created_at DESC"
        return self.execute_query(query, (client_id,))

    def search_assets(self, search_term: str, client_id: Optional[int] = None) -> List[Dict]:
        """Search assets by description or asset number."""
        query = """
            SELECT * FROM assets
            WHERE (description LIKE ? OR asset_number LIKE ?)
        """
        params = [f"%{search_term}%", f"%{search_term}%"]

        if client_id:
            query += " AND client_id = ?"
            params.append(client_id)

        query += " ORDER BY created_at DESC LIMIT 100"
        return self.execute_query(query, tuple(params))

    def update_asset(self, asset_id: int, **kwargs) -> bool:
        """Update asset fields."""
        if not kwargs:
            return False

        # Filter to only allowed fields to prevent SQL injection via column names
        safe_kwargs = {k: v for k, v in kwargs.items() if k in self.ALLOWED_ASSET_FIELDS}
        if not safe_kwargs:
            return False

        set_clause = ', '.join([f"{k} = ?" for k in safe_kwargs.keys()])
        query = f"UPDATE assets SET {set_clause} WHERE asset_id = ?"
        params = tuple(safe_kwargs.values()) + (asset_id,)

        affected = self.execute_update(query, params)
        if affected > 0:
            self.log_audit(
                action_type='UPDATE',
                entity_type='asset',
                entity_id=asset_id,
                description=f"Updated asset {asset_id}",
                new_values=json.dumps(safe_kwargs)
            )
        return affected > 0

    # ========================================================================
    # CLASSIFICATION OPERATIONS
    # ========================================================================

    def create_classification(
        self,
        asset_text: str,
        classification_class: str,
        classification_life: int,
        classification_method: str,
        classification_convention: str,
        **kwargs
    ) -> int:
        """
        Create new classification record.

        Args:
            asset_text: Full text used for classification
            classification_class: Assigned class
            classification_life: Recovery period (years)
            classification_method: Depreciation method
            classification_convention: Tax convention
            **kwargs: Additional classification fields

        Returns:
            New classification_id
        """
        fields = [
            'asset_text', 'classification_class', 'classification_life',
            'classification_method', 'classification_convention'
        ] + list(kwargs.keys())

        values = [
            asset_text, classification_class, classification_life,
            classification_method, classification_convention
        ] + list(kwargs.values())

        placeholders = ', '.join(['?'] * len(fields))
        query = f"""
            INSERT INTO classifications ({', '.join(fields)})
            VALUES ({placeholders})
        """

        classification_id = self.execute_insert(query, tuple(values))

        # Update asset's current classification if asset_id provided
        if 'asset_id' in kwargs and kwargs['asset_id']:
            self.update_asset(
                kwargs['asset_id'],
                current_classification=classification_class,
                current_life=classification_life,
                current_method=classification_method,
                current_convention=classification_convention
            )

        return classification_id

    def store_embedding(self, classification_id: int, embedding_vector: List[float], model: str = "text-embedding-3-small") -> int:
        """
        Store embedding vector for classification.

        Args:
            classification_id: Classification ID
            embedding_vector: List of floats (embedding)
            model: Embedding model name

        Returns:
            New embedding_id
        """
        # Convert embedding to binary blob
        embedding_blob = pickle.dumps(embedding_vector)

        query = """
            INSERT INTO classification_embeddings (classification_id, embedding_model, embedding_vector)
            VALUES (?, ?, ?)
        """
        return self.execute_insert(query, (classification_id, model, embedding_blob))

    def get_classification_history(self, asset_id: int) -> List[Dict]:
        """Get classification history for an asset."""
        query = """
            SELECT * FROM classifications
            WHERE asset_id = ?
            ORDER BY classification_date DESC
        """
        return self.execute_query(query, (asset_id,))

    def get_all_embeddings(self) -> List[Dict]:
        """
        Get all embeddings for similarity search.

        Returns:
            List of dicts with classification_id, asset_text, embedding_vector
        """
        query = """
            SELECT
                c.classification_id,
                c.asset_text,
                c.classification_class,
                c.classification_life,
                c.classification_method,
                c.classification_convention,
                e.embedding_vector
            FROM classifications c
            JOIN classification_embeddings e ON c.classification_id = e.classification_id
        """

        results = self.execute_query(query)

        # Deserialize embedding vectors
        for row in results:
            row['embedding_vector'] = pickle.loads(row['embedding_vector'])

        return results

    # ========================================================================
    # OVERRIDE OPERATIONS
    # ========================================================================

    def create_override(
        self,
        override_type: str,
        override_class: str,
        override_life: int,
        override_method: str,
        override_convention: str,
        **kwargs
    ) -> int:
        """
        Create new override rule.

        Args:
            override_type: Type of override ('asset_id', 'client_category', etc.)
            override_class: Override class
            override_life: Override life
            override_method: Override method
            override_convention: Override convention
            **kwargs: Additional override fields

        Returns:
            New override_id
        """
        fields = [
            'override_type', 'override_class', 'override_life',
            'override_method', 'override_convention'
        ] + list(kwargs.keys())

        values = [
            override_type, override_class, override_life,
            override_method, override_convention
        ] + list(kwargs.values())

        placeholders = ', '.join(['?'] * len(fields))
        query = f"""
            INSERT INTO overrides ({', '.join(fields)})
            VALUES ({placeholders})
        """

        override_id = self.execute_insert(query, tuple(values))
        self.log_audit(
            action_type='CREATE',
            entity_type='override',
            entity_id=override_id,
            client_id=kwargs.get('client_id'),
            description=f"Created override: {override_type}"
        )
        return override_id

    def get_overrides(self, client_id: Optional[int] = None, active_only: bool = True) -> List[Dict]:
        """Get all overrides, optionally filtered by client."""
        query = "SELECT * FROM overrides WHERE 1=1"
        params = []

        if client_id:
            query += " AND (client_id = ? OR client_id IS NULL)"
            params.append(client_id)

        if active_only:
            query += " AND is_active = 1"

        query += " ORDER BY priority DESC, created_at DESC"
        return self.execute_query(query, tuple(params))

    def find_override(self, asset_id: Optional[int] = None, external_asset_id: Optional[str] = None, category: Optional[str] = None) -> Optional[Dict]:
        """
        Find matching override for an asset.

        Args:
            asset_id: Internal asset ID
            external_asset_id: External asset ID
            category: Asset category

        Returns:
            Highest priority matching override, or None
        """
        query = """
            SELECT * FROM overrides
            WHERE is_active = 1
            AND (
                (override_type = 'asset_id' AND (asset_id = ? OR external_asset_id = ?))
                OR (override_type = 'client_category' AND category_name = ?)
            )
            ORDER BY priority DESC, created_at DESC
            LIMIT 1
        """
        results = self.execute_query(query, (asset_id, external_asset_id, category))
        return results[0] if results else None

    # ========================================================================
    # EXPORT OPERATIONS
    # ========================================================================

    def create_export(
        self,
        tax_year: int,
        total_assets: int,
        **kwargs
    ) -> int:
        """
        Create new export record.

        Args:
            tax_year: Tax year
            total_assets: Number of assets in export
            **kwargs: Additional export fields

        Returns:
            New export_id
        """
        fields = ['tax_year', 'total_assets'] + list(kwargs.keys())
        values = [tax_year, total_assets] + list(kwargs.values())
        placeholders = ', '.join(['?'] * len(fields))

        query = f"""
            INSERT INTO exports ({', '.join(fields)})
            VALUES ({placeholders})
        """

        export_id = self.execute_insert(query, tuple(values))
        self.log_audit(
            action_type='EXPORT',
            entity_type='export',
            entity_id=export_id,
            client_id=kwargs.get('client_id'),
            description=f"Created export for tax year {tax_year}"
        )
        return export_id

    def add_export_asset(self, export_id: int, **kwargs) -> int:
        """Add asset to export."""
        fields = ['export_id'] + list(kwargs.keys())
        values = [export_id] + list(kwargs.values())
        placeholders = ', '.join(['?'] * len(fields))

        query = f"""
            INSERT INTO export_assets ({', '.join(fields)})
            VALUES ({placeholders})
        """
        return self.execute_insert(query, tuple(values))

    def get_export(self, export_id: int) -> Optional[Dict]:
        """Get export by ID."""
        query = "SELECT * FROM exports WHERE export_id = ?"
        results = self.execute_query(query, (export_id,))
        return results[0] if results else None

    def get_exports_by_client(self, client_id: int, limit: int = 50) -> List[Dict]:
        """Get recent exports for a client."""
        query = """
            SELECT * FROM exports
            WHERE client_id = ?
            ORDER BY export_date DESC
            LIMIT ?
        """
        return self.execute_query(query, (client_id, limit))

    def get_recent_exports(self, limit: int = 50) -> List[Dict]:
        """Get recent exports across all clients."""
        query = "SELECT * FROM v_export_summary ORDER BY export_date DESC LIMIT ?"
        return self.execute_query(query, (limit,))

    def get_export_assets(self, export_id: int) -> List[Dict]:
        """Get all assets in an export."""
        query = "SELECT * FROM export_assets WHERE export_id = ?"
        return self.execute_query(query, (export_id,))

    def update_export(self, export_id: int, **kwargs) -> bool:
        """Update export fields."""
        if not kwargs:
            return False

        set_clause = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE exports SET {set_clause} WHERE export_id = ?"
        params = tuple(kwargs.values()) + (export_id,)

        return self.execute_update(query, params) > 0

    # ========================================================================
    # APPROVAL OPERATIONS
    # ========================================================================

    def create_approval(
        self,
        approver_name: str,
        approver_email: str,
        approval_status: str,
        **kwargs
    ) -> int:
        """
        Create new approval record.

        Args:
            approver_name: Name of approver
            approver_email: Email of approver
            approval_status: Approval status
            **kwargs: Additional approval fields

        Returns:
            New approval_id
        """
        fields = ['approver_name', 'approver_email', 'approval_status'] + list(kwargs.keys())
        values = [approver_name, approver_email, approval_status] + list(kwargs.values())
        placeholders = ', '.join(['?'] * len(fields))

        query = f"""
            INSERT INTO approvals ({', '.join(fields)})
            VALUES ({placeholders})
        """

        approval_id = self.execute_insert(query, tuple(values))
        self.log_audit(
            action_type='APPROVE',
            entity_type='approval',
            entity_id=approval_id,
            client_id=kwargs.get('client_id'),
            description=f"Approval created by {approver_name}: {approval_status}",
            user_name=approver_name,
            user_email=approver_email
        )
        return approval_id

    def create_checkpoint(
        self,
        approval_id: int,
        checkpoint_number: int,
        checkpoint_name: str,
        checkpoint_status: str,
        **kwargs
    ) -> int:
        """Create approval checkpoint record."""
        fields = [
            'approval_id', 'checkpoint_number', 'checkpoint_name', 'checkpoint_status'
        ] + list(kwargs.keys())

        values = [
            approval_id, checkpoint_number, checkpoint_name, checkpoint_status
        ] + list(kwargs.values())

        placeholders = ', '.join(['?'] * len(fields))
        query = f"""
            INSERT INTO approval_checkpoints ({', '.join(fields)})
            VALUES ({placeholders})
        """
        return self.execute_insert(query, tuple(values))

    def get_approval(self, approval_id: int) -> Optional[Dict]:
        """Get approval by ID."""
        query = "SELECT * FROM approvals WHERE approval_id = ?"
        results = self.execute_query(query, (approval_id,))
        return results[0] if results else None

    def get_approval_checkpoints(self, approval_id: int) -> List[Dict]:
        """Get all checkpoints for an approval."""
        query = """
            SELECT * FROM approval_checkpoints
            WHERE approval_id = ?
            ORDER BY checkpoint_number
        """
        return self.execute_query(query, (approval_id,))

    def get_recent_approvals(self, limit: int = 50) -> List[Dict]:
        """Get recent approvals."""
        query = """
            SELECT * FROM approvals
            ORDER BY approval_timestamp DESC
            LIMIT ?
        """
        return self.execute_query(query, (limit,))

    def get_approvals_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        """Get approvals by status."""
        query = """
            SELECT * FROM approvals
            WHERE approval_status = ?
            ORDER BY approval_timestamp DESC
            LIMIT ?
        """
        return self.execute_query(query, (status, limit))

    def update_approval(self, approval_id: int, **kwargs) -> bool:
        """Update approval fields."""
        if not kwargs:
            return False

        # Filter to only allowed fields to prevent SQL injection via column names
        safe_kwargs = {k: v for k, v in kwargs.items() if k in self.ALLOWED_APPROVAL_FIELDS}
        if not safe_kwargs:
            return False

        set_clause = ', '.join([f"{k} = ?" for k in safe_kwargs.keys()])
        query = f"UPDATE approvals SET {set_clause} WHERE approval_id = ?"
        params = tuple(safe_kwargs.values()) + (approval_id,)

        return self.execute_update(query, params) > 0

    # ========================================================================
    # CLIENT FIELD MAPPING OPERATIONS
    # ========================================================================

    def create_field_mapping(self, client_id: int, source_field: str, target_field: str, **kwargs) -> int:
        """Create client field mapping."""
        fields = ['client_id', 'source_field', 'target_field'] + list(kwargs.keys())
        values = [client_id, source_field, target_field] + list(kwargs.values())
        placeholders = ', '.join(['?'] * len(fields))

        query = f"""
            INSERT INTO client_field_mappings ({', '.join(fields)})
            VALUES ({placeholders})
        """
        return self.execute_insert(query, tuple(values))

    def get_field_mappings(self, client_id: int, active_only: bool = True) -> List[Dict]:
        """Get field mappings for a client."""
        query = "SELECT * FROM client_field_mappings WHERE client_id = ?"
        params = [client_id]

        if active_only:
            query += " AND is_active = 1"

        query += " ORDER BY source_field"
        return self.execute_query(query, tuple(params))

    # ========================================================================
    # AUDIT LOG OPERATIONS
    # ========================================================================

    def log_audit(
        self,
        action_type: str,
        entity_type: str,
        description: str,
        entity_id: Optional[int] = None,
        client_id: Optional[int] = None,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None,
        old_values: Optional[Dict] = None,
        new_values: Optional[Dict] = None,
        session_id: Optional[str] = None
    ) -> int:
        """
        Log audit trail entry.

        Args:
            action_type: Type of action (CREATE, UPDATE, DELETE, etc.)
            entity_type: Type of entity (asset, export, approval, etc.)
            description: Human-readable description
            entity_id: ID of affected entity
            client_id: Client ID
            user_name: User who performed action
            user_email: User email
            old_values: Previous values (for updates)
            new_values: New values (for creates/updates)
            session_id: Session ID

        Returns:
            New audit_id
        """
        query = """
            INSERT INTO audit_log (
                action_type, entity_type, entity_id, client_id,
                description, user_name, user_email,
                old_values, new_values, session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            action_type, entity_type, entity_id, client_id,
            description, user_name, user_email,
            old_values if old_values else None,
            new_values if new_values else None,
            session_id
        )

        return self.execute_insert(query, params)

    def get_audit_log(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        client_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get audit log entries with optional filters."""
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []

        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)

        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)

        if client_id:
            query += " AND client_id = ?"
            params.append(client_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        return self.execute_query(query, tuple(params))

    # ========================================================================
    # ANALYTICS & REPORTING
    # ========================================================================

    def get_classification_accuracy_report(self) -> List[Dict]:
        """Get classification accuracy metrics."""
        return self.execute_query("SELECT * FROM v_classification_accuracy")

    def get_approval_metrics(self) -> List[Dict]:
        """Get approval workflow metrics."""
        return self.execute_query("SELECT * FROM v_approval_metrics")

    def get_client_activity_report(self) -> List[Dict]:
        """Get client activity summary."""
        return self.execute_query("SELECT * FROM v_client_activity")

    def get_dashboard_stats(self, client_id: Optional[int] = None) -> Dict:
        """
        Get dashboard statistics.

        Returns:
            Dictionary with key metrics
        """
        stats = {
            'total_clients': 0,
            'total_assets': 0,
            'total_exports': 0,
            'total_approvals': 0,
            'pending_approvals': 0,
            'recent_activity': []
        }

        # Total clients
        query = "SELECT COUNT(*) as count FROM clients WHERE active = 1"
        result = self.execute_query(query)
        stats['total_clients'] = result[0]['count']

        # Total assets (using parameterized query to prevent SQL injection)
        if client_id:
            query = "SELECT COUNT(*) as count FROM assets WHERE client_id = ?"
            result = self.execute_query(query, (client_id,))
        else:
            query = "SELECT COUNT(*) as count FROM assets"
            result = self.execute_query(query)
        stats['total_assets'] = result[0]['count']

        # Total exports (using parameterized query to prevent SQL injection)
        if client_id:
            query = "SELECT COUNT(*) as count FROM exports WHERE client_id = ?"
            result = self.execute_query(query, (client_id,))
        else:
            query = "SELECT COUNT(*) as count FROM exports"
            result = self.execute_query(query)
        stats['total_exports'] = result[0]['count']

        # Total approvals (using parameterized query to prevent SQL injection)
        if client_id:
            query = "SELECT COUNT(*) as count FROM approvals WHERE client_id = ?"
            result = self.execute_query(query, (client_id,))
        else:
            query = "SELECT COUNT(*) as count FROM approvals"
            result = self.execute_query(query)
        stats['total_approvals'] = result[0]['count']

        # Pending approvals (using parameterized query to prevent SQL injection)
        if client_id:
            query = "SELECT COUNT(*) as count FROM approvals WHERE approval_status IN ('PENDING_REVIEW', 'QUALITY_APPROVED', 'TAX_APPROVED') AND client_id = ?"
            result = self.execute_query(query, (client_id,))
        else:
            query = "SELECT COUNT(*) as count FROM approvals WHERE approval_status IN ('PENDING_REVIEW', 'QUALITY_APPROVED', 'TAX_APPROVED')"
            result = self.execute_query(query)
        stats['pending_approvals'] = result[0]['count']

        # Recent activity (using parameterized query to prevent SQL injection)
        if client_id:
            query = "SELECT * FROM audit_log WHERE client_id = ? ORDER BY timestamp DESC LIMIT 10"
            stats['recent_activity'] = self.execute_query(query, (client_id,))
        else:
            query = "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 10"
            stats['recent_activity'] = self.execute_query(query)

        return stats


# Global instance
_db_instance = None

def get_db() -> DatabaseManager:
    """Get or create global database manager instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance


# ==============================================================================
# ENCRYPTION UTILITIES
# ==============================================================================

def generate_encryption_keys() -> dict:
    """
    Generate new encryption keys for database encryption.

    Returns:
        Dict with FA_ENCRYPTION_KEY and FA_ENCRYPTION_SALT values
        to add to your .env file

    Usage:
        keys = generate_encryption_keys()
        # Add these to your .env file:
        # FA_ENCRYPTION_KEY=<key>
        # FA_ENCRYPTION_SALT=<salt>
    """
    if not ENCRYPTION_AVAILABLE:
        raise ImportError(
            "Encryption requires the 'cryptography' package. "
            "Install with: pip install cryptography"
        )

    from .encryption import generate_encryption_config
    return generate_encryption_config()


def check_encryption_status() -> dict:
    """
    Check the current encryption status.

    Returns:
        Dict with encryption status information
    """
    status = {
        "encryption_module_available": ENCRYPTION_AVAILABLE,
        "cryptography_installed": CRYPTO_AVAILABLE,
        "encryption_key_configured": bool(os.environ.get("FA_ENCRYPTION_KEY")),
        "encryption_salt_configured": bool(os.environ.get("FA_ENCRYPTION_SALT")),
        "encryption_active": False,
        "encrypted_tables": [],
    }

    db = get_db()
    if hasattr(db, '_encryption_enabled'):
        status["encryption_active"] = db._encryption_enabled

    if hasattr(db, '_encrypted_columns') and db._encrypted_columns:
        status["encrypted_tables"] = list(db._encrypted_columns.keys())

    return status


def migrate_to_encrypted(table_name: str, columns: List[str]) -> int:
    """
    Migrate existing plaintext data to encrypted format.

    CAUTION: This is a one-way operation. Backup your database first!

    Args:
        table_name: Name of table to migrate
        columns: List of column names to encrypt

    Returns:
        Number of rows migrated
    """
    if not ENCRYPTION_AVAILABLE or not CRYPTO_AVAILABLE:
        raise ImportError("Encryption not available")

    from .encryption import FieldEncryptor

    db = get_db()
    if not db._encryption_enabled:
        raise ValueError("Encryption not enabled. Set FA_ENCRYPTION_KEY first.")

    encryptor = FieldEncryptor()

    # Get all rows
    rows = db.execute_query(f"SELECT * FROM {table_name}")
    migrated = 0

    for row in rows:
        updates = {}
        for col in columns:
            if col in row and row[col]:
                # Check if already encrypted (heuristic)
                if not encryptor.is_encrypted(str(row[col])):
                    updates[col] = encryptor.encrypt(str(row[col]))

        if updates:
            # Build update query
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            id_col = 'id' if 'id' in row else list(row.keys())[0]
            query = f"UPDATE {table_name} SET {set_clause} WHERE {id_col} = ?"
            params = tuple(updates.values()) + (row[id_col],)
            db.execute_update(query, params)
            migrated += 1

    logger.info(f"Migrated {migrated} rows in {table_name} to encrypted format")
    return migrated
