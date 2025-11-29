# fixed_asset_ai/logic/classification_normalizer.py

import re
from typing import Optional
from openai import OpenAI


ABBREV_MAP = {
    "hvac": "hvac",
    "eqp": "equipment",
    "equip": "equipment",
    "equipmt": "equipment",
    "equipmnt": "equipment",
    "bldg": "building",
    "rm": "room",
    "mfg": "manufacturing",
    "dist": "distribution",
    "whse": "warehouse",
    "comp": "computer",
}


def basic_normalize(desc: str) -> str:
    if not isinstance(desc, str):
        return ""

    s = desc.strip()

    # Replace common delimiters with spaces
    s = re.sub(r"[-_/]+", " ", s)

    # Collapse repeated spaces
    s = re.sub(r"\s+", " ", s)

    # Lowercase
    s = s.lower()

    # Expand abbreviations word by word
    tokens = s.split()
    expanded = []
    for t in tokens:
        expanded.append(ABBREV_MAP.get(t, t))

    return " ".join(expanded).strip()


def needs_gpt_rewrite(desc: str) -> bool:
    """
    Decide if description is too short / unclear and should be rewritten by GPT.
    """
    if not desc:
        return False
    words = desc.split()
    if len(words) <= 2:
        return True
    # If mostly numeric/punct
    alpha_count = sum(c.isalpha() for c in desc)
    if alpha_count < 3:
        return True
    return False


def gpt_rewrite_description(client: OpenAI, desc: str) -> str:
    """
    Ask GPT to rewrite / clarify a short or unclear description.
    Very cheap prompt.
    """
    prompt = f"""
You are a US fixed-asset accountant.
Rewrite the following short or unclear asset description into a clearer,
more standard description that keeps the same meaning.

Description: "{desc}"

Return ONLY the rewritten description as plain text.
"""
    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        text = resp.output_text.strip()
        return text or desc
    except Exception:
        return desc


def normalize_description(desc: str, client: Optional[OpenAI] = None,
                          use_gpt: bool = False) -> str:
    """
    Normalize description text for rule engine:
    1) basic normalization (abbrev, cleaning)
    2) optionally GPT rewrite if very short/unclear
    """
    base = basic_normalize(desc)
    if use_gpt and client is not None and needs_gpt_rewrite(base):
        rewritten = gpt_rewrite_description(client, base)
        return basic_normalize(rewritten)
    return base
