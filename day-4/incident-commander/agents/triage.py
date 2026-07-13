"""Triage - deliberately NOT an agent. One-shot classification, no tools, no
iteration, built as a plain function on purpose. It's in Day 2's Routing
pattern list, which tempts people into calling it an agent - it isn't one:
nothing here iterates, holds state, or exercises judgment across multiple
steps. It fails both the "needs iteration" and "needs isolated context" tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common.json_utils import parse_json_final
from common.llm import TRIAGE_MODEL, get_client

INSTRUCTION = (
    "Classify this monitoring alert. Respond with ONLY a JSON object: "
    '{"severity": "low|med|high|critical", "category": "perf|error|outage|security"}.'
)


def triage(alert: dict) -> dict:
    client = get_client()
    response = client.models.generate_content(
        model=TRIAGE_MODEL,
        contents=f"Alert payload: {alert}",
        config={"system_instruction": INSTRUCTION},
    )
    return parse_json_final(response.text)
