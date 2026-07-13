"""Run this live first. No fact_check wired into the Reconciler - whatever
each worker asserts, including any unverified specific detail the Deep
Dive Worker surfaces, merges into the report at face value.

This uses live web search - the outcome is genuinely live, not scripted.
Watch what the Deep Dive Worker actually claims and whether it survives
into the final report unquestioned.

Run:
    python demo_broken.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import run_research

console = Console()

QUESTION = "What is the tallest building in the world?"

if __name__ == "__main__":
    result = run_research(QUESTION, fact_check_enabled=False, interactive=False, console=console)
    console.rule("[bold red]Report[/bold red]")
    console.print(result["state"]["report"])
    result["audit"].print_summary(console, title=f"Audit Trail - {result['run_id']} (BROKEN)")
