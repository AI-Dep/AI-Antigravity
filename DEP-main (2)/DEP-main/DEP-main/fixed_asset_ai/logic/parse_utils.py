import re
import pandas as pd
from datetime import datetime

def parse_number(v):
    if pd.isna(v):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except:
        return None


def parse_date(v):
    if pd.isna(v) or v == "":
        return None

    # Excel serial dates
    if isinstance(v, (int, float)) and v > 30000:
        try:
            base = pd.to_datetime("1899-12-30")
            return base + pd.to_timedelta(int(v), unit="D")
        except:
            pass

    try:
        dt = pd.to_datetime(v)
        if dt.year > datetime.now().year + 1:
            return None
        return dt
    except:
        pass

    # Extract date from text
    m = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", str(v))
    if m:
        try:
            return pd.to_datetime(m.group(0))
        except:
            pass

    try:
        return pd.to_datetime(v, dayfirst=True)
    except:
        return None


def sanitize_asset_description(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r"[A-Z0-9]{8,}", "[REDACTED ID]", text).strip()
