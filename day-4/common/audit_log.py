"""Append-only audit trail. Every tool call and every agent handoff gets one
entry here - this log is the Agent Identity payoff: after a run, you can
point at exactly which agent proposed what and which agent (or human) caught
it, not just that "the system" did something.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from rich.console import Console
from rich.table import Table


@dataclass
class AuditLog:
    run_id: str
    entries: list[dict] = field(default_factory=list)

    def record(self, agent_id: str, agent_identity: str, action: str, input: Any, output: Any) -> None:
        self.entries.append({
            "agent_id": agent_id,
            "agent_identity": agent_identity,
            "action": action,
            "input": input,
            "output": output,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def print_summary(self, console: Console, title: str = "Audit Trail") -> None:
        table = Table(title=title)
        table.add_column("Agent")
        table.add_column("Identity", style="dim")
        table.add_column("Action")
        table.add_column("Output", overflow="fold")
        for e in self.entries:
            table.add_row(e["agent_id"], e["agent_identity"], e["action"], str(e["output"])[:120])
        console.print(table)
