from __future__ import annotations

import re
from typing import Dict, List

# matches your citation format: [something | p.1-2 | chunk: abc]
CITE_RE = re.compile(r"\[[^\]]*chunk:\s*[A-Za-z0-9_\-]+\]", re.IGNORECASE)

def split_claims(markdown: str) -> List[str]:
    """
    Treat each numbered step / bullet / non-empty sentence-like line as a claim.
    This is intentionally simple and deterministic.
    """
    lines = [ln.strip() for ln in markdown.splitlines() if ln.strip()]
    claims = []

    for ln in lines:
        # Ignore headings
        if ln.startswith("#"):
            continue
        # Count bullets/steps as claims
        if ln.startswith(("-", "*")) or re.match(r"^\d+\.\s+", ln):
            claims.append(ln)
            continue
        # Otherwise, include sentence-ish lines (avoid very short)
        if len(ln) >= 25:
            claims.append(ln)

    return claims

def verify_citations(answer_markdown: str) -> Dict[str, float | int]:
    claims = split_claims(answer_markdown)
    if not claims:
        return {"citation_coverage": 0.0, "unsupported_claims": 0, "total_claims": 0}

    supported = 0
    for c in claims:
        if CITE_RE.search(c):
            supported += 1

    total = len(claims)
    coverage = supported / total if total else 0.0

    return {
        "citation_coverage": float(coverage),
        "unsupported_claims": int(total - supported),
        "total_claims": int(total),
    }