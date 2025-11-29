from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime

class Asset(BaseModel):
    """
    Represents a single fixed asset with flexible validation.

    IMPORTANT: Assets should NOT be rejected due to missing cost or dates.
    The validation rules are advisory - they flag issues but don't prevent processing.
    """
    row_index: int = Field(..., description="Original row number in Excel")

    # Critical Fields
    asset_id: Optional[str] = Field(None, description="Unique Asset Identifier")
    description: str = Field(..., min_length=1, description="Asset Description")
    cost: float = Field(0.0, ge=0, description="Acquisition Cost (0 if unknown)")

    # Dates (all optional - some assets may not have dates)
    acquisition_date: Optional[date] = Field(None, description="Date Acquired")
    in_service_date: Optional[date] = Field(None, description="Date Placed in Service")

    # Classification (AI Predicted)
    macrs_class: Optional[str] = None
    macrs_life: Optional[float] = None
    macrs_method: Optional[str] = None
    macrs_convention: Optional[str] = None

    # Flags
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    is_qualified_improvement: bool = False
    is_bonus_eligible: bool = False

    # Source tracking (for multi-sheet support)
    source_sheet: Optional[str] = Field(None, description="Source Excel sheet name")
    transaction_type: Optional[str] = Field("addition", description="Transaction type: addition, disposal, transfer, existing")
    classification_reason: Optional[str] = Field(None, description="Reason for transaction type classification")

    # Audit Trail
    audit_trail: List['AuditEvent'] = []

    # Validation Errors and Warnings (For UI Display - advisory only)
    validation_errors: List[str] = []
    validation_warnings: List[str] = []

    @validator('acquisition_date', 'in_service_date', pre=True)
    def parse_date(cls, v):
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            # Try multiple date formats
            formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']
            for fmt in formats:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
            return None
        # Try pandas Timestamp
        try:
            import pandas as pd
            if pd.notna(v):
                return pd.to_datetime(v).date()
        except:
            pass
        return None

    @validator('cost', pre=True)
    def validate_cost_type(cls, v):
        if v is None:
            return 0.0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    def check_validity(self):
        """
        Runs business rules and populates validation_errors and validation_warnings.
        Call this after creating the object.

        Errors = Critical issues that BLOCK export (must fix)
        Warnings = Non-critical issues (informational, don't block export)
        """
        self.validation_errors = []
        self.validation_warnings = []

        # === CRITICAL ERRORS (Block Export) ===

        # 1. Cost Validation - Must have valid cost
        if self.cost <= 0:
            self.validation_errors.append("Cost must be positive.")

        # 2. Description Validation - Must have meaningful description
        if len(self.description) < 3:
            self.validation_errors.append("Description is too short.")

        # 3. Classification Validation - Must be classified (not Unclassified or None)
        if not self.macrs_class or self.macrs_class in ["Unclassified", "Unknown", ""]:
            self.validation_errors.append("Asset not classified - needs MACRS class.")

        # 4. Method Validation (only if method is set and invalid)
        valid_methods = ["200DB", "150DB", "SL", "ADS", "Unknown", None, ""]
        if self.macrs_method and self.macrs_method not in valid_methods:
            self.validation_errors.append(f"Invalid Method: {self.macrs_method}")

        # === WARNINGS (Informational, Don't Block Export) ===

        # 5. Date Validation - Missing date is a warning, not an error
        if not self.acquisition_date and not self.in_service_date:
            self.validation_warnings.append("No acquisition or in-service date provided.")
        elif self.acquisition_date and self.acquisition_date > date.today():
            self.validation_warnings.append(f"Acquisition Date {self.acquisition_date} is in the future.")

        # 6. Low Confidence Warning
        if self.confidence_score < 0.8 and self.macrs_class and self.macrs_class not in ["Unclassified", ""]:
            self.validation_warnings.append(f"Low confidence ({self.confidence_score:.0%}) - consider manual review.")

class AuditEvent(BaseModel):
    timestamp: datetime
    user: str
    action: str  # "override", "approve"
    field: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: Optional[str] = None

# Update Asset to include audit trail
Asset.update_forward_refs()
