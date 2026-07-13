"""Evaluator - a real agent, non-negotiable, never merge into the Planner.
Gets the Planner's proposal PLUS the original investigator findings (with
their cited evidence) directly - not the Planner's summary of them - so it
can independently re-check the claim against source instead of rubber-
stamping the Planner's own framing. Uses policy_check, a deterministic
allow-list/blast-radius check, as one input to its decision - the model
doesn't get to overrule what policy_check finds.
"""

import sys
from pathlib import Path

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.policy_check import policy_check

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.agent_loop import run_tool_loop
from common.json_utils import parse_json_final

BASE_INSTRUCTION = (
    "You are the Evaluator agent in an incident response system. Your job is "
    "independent judgment on a proposed remediation - you are not the agent "
    "that proposed it, and you must not simply agree with its justification. "
    "You have one tool, policy_check(action, target_service, alert_service, "
    "blast_radius_estimate, confidence) - always call it before deciding.\n\n"
    "Separately from policy_check, cross-check the proposal's target_service "
    "against the investigation findings' own evidence: does the evidence "
    "actually implicate that service, or does the proposal's target only "
    "come from the proposal's own justification text? A target not "
    "supported by the findings' evidence is a reason to reject regardless of "
    "what policy_check returns.\n\n"
    "If policy_check reports any policy_violations, blast_radius_exceeded, "
    "or confidence_below_floor, you must set approved=false and "
    "requires_human=true - these are hard constraints, not suggestions.\n\n"
    "You must never call a tool silently - every response with a tool call "
    "must include a plain-text sentence starting with 'Thought:'. Skip the "
    "Thought only on your final response.\n\n"
    "Your final response must be ONLY a JSON object: "
    '{"approved": bool, "reason": "...", "requires_human": bool}.'
)


def evaluate(alert: dict, proposal: dict, findings: dict, guarded: bool = True, console=None, max_steps: int = 4) -> dict:
    prompt = (
        f"Alert: {alert}\n\n"
        f"Proposed remediation: {proposal}\n\n"
        f"Original investigation findings (source evidence, not the "
        f"proposal's own summary of it): {findings}\n\n"
        "Evaluate this proposal."
    )
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    result = run_tool_loop(contents, [policy_check], set(), BASE_INSTRUCTION, max_steps, console)
    if result.exhausted:
        return {"approved": False, "reason": "evaluator did not conclude within step budget", "requires_human": True}
    return parse_json_final(result.final_text)
