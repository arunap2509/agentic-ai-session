"""
Pattern: Planning - full plan before execution
============================================================

Build plan (full task list) -> Step 1 -> Step 2 -> Step 3 -> ...
The full plan exists before execution starts, so a long task can't drift
off-goal - there's nothing to drift from, the steps are already fixed.

Run:
    python 03_planning.py
"""

import json
import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask

console = Console()


def build_plan(goal: str) -> list[str]:
    raw = ask(
        f"Goal: {goal}\n\n"
        "Break this into 3-5 short, ordered steps needed to reach the goal. "
        'Reply with ONLY a JSON array of strings, e.g. ["step one", "step two"].'
    )
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(cleaned)


def run(goal: str) -> None:
    console.rule("Planning: build the plan upfront")
    console.print(f"[bold cyan]Goal:[/bold cyan] {goal}\n")

    plan = build_plan(goal)
    console.print("[yellow]Full plan:[/yellow]")
    for i, step in enumerate(plan, 1):
        console.print(f"  {i}. {step}")
    console.print()

    console.rule("Executing the plan step by step")
    results = []
    for i, step in enumerate(plan, 1):
        context = "\n".join(f"- {s}: {r}" for s, r in zip(plan, results)) or "(none yet)"
        output = ask(
            f"Overall goal: {goal}\nPlan so far completed:\n{context}\n\n"
            f"Now execute just this step and report the result concisely: {step}"
        )
        console.print(f"[blue]Step {i} - {step}[/blue]\n  -> {output}\n")
        results.append(output)

    console.print("[bold green]Plan complete.[/bold green]")


if __name__ == "__main__":
    run("Draft a one-paragraph announcement for a new internal API rate limit policy.")
