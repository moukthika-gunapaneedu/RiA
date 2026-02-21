def _cite(src):
    return f"[{src['doc_name']} | p.{src['page_start']}-{src['page_end']} | chunk: {src['chunk_id']}]"

def answer_generic_grounded(question: str, sources: list[dict]) -> str:
    if not sources:
        return (
            "### Unable to answer from the provided dataset\n"
            "I searched the approved manuals but could not find enough evidence.\n"
        )

    lines = [
        f"### Answer (grounded)\n",
        f"**Question:** {question}\n",
        "Here are the most relevant excerpts I found:\n",
    ]

    for i, s in enumerate(sources[:5], 1):
        snippet = s.get("text","").strip().replace("\n", " ")
        lines.append(f"{i}. {snippet[:400]} {_cite(s)}")

    lines.append("\n### Next step\nIf you want, I can extract the exact property name/value *only if it appears explicitly in the excerpts above*.")

    return "\n".join(lines)