"""Metrics Investigator - deliberately borderline, built to go either way via
`real_mode`. In fake mode it's one metrics_query call and done - genuinely
should be a function, not an agent. In real mode it must correlate two
metrics (e.g. latency vs. deploy_events) before concluding, which is a real
multi-turn judgment call. Ship both; this is the best live "is this actually
an agent" discussion piece in the roster.
"""

import sys
from pathlib import Path

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.metrics_query import metrics_query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.agent_loop import run_tool_loop
from common.json_utils import parse_json_final

FAKE_INSTRUCTION = (
    "You are the Metrics Investigator. You have one tool, metrics_query. "
    "Call it exactly once for the most relevant metric, then immediately "
    "give your final answer from that single result - do not make a second "
    "tool call.\n\n"
    "Your final response must be ONLY a JSON object: "
    '{"summary": "...", "evidence": ["..."], "confidence": 0.0-1.0}.'
)

REAL_INSTRUCTION = (
    "You are the Metrics Investigator agent in an incident response system. "
    "You have one tool, metrics_query(metric, service, time_range). "
    "A single metric in isolation is not sufficient evidence of a "
    "deploy-caused regression - you must correlate at least two metrics over "
    "the same window (e.g. latency_p99_ms or error_rate_pct against "
    "deploy_events) and reason explicitly about whether the timing lines up "
    "before concluding. "
    "You must never call a tool silently - every response with a tool call "
    "must include a plain-text sentence starting with 'Thought:'. Skip the "
    "Thought only on your final response.\n\n"
    "Your final response must be ONLY a JSON object: "
    '{"summary": "...", "evidence": ["..."], "confidence": 0.0-1.0}. '
    "evidence must cite the actual metric values/timestamps you retrieved."
)


def investigate(alert: dict, real_mode: bool = True, console=None, max_steps: int = 6) -> dict:
    instruction = REAL_INSTRUCTION if real_mode else FAKE_INSTRUCTION
    question = (
        f"Alert: {alert['service']} reporting a {alert['category']} issue "
        f"around {alert['time']}. Investigate the metrics and determine "
        "whether this correlates with a recent deploy."
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    result = run_tool_loop(contents, [metrics_query], set(), instruction, max_steps, console)
    if result.exhausted:
        return {"summary": "investigation did not conclude within step budget", "evidence": [], "confidence": 0.0}
    return parse_json_final(result.final_text)
