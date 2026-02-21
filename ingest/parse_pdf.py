from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber
from pypdf import PdfReader
from tqdm import tqdm


def clean_text(t: str) -> str:
    t = t.replace("\u00ad", "")  # soft hyphen
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extract_with_pdfplumber(pdf_path: Path) -> List[Dict[str, Any]]:
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": i, "text": clean_text(text)})
    return pages


def extract_with_pypdf(pdf_path: Path) -> List[Dict[str, Any]]:
    pages = []
    reader = PdfReader(str(pdf_path))
    for i, p in enumerate(reader.pages, start=1):
        text = p.extract_text() or ""
        pages.append({"page": i, "text": clean_text(text)})
    return pages


def parse_pdf(pdf_path: Path) -> Tuple[Dict[str, Any] | None, str | None]:
    """
    Returns (doc_json, error_message).
    If doc_json is None, error_message is non-None.
    """
    try:
        try:
            pages = extract_with_pdfplumber(pdf_path)
        except Exception:
            pages = extract_with_pypdf(pdf_path)

        total_chars = sum(len(p["text"]) for p in pages)
        nonempty_pages = sum(1 for p in pages if p["text"])
        return ({
            "doc_name": pdf_path.name,
            "doc_path": str(pdf_path),
            "num_pages": len(pages),
            "nonempty_pages": nonempty_pages,
            "total_chars": total_chars,
            "pages": pages,
        }, None)

    except Exception as e:
        return (None, f"{type(e).__name__}: {e}")


def main():
    raw_dir = Path("data/raw")
    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(raw_dir.rglob("*.pdf"))
    if not pdfs:
        raise SystemExit("No PDFs found under data/raw")

    manifest_path = out_dir / "manifest.json"
    errors_path = out_dir / "parse_errors.jsonl"

    # Resume support: load already-processed json_paths
    processed_json_paths = set()
    manifest: List[Dict[str, Any]] = []
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        processed_json_paths = {m["json_path"] for m in manifest}

    new_manifest = []
    skipped = 0
    written = 0

    for pdf_path in tqdm(pdfs, desc="Parsing PDFs"):
        rel = pdf_path.relative_to(raw_dir)
        safe_stem = "_".join(rel.with_suffix("").parts)
        out_path = out_dir / f"{safe_stem}.json"

        if str(out_path) in processed_json_paths:
            continue  # already done

        doc, err = parse_pdf(pdf_path)
        if err:
            skipped += 1
            # append JSONL error record
            errors_path.open("a", encoding="utf-8").write(json.dumps({
                "ts": time.time(),
                "rel_path": str(rel),
                "abs_path": str(pdf_path),
                "error": err
            }) + "\n")
            continue

        out_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        new_manifest.append({
            "doc_name": doc["doc_name"],
            "rel_path": str(rel),
            "json_path": str(out_path),
            "num_pages": doc["num_pages"],
            "nonempty_pages": doc["nonempty_pages"],
            "total_chars": doc["total_chars"],
        })
        written += 1

        # periodic flush so progress isn't lost
        if written % 50 == 0:
            combined = manifest + new_manifest
            manifest_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")

    combined = manifest + new_manifest
    manifest_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")

    print(f"✅ Done. Total parsed in manifest: {len(combined)}")
    print(f"✅ Newly written this run: {written}")
    print(f"⚠️ Skipped (bad PDFs): {skipped}")
    if errors_path.exists():
        print(f"🧾 Errors logged to: {errors_path}")


if __name__ == "__main__":
    main()