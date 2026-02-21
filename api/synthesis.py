from __future__ import annotations

import re
from typing import Dict, List, Any

from api.generic import answer_generic_grounded

def answer_question(question: str, sources: list[dict]) -> str:
    q = question.lower()

    if "shut down" in q or "shutdown" in q:
        return answer_shutdown_rpd(question, sources)

    # for everything else, don’t pretend — summarize evidence with citations
    return answer_generic_grounded(question, sources)

# matches your citation format: [doc | p.1-2 | chunk: abc]
CITE_RE = re.compile(r"\[[^\]]*chunk:\s*[A-Za-z0-9_\-]+\]", re.IGNORECASE)


def split_claims(markdown: str) -> List[str]:
    """
    Deterministic claim splitter:
    - bullets and numbered steps are claims
    - other lines >= 25 chars are treated as claims
    - headings ignored
    """
    lines = [ln.strip() for ln in (markdown or "").splitlines() if ln.strip()]
    claims: List[str] = []

    for ln in lines:
        if ln.startswith("#"):
            continue

        if ln.startswith(("-", "*")) or re.match(r"^\d+\.\s+", ln):
            claims.append(ln)
            continue

        if len(ln) >= 25:
            claims.append(ln)

    return claims


def verify_citations(answer_markdown: str, *, min_coverage: float = 0.95) -> Dict[str, Any]:
    claims = split_claims(answer_markdown)
    if not claims:
        return {
            "citation_coverage": 0.0,
            "unsupported_claims": 0,
            "total_claims": 0,
            "unsupported_claim_texts": [],
            "needs_confirmation": True,
        }

    unsupported: List[str] = []
    supported = 0

    for c in claims:
        if CITE_RE.search(c):
            supported += 1
        else:
            unsupported.append(c)

    total = len(claims)
    coverage = supported / total if total else 0.0

    needs_confirmation = (coverage < min_coverage) or (len(unsupported) > 0)

    return {
        "citation_coverage": float(coverage),
        "unsupported_claims": int(total - supported),
        "total_claims": int(total),
        "unsupported_claim_texts": unsupported,
        "needs_confirmation": bool(needs_confirmation),
    }