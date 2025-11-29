# fixed_asset_ai/logic/semantic_labels.py

from __future__ import annotations

import numpy as np
from typing import List, Dict, Any, Optional
from openai import OpenAI

from .api_utils import openai_retry

# In-memory cache of label embeddings so we do not recompute every time
_LABEL_EMBED_CACHE: Dict[str, List[float]] = {}

EMBED_MODEL = "text-embedding-3-small"


# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _label_catalog() -> List[Dict[str, Any]]:
    """
    Canonical MACRS labels used as semantic targets.
    You can expand this list as needed.
    """
    return [
        {
            "code": "OFFICE_EQUIP_5",
            "label": "5yr Office Equipment",
            "life": 5,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Computers, laptops, servers, monitors, printers, copiers, "
                "routers, switches, phones, and small office electronic equipment."
            ),
        },
        {
            "code": "OFFICE_FURN_7",
            "label": "7yr Office Furniture",
            "life": 7,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Office desks, tables, conference tables, workstations, "
                "chairs, filing cabinets, bookcases, cubicles, reception furniture."
            ),
        },
        {
            "code": "MACH_EQUIP_7",
            "label": "7yr Machinery & Equipment",
            "life": 7,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Manufacturing and industrial machinery, forklifts, lift trucks, "
                "pallet jacks, scissor lifts, skid steers, construction equipment, "
                "shop tools and production equipment."
            ),
        },
        {
            "code": "MAT_HANDLING_7",
            "label": "7yr Material Handling & Warehouse Racks",
            "life": 7,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Warehouse shelving, pallet racking, storage racks, "
                "mezzanine racks, cantilever racks and similar material "
                "handling systems used to store inventory or materials."
            ),
        },
        {
            "code": "AUTO_5",
            "label": "5yr Auto / Vehicle",
            "life": 5,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Passenger autos, SUVs, light trucks, and vans used in business, "
                "subject to luxury auto depreciation limitations."
            ),
        },
        {
            "code": "SOFTWARE_5",
            "label": "5yr Off-the-Shelf Software",
            "life": 5,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Non-custom, off-the-shelf computer software and software licenses "
                "that are depreciable over five years under MACRS."
            ),
        },
        {
            "code": "LAND_IMPROV_15",
            "label": "15yr Land Improvements",
            "life": 15,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Parking lots, paving, sidewalks, curbs, fences, retaining walls, "
                "exterior lighting and other site improvements to land."
            ),
        },
        {
            "code": "QIP_15",
            "label": "15yr Qualified Improvement Property",
            "life": 15,
            "method": "MACRS GDS",
            "convention": "HY",
            "description": (
                "Interior improvements to nonresidential buildings placed in service "
                "after the building, excluding enlargements, elevators/escalators, "
                "and internal structural framework. Eligible for bonus depreciation."
            ),
        },
        {
            "code": "RES_RENTAL_27",
            "label": "27.5yr Residential Rental Property",
            "life": 27.5,
            "method": "MACRS GDS",
            "convention": "MM",
            "description": (
                "Buildings where 80 percent or more of gross rental income is from "
                "dwelling units, such as apartments and residential rental houses."
            ),
        },
        {
            "code": "NONRES_39",
            "label": "39yr Nonresidential Real Property",
            "life": 39,
            "method": "MACRS GDS",
            "convention": "MM",
            "description": (
                "Commercial buildings, warehouses, offices, retail stores and their "
                "structural components, such as HVAC, plumbing, electrical, roofs, "
                "and fire protection systems."
            ),
        },
        {
            "code": "LEASEHOLD_39",
            "label": "39yr Nonresidential Leasehold / Buildout",
            "life": 39,
            "method": "MACRS GDS",
            "convention": "MM",
            "description": (
                "Tenant improvements and buildouts to nonresidential space that are "
                "not qualified improvement property but are structural in nature."
            ),
        },
        {
            "code": "LAND_NONDEP",
            "label": "Nondepreciable Land",
            "life": None,
            "method": "None",
            "convention": "None",
            "description": (
                "Bare land and land value not allocated to depreciable improvements "
                "or buildings."
            ),
        },
    ]


@openai_retry
def _create_label_embeddings(client: OpenAI, texts: List[str]):
    """
    Create embeddings for label texts with retry logic.

    Retries up to 4 times with exponential backoff on API failures.
    """
    return client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )


def _embed_labels_if_needed(client: OpenAI) -> List[Dict[str, Any]]:
    """
    Ensure all labels have embeddings in the global cache.
    Returns the label catalog with an 'embedding' key on each label.
    """
    global _LABEL_EMBED_CACHE

    catalog = _label_catalog()

    # If we already have a full cache of embeddings, reuse it.
    if _LABEL_EMBED_CACHE and len(_LABEL_EMBED_CACHE) == len(catalog):
        for lbl in catalog:
            code = lbl["code"]
            if code in _LABEL_EMBED_CACHE:
                lbl["embedding"] = _LABEL_EMBED_CACHE[code]
        return catalog

    # Otherwise embed all labels (label + description)
    texts = [
        f"{lbl['label']} – {lbl['description']}"
        for lbl in catalog
    ]

    try:
        resp = _create_label_embeddings(client, texts)

        _LABEL_EMBED_CACHE = {}
        for lbl, emb_data in zip(catalog, resp.data):
            emb = emb_data.embedding
            lbl["embedding"] = emb
            _LABEL_EMBED_CACHE[lbl["code"]] = emb

        return catalog
    except Exception as e:
        # If all retries fail, raise exception - cannot do semantic matching without embeddings
        raise RuntimeError(f"Failed to create label embeddings after all retries: {str(e)}")


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def semantic_label_classify(
    client: OpenAI,
    description_clean: str,
    client_category: str = "",
    industry: str = "",
    min_similarity: float = 0.75,
) -> Optional[Dict[str, Any]]:
    """
    Classify an asset by semantically matching it against canonical MACRS labels.

    Returns:
        {
            "source": "semantic_label",
            "category": <label string>,
            "macrs_life": <int or float or None>,
            "method": <str>,
            "convention": <str>,
            "confidence": <float 0–1>,
            "notes": <str>,
            "semantic_label_code": <str>,
            "semantic_similarity": <float>,
        }

    or None if similarity < min_similarity or if an error occurs.
    """

    description_clean = (description_clean or "").strip()
    client_category = (client_category or "").strip()
    industry = (industry or "").strip()

    if not description_clean:
        return None

    # Build a rich context string for the embedding to improve semantic accuracy
    context_parts = [
        f"Asset description: {description_clean}",
        f"Client category: {client_category or 'unknown'}",
        f"Business industry: {industry or 'unknown'}",
        "Classify this asset into one US tax MACRS classification label.",
    ]
    context = " | ".join(context_parts)

    # Get embedding for this asset description + context (with retry logic)
    try:
        @openai_retry
        def create_query_embedding():
            return client.embeddings.create(
                model=EMBED_MODEL,
                input=[context],
            )

        q_resp = create_query_embedding()
        q_vec = np.array(q_resp.data[0].embedding, dtype=float)
    except Exception as e:
        # If embedding fails after all retries, cannot do semantic matching
        return None

    # Load / compute label embeddings
    labels = _embed_labels_if_needed(client)

    best_lbl: Optional[Dict[str, Any]] = None
    best_sim: float = 0.0

    for lbl in labels:
        emb_vec = np.array(lbl.get("embedding", []), dtype=float)
        sim = _cosine_sim(q_vec, emb_vec)
        if sim > best_sim:
            best_sim = sim
            best_lbl = lbl

    if best_lbl is None or best_sim < min_similarity:
        return None

    # Convert similarity into a confidence score
    # Higher similarity → closer to 1.0
    confidence = min(0.98, 0.60 + best_sim * 0.40)

    return {
        "source": "semantic_label",
        "category": best_lbl["label"],
        "macrs_life": best_lbl["life"],
        "method": best_lbl["method"],
        "convention": best_lbl["convention"],
        "confidence": confidence,
        "notes": f"Semantic match to '{best_lbl['label']}' (similarity={best_sim:.3f}).",
        "semantic_label_code": best_lbl["code"],
        "semantic_similarity": float(best_sim),
    }
