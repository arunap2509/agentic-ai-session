"""Runbook lookup - keyword match over a small static doc set, no reasoning
loop. Called directly by the orchestrator (or handed to an agent as a single
lookup, never as something to iterate on) - conceptually this is closer to
an MCP *resource* fetch than a tool an agent reasons with, per Day 2's
resources-vs-tools distinction: it's data to read, not an action to decide
whether/how to take.
"""

import re
from pathlib import Path

RUNBOOKS_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "runbooks"

_STOPWORDS = {"the", "a", "an", "is", "are", "to", "for", "of", "in", "on", "and", "or", "this"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOPWORDS}


def runbook_retrieval(query: str, top_n: int = 2) -> list[dict]:
    """Look up runbook snippets relevant to a query via keyword overlap.

    Args:
        query: Free-text description of the symptom or proposed action.
        top_n: How many top-scoring runbooks to return.
    """
    query_words = _words(query)
    scored = []
    for path in sorted(RUNBOOKS_DIR.glob("*.md")):
        content = path.read_text()
        overlap = len(query_words & _words(content))
        if overlap > 0:
            scored.append((overlap, path.stem, content.strip()))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [{"runbook": name, "content": content} for _, name, content in scored[:top_n]]
