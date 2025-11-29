# logic/memory_engine.py

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

import numpy as np

# Try to import OpenAI, but don't fail if not available
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

# Try to import rapidfuzz for local similarity
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


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

    Works in two modes:
      1. Embedding mode (requires OpenAI API key) - semantic similarity
      2. Fuzzy mode (no API key) - string-based similarity with rapidfuzz
    """

    def __init__(self, embed_model: str = "text-embedding-3-small"):
        self.embed_model = embed_model
        self.client = None
        self.use_embeddings = False

        # Try to use OpenAI embeddings if API key is available
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and OPENAI_AVAILABLE:
            try:
                self.client = OpenAI()
                self.use_embeddings = True
            except Exception as e:
                print(f"Warning: OpenAI client initialization failed: {e}")
                self.use_embeddings = False

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

    def embed(self, text: str) -> Optional[List[float]]:
        """Get embedding for text. Returns None if embeddings not available."""
        if not self.use_embeddings or not self.client:
            return None

        try:
            response = self.client.embeddings.create(
                model=self.embed_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Warning: Embedding failed: {e}")
            return None

    # ---------------------------
    # Store classification memory
    # ---------------------------

    def store(self, text: str, classification: Dict[str, Any]):
        """Store a classification in memory for future similarity matching."""
        entry = {
            "text": text,
            "classification": classification,
        }

        # Add embedding if available
        if self.use_embeddings:
            emb = self.embed(text)
            if emb:
                entry["embedding"] = emb

        self.memory["assets"].append(entry)
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

        Uses embedding similarity if available, otherwise falls back to
        fuzzy string matching.
        """
        if not self.memory["assets"]:
            return None

        best_score = -1
        best_item = None

        # Try embedding-based similarity first
        if self.use_embeddings:
            emb_new = self.embed(text)
            if emb_new:
                emb_new = np.array(emb_new)
                for item in self.memory["assets"]:
                    if "embedding" in item:
                        emb_old = np.array(item["embedding"])
                        sim = self._cosine_similarity(emb_new, emb_old)
                        if sim > best_score:
                            best_score = sim
                            best_item = item

        # Fall back to fuzzy string matching if no embedding match found
        if best_score < threshold and RAPIDFUZZ_AVAILABLE:
            text_lower = text.lower().strip()
            for item in self.memory["assets"]:
                stored_text = item.get("text", "").lower().strip()
                # Use token_set_ratio for better matching of reordered words
                sim = fuzz.token_set_ratio(text_lower, stored_text) / 100.0
                if sim > best_score:
                    best_score = sim
                    best_item = item

        if best_score >= threshold and best_item:
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

    def get_stats(self) -> Dict[str, Any]:
        """Get memory engine statistics."""
        return {
            "total_patterns": len(self.memory.get("assets", [])),
            "use_embeddings": self.use_embeddings,
            "mode": "embedding" if self.use_embeddings else "fuzzy"
        }


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
