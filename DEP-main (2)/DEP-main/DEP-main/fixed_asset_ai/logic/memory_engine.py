# logic/memory_engine.py

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

import numpy as np
from openai import OpenAI


MEMORY_PATH = Path(__file__).resolve().parent / "classification_memory.json"


class MemoryEngine:
    """
    Unified memory + similarity engine.
    Replaces:
      - classification_memory.py
      - similarity_memory.py

    Features:
      - store(asset_text, classification)
      - query_similar(asset_text)
      - load/save memory
    """

    def __init__(self, embed_model: str = "text-embedding-3-small"):
        self.embed_model = embed_model
        self.client = OpenAI()

        # embedding memory { "assets": [ { "text": ..., "embedding": [...], "class": {...} } ] }
        self.memory = self._load_memory()

    # ---------------------------
    # File persistence
    # ---------------------------

    def _load_memory(self) -> Dict[str, Any]:
        if not MEMORY_PATH.exists():
            return {"assets": []}
        try:
            with MEMORY_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"assets": []}

    def save_memory(self):
        try:
            with MEMORY_PATH.open("w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ---------------------------
    # Embedding utility
    # ---------------------------

    def embed(self, text: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self.embed_model,
            input=text,
        )
        return response.data[0].embedding

    # ---------------------------
    # Store classification memory
    # ---------------------------

    def store(self, text: str, classification: Dict[str, Any]):
        emb = self.embed(text)
        self.memory["assets"].append({
            "text": text,
            "embedding": emb,
            "classification": classification,
        })
        self.save_memory()

    # ---------------------------
    # Similarity Search
    # ---------------------------

    def query_similar(
        self,
        text: str,
        threshold: float = 0.82
    ) -> Optional[Dict[str, Any]]:
        """
        Returns classification of most similar stored asset
        if similarity >= threshold.
        """
        emb_new = np.array(self.embed(text))
        best_score = -1
        best_item = None

        for item in self.memory["assets"]:
            emb_old = np.array(item["embedding"])
            sim = self._cosine_similarity(emb_new, emb_old)
            if sim > best_score:
                best_score = sim
                best_item = item

        if best_score >= threshold:
            return {
                "classification": best_item["classification"],
                "similarity": float(best_score)
            }

        return None

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# Create a shared global memory engine instance
memory_engine = MemoryEngine()
