"""
Data Migration Script: JSON to SQLite
Migrates all existing JSON-based data to the new SQLite database

Migrates:
- classification_memory.json → classifications + classification_embeddings tables
- overrides.json → overrides table
- fa_cs_import_mappings.json → client_field_mappings table
- approval_*.json files → approvals + approval_checkpoints tables
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import glob

from .database_manager import get_db


# Paths
LOGIC_DIR = Path(__file__).resolve().parent
CLASSIFICATION_MEMORY_PATH = LOGIC_DIR / "classification_memory.json"
OVERRIDES_PATH = LOGIC_DIR / "overrides.json"
IMPORT_MAPPINGS_PATH = LOGIC_DIR / "fa_cs_import_mappings.json"


class DataMigration:
    """Migrate JSON data to SQLite database."""

    def __init__(self):
        self.db = get_db()
        self.stats = {
            'classifications_migrated': 0,
            'embeddings_migrated': 0,
            'overrides_migrated': 0,
            'field_mappings_migrated': 0,
            'approvals_migrated': 0,
            'errors': []
        }

    def migrate_all(self, verbose: bool = True):
        """
        Run all migrations.

        Args:
            verbose: Print progress messages
        """
        if verbose:
            print("=" * 80)
            print("FIXED ASSET AI - DATA MIGRATION")
            print("Migrating JSON data to SQLite database")
            print("=" * 80)
            print()

        # Ensure default client exists
        self._ensure_default_client()

        # Run migrations
        self.migrate_classification_memory(verbose)
        self.migrate_overrides(verbose)
        self.migrate_import_mappings(verbose)
        self.migrate_approval_files(verbose)

        # Print summary
        if verbose:
            self.print_summary()

    def _ensure_default_client(self):
        """Ensure default client exists for migration."""
        client = self.db.get_client(1)
        if not client:
            self.db.create_client(
                client_name="Default Client",
                client_code="DEFAULT",
                active=True,
                notes="Default client for data migration from JSON files"
            )

    def migrate_classification_memory(self, verbose: bool = True):
        """
        Migrate classification_memory.json to classifications table.

        Structure:
        {
            "assets": [
                {
                    "text": "asset description",
                    "embedding": [0.1, 0.2, ...],
                    "classification": {
                        "class": "Office Equipment",
                        "life": 5,
                        "method": "MACRS GDS",
                        "convention": "HY",
                        "bonus": true,
                        "qip": false
                    }
                }
            ]
        }
        """
        if verbose:
            print("Migrating classification memory...")

        if not CLASSIFICATION_MEMORY_PATH.exists():
            if verbose:
                print("  ⚠️  classification_memory.json not found - skipping")
            return

        try:
            with open(CLASSIFICATION_MEMORY_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            assets = data.get('assets', [])
            if verbose:
                print(f"  Found {len(assets)} classifications to migrate")

            for idx, asset in enumerate(assets):
                try:
                    # Extract classification data
                    text = asset.get('text', '')
                    embedding = asset.get('embedding', [])
                    classification = asset.get('classification', {})

                    if not text or not classification:
                        continue

                    # Create classification record
                    classification_id = self.db.create_classification(
                        asset_text=text,
                        classification_class=classification.get('class', ''),
                        classification_life=classification.get('life', 0),
                        classification_method=classification.get('method', ''),
                        classification_convention=classification.get('convention', ''),
                        is_bonus_eligible=classification.get('bonus', False),
                        is_qip=classification.get('qip', False),
                        source='memory',
                        client_id=1  # Default client
                    )

                    # Store embedding if available
                    if embedding and len(embedding) > 0:
                        self.db.store_embedding(
                            classification_id=classification_id,
                            embedding_vector=embedding,
                            model="text-embedding-3-small"
                        )
                        self.stats['embeddings_migrated'] += 1

                    self.stats['classifications_migrated'] += 1

                    if verbose and (idx + 1) % 10 == 0:
                        print(f"  Migrated {idx + 1}/{len(assets)} classifications...")

                except Exception as e:
                    self.stats['errors'].append(f"Classification {idx}: {str(e)}")

            if verbose:
                print(f"  ✅ Migrated {self.stats['classifications_migrated']} classifications")
                print(f"  ✅ Migrated {self.stats['embeddings_migrated']} embeddings")

        except Exception as e:
            error_msg = f"Error migrating classification memory: {str(e)}"
            self.stats['errors'].append(error_msg)
            if verbose:
                print(f"  ❌ {error_msg}")

    def migrate_overrides(self, verbose: bool = True):
        """
        Migrate overrides.json to overrides table.

        Structure:
        {
            "by_asset_id": {
                "BA-1001": {
                    "class": "Office Furniture",
                    "life": 7,
                    "method": "MACRS GDS",
                    "convention": "HY",
                    "bonus": true,
                    "qip": false
                }
            },
            "by_client_category": {
                "Leasehold Improvements": {
                    "class": "QIP",
                    "life": 15,
                    ...
                }
            }
        }
        """
        if verbose:
            print("\nMigrating overrides...")

        if not OVERRIDES_PATH.exists():
            if verbose:
                print("  ⚠️  overrides.json not found - skipping")
            return

        try:
            with open(OVERRIDES_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Migrate asset ID overrides
            by_asset_id = data.get('by_asset_id', {})
            if verbose:
                print(f"  Found {len(by_asset_id)} asset ID overrides")

            for asset_id, override in by_asset_id.items():
                try:
                    self.db.create_override(
                        override_type='asset_id',
                        external_asset_id=asset_id,
                        override_class=override.get('class', ''),
                        override_life=override.get('life', 0),
                        override_method=override.get('method', ''),
                        override_convention=override.get('convention', ''),
                        is_bonus_eligible=override.get('bonus', False),
                        is_qip=override.get('qip', False),
                        client_id=1,  # Default client
                        priority=10,  # Higher priority for asset ID overrides
                        is_active=True,
                        created_by='migration'
                    )
                    self.stats['overrides_migrated'] += 1
                except Exception as e:
                    self.stats['errors'].append(f"Override {asset_id}: {str(e)}")

            # Migrate category overrides
            by_category = data.get('by_client_category', {})
            if verbose:
                print(f"  Found {len(by_category)} category overrides")

            for category, override in by_category.items():
                try:
                    self.db.create_override(
                        override_type='client_category',
                        category_name=category,
                        override_class=override.get('class', ''),
                        override_life=override.get('life', 0),
                        override_method=override.get('method', ''),
                        override_convention=override.get('convention', ''),
                        is_bonus_eligible=override.get('bonus', False),
                        is_qip=override.get('qip', False),
                        client_id=1,  # Default client
                        priority=5,  # Lower priority than asset ID overrides
                        is_active=True,
                        created_by='migration'
                    )
                    self.stats['overrides_migrated'] += 1
                except Exception as e:
                    self.stats['errors'].append(f"Category override {category}: {str(e)}")

            if verbose:
                print(f"  ✅ Migrated {self.stats['overrides_migrated']} overrides")

        except Exception as e:
            error_msg = f"Error migrating overrides: {str(e)}"
            self.stats['errors'].append(error_msg)
            if verbose:
                print(f"  ❌ {error_msg}")

    def migrate_import_mappings(self, verbose: bool = True):
        """
        Migrate fa_cs_import_mappings.json to client_field_mappings table.

        Structure:
        {
            "default": {
                "mapping_name": "Default AI Export Mapping",
                "description": "...",
                "field_mappings": {
                    "Asset #": "Asset Number",
                    "Description": "Asset Description",
                    ...
                },
                "import_settings": {
                    "skip_header_rows": 0,
                    ...
                }
            }
        }
        """
        if verbose:
            print("\nMigrating import mappings...")

        if not IMPORT_MAPPINGS_PATH.exists():
            if verbose:
                print("  ⚠️  fa_cs_import_mappings.json not found - skipping")
            return

        try:
            with open(IMPORT_MAPPINGS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Process each client's mappings
            for key, mapping_config in data.items():
                # Skip metadata fields
                if key.startswith('_'):
                    continue

                if not isinstance(mapping_config, dict):
                    continue

                # Get or create client
                if key == 'default':
                    client_id = 1  # Default client
                else:
                    # Check if client exists
                    clients = self.db.get_all_clients(active_only=False)
                    existing = [c for c in clients if c['client_code'] == key.upper()]

                    if existing:
                        client_id = existing[0]['client_id']
                    else:
                        # Create new client
                        client_id = self.db.create_client(
                            client_name=mapping_config.get('mapping_name', key),
                            client_code=key.upper(),
                            active=True,
                            notes=f"Migrated from fa_cs_import_mappings.json: {key}"
                        )

                # Migrate field mappings
                field_mappings = mapping_config.get('field_mappings', {})
                if verbose:
                    print(f"  Migrating {len(field_mappings)} field mappings for {key}...")

                for source_field, target_field in field_mappings.items():
                    try:
                        self.db.create_field_mapping(
                            client_id=client_id,
                            source_field=source_field,
                            target_field=target_field,
                            mapping_name=mapping_config.get('mapping_name', ''),
                            description=mapping_config.get('description', ''),
                            is_active=True
                        )
                        self.stats['field_mappings_migrated'] += 1
                    except Exception as e:
                        self.stats['errors'].append(f"Field mapping {source_field}: {str(e)}")

                # Migrate import settings
                import_settings = mapping_config.get('import_settings', {})
                if import_settings:
                    try:
                        # Check if settings already exist
                        existing_settings = self.db.execute_query(
                            "SELECT * FROM client_import_settings WHERE client_id = ?",
                            (client_id,)
                        )

                        if not existing_settings:
                            self.db.execute_insert(
                                """
                                INSERT INTO client_import_settings (
                                    client_id, skip_header_rows, update_existing_assets,
                                    validate_before_import, create_backup
                                ) VALUES (?, ?, ?, ?, ?)
                                """,
                                (
                                    client_id,
                                    import_settings.get('skip_header_rows', 0),
                                    import_settings.get('update_existing_assets', False),
                                    import_settings.get('validate_before_import', True),
                                    import_settings.get('create_backup', True)
                                )
                            )
                    except Exception as e:
                        self.stats['errors'].append(f"Import settings for {key}: {str(e)}")

            if verbose:
                print(f"  ✅ Migrated {self.stats['field_mappings_migrated']} field mappings")

        except Exception as e:
            error_msg = f"Error migrating import mappings: {str(e)}"
            self.stats['errors'].append(error_msg)
            if verbose:
                print(f"  ❌ {error_msg}")

    def migrate_approval_files(self, verbose: bool = True):
        """
        Migrate approval_*.json files to approvals table.

        Searches for approval_YYYYMMDD_HHMMSS.json files and imports them.
        """
        if verbose:
            print("\nMigrating approval files...")

        # Find all approval JSON files
        approval_files = glob.glob(str(LOGIC_DIR / "approval_*.json"))

        if not approval_files:
            if verbose:
                print("  ⚠️  No approval files found - skipping")
            return

        if verbose:
            print(f"  Found {len(approval_files)} approval files")

        for file_path in approval_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    approval_data = json.load(f)

                # Extract approval info
                approver_name = approval_data.get('approver_name', 'Unknown')
                approver_email = approval_data.get('approver_email', '')
                approval_status = approval_data.get('status', 'UNKNOWN')
                approval_notes = approval_data.get('approval_notes', '')
                rpa_ready = approval_data.get('rpa_ready', False)

                # Create approval record
                approval_id = self.db.create_approval(
                    approver_name=approver_name,
                    approver_email=approver_email,
                    approval_status=approval_status,
                    approval_notes=approval_notes,
                    rpa_ready=rpa_ready,
                    client_id=1  # Default client
                )

                # Migrate checkpoints
                checkpoints = approval_data.get('checkpoints', {})

                # Checkpoint 1: Quality
                if 'checkpoint_1_quality' in checkpoints:
                    cp1 = checkpoints['checkpoint_1_quality']
                    self.db.create_checkpoint(
                        approval_id=approval_id,
                        checkpoint_number=1,
                        checkpoint_name='QUALITY_REVIEW',
                        checkpoint_status='PASSED' if cp1.get('is_valid') else 'FAILED',
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
                        checkpoint_status='PASSED',
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

                self.stats['approvals_migrated'] += 1

                if verbose and self.stats['approvals_migrated'] % 5 == 0:
                    print(f"  Migrated {self.stats['approvals_migrated']}/{len(approval_files)} approvals...")

            except Exception as e:
                self.stats['errors'].append(f"Approval file {os.path.basename(file_path)}: {str(e)}")

        if verbose:
            print(f"  ✅ Migrated {self.stats['approvals_migrated']} approvals")

    def print_summary(self):
        """Print migration summary."""
        print()
        print("=" * 80)
        print("MIGRATION SUMMARY")
        print("=" * 80)
        print(f"Classifications migrated:  {self.stats['classifications_migrated']}")
        print(f"Embeddings migrated:       {self.stats['embeddings_migrated']}")
        print(f"Overrides migrated:        {self.stats['overrides_migrated']}")
        print(f"Field mappings migrated:   {self.stats['field_mappings_migrated']}")
        print(f"Approvals migrated:        {self.stats['approvals_migrated']}")
        print()

        if self.stats['errors']:
            print(f"⚠️  {len(self.stats['errors'])} errors occurred:")
            for error in self.stats['errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more")
        else:
            print("✅ All data migrated successfully!")

        print("=" * 80)


def main():
    """Run migration."""
    migration = DataMigration()
    migration.migrate_all(verbose=True)


if __name__ == "__main__":
    main()
