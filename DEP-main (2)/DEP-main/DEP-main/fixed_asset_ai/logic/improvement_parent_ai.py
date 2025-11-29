import pandas as pd
import re

# Words indicating an improvement
IMPROVEMENT_KEYWORDS = [
    "improv", "improvement", "reno", "renovation", "repair",
    "hvac", "roof", "floor", "flooring", "carpet", "lighting",
    "build-out", "build out", "buildout", "remodel", "upgrade",
    "expansion", "addition", "plumbing"
]

# Words indicating a possible parent (usually building)
PARENT_KEYWORDS = [
    "building", "warehouse", "facility", "office", "property",
    "store", "retail", "shop", "location", "plant", "center",
    "unit", "suite"
]

def _normalize(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return text.strip()

def suggest_parent(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds: Suggested Parent Asset ID (for improvements)
    """
    df = df.copy()

    if "Description" not in df.columns or "Asset ID" not in df.columns:
        df["Suggested Parent Asset ID"] = ""
        return df

    # Normalize descriptions
    df["_norm_desc"] = df["Description"].apply(_normalize)

    # Identify improvement candidates
    df["is_improvement"] = df["_norm_desc"].apply(
        lambda d: any(k in d for k in IMPROVEMENT_KEYWORDS)
    )

    # Identify parent candidates (typically buildings / real property)
    if "Final Category Used" in df.columns:
        df["is_parent"] = df["Final Category Used"].astype(str).str.contains(
            "Real Property|Building|Nonresidential|Residential",
            case=False, na=False
        )
    else:
        df["is_parent"] = df["_norm_desc"].apply(
            lambda d: any(k in d for k in PARENT_KEYWORDS)
        )

    parent_df = df[df["is_parent"]]

    suggestions = []

    for idx, row in df.iterrows():
        if not row["is_improvement"]:
            suggestions.append("")
            continue

        desc_words = set(row["_norm_desc"].split())
        best_id = ""
        best_overlap = 0

        for _, prow in parent_df.iterrows():
            pwords = set(prow["_norm_desc"].split())
            overlap = len(desc_words & pwords)

            # Use highest overlap
            if overlap > best_overlap:
                best_overlap = overlap
                best_id = prow["Asset ID"]

        suggestions.append(best_id)

    df["Suggested Parent Asset ID"] = suggestions
    df.drop(columns=["_norm_desc","is_parent","is_improvement"], inplace=True)

    return df
