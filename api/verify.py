from __future__ import annotations

import re
from typing import Any, Dict, List

# matches your citation format: [doc | p.1-2 | chunk: abc]
CITE_RE = re.compile(r"\[[^\]]*chunk:\s*[A-Za-z0-9_\-]+\]", re.IGNORECASE)

def split_claims(markdown: str) -> List[str]:
    """
    Treat each numbered step / bullet / non-empty sentence-like line as a claim.
    Simple + deterministic.
    """
    lines = [ln.strip() for ln in markdown.splitlines() if ln.strip()]
    claims: List[str] = []

    for ln in lines:
        # ignore headings
        if ln.startswith("#"):
            continue
        # bullets/steps count as claims
        if ln.startswith(("-", "*")) or re.match(r"^\d+\.\s+", ln):
            claims.append(ln)
            continue
        # sentence-ish lines (avoid very short)
        if len(ln) >= 25:
            claims.append(ln)

    return claims

def verify_citations(answer_markdown: str, min_coverage: float = 0.85) -> Dict[str, Any]:
    claims = split_claims(answer_markdown)
    if not claims:
        return {
            "citation_coverage": 0.0,
            "unsupported_claims": 0,
            "total_claims": 0,
            "needs_confirmation": True,
            "unsupported_claim_texts": [],
        }

    supported = 0
    unsupported_texts: List[str] = []

    for c in claims:
        if CITE_RE.search(c):
            supported += 1
        else:
            unsupported_texts.append(c)

    total = len(claims)
    coverage = supported / total if total else 0.0

    return {
        "citation_coverage": float(coverage),
        "unsupported_claims": int(total - supported),
        "total_claims": int(total),
        "needs_confirmation": bool(coverage < min_coverage),
        "unsupported_claim_texts": unsupported_texts[:12],  # cap payload
    }