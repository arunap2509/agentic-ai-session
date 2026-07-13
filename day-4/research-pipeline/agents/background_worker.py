"""Background Worker - real agent, isolation justified by raw-search-result
volume: it may need several searches to build a solid foundational answer,
which nobody downstream should have to redo.
"""

import sys
from pathlib import Path

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.agent_loop import run_tool_loop
from common.json_utils import parse_json_final
from common.web_search import web_search

INSTRUCTION = (
    "You are the Background Worker in a research pipeline. You have one "
    "tool, web_search(query). Your job is foundational context: what the "
    "topic is, its history, and the widely-established facts behind it - "
    "not breaking news. If your first search is too broad to be useful, "
    "narrow it and search again. "
    "You must never call a tool silently - every response with a tool call "
    "must include a plain-text sentence starting with 'Thought:'. Skip the "
    "Thought only on your final response.\n\n"
    "Your final response must be ONLY a JSON object: "
    '{"summary": "...", "key_facts": ["..."], "confidence": 0.0-1.0, '
    '"sources": ["<url>", ...]}.'
)


def research(question: str, console=None, max_steps: int = 6) -> dict:
    prompt = f"Research question: {question}\n\nProvide the foundational background."
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    result = run_tool_loop(contents, [web_search], set(), INSTRUCTION, max_steps, console)
    if result.exhausted:
        return {"summary": "did not conclude within step budget", "key_facts": [], "confidence": 0.0, "sources": []}
    return parse_json_final(result.final_text)
