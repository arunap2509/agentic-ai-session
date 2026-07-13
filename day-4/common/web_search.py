"""General-purpose RETRIEVE tool, shared by any Day 4 agent that needs to
research an arbitrary topic. Wraps Gemini's native Google Search grounding
in a plain Python function so it plugs into run_tool_loop exactly like any
other tool - the calling agent's loop stays an explicit, visible
Thought/Action/Observation cycle instead of an opaque server-side search.
"""

from google.genai import types

from common.llm import MODEL, get_client


def web_search(query: str) -> dict:
    """RETRIEVE: Search the live web and return a grounded answer.

    Args:
        query: A specific search query - narrow, targeted queries return
            more useful results than broad restatements of the whole
            research question.

    Returns {"answer": synthesized text grounded in real search results,
    "sources": [{"title": ..., "url": ...}, ...]}. If sources is empty,
    treat the answer as ungrounded and say so rather than presenting it as
    verified.
    """
    client = get_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    candidate = response.candidates[0]
    sources = []
    grounding = candidate.grounding_metadata
    if grounding and grounding.grounding_chunks:
        for chunk in grounding.grounding_chunks:
            if chunk.web:
                sources.append({"title": chunk.web.title, "url": chunk.web.uri})
    return {"answer": response.text, "sources": sources}
