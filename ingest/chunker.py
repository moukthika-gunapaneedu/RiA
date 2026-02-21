from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
from tqdm import tqdm


HEADING_RE = re.compile(
    r"""^(
        (\d+(\.\d+){0,4}\s+.+)                 # numbered headings like 3.2 Title
        |([A-Z][A-Z0-9 /:-]{6,})               # ALL CAPS headings
        |([A-Z][a-z].{0,80}:)$                 # Title-ish ending with colon
    )$""",
    re.VERBOSE
)

def is_heading(line: str) -> bool:
    line = line.strip()
    if len(line) < 4 or len(line) > 140:
        return False
    return bool(HEADING_RE.match(line))

def normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())

def split_into_blocks(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocks = []
    for p in pages:
        page_no = p["page"]
        text = (p["text"] or "").strip()
        if not text:
            continue
        parts = [b.strip() for b in text.split("\n\n") if b.strip()]
        for b in parts:
            blocks.append({"page": page_no, "block": b})
    return blocks

def build_sections(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    current_section = "UNSPECIFIED"
    sectioned = []
    for b in blocks:
        lines = [normalize_line(x) for x in b["block"].split("\n") if x.strip()]
        if lines and is_heading(lines[0]):
            current_section = lines[0]
            content = "\n".join(lines[1:]).strip()
            if content:
                sectioned.append({"page": b["page"], "section": current_section, "text": content})
        else:
            sectioned.append({"page": b["page"], "section": current_section, "text": "\n".join(lines).strip()})
    return sectioned

def token_count_rough(text: str) -> int:
    return len(re.findall(r"\w+", text))

def make_chunk_id(doc_name: str, page_start: int, page_end: int, section: str, chunk_index: int, text: str) -> str:
    base = f"{doc_name}|p{page_start}-{page_end}|{section}|{chunk_index}|{text[:200]}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    safe_doc = re.sub(r"[^A-Za-z0-9]+", "_", doc_name)[:40]
    return f"{safe_doc}_p{page_start:04d}_p{page_end:04d}_c{chunk_index:03d}_{h}"

def chunk_document(doc: Dict[str, Any], target_tokens: int = 520, overlap_tokens: int = 90) -> List[Dict[str, Any]]:
    doc_name = doc["doc_name"]
    blocks = split_into_blocks(doc["pages"])
    sectioned = build_sections(blocks)

    chunks: List[Dict[str, Any]] = []
    buffer: List[Tuple[int, str]] = []
    buffer_tokens = 0
    chunk_index = 0
    current_section = "UNSPECIFIED"

    def flush():
        nonlocal buffer, buffer_tokens, chunk_index
        if not buffer:
            return
        pages = [p for p, _ in buffer]
        page_start, page_end = min(pages), max(pages)
        text = "\n".join(t for _, t in buffer).strip()

        cid = make_chunk_id(doc_name, page_start, page_end, current_section, chunk_index, text)
        chunks.append({
            "chunk_id": cid,
            "doc_name": doc_name,
            "page_start": page_start,
            "page_end": page_end,
            "section": current_section,
            "text": text,
            "tokens_rough": token_count_rough(text),
        })
        chunk_index += 1

        # overlap
        if overlap_tokens > 0:
            kept = []
            kept_tokens = 0
            for p, t in reversed(buffer):
                kept.append((p, t))
                kept_tokens += token_count_rough(t)
                if kept_tokens >= overlap_tokens:
                    break
            buffer = list(reversed(kept))
            buffer_tokens = sum(token_count_rough(t) for _, t in buffer)
        else:
            buffer = []
            buffer_tokens = 0

    for item in sectioned:
        txt = item["text"]
        if not txt:
            continue

        if item["section"] != current_section:
            flush()
            current_section = item["section"]

        tks = token_count_rough(txt)
        if buffer_tokens + tks > target_tokens and buffer:
            flush()

        buffer.append((item["page"], txt))
        buffer_tokens += tks

        if buffer_tokens >= target_tokens:
            flush()

    flush()
    return chunks

def main():
    processed_dir = Path("data/processed")
    manifest_path = processed_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Missing data/processed/manifest.json. Run parse step first.")

    out_path = Path("index/chunks.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_chunks = []

    for item in tqdm(manifest, desc="Chunking docs"):
        doc_json = json.loads(Path(item["json_path"]).read_text(encoding="utf-8"))
        all_chunks.extend(chunk_document(doc_json, target_tokens=520, overlap_tokens=90))

    df = pd.DataFrame(all_chunks)
    df.to_parquet(out_path, index=False)

    print(f"✅ Wrote {len(df)} chunks → {out_path}")
    print("\n--- Quick stats ---")
    print(df['tokens_rough'].describe(percentiles=[0.1,0.5,0.9]).to_string())

if __name__ == "__main__":
    main()