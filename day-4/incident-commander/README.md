# Deployment Incident Commander

A monitoring alert comes in, gets triaged, investigated (logs + metrics),
a remediation gets proposed, independently checked, and executed if safe
(or held for a human), then a postmortem gets written.

## Setup

From `day-4/` (one level up):
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste in your GEMINI_API_KEY
```

## How to run

```
cd incident-commander
python demo_broken.py   # no allow-list, no evaluator, no human gate
python demo_fixed.py    # all guardrails on
```

Both print a full transcript of every agent call plus an audit trail
table at the end (`{agent_id, agent_identity, action, input, output,
timestamp}` per row).

## Examples

`demo_broken.py`/`demo_fixed.py` use one fixed alert. To try others, call
the orchestrator directly:

```python
import sys; sys.path.insert(0, ".")
from rich.console import Console
from orchestrator import run_incident

result = run_incident(
    {"service": "checkout-service", "category": "error", "severity": "high", "time": "2026-07-13T04:15:00Z"},
    mode="fixed",       # or "broken"
    guarded=True,       # data/instruction envelope framing on/off
    interactive=False,  # False = never blocks on input(), returns needs_review instead
    console=Console(),
)
print(result["state"]["execution_result"])
```

All available data lives in an 8-hour window starting `2026-07-13T00:00:00Z`.
Five to try:

1. ```python
   {"service": "checkout-service", "category": "error", "severity": "high", "time": "2026-07-13T04:15:00Z"}
   ```
2. ```python
   {"service": "checkout-service", "category": "error", "severity": "high", "time": "2026-07-13T04:10:00Z"}
   ```
3. ```python
   {"service": "checkout-service", "category": "perf", "severity": "low", "time": "2026-07-13T02:00:00Z"}
   ```
4. ```python
   {"service": "shipping-service", "category": "perf", "severity": "med", "time": "2026-07-13T01:20:00Z"}
   ```
5. ```python
   {"service": "auth-service", "category": "error", "severity": "med", "time": "2026-07-13T05:30:00Z"}
   ```

Other option: `real_metrics_mode=False` on the Metrics Investigator (single
query instead of correlating two metrics).

## What each component does

- **Triage** (`agents/triage.py`) — a plain function, not an agent. One
  call classifies the alert's severity and category.
- **Log Investigator** (`agents/log_investigator.py`) — searches logs
  over multiple turns to find the root cause.
- **Metrics Investigator** (`agents/metrics_investigator.py`) — checks
  metrics (latency, error rate, deploy events) for correlation with the
  incident.
- **Runbook Retrieval** (`tools/runbook_retrieval.py`) — a plain lookup
  (keyword match), not an agent. Finds relevant runbook guidance.
- **Remediation Planner** (`agents/remediation_planner.py`) — proposes a
  fix based on the investigation findings and runbook guidance. Has no
  tools and never executes anything itself.
- **Evaluator** (`agents/evaluator.py`) — independently checks the
  proposed fix against policy and the original evidence before it's
  allowed to run.
- **Postmortem** (`agents/postmortem.py`) — a plain function that
  formats a summary of the incident and its resolution.
- **Orchestrator** (`orchestrator.py`) — runs the whole pipeline: triage
  → investigate → propose → evaluate → execute or escalate → postmortem.

**Tools** (`tools/`): `log_search`, `metrics_query`, `runbook_retrieval`,
`ticket_create_update`, `notify`, `policy_check`, `remediation_execute`.
