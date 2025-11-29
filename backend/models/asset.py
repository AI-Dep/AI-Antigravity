from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime

class Asset(BaseModel):
    """
    Represents a single fixed asset with strict validation.
    """
    row_index: int = Field(..., description="Original row number in Excel")
    
    # Critical Fields
    asset_id: Optional[str] = Field(None, description="Unique Asset Identifier")
    description: str = Field(..., min_length=2, description="Asset Description")
    cost: float = Field(..., gt=0, description="Acquisition Cost")
    
    # Dates
    acquisition_date: Optional[date] = Field(None, description="Date Acquired")
    in_service_date: Optional[date] = Field(None, description="Date Placed in Service")
    
    # Tax Depreciation (Federal MACRS)
    macrs_class: Optional[str] = None
    macrs_life: Optional[float] = None
    macrs_method: Optional[str] = None  # 200DB, 150DB, SL, ADS
    macrs_convention: Optional[str] = None  # HY, MQ, MM

    # Book Depreciation (GAAP/Financial)
    book_life: Optional[float] = None
    book_method: Optional[str] = None  # SL, DB, etc.
    book_convention: Optional[str] = None

    # State Depreciation (may differ from federal)
    state_life: Optional[float] = None
    state_method: Optional[str] = None
    state_convention: Optional[str] = None
    state_bonus_allowed: bool = True  # Some states don't allow bonus

    # Flags
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    is_qualified_improvement: bool = False
    is_bonus_eligible: bool = False
    
    # Audit Trail
    audit_trail: List['AuditEvent'] = []
    
    # Validation Errors and Warnings (For UI Display)
    validation_errors: List[str] = []  # Critical issues that block export
    validation_warnings: List[str] = []  # Non-critical issues (info only)

    @validator('acquisition_date', pre=True)
    def parse_date(cls, v):
        if isinstance(v, str):
            try:
                return datetime.strptime(v, '%Y-%m-%d').date()
            except ValueError:
                return None 
        return v

    @validator('cost')
    def validate_cost_type(cls, v):
        return v

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

