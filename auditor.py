from datetime import datetime
from typing import Optional
from models.asset import Asset, AuditEvent
from backend.logic import macrs_classification

class AuditorService:
    """
    Service to log changes to assets for CPA review.
    """

    def log_override(self, asset: Asset, field: str, old_val: str, new_val: str, user: str = "CPA User", reason: str = "") -> Asset:
        """
        Logs a manual override of an asset field.
        """
        event = AuditEvent(
            timestamp=datetime.now(),
            user=user,
            action="override",
            field=field,
            old_value=str(old_val),
            new_value=str(new_val),
            reason=reason
        )
        asset.audit_trail.append(event)
        
        # Persist override to the logic engine so it learns
        # We construct a classification dict with the new values
        # Note: This assumes we are overriding the main classification fields
        # If we are just changing one field, we should probably get the current state
        if field in ["macrs_class", "macrs_life", "macrs_method", "macrs_convention", "is_bonus_eligible", "is_qualified_improvement"]:
            classification = {
                "class": asset.macrs_class,
                "life": asset.macrs_life,
                "method": asset.macrs_method,
                "convention": asset.macrs_convention,
                "bonus": asset.is_bonus_eligible,
                "qip": asset.is_qualified_improvement
            }
            # Update the specific field in the classification dict
            # (Actually asset object is already updated by the caller usually, but let's be safe)
            
            macrs_classification.add_override(
                asset_id=asset.asset_id,
                classification=classification,
                reason=reason,
                user=user
            )
            
        return asset

    def log_approval(self, asset: Asset, user: str = "CPA User") -> Asset:
        """
        Logs the approval of an asset.
        """
        event = AuditEvent(
            timestamp=datetime.now(),
            user=user,
            action="approve",
            reason="User confirmed classification"
        )
        asset.audit_trail.append(event)
        return asset
