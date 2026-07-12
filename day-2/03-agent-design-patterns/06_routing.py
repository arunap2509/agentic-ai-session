"""
Pattern: Routing
==============================

Request comes in -> Router classifies intent -> sent to the right
specialist (billing / technical / general), instead of one agent
handling everything.

Run:
    python 06_routing.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask

console = Console()

SPECIALISTS = {
    "billing": "You are a billing support specialist. Be precise about charges, refunds, invoices.",
    "technical": "You are a technical support specialist. Be precise about error messages and fixes.",
    "general": "You are a general support agent. Be friendly and point to the right resource.",
}


def route(request: str) -> str:
    label = ask(
        f"Request: {request}\n\n"
        "Classify this into exactly one word: billing, technical, or general. "
        "Reply with only that one word."
    )
    label = label.strip().lower()
    return label if label in SPECIALISTS else "general"


def run(request: str) -> None:
    console.rule(f"Request: {request}")
    intent = route(request)
    console.print(f"[yellow]Router classified intent as:[/yellow] {intent}")

    reply = ask(request, system=SPECIALISTS[intent])
    console.print(f"[bold green]{intent.title()} specialist:[/bold green] {reply}")


if __name__ == "__main__":
    run("I was charged twice for my subscription this month.")
    run("The app crashes every time I upload a file over 10MB.")
    run("What are your support hours?")
