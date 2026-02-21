from __future__ import annotations

import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import faiss


def tokenize(text: str):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return [t for t in text.split() if len(t) > 1]


def main():
    chunks_path = Path("index/chunks.parquet")
    if not chunks_path.exists():
        raise SystemExit("Missing index/chunks.parquet. Run chunking first.")

    df = pd.read_parquet(chunks_path)
    texts = df["text"].fillna("").tolist()

    # -------- BM25 --------
    tokenized = [tokenize(t) for t in texts]
    bm25 = BM25Okapi(tokenized)

    Path("index").mkdir(exist_ok=True)

    with open("index/bm25.pkl", "wb") as f:
        pickle.dump({"bm25": bm25, "tokenized": tokenized}, f)

    # -------- Vector --------
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    model = SentenceTransformer(model_name)

    emb = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    emb = np.asarray(emb, dtype="float32")

    dim = emb.shape[1]
    index = faiss.IndexFlatIP(dim)  # cosine similarity (normalized)
    index.add(emb)

    faiss.write_index(index, "index/faiss.index")

    df.to_parquet("index/chunks_with_ids.parquet", index=False)

    print("✅ Built BM25 + FAISS")
    print("BM25 docs:", len(tokenized))
    print("FAISS vectors:", index.ntotal)
    print("Embedding model:", model_name)


if __name__ == "__main__":
    main()