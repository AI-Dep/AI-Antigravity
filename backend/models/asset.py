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
    transaction_type: Optional[str] = Field("addition", description="Transaction type: addition, disposal, transfer")

    # Audit Trail
    audit_trail: List['AuditEvent'] = []

    # Validation Errors (For UI Display - advisory only)
    validation_errors: List[str] = []

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
        Runs business rules and populates validation_errors.
        Call this after creating the object.

        IMPORTANT: These are ADVISORY warnings, not rejection criteria.
        Assets should still be processed even with validation errors.
        """
        self.validation_errors = []

        # 1. Cost Validation (advisory - cost of 0 is allowed but flagged)
        if self.cost <= 0:
            self.validation_errors.append("Cost is missing or zero - needs review.")

        # 2. Date Validation (advisory - missing dates are allowed but flagged)
        if not self.acquisition_date and not self.in_service_date:
            self.validation_errors.append("Missing date information - needs review.")
        elif self.acquisition_date and self.acquisition_date > date.today():
            self.validation_errors.append(f"Acquisition Date {self.acquisition_date} is in the future.")
        elif self.in_service_date and self.in_service_date > date.today():
            self.validation_errors.append(f"In-Service Date {self.in_service_date} is in the future.")

        # 3. Description Validation
        if len(self.description) < 3:
            self.validation_errors.append("Description is very short - may need review.")

        # 4. Method Validation
        valid_methods = ["200DB", "150DB", "SL", "ADS", "Unknown", None, ""]
        if self.macrs_method and self.macrs_method not in valid_methods:
            # Don't reject - just flag for review
            pass  # Allow any method, classification will handle it

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

