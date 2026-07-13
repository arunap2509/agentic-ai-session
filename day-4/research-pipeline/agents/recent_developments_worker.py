"""Recent Developments Worker - real agent, same isolation justification as
Background Worker, different angle: what's changed, current state, recent
coverage - not the historical foundation.
"""

import sys
from pathlib import Path

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.agent_loop import run_tool_loop
from common.json_utils import parse_json_final
from common.web_search import web_search

INSTRUCTION = (
    "You are the Recent Developments Worker in a research pipeline. You "
    "have one tool, web_search(query). Your job is what's recent or "
    "currently true: the current state of the topic, anything that has "
    "changed, ongoing debate, or recent coverage - not the historical "
    "background. If your first search comes back generic or off-topic, "
    "refine your query (add a year, a more specific angle) and search "
    "again. "
    "You must never call a tool silently - every response with a tool call "
    "must include a plain-text sentence starting with 'Thought:'. Skip the "
    "Thought only on your final response.\n\n"
    "Your final response must be ONLY a JSON object: "
    '{"summary": "...", "key_events": ["..."], "confidence": 0.0-1.0, '
    '"sources": ["<url>", ...]}.'
)


def research(question: str, console=None, max_steps: int = 6) -> dict:
    prompt = f"Research question: {question}\n\nWhat's the current/recent state of this?"
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    result = run_tool_loop(contents, [web_search], set(), INSTRUCTION, max_steps, console)
    if result.exhausted:
        return {"summary": "did not conclude within step budget", "key_events": [], "confidence": 0.0, "sources": []}
    return parse_json_final(result.final_text)
