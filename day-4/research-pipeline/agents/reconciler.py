"""Reconciler - real agent, justified by conflict resolution across
independent sources, not workload: it has to actually detect and address
tension between findings (e.g. Background implies one thing, Recent
Developments implies another), not just concatenate them.
`fact_check_enabled=False` is the broken demo: no fact_check tool at all,
findings merged at face value. `fact_check_enabled=True` is fixed: every
specific factual claim (a date, a number, a named detail) must be
fact_checked before it can appear in reconciled_summary; anything that
fails is flagged, not dropped or silently kept.
"""

import sys
from pathlib import Path

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.fact_check import fact_check

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.agent_loop import run_tool_loop
from common.json_utils import parse_json_final
from common.llm import MODEL, get_client

BASE_INSTRUCTION = (
    "You are the Reconciler in a research pipeline. You are given three "
    "independent findings on the same research question (Background, "
    "Recent Developments, Deep Dive). Do not just concatenate them - "
    "actively detect contradictions or tension between them and address "
    "the tension explicitly in your summary rather than ignoring it.\n\n"
    "Your final response must be ONLY a JSON object: "
    '{"reconciled_summary": "...", "flagged_conflicts": ["..."], '
    '"unresolved_conflicts": ["..."], "confidence": 0.0-1.0}.'
)

FACT_CHECK_CLAUSE = (
    "\n\nYou have one tool, fact_check(claim). Before any specific factual "
    "claim (a date, a number, a named detail) appears in "
    "reconciled_summary, you must call fact_check on it. If fact_check "
    "returns supported=false, do NOT include that claim in "
    "reconciled_summary - put it in unresolved_conflicts with the reason "
    "instead, plainly, not hidden. Any claim from a worker whose own "
    "confidence was below 0.7 must also be fact_checked before being "
    "trusted, regardless of how confident you personally feel about it.\n"
    "You must never call a tool silently - every response with a tool call "
    "must include a plain-text sentence starting with 'Thought:'. Skip the "
    "Thought only on your final response."
)


def reconcile(findings: dict, fact_check_enabled: bool = True, console=None, max_steps: int = 16) -> dict:
    prompt = f"Findings to reconcile:\n{findings}"

    if not fact_check_enabled:
        response = get_client().models.generate_content(
            model=MODEL, contents=prompt, config={"system_instruction": BASE_INSTRUCTION},
        )
        return parse_json_final(response.text)

    instruction = BASE_INSTRUCTION + FACT_CHECK_CLAUSE
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    result = run_tool_loop(contents, [fact_check], set(), instruction, max_steps, console)
    if result.exhausted:
        return {"reconciled_summary": "did not conclude within step budget", "flagged_conflicts": [], "unresolved_conflicts": list(findings), "confidence": 0.0}
    return parse_json_final(result.final_text)
