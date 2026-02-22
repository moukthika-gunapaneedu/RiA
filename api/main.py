from __future__ import annotations

import re
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.retrieval import HybridRetriever
from api.synthesis import answer_question
from api.verify import verify_citations
from api.refine import extract_entities_from_sources, build_refined_query


app = FastAPI(title="RIA API", version="0.2")
retriever = HybridRetriever(index_dir="index")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"ok": True, "service": "ria-api"}


@app.get("/")
def root():
    return {"service": "ria-api", "routes": ["/health", "/ask"]}


# -------------------------
# Helpers (deterministic)
# -------------------------
def diversify_by_doc(hits: List[Dict[str, Any]], max_per_doc: int = 2) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for h in hits:
        doc = h.get("doc_name", "UNKNOWN")
        counts[doc] = counts.get(doc, 0) + 1
        if counts[doc] <= max_per_doc:
            out.append(h)
    return out

def evidence_overlap_ratio(question: str, evidence_text: str) -> float:
    q_words = [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", question) if len(w) > 3]
    if not q_words:
        return 0.0
    e = evidence_text.lower()
    hit = sum(1 for w in set(q_words) if w in e)
    return hit / max(1, len(set(q_words)))

def format_round_payload(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in items:
        out.append(
            {
                "chunk_id": r.get("chunk_id"),
                "doc_name": r.get("doc_name"),
                "page_start": int(r.get("page_start", 0)),
                "page_end": int(r.get("page_end", 0)),
                "section": r.get("section", "UNSPECIFIED"),
                "text": r.get("text", ""),
            }
        )
    return out


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    q = req.question.strip()

    plan = [
        "Identify intent and key constraints from the question.",
        "Retrieve evidence (iterative hybrid retrieval).",
        "Extract entities (product terms/commands/keywords) from evidence.",
        "Refine the query and retrieve again until evidence stabilizes.",
        "Synthesize a step-by-step answer grounded in evidence with citations.",
        "Verify citations and warn when coverage is weak.",
    ]

    # -------------------------
    # Agentic retrieval loop
    # -------------------------
    MAX_ITERS = 3
    TOPK_FIRST = 12
    TOPK_NEXT = 10

    seen_chunk_ids = set()
    evidence_pool: Dict[str, Dict[str, Any]] = {}
    refined_queries: List[str] = []
    entities: Dict[str, List[str]] = {"software": [], "commands": [], "keywords": []}

    current_query = q
    stop_reason = "max_iters"
    iteration_new_counts: List[int] = []
    trace_steps: List[Dict[str, Any]] = []

    # Keep a snapshot of "round1" and "round2" for your UI
    round1_hits: List[Dict[str, Any]] = []
    round2_hits: List[Dict[str, Any]] = []

    for i in range(MAX_ITERS):
        hits = retriever.hybrid_search(
            current_query,
            top_k=TOPK_FIRST if i == 0 else TOPK_NEXT,
        )
        hits = diversify_by_doc(hits, max_per_doc=2)

        if i == 0:
            round1_hits = hits[:]
        if i == 1:
            round2_hits = hits[:]

        new_count = 0
        for r in hits:
            cid = r.get("chunk_id")
            if not cid:
                continue
            if cid not in seen_chunk_ids:
                seen_chunk_ids.add(cid)
                evidence_pool[cid] = r
                new_count += 1

        iteration_new_counts.append(new_count)

        trace_steps.append(
            {
                "iter": i + 1,
                "query": current_query,
                "new_chunks_added": new_count,
                "top_hits": [(h.get("doc_name"), h.get("chunk_id")) for h in hits[:5]],
            }
        )

        # stop if no new evidence after first pass
        if i > 0 and new_count == 0:
            stop_reason = "no_new_evidence"
            break

        # refine query using what we found so far
        entities = extract_entities_from_sources(list(evidence_pool.values()))
        current_query = build_refined_query(q, entities)
        refined_queries.append(current_query)

    evidence = list(evidence_pool.values())

    trace = {
        "iterations": len(iteration_new_counts),
        "new_chunks_per_iteration": iteration_new_counts,
        "stop_reason": stop_reason,
        "final_query": current_query,
        "total_unique_chunks": len(evidence_pool),
        "steps": trace_steps,
    }

    # -------------------------
    # If no evidence at all
    # -------------------------
    if not evidence:
        answer_markdown = (
            "### Not enough evidence in the approved manuals\n"
            "I searched the provided dataset but could not find documentation that supports an answer.\n"
            "Try adding product/version, OS, module name, or the exact UI screen/setting label.\n"
        )
        verification = {
            "citation_coverage": 0.0,
            "unsupported_claims": 0,
            "total_claims": 0,
            "needs_confirmation": True,
            "unsupported_claim_texts": [],
            "conflicts": 0,
        }
        return {
            "plan": plan,
            "round1": [],
            "entities": entities,
            "refined_queries": refined_queries,
            "round2": [],
            "verification": verification,
            "answer_markdown": answer_markdown,
            "trace": trace,
        }

    # -------------------------
    # Overlap guard: prevents "same answer for everything"
    # -------------------------
    evidence_text = "\n".join([c.get("text", "") for c in evidence])
    overlap = evidence_overlap_ratio(q, evidence_text)
    trace["evidence_overlap"] = overlap

    if overlap < 0.12:
        answer_markdown = (
            "### Not enough evidence in the approved manuals\n"
            "I found documentation, but it does not clearly match this question.\n"
            "Try adding product version, OS, module name, or the exact UI screen/setting label.\n"
        )
        verification = {
            "citation_coverage": 0.0,
            "unsupported_claims": 0,
            "total_claims": 0,
            "needs_confirmation": True,
            "unsupported_claim_texts": [],
            "conflicts": 0,
        }
        trace["stop_reason"] = "low_evidence_overlap"
        return {
            "plan": plan,
            "round1": format_round_payload(round1_hits),
            "entities": entities,
            "refined_queries": refined_queries,
            "round2": format_round_payload(round2_hits),
            "verification": verification,
            "answer_markdown": answer_markdown,
            "trace": trace,
        }

    # -------------------------
    # Synthesize + verify
    # -------------------------
    answer_markdown = answer_question(q, evidence)
    verification = verify_citations(answer_markdown)
    verification["conflicts"] = 0

    if verification.get("needs_confirmation"):
        unsupported = verification.get("unsupported_claim_texts", [])
        answer_markdown = (
            "### ⚠️ Partial evidence found — manual confirmation recommended\n\n"
            "The system found relevant documentation, but not every statement could be fully supported "
            "by explicit citations in the approved dataset.\n\n"
            + answer_markdown
            + "\n\n---\n"
            + "### Unsupported or weakly supported statements:\n"
            + ("\n".join([f"- {u}" for u in unsupported]) if unsupported else "- (none listed)")
        )

    return {
        "plan": plan,
        "round1": format_round_payload(round1_hits),
        "entities": entities,
        "refined_queries": refined_queries,
        "round2": format_round_payload(round2_hits),
        "verification": verification,
        "answer_markdown": answer_markdown,
        "trace": trace,
    }