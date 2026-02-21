from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return [t for t in text.split() if len(t) > 1]


class HybridRetriever:
    def __init__(self, index_dir: str = "index"):
        index_dir = str(index_dir)
        self.df = pd.read_parquet(Path(index_dir) / "chunks_with_ids.parquet")

        with open(Path(index_dir) / "bm25.pkl", "rb") as f:
            payload = pickle.load(f)
        self.bm25 = payload["bm25"]

        self.faiss_index = faiss.read_index(str(Path(index_dir) / "faiss.index"))
        self.model_name = "sentence-transformers/all-MiniLM-L6-v2"
        self.model = SentenceTransformer(self.model_name)

    def bm25_search(self, query: str, k: int = 20) -> List[Tuple[int, float]]:
        toks = _tokenize(query)
        scores = self.bm25.get_scores(toks)  # array length N
        idx = np.argsort(scores)[::-1][:k]
        return [(int(i), float(scores[i])) for i in idx]

    def vec_search(self, query: str, k: int = 20) -> List[Tuple[int, float]]:
        qv = self.model.encode([query], normalize_embeddings=True)
        qv = np.asarray(qv, dtype="float32")
        scores, idx = self.faiss_index.search(qv, k)
        return [(int(i), float(scores[0][pos])) for pos, i in enumerate(idx[0]) if i != -1]

    def hybrid_search(self, query: str, k_bm25: int = 25, k_vec: int = 25, top_k: int = 8) -> List[Dict[str, Any]]:
        bm = self.bm25_search(query, k=k_bm25)
        vc = self.vec_search(query, k=k_vec)

        # normalize each score list to 0..1 to combine
        def norm(pairs):
            if not pairs:
                return {}
            vals = np.array([s for _, s in pairs], dtype="float32")
            lo, hi = float(vals.min()), float(vals.max())
            if hi - lo < 1e-9:
                return {i: 1.0 for i, _ in pairs}
            return {i: float((s - lo) / (hi - lo)) for i, s in pairs}

        bm_n = norm(bm)
        vc_n = norm(vc)

        candidates = set(bm_n.keys()) | set(vc_n.keys())
        scored = []
        for i in candidates:
            score = 0.55 * bm_n.get(i, 0.0) + 0.45 * vc_n.get(i, 0.0)
            scored.append((i, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_k]

        out = []
        for i, s in top:
            row = self.df.iloc[i].to_dict()
            row["hybrid_score"] = float(s)
            out.append(row)
        return out