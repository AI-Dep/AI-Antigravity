from typing import List, Dict, Optional
from datetime import date
from backend.models.asset import Asset
from backend.logic import macrs_classification
from backend.logic import transaction_classifier
from backend.logic import tax_year_config
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
            self._apply_classification(asset, result, tax_year=effective_tax_year)

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
                "Disposal Date": asset.disposal_date,  # Pass actual disposal date for prior/current year check
                "Transfer Date": asset.transfer_date,  # Pass actual transfer date for prior/current year check
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

            # Suggest depreciation election for CY additions
            if trans_type == "Current Year Addition":
                self._suggest_depreciation_election(asset, tax_year)

            # IMPORTANT: Override confidence score for disposals and transfers
            # For these transaction types, MACRS classification confidence is not meaningful
            # Instead, use data completeness as the confidence metric
            if "Disposal" in trans_type:
                asset.confidence_score = self._calculate_disposal_confidence(asset)
            elif "Transfer" in trans_type:
                asset.confidence_score = self._calculate_transfer_confidence(asset)

        return assets

    def _calculate_disposal_confidence(self, asset: Asset) -> float:
        """
        Calculate confidence for disposal based on data completeness.

        For disposals, CPAs care about having complete data for gain/loss calculation,
        NOT about MACRS classification accuracy (the asset is being removed).

        High confidence (95%): Has disposal date + cost + accumulated depreciation
        Medium confidence (85%): Has disposal date + cost
        Low confidence (70%): Has disposal date only
        Needs review (50%): Missing disposal date
        """
        score = 0.50  # Base score - needs review

        # Disposal date is critical
        if asset.disposal_date:
            score = 0.70

            # Cost is important for gain/loss
            if asset.cost and asset.cost > 0:
                score = 0.85

                # Accumulated depreciation needed for accurate gain/loss
                if asset.accumulated_depreciation is not None:
                    score = 0.95

                # Proceeds present (even if $0) is good
                if asset.proceeds is not None:
                    score = min(0.98, score + 0.03)

        return score

    def _calculate_transfer_confidence(self, asset: Asset) -> float:
        """
        Calculate confidence for transfer based on data completeness.

        For transfers, CPAs care about having complete transfer documentation,
        NOT about MACRS classification (it doesn't change on transfer).

        High confidence (95%): Has transfer date + from/to location info
        Medium confidence (85%): Has transfer date only
        Needs review (60%): Missing transfer date
        """
        score = 0.60  # Base score - needs review

        # Transfer date is critical
        if asset.transfer_date:
            score = 0.85

            # From/To location info makes it complete
            has_from = asset.from_location and str(asset.from_location).strip()
            has_to = asset.to_location and str(asset.to_location).strip()

            if has_from or has_to:
                score = 0.92
            if has_from and has_to:
                score = 0.98

        return score

    def _suggest_depreciation_election(self, asset: Asset, tax_year: int):
        """
        Suggest optimal depreciation election based on asset characteristics.

        De Minimis Safe Harbor: Assets <= $2,500 can be expensed immediately
        Section 179: Up to $1,220,000 (2024) / $2,500,000 (2025 OBBBA) for qualifying property
        Bonus: 80% (2024) / 100% (2025+ OBBBA) of cost for qualifying property
        MACRS: Standard depreciation

        Note: These are SUGGESTIONS only. CPA makes final decision based on client income.
        """
        cost = asset.cost or 0
        de_minimis_threshold = 2500  # IRS de minimis safe harbor for taxpayers with AFS

        # Default to MACRS
        election = "MACRS"
        reason = "Standard MACRS depreciation"

        # Existing assets don't get elections - they continue prior treatment
        if asset.transaction_type != "Current Year Addition":
            asset.depreciation_election = "MACRS"
            asset.election_reason = "Existing asset - continuing prior depreciation"
            return

        # De Minimis Safe Harbor - assets under $2,500
        if 0 < cost <= de_minimis_threshold:
            election = "DeMinimis"
            reason = f"Cost ${cost:,.0f} qualifies for de minimis safe harbor (≤$2,500)"

        # Section 179 candidates - mid-range assets
        elif de_minimis_threshold < cost <= 50000 and asset.is_bonus_eligible:
            election = "Section179"
            reason = f"Cost ${cost:,.0f} - consider Section 179 for immediate deduction"

        # Bonus depreciation candidates - larger qualifying property
        elif asset.is_bonus_eligible:
            # Use centralized tax config for OBBBA/TCJA compliant bonus rates
            bonus_rate = tax_year_config.get_bonus_percentage(tax_year)
            bonus_pct = int(bonus_rate * 100)
            election = "Bonus"
            reason = f"Qualifying property - {bonus_pct}% bonus depreciation available"

        # Real property - no bonus/179
        elif asset.macrs_life and asset.macrs_life >= 27.5:
            election = "MACRS"
            reason = "Real property - standard straight-line MACRS"

        asset.depreciation_election = election
        asset.election_reason = reason

    def _apply_classification(self, asset: Asset, result: Dict, tax_year: int = None):
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
        # Pass tax_year for date validation against tax year
        asset.check_validity(tax_year=tax_year or self.tax_year)

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

