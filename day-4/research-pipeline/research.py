"""Interactive entry point - type any research question, live.

Run:
    python research.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import run_research

console = Console()

if __name__ == "__main__":
    console.print("[bold]Multi-Source Analyst[/bold] - ask a research question, blank line to quit.\n")
    while True:
        question = input("Research question: ").strip()
        if not question:
            break
        run_research(question, fact_check_enabled=True, interactive=True, console=console)
        console.print()
