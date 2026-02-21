from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List
from api.retrieval import HybridRetriever
from api.synthesis import answer_question
from api.verify import verify_citations
from api.refine import extract_entities_from_sources, build_refined_query


app = FastAPI(title="RIA API", version="0.1")
retriever = HybridRetriever(index_dir="index")

# Allow GitHub Pages + local dev
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
    return {"service": "ria-api", "routes": ["/health", "/ask", "/docs"]}

@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    q = req.question.strip()

    plan = [
    "Identify the system and intent (command/property/requirements/workflow).",
    "Retrieve evidence (pass 1) using hybrid retrieval across manuals.",
    "Extract key entities from evidence and refine the query.",
    "Retrieve evidence (pass 2) and merge into a single evidence pool.",
    "Generate step-by-step answer with citations; mark unknown if unsupported.",
    "Verify citation coverage and flag unsupported claims.",
    ]

    round1 = retriever.hybrid_search(q, top_k=8)
    entities = extract_entities_from_sources(round1)
    refined_query = build_refined_query(q, entities)
    round2 = retriever.hybrid_search(refined_query, top_k=5)

    all_chunks = {r["chunk_id"]: r for r in round1}
    for r in round2:
        all_chunks[r["chunk_id"]] = r

    evidence = list(all_chunks.values())

    if not round1:
        answer_markdown = (
            "### Unable to answer from the provided dataset\n"
            "I searched the approved manuals but could not find enough evidence.\n"
            "Try adding product/version details (e.g., RPD version, server role, OS).\n"
        )
        verification = {"citation_coverage": 0.0, "unsupported_claims": 0, "total_claims": 0, "conflicts": 0}
        return {
            "plan": plan,
            "round1": [],
            "entities": {"software": [], "keywords": []},
            "refined_queries": [],
            "round2": [],
            "verification": verification,
            "answer_markdown": answer_markdown,
        }

    from api.synthesis import answer_question
    answer_markdown = answer_question(q, evidence)
    verification = verify_citations(answer_markdown)

    if verification["needs_confirmation"]:
        unsupported = verification.get("unsupported_claim_texts", [])

        answer_markdown = (
            "### ⚠️ Partial evidence found — manual confirmation recommended\n\n"
            "The system found relevant documentation, but not every claim could be fully supported "
            "by explicit citations in the approved dataset.\n\n"
            + answer_markdown
            + "\n\n---\n"
            + "### Unsupported or weakly supported statements:\n"
            + "\n".join([f"- {u}" for u in unsupported])
        )
    verification["conflicts"] = 0

    return {
        "plan": plan,
        "round1": [
            {
                "chunk_id": r["chunk_id"],
                "doc_name": r["doc_name"],
                "page_start": int(r["page_start"]),
                "page_end": int(r["page_end"]),
                "section": r.get("section", "UNSPECIFIED"),
                "text": r["text"],
            }
            for r in round1
        ],
        "entities": entities,
        "refined_queries": [refined_query],
        "round2": round2,
        "verification": verification,
        "answer_markdown": answer_markdown,
    }