import pandas as pd
import os
from backend.services.importer import ImporterService
from backend.services.classifier import ClassifierService

def create_test_excel():
    data = {
        "Asset ID": ["A001", "A002", "A003"],
        "Description": ["Dell Latitude Laptop", "Office Chair", "Ford F-150 Truck"],
        "Cost": [1200.00, 350.00, 45000.00],
        "Acquisition Date": ["2024-01-15", "2024-02-01", "2024-03-10"]
    }
    df = pd.DataFrame(data)
    df.to_excel("test_assets.xlsx", index=False)
    return "test_assets.xlsx"

def test_logic():
    print("--- Testing Backend Logic ---")
    
    # 1. Create Dummy File
    file_path = create_test_excel()
    print(f"Created test file: {file_path}")
    
    try:
        # 2. Test Importer
        print("\nTesting ImporterService...")
        importer = ImporterService()
        assets = importer.parse_excel(file_path)
        print(f"Imported {len(assets)} assets.")
        for a in assets:
            print(f" - {a.asset_id}: {a.description} (${a.cost})")
            
        assert len(assets) == 3
        assert assets[0].description == "Dell Latitude Laptop"
        
        # 3. Test Classifier
        print("\nTesting ClassifierService...")
        classifier = ClassifierService()
        classified = classifier.classify_batch(assets)
        
        for a in classified:
            print(f" - {a.description} -> {a.macrs_class} ({a.macrs_life} yr)")
            
        assert classified[0].macrs_class == "Computer Equipment"
        assert classified[1].macrs_class == "Office Furniture"
        assert classified[2].macrs_class == "Passenger Automobile"
        
        print("\n✅ ALL TESTS PASSED")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    test_logic()
