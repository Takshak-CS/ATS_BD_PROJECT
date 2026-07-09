from __future__ import annotations

import json
from pathlib import Path

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover - only exercised without dependency
    faiss = None


class CandidateFaissIndex:
    def __init__(self) -> None:
        if faiss is None:
            raise RuntimeError(
                "FAISS retrieval requires faiss-cpu. Install the embedding service "
                "dependencies before running this service."
            )

    def build(self, embeddings: np.ndarray):
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        return index

    def search(self, index, query_vector: np.ndarray, top_k: int):
        scores, indices = index.search(query_vector.reshape(1, -1), top_k)
        return scores[0], indices[0]

    def write(self, index, path: Path, metadata: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(path))
        metadata_path = path.with_suffix(".meta.json")
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
