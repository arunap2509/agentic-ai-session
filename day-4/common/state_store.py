"""Shared state keyed by run id (incident_id / research_id). Agents never talk
to each other directly - everything passes through orchestrator state, which
is what makes the audit trail complete: every handoff is a write here, not a
side-channel between two agents.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunState:
    run_id: str
    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def save(self, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{self.run_id}.json"
        path.write_text(json.dumps(asdict(self), indent=2, default=str))
        return path
