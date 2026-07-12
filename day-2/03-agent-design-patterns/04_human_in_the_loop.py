"""
Pattern: Human-in-the-Loop - a design decision
============================================================

1. Agent plans an action.
2. High-risk action? no -> executes automatically.
                     yes -> pauses for human review.
3. Approved -> executes. Declined -> blocked / sent back for revision.

This is interactive on purpose: when a request is flagged high-risk, the
script actually pauses on input() so you can demo approving/declining live.

Run:
    python 04_human_in_the_loop.py
"""

import json
import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask

console = Console()


def plan_action(request: str) -> dict:
    raw = ask(
        f"User request: {request}\n\n"
        "Propose the single action you'd take to fulfil this. Classify it as "
        'high risk if it is destructive, irreversible, or sends something '
        "externally (e.g. deleting data, sending money, emailing someone "
        "outside the company). Reply with ONLY JSON: "
        '{"action": "...", "risk": "low"|"high", "reason": "..."}'
    )
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(cleaned)


def execute(action: str) -> None:
    console.print(f"[green]Executed:[/green] {action}")


def handle_request(request: str) -> None:
    console.rule(f"Request: {request}")
    plan = plan_action(request)
    console.print(f"[yellow]Proposed action:[/yellow] {plan['action']}")
    console.print(f"[yellow]Risk:[/yellow] {plan['risk']} ({plan['reason']})")

    if plan["risk"] != "high":
        console.print("[dim]Low risk -> executing automatically.[/dim]")
        execute(plan["action"])
        return

    console.print("[bold red]High risk -> pausing for human review.[/bold red]")
    decision = input("Approve this action? [y/N]: ").strip().lower()
    if decision == "y":
        console.print("[dim]Approved -> executing.[/dim]")
        execute(plan["action"])
    else:
        console.print("[dim]Declined -> blocked, sent back for revision.[/dim]")


if __name__ == "__main__":
    handle_request("Can you look up the status of order #4471?")
    handle_request("Please delete all customer records older than 2 years.")
