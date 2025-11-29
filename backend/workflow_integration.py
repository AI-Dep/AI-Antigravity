"""
Workflow Integration Layer
Integrates SQLite database with existing export and approval workflows

This module provides wrapper functions that:
1. Save export data to database after generation
2. Save approval records to database during workflow
3. Track classification history
4. Maintain audit trails
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import hashlib
import json

from .database_manager import get_db


class WorkflowIntegration:
    """Integration layer between workflows and database."""

    def __init__(self):
        self.db = get_db()

    # ========================================================================
    # EXPORT WORKFLOW INTEGRATION
    # ========================================================================

    def save_export_to_database(
        self,
        df: pd.DataFrame,
        tax_year: int,
        export_filename: str,
        export_path: str = "",
        client_id: int = 1,
        created_by: str = "system",
        approval_id: Optional[int] = None
    ) -> int:
        """
        Save export data to database.

        Args:
            df: Export DataFrame
            tax_year: Tax year
            export_filename: Filename of export
            export_path: Full path to export file
            client_id: Client ID (default 1)
            created_by: User who created export
            approval_id: Associated approval ID

        Returns:
            export_id of created export record
        """
        # Calculate summary statistics
        total_assets = len(df)

        # Count transaction types
        additions = len(df[df.get("Transaction Type", pd.Series()).str.contains("addition", case=False, na=False)])
        disposals = len(df[df.get("Transaction Type", pd.Series()).str.contains("disposal", case=False, na=False)])
        transfers = len(df[df.get("Transaction Type", pd.Series()).str.contains("transfer", case=False, na=False)])

        # Calculate financial totals (support both old and new column names)
        total_cost = df.get("Tax Cost", df.get("Cost/Basis", pd.Series([0.0]))).sum()
        total_section_179 = df.get("Tax Sec 179 Expensed", df.get("Section 179 Amount", pd.Series([0.0]))).sum()
        total_bonus = df.get("Bonus Amount", pd.Series([0.0])).sum()
        total_depreciable_basis = df.get("Depreciable Basis", pd.Series([0.0])).sum()
        total_macrs_year1 = df.get("Tax Cur Depreciation", df.get("MACRS Year 1 Depreciation", pd.Series([0.0]))).sum()
        total_de_minimis = df.get("De Minimis Expensed", pd.Series([0.0])).sum()
        total_sec179_carryforward = df.get("Section 179 Carryforward", pd.Series([0.0])).sum()

        # Calculate year 1 total deduction
        year1_total_deduction = total_section_179 + total_bonus + total_macrs_year1 + total_de_minimis

        # Generate audit hash
        audit_hash = self._generate_export_hash(df, tax_year)

        # Create export record
        export_id = self.db.create_export(
            tax_year=tax_year,
            total_assets=total_assets,
            export_filename=export_filename,
            export_path=export_path,
            client_id=client_id,
            additions_count=additions,
            disposals_count=disposals,
            transfers_count=transfers,
            total_cost=float(total_cost),
            total_section_179=float(total_section_179),
            total_bonus=float(total_bonus),
            total_depreciable_basis=float(total_depreciable_basis),
            total_macrs_year1=float(total_macrs_year1),
            total_de_minimis=float(total_de_minimis),
            total_sec179_carryforward=float(total_sec179_carryforward),
            year1_total_deduction=float(year1_total_deduction),
            approval_status="PENDING",
            rpa_status="NOT_STARTED",
            audit_hash=audit_hash,
            created_by=created_by
        )

        # Save individual assets
        self._save_export_assets(export_id, df)

        return export_id

    def _save_export_assets(self, export_id: int, df: pd.DataFrame):
        """Save individual assets from export to database."""
        for _, row in df.iterrows():
            try:
                self.db.add_export_asset(
                    export_id=export_id,
                    asset_number=str(row.get("Asset #", "")),
                    description=str(row.get("Description", "")),
                    transaction_type=str(row.get("Transaction Type", "")),
                    cost=float(row.get("Tax Cost", row.get("Cost/Basis", 0))),
                    classification=str(row.get("Tax Class", "")),
                    life=int(row.get("Tax Life", 0)) if pd.notna(row.get("Tax Life")) else 0,
                    method=str(row.get("Tax Method", "")),
                    convention=str(row.get("Convention", "")),
                    section_179_amount=float(row.get("Tax Sec 179 Expensed", row.get("Section 179 Amount", 0))),
                    bonus_amount=float(row.get("Bonus Amount", 0)),
                    macrs_depreciation=float(row.get("Tax Cur Depreciation", row.get("MACRS Year 1 Depreciation", 0))),
                    de_minimis_amount=float(row.get("De Minimis Expensed", 0))
                )
            except Exception as e:
                # Log error but continue processing
                print(f"Error saving asset: {str(e)}")
                continue

    def _generate_export_hash(self, df: pd.DataFrame, tax_year: int) -> str:
        """Generate SHA256 hash for export audit trail."""
        # Create deterministic string representation
        data_str = f"{tax_year}:{len(df)}:{df['Tax Cost'].sum() if 'Tax Cost' in df.columns else 0}"
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def update_export_status(
        self,
        export_id: int,
        approval_status: Optional[str] = None,
        rpa_status: Optional[str] = None,
        rpa_method: Optional[str] = None,
        approval_id: Optional[int] = None
    ) -> bool:
        """
        Update export status.

        Args:
            export_id: Export ID to update
            approval_status: New approval status
            rpa_status: New RPA status
            rpa_method: RPA method used
            approval_id: Associated approval ID

        Returns:
            True if updated successfully
        """
        kwargs = {}
        if approval_status:
            kwargs['approval_status'] = approval_status
        if rpa_status:
            kwargs['rpa_status'] = rpa_status
        if rpa_method:
            kwargs['rpa_method'] = rpa_method
        if approval_id:
            kwargs['approval_id'] = approval_id
        if rpa_status == 'COMPLETED':
            kwargs['rpa_completed_at'] = datetime.now().isoformat()

        return self.db.update_export(export_id, **kwargs)

    # ========================================================================
    # APPROVAL WORKFLOW INTEGRATION
    # ========================================================================

    def save_approval_to_database(
        self,
        approval_record: Dict,
        export_id: Optional[int] = None,
        client_id: int = 1
    ) -> int:
        """
        Save approval record to database.

        Args:
            approval_record: Approval record from human_approval_workflow
            export_id: Associated export ID
            client_id: Client ID

        Returns:
            approval_id of created approval
        """
        # Extract approval info
        approver_name = approval_record.get('approver_name', 'Unknown')
        approver_email = approval_record.get('approver_email', '')
        approval_status = approval_record.get('status', 'UNKNOWN')
        approval_notes = approval_record.get('approval_notes', '')
        rpa_ready = approval_record.get('rpa_ready', False)

        # Determine checkpoint statuses
        checkpoints = approval_record.get('checkpoints', {})

        cp1_status = self._get_checkpoint_status(checkpoints.get('checkpoint_1_quality'))
        cp2_status = self._get_checkpoint_status(checkpoints.get('checkpoint_2_tax'))
        cp3_status = self._get_checkpoint_status(checkpoints.get('checkpoint_3_checklist'))

        all_passed = (cp1_status == 'PASSED' and cp2_status == 'PASSED' and cp3_status == 'PASSED')

        # Create approval record
        approval_id = self.db.create_approval(
            approver_name=approver_name,
            approver_email=approver_email,
            approval_status=approval_status,
            export_id=export_id,
            client_id=client_id,
            checkpoint_1_status=cp1_status,
            checkpoint_2_status=cp2_status,
            checkpoint_3_status=cp3_status,
            all_checkpoints_passed=all_passed,
            rpa_ready=rpa_ready,
            approval_notes=approval_notes
        )

        # Save individual checkpoints
        self._save_checkpoint_details(approval_id, checkpoints)

        # Update export if provided
        if export_id:
            self.update_export_status(
                export_id=export_id,
                approval_status=approval_status,
                approval_id=approval_id
            )

        return approval_id

    def _get_checkpoint_status(self, checkpoint_data: Optional[Dict]) -> str:
        """Determine checkpoint status from checkpoint data."""
        if not checkpoint_data:
            return 'UNKNOWN'

        if checkpoint_data.get('is_valid') is False:
            return 'FAILED'

        if checkpoint_data.get('critical_count', 0) > 0:
            return 'FAILED'

        if checkpoint_data.get('error_count', 0) > 0:
            return 'WARNING'

        if checkpoint_data.get('all_passed') is False:
            return 'FAILED'

        return 'PASSED'

    def _save_checkpoint_details(self, approval_id: int, checkpoints: Dict):
        """Save detailed checkpoint data."""
        # Checkpoint 1: Quality
        if 'checkpoint_1_quality' in checkpoints:
            cp1 = checkpoints['checkpoint_1_quality']
            self.db.create_checkpoint(
                approval_id=approval_id,
                checkpoint_number=1,
                checkpoint_name='QUALITY_REVIEW',
                checkpoint_status=self._get_checkpoint_status(cp1),
                is_valid=cp1.get('is_valid', False),
                critical_count=cp1.get('critical_count', 0),
                error_count=cp1.get('error_count', 0),
                warning_count=cp1.get('warning_count', 0),
                total_issues=cp1.get('total_issues', 0),
                validation_details=json.dumps(cp1)
            )

        # Checkpoint 2: Tax
        if 'checkpoint_2_tax' in checkpoints:
            cp2 = checkpoints['checkpoint_2_tax']
            self.db.create_checkpoint(
                approval_id=approval_id,
                checkpoint_number=2,
                checkpoint_name='TAX_REVIEW',
                checkpoint_status='PASSED',  # Tax review always passes if completed
                tax_summary=json.dumps(cp2)
            )

        # Checkpoint 3: Pre-RPA
        if 'checkpoint_3_checklist' in checkpoints:
            cp3 = checkpoints['checkpoint_3_checklist']
            self.db.create_checkpoint(
                approval_id=approval_id,
                checkpoint_number=3,
                checkpoint_name='PRE_RPA_CHECKLIST',
                checkpoint_status='PASSED' if cp3.get('all_passed') else 'FAILED',
                checklist_results=json.dumps(cp3)
            )

    # ========================================================================
    # CLASSIFICATION WORKFLOW INTEGRATION
    # ========================================================================

    def save_classification(
        self,
        asset_text: str,
        classification: Dict,
        source: str = 'gpt',
        confidence_score: Optional[float] = None,
        embedding: Optional[List[float]] = None,
        client_id: int = 1,
        asset_id: Optional[int] = None,
        classified_by: Optional[str] = None
    ) -> int:
        """
        Save classification to database.

        Args:
            asset_text: Full asset text
            classification: Classification dict with class, life, method, convention
            source: Classification source ('gpt', 'rules', 'manual', 'override')
            confidence_score: Confidence score (0-1)
            embedding: Embedding vector
            client_id: Client ID
            asset_id: Associated asset ID
            classified_by: User who classified

        Returns:
            classification_id
        """
        # Create classification record
        classification_id = self.db.create_classification(
            asset_text=asset_text,
            classification_class=classification.get('class', ''),
            classification_life=classification.get('life', 0),
            classification_method=classification.get('method', ''),
            classification_convention=classification.get('convention', ''),
            is_bonus_eligible=classification.get('bonus', False),
            is_qip=classification.get('qip', False),
            source=source,
            confidence_score=confidence_score,
            asset_id=asset_id,
            classified_by=classified_by
        )

        # Store embedding if provided
        if embedding and len(embedding) > 0:
            self.db.store_embedding(
                classification_id=classification_id,
                embedding_vector=embedding
            )

        return classification_id

    def load_classification_memory(self) -> List[Dict]:
        """
        Load classification memory from database (replaces JSON file).

        Returns:
            List of classification records with embeddings
        """
        return self.db.get_all_embeddings()

    def query_similar_classifications(
        self,
        embedding: List[float],
        threshold: float = 0.82
    ) -> Optional[Dict]:
        """
        Query similar classifications (replaces memory engine similarity search).

        Args:
            embedding: Query embedding vector
            threshold: Similarity threshold

        Returns:
            Most similar classification if above threshold
        """
        import numpy as np

        # Get all embeddings
        all_embeddings = self.db.get_all_embeddings()

        if not all_embeddings:
            return None

        # Calculate similarities
        query_vec = np.array(embedding)
        best_score = -1
        best_item = None

        for item in all_embeddings:
            stored_vec = np.array(item['embedding_vector'])
            similarity = self._cosine_similarity(query_vec, stored_vec)

            if similarity > best_score:
                best_score = similarity
                best_item = item

        if best_score >= threshold:
            return {
                'classification': {
                    'class': best_item['classification_class'],
                    'life': best_item['classification_life'],
                    'method': best_item['classification_method'],
                    'convention': best_item['classification_convention'],
                },
                'similarity': float(best_score)
            }

        return None

    @staticmethod
    def _cosine_similarity(a: 'np.ndarray', b: 'np.ndarray') -> float:
        """Calculate cosine similarity between two vectors."""
        import numpy as np

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    # ========================================================================
    # OVERRIDE MANAGEMENT
    # ========================================================================

    def load_overrides_from_database(self, client_id: int = 1) -> Tuple[Dict, Dict]:
        """
        Load overrides from database (replaces overrides.json).

        Args:
            client_id: Client ID

        Returns:
            Tuple of (by_asset_id, by_client_category) dicts
        """
        overrides = self.db.get_overrides(client_id=client_id, active_only=True)

        by_asset_id = {}
        by_client_category = {}

        for override in overrides:
            override_dict = {
                'class': override['override_class'],
                'life': override['override_life'],
                'method': override['override_method'],
                'convention': override['override_convention'],
                'bonus': override['is_bonus_eligible'],
                'qip': override['is_qip']
            }

            if override['override_type'] == 'asset_id' and override.get('external_asset_id'):
                by_asset_id[override['external_asset_id']] = override_dict
            elif override['override_type'] == 'client_category' and override.get('category_name'):
                by_client_category[override['category_name']] = override_dict

        return by_asset_id, by_client_category

    # ========================================================================
    # FIELD MAPPING MANAGEMENT
    # ========================================================================

    def load_field_mappings(self, client_id: int = 1) -> Dict:
        """
        Load field mappings from database (replaces fa_cs_import_mappings.json).

        Args:
            client_id: Client ID

        Returns:
            Field mappings dict compatible with RPA module
        """
        mappings = self.db.get_field_mappings(client_id=client_id, active_only=True)

        if not mappings:
            # Return default mappings
            return self._get_default_field_mappings()

        # Convert to expected format
        field_mappings = {}
        for mapping in mappings:
            field_mappings[mapping['source_field']] = mapping['target_field']

        return {
            'mapping_name': mappings[0].get('mapping_name', 'Custom Mapping'),
            'field_mappings': field_mappings
        }

    def _get_default_field_mappings(self) -> Dict:
        """Get default field mappings."""
        return {
            'mapping_name': 'Default AI Export Mapping',
            'field_mappings': {
                'Asset #': 'Asset Number',
                'Description': 'Asset Description',
                'Date In Service': 'Date Placed in Service',
                'Tax Cost': 'Cost/Basis',
                'Tax Method': 'Depreciation Method',
                'Tax Life': 'Recovery Period',
                'Convention': 'Convention',
                'Tax Sec 179 Expensed': 'Section 179 Deduction',
                'Bonus Amount': 'Bonus Depreciation',
            }
        }


# Global instance
_integration_instance = None

def get_integration() -> WorkflowIntegration:
    """Get or create global integration instance."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = WorkflowIntegration()
    return _integration_instance
