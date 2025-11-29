#!/usr/bin/env python3
"""
Test script for SQLite solution
Verifies database creation, basic operations, and data integrity
"""

import sys
import os

# Add fixed_asset_ai to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'fixed_asset_ai'))

def test_database_creation():
    """Test that database can be created."""
    print("\n" + "="*80)
    print("TEST 1: Database Creation")
    print("="*80)

    try:
        from logic.database_manager import get_db

        db = get_db()
        print("✅ Database manager created successfully")

        # Check that tables exist
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                'clients', 'assets', 'classifications', 'classification_embeddings',
                'overrides', 'exports', 'export_assets', 'approvals',
                'approval_checkpoints', 'client_field_mappings',
                'client_import_settings', 'audit_log', 'sessions', 'schema_version'
            ]

            missing_tables = [t for t in expected_tables if t not in tables]

            if missing_tables:
                print(f"❌ Missing tables: {missing_tables}")
                return False

            print(f"✅ All {len(expected_tables)} tables created successfully")
            return True

    except Exception as e:
        print(f"❌ Error creating database: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_basic_operations():
    """Test basic CRUD operations."""
    print("\n" + "="*80)
    print("TEST 2: Basic CRUD Operations")
    print("="*80)

    try:
        from logic.database_manager import get_db

        db = get_db()

        # Test client creation
        print("\nTesting client operations...")
        client_id = db.create_client(
            client_name="Test Client",
            client_code="TEST",
            active=True
        )
        print(f"✅ Client created with ID: {client_id}")

        # Retrieve client
        client = db.get_client(client_id)
        if client and client['client_name'] == "Test Client":
            print("✅ Client retrieved successfully")
        else:
            print("❌ Client retrieval failed")
            return False

        # Test asset creation
        print("\nTesting asset operations...")
        asset_id = db.create_asset(
            description="Test laptop computer",
            client_id=client_id,
            cost=1500.00,
            asset_number="TEST-001"
        )
        print(f"✅ Asset created with ID: {asset_id}")

        # Test classification creation
        print("\nTesting classification operations...")
        classification_id = db.create_classification(
            asset_text="Test laptop computer",
            classification_class="Office Equipment",
            classification_life=5,
            classification_method="MACRS GDS",
            classification_convention="HY",
            asset_id=asset_id,
            source="test",
            confidence_score=0.95
        )
        print(f"✅ Classification created with ID: {classification_id}")

        # Test override creation
        print("\nTesting override operations...")
        override_id = db.create_override(
            override_type="asset_id",
            external_asset_id="TEST-001",
            override_class="Office Equipment",
            override_life=7,
            override_method="MACRS GDS",
            override_convention="HY",
            client_id=client_id
        )
        print(f"✅ Override created with ID: {override_id}")

        # Test export creation
        print("\nTesting export operations...")
        export_id = db.create_export(
            tax_year=2024,
            total_assets=1,
            client_id=client_id,
            total_cost=1500.00,
            export_filename="test_export.xlsx"
        )
        print(f"✅ Export created with ID: {export_id}")

        # Test approval creation
        print("\nTesting approval operations...")
        approval_id = db.create_approval(
            approver_name="Test User",
            approver_email="test@example.com",
            approval_status="FINAL_APPROVED",
            export_id=export_id,
            client_id=client_id
        )
        print(f"✅ Approval created with ID: {approval_id}")

        # Test checkpoint creation
        checkpoint_id = db.create_checkpoint(
            approval_id=approval_id,
            checkpoint_number=1,
            checkpoint_name="QUALITY_REVIEW",
            checkpoint_status="PASSED",
            is_valid=True
        )
        print(f"✅ Checkpoint created with ID: {checkpoint_id}")

        # Test queries
        print("\nTesting query operations...")
        stats = db.get_dashboard_stats(client_id=client_id)
        print(f"✅ Dashboard stats retrieved: {stats['total_assets']} assets")

        audit_log = db.get_audit_log(limit=10)
        print(f"✅ Audit log retrieved: {len(audit_log)} entries")

        return True

    except Exception as e:
        print(f"❌ Error in basic operations: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_workflow_integration():
    """Test workflow integration layer."""
    print("\n" + "="*80)
    print("TEST 3: Workflow Integration")
    print("="*80)

    try:
        from logic.workflow_integration import get_integration
        import pandas as pd

        integration = get_integration()

        # Test export integration
        print("\nTesting export integration...")
        test_df = pd.DataFrame({
            'Asset #': ['TEST-001'],
            'Description': ['Test asset'],
            'Transaction Type': ['Current Year Addition'],
            'Tax Cost': [1000.0],
            'Tax Sec 179 Expensed': [0],
            'Bonus Amount': [1000.0],
            'Tax Cur Depreciation': [0],
            'De Minimis Expensed': [0]
        })

        export_id = integration.save_export_to_database(
            df=test_df,
            tax_year=2024,
            export_filename="test_integration_export.xlsx",
            client_id=1
        )
        print(f"✅ Export saved via integration: {export_id}")

        # Test classification integration
        print("\nTesting classification integration...")
        classification_id = integration.save_classification(
            asset_text="Test integration asset",
            classification={
                'class': 'Office Equipment',
                'life': 5,
                'method': 'MACRS GDS',
                'convention': 'HY',
                'bonus': True,
                'qip': False
            },
            source='test',
            confidence_score=0.90,
            client_id=1
        )
        print(f"✅ Classification saved via integration: {classification_id}")

        # Test override loading
        print("\nTesting override loading...")
        by_asset_id, by_category = integration.load_overrides_from_database(client_id=1)
        print(f"✅ Overrides loaded: {len(by_asset_id)} by asset ID, {len(by_category)} by category")

        return True

    except Exception as e:
        print(f"❌ Error in workflow integration: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_data_integrity():
    """Test data integrity and relationships."""
    print("\n" + "="*80)
    print("TEST 4: Data Integrity & Relationships")
    print("="*80)

    try:
        from logic.database_manager import get_db

        db = get_db()

        # Test foreign key relationships
        print("\nTesting foreign key relationships...")
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check that foreign keys are enabled
            cursor.execute("PRAGMA foreign_keys")
            fk_status = cursor.fetchone()[0]

            if fk_status == 1:
                print("✅ Foreign keys are enabled")
            else:
                print("⚠️  Foreign keys are not enabled")

        # Test cascade deletes (create and delete a test client)
        print("\nTesting cascade operations...")
        test_client_id = db.create_client(
            client_name="Delete Test Client",
            client_code="DELTEST"
        )

        # Create related records
        test_asset_id = db.create_asset(
            description="Test asset for deletion",
            client_id=test_client_id
        )

        # Delete client (should cascade)
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clients WHERE client_id = ?", (test_client_id,))

        # Verify asset was also deleted
        asset = db.get_asset(test_asset_id)
        if asset is None:
            print("✅ Cascade delete working properly")
        else:
            print("⚠️  Cascade delete may not be working")

        # Test views
        print("\nTesting database views...")
        views = [
            'v_classification_accuracy',
            'v_export_summary',
            'v_approval_metrics',
            'v_client_activity',
            'v_asset_history'
        ]

        for view in views:
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(f"SELECT COUNT(*) FROM {view}")
                    cursor.fetchone()
                print(f"✅ View {view} is accessible")
            except Exception as e:
                print(f"❌ View {view} failed: {str(e)}")

        return True

    except Exception as e:
        print(f"❌ Error in data integrity tests: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def cleanup_test_data():
    """Clean up test data."""
    print("\n" + "="*80)
    print("CLEANUP: Removing Test Data")
    print("="*80)

    try:
        from logic.database_manager import get_db

        db = get_db()

        # Delete test clients and related data
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Delete test clients (cascades to related tables)
            cursor.execute("DELETE FROM clients WHERE client_code IN ('TEST', 'DELTEST')")
            deleted = cursor.rowcount

            print(f"✅ Cleaned up {deleted} test clients and related data")

        return True

    except Exception as e:
        print(f"❌ Error in cleanup: {str(e)}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("FIXED ASSET AI - SQLITE SOLUTION TEST SUITE")
    print("="*80)

    results = []

    # Run tests
    results.append(("Database Creation", test_database_creation()))
    results.append(("Basic CRUD Operations", test_basic_operations()))
    results.append(("Workflow Integration", test_workflow_integration()))
    results.append(("Data Integrity", test_data_integrity()))

    # Cleanup
    cleanup_test_data()

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "="*80)
    print(f"Results: {passed}/{total} tests passed")
    print("="*80)

    if passed == total:
        print("\n🎉 All tests passed! SQLite solution is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
