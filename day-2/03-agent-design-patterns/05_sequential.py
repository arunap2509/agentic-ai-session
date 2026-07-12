"""
Pattern: Sequential
=================================

Agent A -> Agent B -> Agent C
One agent's output becomes the next agent's input, straight down the line.
Each "agent" here is just the same model with a different system prompt -
the point is the pipeline shape, not the model.

Run:
    python 05_sequential.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask

console = Console()


def run(topic: str) -> None:
    console.rule("Sequential pipeline")
    console.print(f"[bold cyan]Topic:[/bold cyan] {topic}\n")

    outline = ask(
        f"Topic: {topic}",
        system="You are Agent A: Outliner. Produce a 3-bullet outline for a short post. Bullets only.",
    )
    console.print(f"[yellow]Agent A (outline):[/yellow]\n{outline}\n")

    draft = ask(
        f"Outline:\n{outline}",
        system="You are Agent B: Drafter. Turn the given outline into a short 3-paragraph draft.",
    )
    console.print(f"[blue]Agent B (draft):[/blue]\n{draft}\n")

    final = ask(
        f"Draft:\n{draft}",
        system="You are Agent C: Editor. Tighten the given draft, fix any awkward phrasing, keep it short.",
    )
    console.print(f"[bold green]Agent C (final):[/bold green]\n{final}")


if __name__ == "__main__":
    run("Why code review catches bugs that tests miss")
