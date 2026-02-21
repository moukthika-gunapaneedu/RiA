from __future__ import annotations

import re
from typing import Dict, List

def extract_entities_from_sources(sources: List[Dict]) -> Dict[str, List[str]]:
    software = set()
    commands = set()
    keywords = set()

    for s in sources:
        text = s.get("text", "")

        # detect RPD product mentions
        if "RICOH ProcessDirector" in text:
            software.add("RICOH ProcessDirector")

        # detect commands
        for cmd in ["stopaiw", "startaiw"]:
            if cmd in text:
                commands.add(cmd)

        # detect DB types
        if "PostgreSQL" in text:
            keywords.add("PostgreSQL")
        if "DB2" in text:
            keywords.add("DB2")

    return {
        "software": list(software),
        "commands": list(commands),
        "keywords": list(keywords),
    }


def build_refined_query(original_question: str, entities: Dict[str, List[str]]) -> str:
    parts = [original_question]

    for group in entities.values():
        for item in group:
            parts.append(item)

    return " ".join(parts)