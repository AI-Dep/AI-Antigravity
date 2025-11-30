from typing import List, Dict, Optional
from datetime import date
from backend.models.asset import Asset
from backend.logic import macrs_classification
from backend.logic import transaction_classifier
from backend.logic.fa_cs_mappings import (
    FA_CS_WIZARD_5_YEAR,
    FA_CS_WIZARD_7_YEAR,
    FA_CS_WIZARD_15_YEAR,
    FA_CS_WIZARD_27_5_YEAR,
    FA_CS_WIZARD_39_YEAR,
    FA_CS_WIZARD_NON_DEPRECIABLE,
    FA_CS_WIZARD_INTANGIBLE,
)


class ClassifierService:
    """
    Service to classify assets into MACRS categories using the advanced rule engine.
    Also handles transaction type classification (addition vs existing vs disposal vs transfer).
    """

    def __init__(self):
        self.tax_year: int = date.today().year  # Default to current year

    def set_tax_year(self, year: int):
        """Set the tax year for transaction classification."""
        self.tax_year = year

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

    def classify_batch(self, assets: List[Asset], tax_year: Optional[int] = None) -> List[Asset]:
        """
        Classifies a list of assets for both MACRS categories AND transaction types.

        Args:
            assets: List of Asset objects
            tax_year: Tax year for transaction classification (defaults to self.tax_year)

        Returns:
            List of classified Asset objects
        """
        if not assets:
            return []

        # Use provided tax_year or fall back to instance default
        effective_tax_year = tax_year or self.tax_year

        # Convert to dicts for MACRS classification
        asset_dicts = []
        for asset in assets:
            asset_dicts.append({
                "description": asset.description,
                "cost": asset.cost,
                "client_category": getattr(asset, "client_category", ""),
                "asset_id": asset.asset_id
            })

        # Run batch MACRS classification
        results = macrs_classification.classify_assets_batch(asset_dicts)

        # Apply MACRS results back to Asset objects
        for asset, result in zip(assets, results):
            self._apply_classification(asset, result)

        # Run transaction type classification
        self._classify_transaction_types(assets, effective_tax_year)

        return assets

    def _classify_transaction_types(self, assets: List[Asset], tax_year: int):
        """
        Classify transaction types (addition vs existing vs disposal vs transfer).

        CRITICAL: This ensures proper tax treatment:
        - Current Year Additions: Eligible for Section 179 and Bonus depreciation
        - Existing Assets: NOT eligible for Section 179/Bonus (only regular MACRS)
        - Disposals: Need gain/loss calculation
        - Transfers: Location/department change only
        """
        import pandas as pd

        for asset in assets:
            # Build row dict for transaction classifier
            row_dict = {
                "Transaction Type": asset.transaction_type or "",
                "Sheet Role": asset.source_sheet or "",
                "In Service Date": asset.in_service_date,
                "Acquisition Date": asset.acquisition_date,
                "Disposal Date": None,  # Asset model doesn't have this yet
                "Description": asset.description,
            }
            row = pd.Series(row_dict)

            # Classify transaction type (returns type, reason, confidence)
            trans_type, reason, trans_confidence = transaction_classifier.classify_transaction_type(
                row, tax_year, verbose=False
            )

            # Update asset with proper transaction type
            asset.transaction_type = trans_type
            asset.classification_reason = reason

            # CRITICAL: Adjust bonus eligibility based on transaction type
            # Section 179 and Bonus are ONLY for current year additions
            if trans_type != "Current Year Addition":
                asset.is_bonus_eligible = False

            # If transaction type has low confidence, add a warning
            if trans_confidence < 0.80:
                if not hasattr(asset, 'validation_warnings') or asset.validation_warnings is None:
                    asset.validation_warnings = []
                asset.validation_warnings.append(
                    f"Low confidence ({trans_confidence:.0%}) for transaction type '{trans_type}' - manual review recommended"
                )

        return assets

    def _apply_classification(self, asset: Asset, result: Dict):
        """Applies classification result to Asset object and runs validation."""
        asset.macrs_class = result.get("final_class", "Unclassified")
        asset.macrs_life = result.get("final_life")
        asset.macrs_method = result.get("final_method")
        asset.macrs_convention = result.get("final_convention")
        asset.is_bonus_eligible = result.get("bonus", False)
        asset.is_qualified_improvement = result.get("qip", False)
        asset.confidence_score = result.get("confidence", 0.0)

        # Set FA CS Wizard Category for UI display
        # This is the exact dropdown text users select in FA CS Add Asset wizard
        asset.fa_cs_wizard_category = self._get_wizard_category(
            asset.description,
            asset.macrs_class,
            asset.macrs_life
        )

        # Run validation AFTER classification is applied
        # This ensures we can check if the asset was successfully classified
        asset.check_validity()

    def _get_wizard_category(self, description: str, macrs_class: str, life: float) -> str:
        """
        Get FA CS wizard dropdown text for an asset.

        Maps classification to the exact text that appears in FA CS Add Asset Wizard
        dropdown. This is what users click to set up the asset in FA CS.

        Args:
            description: Asset description
            macrs_class: MACRS classification (e.g., "Computer Equipment")
            life: Recovery period in years (5, 7, 15, etc.)

        Returns:
            Exact FA CS wizard dropdown text
        """
        combined = f"{macrs_class or ''} {description or ''}".lower()

        # Try life-based mapping first for precision
        try:
            life_float = float(life) if life else 0
        except (ValueError, TypeError):
            life_float = 0

        # Check by recovery period
        if life_float == 5 or abs(life_float - 5) < 0.1:
            # 5-year property
            for keyword, wizard_text in FA_CS_WIZARD_5_YEAR.items():
                if keyword in combined:
                    return wizard_text
            # Default 5-year
            return "Computer, monitor, laptop, PDA, other computer related, property used in research"

        elif life_float == 7 or abs(life_float - 7) < 0.1:
            # 7-year property
            for keyword, wizard_text in FA_CS_WIZARD_7_YEAR.items():
                if keyword in combined:
                    return wizard_text
            # Default 7-year
            return "Furniture and fixtures - office"

        elif life_float == 15 or abs(life_float - 15) < 0.1:
            # 15-year property
            for keyword, wizard_text in FA_CS_WIZARD_15_YEAR.items():
                if keyword in combined:
                    return wizard_text
            # Default 15-year
            return "Land improvement (sidewalk, road, bridge, fence, landscaping)"

        elif life_float == 27.5 or abs(life_float - 27.5) < 0.1:
            # 27.5-year residential
            return "Residential rental property (27.5 year)"

        elif life_float == 39 or abs(life_float - 39) < 0.1:
            # 39-year nonresidential
            return "Nonresidential real property (39 year)"

        elif life_float == 3 or abs(life_float - 3) < 0.1:
            # 3-year property (software)
            return "Software - off the shelf"

        # Check category keywords for non-standard lives
        for keyword, wizard_text in FA_CS_WIZARD_NON_DEPRECIABLE.items():
            if keyword in combined:
                return wizard_text

        for keyword, wizard_text in FA_CS_WIZARD_INTANGIBLE.items():
            if keyword in combined:
                return wizard_text

        # Default based on category analysis
        if "vehicle" in combined or "auto" in combined or "car" in combined:
            return "Automobile - passenger (used over 50% for business)"
        if "computer" in combined or "laptop" in combined or "server" in combined:
            return "Computer, monitor, laptop, PDA, other computer related, property used in research"
        if "furniture" in combined or "desk" in combined or "chair" in combined:
            return "Furniture and fixtures - office"
        if "equipment" in combined or "machinery" in combined:
            return "Machinery and equipment - manufacturing"

        # Ultimate fallback
        return "Machinery and equipment - manufacturing"

