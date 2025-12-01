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
    unique_id: Optional[int] = Field(None, description="Unique ID for storage (set by API)")

    # Critical Fields
    asset_id: Optional[str] = Field(None, description="Unique Asset Identifier from client")
    description: str = Field(..., min_length=1, description="Asset Description")
    cost: float = Field(0.0, ge=0, description="Acquisition Cost (0 if unknown)")

    # FA CS Cross-Reference - Maps client's Asset ID to FA CS numeric Asset #
    # FA CS requires numeric-only Asset #, but clients may use alphanumeric IDs
    # This field allows CPA to specify the exact FA CS number to use
    fa_cs_asset_number: Optional[int] = Field(
        None,
        ge=1,  # FA CS requires positive asset numbers
        description="FA CS Asset # (numeric, >= 1). If not set, auto-generated from asset_id or row_index"
    )

    # Dates (all optional - some assets may not have dates)
    acquisition_date: Optional[date] = Field(None, description="Date Acquired")
    in_service_date: Optional[date] = Field(None, description="Date Placed in Service")

    # Classification (AI Predicted)
    macrs_class: Optional[str] = None
    macrs_life: Optional[float] = None
    macrs_method: Optional[str] = None
    macrs_convention: Optional[str] = None

    # FA CS Wizard Category - exact dropdown text for FA CS Add Asset wizard
    # This is what users select in FA CS; the software auto-fills method/life
    fa_cs_wizard_category: Optional[str] = None

    # Flags
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    is_qualified_improvement: bool = False
    is_bonus_eligible: bool = False

    # Depreciation Election - CPA decision for tax treatment
    # This is what gets sent to FA CS and affects Year 1 depreciation
    depreciation_election: Optional[str] = Field(
        "MACRS",
        description="Depreciation election: MACRS, Section179, Bonus, DeMinimis, ADS"
    )
    election_reason: Optional[str] = Field(
        None,
        description="Reason for election (auto-suggested or user-specified)"
    )

    # Source tracking (for multi-sheet support)
    source_sheet: Optional[str] = Field(None, description="Source Excel sheet name")
    transaction_type: Optional[str] = Field("addition", description="Transaction type: addition, disposal, transfer, existing")
    classification_reason: Optional[str] = Field(None, description="Reason for transaction type classification")

    # Disposal fields (for disposed assets)
    disposal_date: Optional[date] = Field(None, description="Date asset was disposed/sold")
    proceeds: Optional[float] = Field(None, description="Sale proceeds from disposal")
    sale_price: Optional[float] = Field(None, description="Alias for proceeds")
    accumulated_depreciation: Optional[float] = Field(None, description="Accumulated depreciation at disposal")
    is_disposed: bool = Field(False, description="Flag indicating asset is disposed")

    # Transfer fields (for transferred assets)
    from_location: Optional[str] = Field(None, description="Original location/department")
    to_location: Optional[str] = Field(None, description="New location/department")
    transfer_date: Optional[date] = Field(None, description="Date of transfer")
    is_transfer: bool = Field(False, description="Flag indicating asset is a transfer")

    # Audit Trail
    audit_trail: List['AuditEvent'] = Field(default_factory=list)

    # Validation Errors and Warnings (For UI Display - advisory only)
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)

    @validator('acquisition_date', 'in_service_date', 'disposal_date', 'transfer_date', pre=True)
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
        except (ValueError, TypeError, Exception):
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

    def check_validity(self, tax_year: int = None):
        """
        Runs business rules and populates validation_errors and validation_warnings.
        Call this after creating the object.

        Errors = Critical issues that BLOCK export (must fix)
        Warnings = Non-critical issues (informational, don't block export)

        Args:
            tax_year: Optional tax year for date validation. If provided, validates
                     that asset dates are consistent with the tax year.
        """
        self.validation_errors = []
        self.validation_warnings = []

        # === CRITICAL ERRORS (Block Export) ===

        # 1. Cost Validation - Must have valid cost (except for Transfers)
        # Transfers don't require cost as they're just moving assets between locations/departments
        # Check for all transfer types: "Transfer", "Current Year Transfer", "Prior Year Transfer"
        is_transfer = self.transaction_type and "transfer" in self.transaction_type.lower()
        if self.cost <= 0 and not is_transfer:
            self.validation_errors.append("Cost must be positive.")

        # 2. Description Validation - Must have meaningful description
        if len(self.description) < 3:
            self.validation_errors.append("Description is too short.")

        # 3. Classification Validation - Must be classified (not Unclassified or None)
        # Transfers don't require classification - they reference existing assets
        if not is_transfer:
            if not self.macrs_class or self.macrs_class in ["Unclassified", "Unknown", ""]:
                self.validation_errors.append("Asset not classified - needs MACRS class.")

        # 4. Method Validation (only if method is set and invalid)
        valid_methods = ["200DB", "150DB", "SL", "ADS", "Unknown", None, ""]
        if self.macrs_method and self.macrs_method not in valid_methods:
            self.validation_errors.append(f"Invalid Method: {self.macrs_method}")

        # 5. Tax Year Date Validation - Asset date must not be after tax year end
        # This is a CRITICAL ERROR because you can't report future assets
        if tax_year:
            effective_date = self.in_service_date or self.acquisition_date
            if effective_date:
                if effective_date.year > tax_year:
                    self.validation_errors.append(
                        f"In-service date {effective_date} is after tax year {tax_year}. "
                        f"Cannot include future assets in {tax_year} return."
                    )

        # === WARNINGS (Informational, Don't Block Export) ===

        # 6. Date Validation - Missing date is a warning, not an error
        if not self.acquisition_date and not self.in_service_date:
            self.validation_warnings.append("No acquisition or in-service date provided.")
        elif self.acquisition_date and self.acquisition_date > date.today():
            self.validation_warnings.append(f"Acquisition Date {self.acquisition_date} is in the future.")

        # 7. Low Confidence Warning
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
