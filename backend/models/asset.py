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
    
    # Classification (AI Predicted)
    macrs_class: Optional[str] = None
    macrs_life: Optional[float] = None
    macrs_method: Optional[str] = None
    macrs_convention: Optional[str] = None
    
    # Flags
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    is_qualified_improvement: bool = False
    is_bonus_eligible: bool = False
    
    # Audit Trail
    audit_trail: List['AuditEvent'] = []
    
    # Validation Errors (For UI Display)
    validation_errors: List[str] = []

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
        Runs business rules and populates validation_errors.
        Call this after creating the object.
        """
        self.validation_errors = []
        
        # 1. Cost Validation
        if self.cost <= 0:
            self.validation_errors.append("Cost must be positive.")
            
        # 2. Date Validation
        if not self.acquisition_date:
            self.validation_errors.append("Missing or invalid Acquisition Date.")
        elif self.acquisition_date > date.today():
            self.validation_errors.append(f"Acquisition Date {self.acquisition_date} is in the future.")
            
        # 3. Description Validation
        if len(self.description) < 3:
            self.validation_errors.append("Description is too short.")
            
        # 4. Method Validation
        valid_methods = ["200DB", "150DB", "SL", "ADS", "Unknown", None]
        if self.macrs_method not in valid_methods:
            self.validation_errors.append(f"Invalid Method: {self.macrs_method}")

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

