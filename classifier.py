from typing import List, Dict
from models.asset import Asset
from backend.logic import macrs_classification

class ClassifierService:
    """
    Service to classify assets into MACRS categories using the advanced rule engine.
    """
    
    def classify_asset(self, asset: Asset) -> Asset:
        """
        Predicts MACRS classification for a single asset.
        """
        # Convert Asset model to dict for the logic engine
        asset_dict = {
            "description": asset.description,
            "cost": asset.cost,
            "client_category": getattr(asset, "client_category", ""), # If we add this field later
            "asset_id": asset.asset_id
        }
        
        # Use the advanced classification logic
        # Note: classify_assets_batch is more efficient even for single items if we want consistent logic
        # But for single item, we can use _try_fast_classification or fallback
        
        # Let's use the batch logic for consistency as it handles everything
        results = macrs_classification.classify_assets_batch([asset_dict], batch_size=1)
        
        if results:
            result = results[0]
            self._apply_classification(asset, result)
            
        return asset

    def classify_batch(self, assets: List[Asset]) -> List[Asset]:
        """Classifies a list of assets."""
        if not assets:
            return []
            
        # Convert to dicts
        asset_dicts = []
        for asset in assets:
            asset_dicts.append({
                "description": asset.description,
                "cost": asset.cost,
                "client_category": getattr(asset, "client_category", ""),
                "asset_id": asset.asset_id
            })
            
        # Run batch classification
        results = macrs_classification.classify_assets_batch(asset_dicts)
        
        # Apply results back to Asset objects
        for asset, result in zip(assets, results):
            self._apply_classification(asset, result)
            
        return assets

    def _apply_classification(self, asset: Asset, result: Dict):
        """Applies classification result to Asset object."""
        asset.macrs_class = result.get("final_class", "Unclassified")
        asset.macrs_life = result.get("final_life")
        asset.macrs_method = result.get("final_method")
        asset.macrs_convention = result.get("final_convention")
        asset.is_bonus_eligible = result.get("bonus", False)
        asset.is_qualified_improvement = result.get("qip", False)
        asset.confidence_score = result.get("confidence", 0.0)
        # We could store reasoning/notes if the Asset model supported it

