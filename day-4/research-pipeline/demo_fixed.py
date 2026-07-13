"""The fix, live: mandatory fact_check on every specific claim before it
can enter reconciled_summary, a hard-coded confidence floor, flagged-not-
hidden conflicts, and a human gate before publish.

Run:
    python demo_fixed.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import run_research

console = Console()

QUESTION = "What is the tallest building in the world?"

if __name__ == "__main__":
    result = run_research(QUESTION, fact_check_enabled=True, interactive=True, console=console)
    console.rule("[bold green]Report[/bold green]")
    console.print(result["state"]["report"])
    result["audit"].print_summary(console, title=f"Audit Trail - {result['run_id']} (FIXED)")
