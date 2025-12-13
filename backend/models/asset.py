from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime

class Asset(BaseModel):
    """
    Represents a single account/asset for Form 5471 processing.

    Supports both Trial Balance accounts (for Form 5471) and Fixed Assets.
    The validation rules are advisory - they flag issues but don't prevent processing.
    """
    row_index: int = Field(..., description="Original row number in Excel")
    unique_id: Optional[int] = Field(None, description="Unique ID for storage (set by API)")

    # ==========================================================================
    # FORM 5471 FIELDS - Primary fields for Trial Balance → 5471 mapping
    # ==========================================================================

    # Account identification
    account_number: Optional[str] = Field(None, description="GL Account Number (e.g., 121001)")
    description: str = Field(..., min_length=1, description="Account/Asset Description")

    # Form 5471 Schedule mapping
    schedule: Optional[str] = Field(None, description="Form 5471 Schedule (Sch C, Sch E, Sch F)")
    line: Optional[str] = Field(None, description="Schedule line number (e.g., 1, 2a, 14)")
    line_description: Optional[str] = Field(None, description="IRS line description")
    account_type: Optional[str] = Field(None, description="Account type: asset, liability, equity, income, expense")

    # Balances (for Trial Balance)
    balance: float = Field(0.0, description="Account balance (ending balance)")
    usd_amount: float = Field(0.0, description="USD equivalent amount")
    debit: Optional[float] = Field(None, description="Debit amount")
    credit: Optional[float] = Field(None, description="Credit amount")
    beginning_balance: Optional[float] = Field(None, description="Beginning balance")

    # Classification confidence
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    classification_reason: Optional[str] = Field(None, description="Reason for 5471 classification")

    # Multi-entity support
    entity: Optional[str] = Field(None, description="CFC Entity name/code for multi-entity TB files")
    currency: Optional[str] = Field(None, description="Currency code (e.g., USD, CLP, EUR)")

    # ==========================================================================
    # LEGACY FIXED ASSET FIELDS - Kept for backward compatibility
    # ==========================================================================

    # Legacy asset ID field (maps to account_number for TB)
    asset_id: Optional[str] = Field(None, description="Legacy: Asset ID (use account_number for TB)")
    cost: float = Field(0.0, ge=0, description="Legacy: Acquisition Cost (use balance for TB)")

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
    net_book_value: Optional[float] = Field(None, description="Net book value (Cost - Accumulated Depreciation)")
    gain_loss: Optional[float] = Field(None, description="Gain/Loss on disposal (positive=gain, negative=loss)")
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

    # Description Quality Flags - For identifying vague/vendor-only descriptions
    requires_manual_entry: bool = Field(
        False,
        description="True if description is too vague for automated classification (e.g., 'Amazon', 'Lamprecht')"
    )
    quality_issues: List[str] = Field(
        default_factory=list,
        description="List of description quality issues (e.g., 'vendor name only', 'incomplete description')"
    )

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

    @validator('cost', 'balance', 'usd_amount', pre=True)
    def validate_numeric_fields(cls, v):
        if v is None:
            return 0.0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    def check_validity(self, tax_year: int = None, mode: str = "5471"):
        """
        Runs business rules and populates validation_errors and validation_warnings.
        Call this after creating the object.

        Errors = Critical issues that BLOCK export (must fix)
        Warnings = Non-critical issues (informational, don't block export)

        Args:
            tax_year: Optional tax year for date validation.
            mode: "5471" for Form 5471/Trial Balance mode, "fa" for legacy Fixed Asset mode
        """
        self.validation_errors = []
        self.validation_warnings = []

        if mode == "5471":
            # === FORM 5471 VALIDATION ===

            # 1. Description Validation - Must have meaningful description
            if len(self.description) < 2:
                self.validation_errors.append("Account description is too short.")

            # 2. Schedule/Line Classification - Must be mapped to a 5471 schedule
            if not self.schedule or self.schedule in ["Unknown", ""]:
                self.validation_errors.append("Account not mapped to Form 5471 schedule.")

            # 3. Line number validation
            if self.schedule and self.schedule != "Unknown" and not self.line:
                self.validation_warnings.append("Schedule assigned but no line number specified.")

            # 4. Low Confidence Warning
            if self.confidence_score < 0.4:
                self.validation_warnings.append(
                    f"Low confidence ({self.confidence_score:.0%}) - review schedule/line mapping."
                )
            elif self.confidence_score < 0.7:
                self.validation_warnings.append(
                    f"Medium confidence ({self.confidence_score:.0%}) - verify mapping is correct."
                )

            # 5. Zero balance warning (might be intentional)
            if self.balance == 0 and self.usd_amount == 0:
                self.validation_warnings.append("Account has zero balance.")

        else:
            # === LEGACY FIXED ASSET VALIDATION ===

            # 1. Cost Validation - Must have valid cost (except for Transfers)
            trans_type_str = str(self.transaction_type).lower() if self.transaction_type and isinstance(self.transaction_type, str) else ""
            is_transfer = "transfer" in trans_type_str
            if self.cost <= 0 and not is_transfer:
                self.validation_errors.append("Cost must be positive.")

            # 2. Description Validation - Must have meaningful description
            if len(self.description) < 3:
                self.validation_errors.append("Description is too short.")

            # 3. Classification Validation - Must be classified (not Unclassified or None)
            if not is_transfer:
                if not self.macrs_class or self.macrs_class in ["Unclassified", "Unknown", ""]:
                    self.validation_errors.append("Asset not classified - needs MACRS class.")

            # 4. Method Validation (only if method is set and invalid)
            valid_methods = ["200DB", "150DB", "SL", "ADS", "Unknown", None, ""]
            if self.macrs_method and self.macrs_method not in valid_methods:
                self.validation_errors.append(f"Invalid Method: {self.macrs_method}")

            # 5. Tax Year Date Validation
            if tax_year:
                effective_date = self.in_service_date or self.acquisition_date
                if effective_date:
                    if effective_date.year > tax_year:
                        self.validation_errors.append(
                            f"In-service date {effective_date} is after tax year {tax_year}."
                        )

            # 6. Date Validation - Missing date is a warning
            if not self.acquisition_date and not self.in_service_date:
                self.validation_warnings.append("No acquisition or in-service date provided.")

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
