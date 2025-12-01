"""
Fixed Asset AI - FA CS Wizard Category Mappings

Maps asset classifications to exact FA CS wizard dropdown text
for RPA automation compatibility.

Author: Fixed Asset AI Team
"""

from __future__ import annotations

from typing import Optional


# ==============================================================================
# FA CS WIZARD DROPDOWN TEXT MAPPINGS
# ==============================================================================

# Exact text that appears in FA CS Add Asset Wizard dropdown
# CRITICAL: Must match exactly for UiPath RPA to select correctly

FA_CS_WIZARD_5_YEAR = {
    "computer": "Computer, monitor, laptop, PDA, other computer related, property used in research",
    "automobile": "Automobile - passenger (used over 50% for business)",
    "auto": "Automobile - passenger (used over 50% for business)",
    "car": "Automobile - passenger (used over 50% for business)",
    "vehicle": "Automobile - passenger (used over 50% for business)",
    "truck": "Light truck or van (actual weight under 13,000 lbs)",
    "van": "Light truck or van (actual weight under 13,000 lbs)",
    "suv": "Light truck or van (actual weight under 13,000 lbs)",
    "appliance": "Appliance - large (refrigerator, stove, washer, dryer, etc.)",
    "refrigerator": "Appliance - large (refrigerator, stove, washer, dryer, etc.)",
    "copier": "Calculator, copier, fax, noncomputer office machine, typewriter",
    "calculator": "Calculator, copier, fax, noncomputer office machine, typewriter",
    "fax": "Calculator, copier, fax, noncomputer office machine, typewriter",
    "typewriter": "Calculator, copier, fax, noncomputer office machine, typewriter",
}

FA_CS_WIZARD_7_YEAR = {
    "furniture": "Furniture and fixtures - office",
    "office furniture": "Furniture and fixtures - office",
    "desk": "Furniture and fixtures - office",
    "chair": "Furniture and fixtures - office",
    "cabinet": "Furniture and fixtures - office",
    "shelving": "Furniture and fixtures - office",
    "machinery": "Machinery and equipment - manufacturing",
    "equipment": "Machinery and equipment - manufacturing",
    "tools": "Machinery and equipment - manufacturing",
    # NOTE: HVAC removed - it is 15-year building equipment, not 7-year
    "generator": "Machinery and equipment - manufacturing",
}

FA_CS_WIZARD_15_YEAR = {
    "land improvement": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
    "sidewalk": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
    "parking lot": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
    "fence": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
    "landscaping": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
    "driveway": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
    "qip": "Qualified improvement property (QIP) - 15 year",
    "qualified improvement": "Qualified improvement property (QIP) - 15 year",
    "leasehold improvement": "Qualified improvement property (QIP) - 15 year",
    "tenant improvement": "Qualified improvement property (QIP) - 15 year",
    "build out": "Qualified improvement property (QIP) - 15 year",
    "buildout": "Qualified improvement property (QIP) - 15 year",
    # Building equipment - 15-year per Pub 946
    "hvac": "Land improvement (sidewalk, road, bridge, fence, landscaping)",  # FA CS maps HVAC to land improvement category
    "air conditioning": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
    "heating system": "Land improvement (sidewalk, road, bridge, fence, landscaping)",
}

FA_CS_WIZARD_27_5_YEAR = {
    "residential": "Residential rental property (27.5 year)",
    "rental": "Residential rental property (27.5 year)",
    "apartment": "Residential rental property (27.5 year)",
    "duplex": "Residential rental property (27.5 year)",
    "rental house": "Residential rental property (27.5 year)",
}

FA_CS_WIZARD_39_YEAR = {
    "building": "Nonresidential real property (39 year)",
    "nonresidential": "Nonresidential real property (39 year)",
    "commercial": "Nonresidential real property (39 year)",
    "office building": "Nonresidential real property (39 year)",
    "warehouse": "Nonresidential real property (39 year)",
    "retail": "Nonresidential real property (39 year)",
    "industrial": "Nonresidential real property (39 year)",
}

FA_CS_WIZARD_NON_DEPRECIABLE = {
    "land": "Land (non-depreciable)",
    "lot": "Land (non-depreciable)",
    "parcel": "Land (non-depreciable)",
}

FA_CS_WIZARD_INTANGIBLE = {
    "intangible": "Intangible asset - Section 197 (15 year amortization)",
    "goodwill": "Intangible asset - Section 197 (15 year amortization)",
    "patent": "Intangible asset - Section 197 (15 year amortization)",
    "trademark": "Intangible asset - Section 197 (15 year amortization)",
    "customer list": "Intangible asset - Section 197 (15 year amortization)",
    "covenant": "Intangible asset - Section 197 (15 year amortization)",
    "franchise": "Intangible asset - Section 197 (15 year amortization)",
    "license": "Intangible asset - Section 197 (15 year amortization)",
}


def _get_fa_cs_wizard_category(row) -> str:
    """
    Get FA CS wizard dropdown text for asset classification.

    Maps our classification to the exact text in FA CS Add Asset Wizard
    dropdown for UiPath RPA automation.

    Args:
        row: DataFrame row with asset data

    Returns:
        Exact FA CS wizard dropdown text, or empty string for disposals/transfers
    """
    from .fa_export_validation import _is_disposal, _is_transfer

    # Skip disposals and transfers
    if _is_disposal(row) or _is_transfer(row):
        return ""

    category = str(row.get("Final Category", "")).lower()
    description = str(row.get("Description", "")).lower()
    life = row.get("Tax Life") or row.get("Recovery Period") or row.get("MACRS Life")

    combined = f"{category} {description}"

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

    # Check category keywords for non-standard lives
    for keyword, wizard_text in FA_CS_WIZARD_NON_DEPRECIABLE.items():
        if keyword in combined:
            return wizard_text

    for keyword, wizard_text in FA_CS_WIZARD_INTANGIBLE.items():
        if keyword in combined:
            return wizard_text

    # Default based on category analysis
    if "vehicle" in combined or "auto" in combined:
        return "Automobile - passenger (used over 50% for business)"
    if "computer" in combined:
        return "Computer, monitor, laptop, PDA, other computer related, property used in research"
    if "furniture" in combined:
        return "Furniture and fixtures - office"
    if "equipment" in combined or "machinery" in combined:
        return "Machinery and equipment - manufacturing"

    # Ultimate fallback
    return "Machinery and equipment - manufacturing"


def get_all_wizard_categories() -> list:
    """
    Get list of all available FA CS wizard categories.

    Returns:
        List of wizard category strings
    """
    categories = set()

    for mapping in [
        FA_CS_WIZARD_5_YEAR,
        FA_CS_WIZARD_7_YEAR,
        FA_CS_WIZARD_15_YEAR,
        FA_CS_WIZARD_27_5_YEAR,
        FA_CS_WIZARD_39_YEAR,
        FA_CS_WIZARD_NON_DEPRECIABLE,
        FA_CS_WIZARD_INTANGIBLE,
    ]:
        categories.update(mapping.values())

    return sorted(list(categories))


def get_wizard_category_by_life(life: float) -> Optional[str]:
    """
    Get default wizard category for a given recovery period.

    Args:
        life: MACRS recovery period in years

    Returns:
        Default wizard category string or None
    """
    life_mapping = {
        5: "Computer, monitor, laptop, PDA, other computer related, property used in research",
        7: "Furniture and fixtures - office",
        15: "Land improvement (sidewalk, road, bridge, fence, landscaping)",
        27.5: "Residential rental property (27.5 year)",
        39: "Nonresidential real property (39 year)",
    }

    # Check for close match (handle floating point)
    for period, category in life_mapping.items():
        if abs(float(life) - period) < 0.1:
            return category

    return None
