from __future__ import annotations

import re
from typing import Dict, List

# lightweight token extraction (no LLM)
TOKEN_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_\-]{2,}\b")

STOPWORDS = {
    "the","and","for","with","from","this","that","then","than","into","onto","when","what",
    "where","how","does","do","did","can","will","should","would","could","are","is","was",
    "were","been","being","it","its","you","your","they","their","them","we","our","but",
    "also","may","might","must","not","no","yes","a","an","to","of","in","on","at","as"
}

def extract_entities_from_sources(sources: List[Dict]) -> Dict[str, List[str]]:
    software = set()
    commands = set()
    keywords = set()

    for s in sources:
        text = (s.get("text") or "")

        # product mention
        if "RICOH ProcessDirector" in text:
            software.add("RICOH ProcessDirector")
        if "ProcessDirector" in text:
            software.add("ProcessDirector")

        # useful keywords often present in manuals
        for kw in ["DB2", "PostgreSQL", "Windows", "Linux", "workflow", "property", "RAM", "memory", "disk", "logs"]:
            if kw.lower() in text.lower():
                keywords.add(kw)

        # pull command-like tokens (deterministic)
        for tok in TOKEN_RE.findall(text):
            t = tok.lower()
            if t in STOPWORDS:
                continue
            # keep likely commands / executable-ish tokens
            if any(x in t for x in ["aiw", "rpd", "pd", "db2", "psql", "systemctl", "service", "cmd", "exe"]):
                commands.add(t)
            # also keep explicit start/stop commands if present
            if t in {"stopaiw", "startaiw"}:
                commands.add(t)

    return {
        "software": sorted(list(software))[:5],
        "commands": sorted(list(commands))[:10],
        "keywords": sorted(list(keywords))[:10],
    }

def build_refined_query(original_question: str, entities: Dict[str, List[str]]) -> str:
    # Avoid making query huge — keep it tight
    parts = [original_question]

    for k in ["software", "commands", "keywords"]:
        for item in entities.get(k, []):
            parts.append(item)

    return " ".join(parts)