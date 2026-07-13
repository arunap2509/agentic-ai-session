"""Deep Dive Worker - real agent, pulls specific, precise, checkable details
(exact numbers, dates, named sources/documents) rather than a general
summary. This is where hallucination risk naturally concentrates: a
specific-sounding detail is exactly what's tempting to fill in under
pressure to look thorough, and exactly what the Reconciler's fact_check
step exists to catch downstream.
"""

import sys
from pathlib import Path

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.agent_loop import run_tool_loop
from common.json_utils import parse_json_final
from common.web_search import web_search

INSTRUCTION = (
    "You are the Deep Dive Worker in a research pipeline. You have one "
    "tool, web_search(query). Your job is precision: find the specific, "
    "checkable details behind the topic - exact dates, numbers, named "
    "sources or documents, direct quotes - not a general summary. Search "
    "for the specific fact, not just the general topic. If a specific "
    "detail genuinely isn't available from your searches, say so plainly "
    "in specific_details rather than estimating one - a wrong specific "
    "number is worse than admitting it wasn't found. "
    "You must never call a tool silently - every response with a tool call "
    "must include a plain-text sentence starting with 'Thought:'. Skip the "
    "Thought only on your final response.\n\n"
    "Your final response must be ONLY a JSON object: "
    '{"summary": "...", "specific_details": {"<label>": "<value or '
    '\'not found\'>"}, "confidence": 0.0-1.0, "sources": ["<url>", ...]}.'
)


def research(question: str, console=None, max_steps: int = 8) -> dict:
    prompt = f"Research question: {question}\n\nFind the specific, precise, checkable details."
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    result = run_tool_loop(contents, [web_search], set(), INSTRUCTION, max_steps, console)
    if result.exhausted:
        return {"summary": "did not conclude within step budget", "specific_details": {}, "confidence": 0.0, "sources": []}
    return parse_json_final(result.final_text)
