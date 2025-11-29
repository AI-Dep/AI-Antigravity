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

        # Validate OpenAI API key before creating client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set.\n"
                "Please set your OpenAI API key:\n"
                "  export OPENAI_API_KEY='your-api-key-here'\n"
                "Or add it to your .env file."
            )

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
        """
        Calculate cosine similarity between two vectors.
        Returns 0.0 if either vector has zero norm (division by zero protection).
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        # Prevent division by zero
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))


# Lazy initialization: Create memory engine only when first used
# This prevents API key validation from failing at module import time
_memory_engine_instance = None

def get_memory_engine():
    """
    Get or create the shared memory engine instance (lazy initialization).
    This delays API key validation until the memory engine is actually needed.
    """
    global _memory_engine_instance
    if _memory_engine_instance is None:
        _memory_engine_instance = MemoryEngine()
    return _memory_engine_instance

# For backward compatibility, provide memory_engine as a property
class _MemoryEngineProxy:
    """Proxy to maintain backward compatibility with code that uses memory_engine directly."""
    def __getattr__(self, name):
        return getattr(get_memory_engine(), name)

memory_engine = _MemoryEngineProxy()
