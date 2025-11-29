import pandas as pd
from datetime import datetime

def detect_transaction(row, year: int) -> str:
    desc = str(row["Description"]).lower()
    raw = str(row["Raw Txn Label"]).lower()
    role = row["Sheet Role"]

    disp = row.get("Disposal Date")
    proceeds = row.get("Proceeds")
    gl = row.get("Book Gain/Loss")
    pis = row.get("PIS Date")
    acq = row.get("Acquisition Date")

    # Disposal
    if pd.notna(disp) or pd.notna(proceeds) or pd.notna(gl):
        return "Disposal"

    # Transfer
    if role == "transfers":
        return "Transfer"
    if any(k in desc for k in ["transfer","xfer","reclass"]):
        return "Transfer"
    if any(k in raw for k in ["transfer","xfer","reclass"]):
        return "Transfer"

    # Addition
    pis_final = pis or acq
    if pis_final is not None:
        try:
            if pd.to_datetime(pis_final).year == year:
                return "Addition"
        except (ValueError, TypeError, AttributeError):
            # Date parsing failed - continue with keyword-based detection
            pass

    # NOTE: Changed "add" to "addition" and "new" to "new asset"/"new purchase"
    # "add" is too broad (matches "address", "additional")
    # "new" is too broad (matches "renewal", "renewed", "news")
    if any(k in raw for k in ["addition", "purchase", "acquisition", "new asset", "new purchase"]):
        return "Addition"

    if role == "additions":
        return "Addition"

    return "Existing"
