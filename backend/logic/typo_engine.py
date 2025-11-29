# logic/typo_engine.py

import difflib
import re
from typing import List, Dict, Optional


class TypoEngine:
    """
    Unified typo detection + correction engine.
    Replaces:
      - typo_corrector.py
      - typo_detector.py

    Provides:
      - detect_typos(text)
      - correct_category(text)
      - correct_description(text)
    """

    # Common category keywords and normalized forms
    CATEGORY_MAP = {
        "machienry": "Machinery",
        "machinery & equip": "Machinery & Equipment",
        "mach": "Machinery",
        "equipmnt": "Equipment",
        "office furinture": "Office Furniture",
        "office equpment": "Office Equipment",
        "vehcle": "Vehicle",
        "vechile": "Vehicle",
        "softwre": "Software",
        "land improvmnt": "Land Improvements",
        "leasehold improve": "Leasehold Improvements",
    }

    # Regex to detect “broken” descriptions with scrambled characters
    DESCRIPTION_ISSUE_PATTERN = re.compile(
        r"[^a-zA-Z0-9\s\-\.,/()]+"
    )

    def __init__(self):
        self.category_keywords = list(set(self.CATEGORY_MAP.values()))

    # ---------------------------
    # Typo Detection
    # ---------------------------

    def detect_typos(self, text: str) -> List[str]:
        """
        Detects obvious typos in a text field.
        Returns a list of warning strings.
        """
        issues = []

        if not isinstance(text, str) or not text.strip():
            return ["Empty or invalid text"]

        # detect non-standard characters
        if self.DESCRIPTION_ISSUE_PATTERN.search(text):
            issues.append("Text contains unusual or corrupted characters")

        # fuzzy detect category-like words
        tokens = text.lower().split()
        for token in tokens:
            if token not in [k.lower() for k in self.category_keywords]:
                close = difflib.get_close_matches(
                    token,
                    [k.lower() for k in self.category_keywords],
                    n=1,
                    cutoff=0.85
                )
                if close:
                    issues.append(f"Possible typo: '{token}' -> '{close[0]}'")

        return issues

    # ---------------------------
    # Typo Correction
    # ---------------------------

    def correct_category(self, text: str) -> str:
        """
        Corrects category-level misspellings using fuzzy match + map.
        """
        if not isinstance(text, str) or not text.strip():
            return text

        text_lower = text.lower().strip()

        # direct map hits
        if text_lower in self.CATEGORY_MAP:
            return self.CATEGORY_MAP[text_lower]

        # fuzzy match to standardized category list
        match = difflib.get_close_matches(
            text_lower,
            [c.lower() for c in self.category_keywords],
            n=1,
            cutoff=0.80
        )
        if match:
            corrected = match[0]
            for c in self.category_keywords:
                if c.lower() == corrected:
                    return c

        return text

    def correct_description(self, text: str) -> str:
        """
        Cleans and normalizes asset descriptions:
         - Fix repeated spaces
         - Remove corrupted characters
         - Normalize dashes
        """
        if not isinstance(text, str):
            return text

        t = text.strip()
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r"[^\w\s\-\.,/()]", "", t)  # remove corrupted chars
        t = t.replace("–", "-").replace("—", "-")

        return t


# Create shared instance
typo_engine = TypoEngine()
