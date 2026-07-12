"""
Data Analyst Agent - memory.py

Two turns: "What was total revenue in Q1 2026?" then "Now break that down
by region." - note the second question never restates "Q1 2026". The
stateful version carries the conversation history forward, so the model
can resolve "that" from Turn 1. The stateless control runs the same
follow-up as a fresh call with no prior turn, to show what's actually
being bought by keeping the history around - not asserted, demonstrated.

Run:
    python memory.py
"""

import sys
from pathlib import Path

from google.genai import types
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from base_agent import DB_PATH, SYSTEM_INSTRUCTION, run_query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.agent_loop import run_tool_loop

console = Console()

TURN_1 = "What was total revenue in Q1 2026?"
TURN_2 = "Now break that down by region."


def main() -> None:
    console.rule("Stateful - same conversation, history kept")
    console.print(f"[bold cyan]Turn 1:[/bold cyan] {TURN_1}")
    contents = [types.Content(role="user", parts=[types.Part(text=TURN_1)])]
    result = run_tool_loop(contents, [run_query], set(), SYSTEM_INSTRUCTION, max_steps=4, console=console)
    console.print(f"[green]Answer:[/green] {result.final_text}\n")

    console.print(f"[bold cyan]Turn 2:[/bold cyan] {TURN_2}")
    contents.append(types.Content(role="user", parts=[types.Part(text=TURN_2)]))
    result = run_tool_loop(contents, [run_query], set(), SYSTEM_INSTRUCTION, max_steps=4, console=console)
    console.print(f"[green]Answer:[/green] {result.final_text}\n")

    console.rule("Stateless control - Turn 2 asked fresh, no Turn 1 history")
    console.print(f"[bold cyan]Question:[/bold cyan] {TURN_2}")
    fresh_contents = [types.Content(role="user", parts=[types.Part(text=TURN_2)])]
    result = run_tool_loop(fresh_contents, [run_query], set(), SYSTEM_INSTRUCTION, max_steps=4, console=console)
    console.print(f"[red]Answer:[/red] {result.final_text}")


if __name__ == "__main__":
    main()
