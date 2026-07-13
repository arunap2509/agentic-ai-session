"""fact_check - the Reconciler's tool, general-purpose version. Verifies a
specific claim against a fresh, independent web search rather than trusting
whatever a worker already asserted - the point is that this check doesn't
just re-read the worker's own reasoning, it goes back to live sources.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.llm import MODEL, get_client
from common.web_search import web_search

INSTRUCTION = (
    "You verify a single factual claim using fresh search results. Reply "
    "with ONLY 'SUPPORTED' or 'NOT SUPPORTED: <short reason>'. A claim is "
    "SUPPORTED only if the search results directly state it or it's "
    "clearly, consistently corroborated across multiple results. A "
    "plausible-sounding specific detail that the search results don't "
    "actually confirm is NOT SUPPORTED, even if nothing contradicts it."
)


def fact_check(claim: str) -> dict:
    """Verify a specific factual claim against a fresh, independent search.

    Args:
        claim: The specific factual claim to verify, e.g. "the IAU vote to
            reclassify Pluto took place in Prague in August 2006".
    """
    search_result = web_search(claim)
    response = get_client().models.generate_content(
        model=MODEL,
        contents=f"Claim: {claim}\n\nFresh search results:\n{search_result['answer']}",
        config={"system_instruction": INSTRUCTION},
    )
    verdict = (response.text or "").strip()
    supported = verdict.upper().startswith("SUPPORTED")
    detail = verdict.split(":", 1)[1].strip() if not supported and ":" in verdict else verdict
    return {"supported": supported, "detail": detail, "sources": search_result["sources"]}
