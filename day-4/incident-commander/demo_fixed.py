"""The 4-part fix, live: (1) untrusted-data envelope framing on every agent
that touches raw log/finding content, (2) allow-list + enum action on
remediation_execute, (3) hard-coded blast-radius/confidence threshold
forcing human review independent of the Evaluator's own judgment, (4) a
real human-in-the-loop gate before anything executes.

Run:
    python demo_fixed.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import run_incident

console = Console()

ALERT = {
    "service": "checkout-service",
    "category": "error",
    "severity": "high",
    "time": "2026-07-13T04:15:00Z",
}

if __name__ == "__main__":
    result = run_incident(ALERT, mode="fixed", guarded=True, interactive=True, console=console)
    console.rule("[bold green]Result[/bold green]")
    console.print(result["state"]["execution_result"])
    result["audit"].print_summary(console, title=f"Audit Trail - {result['incident_id']} (FIXED)")
