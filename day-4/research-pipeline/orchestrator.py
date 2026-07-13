"""Deterministic control flow: fan out to three workers concurrently, hand
condensed findings to the Reconciler, format, gate on a human before
publishing. Workers never talk to each other - everything passes through
this file's state, same discipline as incident-commander's orchestrator.
"""

import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents import background_worker, deep_dive_worker, recent_developments_worker, reconciler, report_writer
from tools.publish_report import publish_report

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.audit_log import AuditLog
from common.state_store import RunState

IDENTITY = {
    "background_worker": "background-worker@research-pipeline",
    "recent_developments_worker": "recent-developments-worker@research-pipeline",
    "deep_dive_worker": "deep-dive-worker@research-pipeline",
    "reconciler": "reconciler-agent@research-pipeline",
    "report_writer": "report-writer-fn@research-pipeline",
    "orchestrator": "orchestrator@research-pipeline",
    "human": "human-reviewer",
}

CONFIDENCE_FLOOR = 0.7


def run_research(
    question: str,
    fact_check_enabled: bool = True,
    interactive: bool = True,
    console: Console | None = None,
) -> dict:
    console = console or Console()
    run_id = f"res-{uuid.uuid4().hex[:8]}"
    audit = AuditLog(run_id=run_id)
    state = RunState(run_id=run_id)
    state.set("question", question)
    state.set("fact_check_enabled", fact_check_enabled)

    console.rule(f"[bold]Research {run_id}[/bold] - {question!r} - fact_check_enabled={fact_check_enabled}")

    console.rule("Workers (parallel)")
    with ThreadPoolExecutor(max_workers=3) as pool:
        background_future = pool.submit(background_worker.research, question, console)
        recent_future = pool.submit(recent_developments_worker.research, question, console)
        deep_dive_future = pool.submit(deep_dive_worker.research, question, console)
        background = background_future.result()
        recent = recent_future.result()
        deep_dive = deep_dive_future.result()

    audit.record("background_worker", IDENTITY["background_worker"], "research", question, background)
    audit.record("recent_developments_worker", IDENTITY["recent_developments_worker"], "research", question, recent)
    audit.record("deep_dive_worker", IDENTITY["deep_dive_worker"], "research", question, deep_dive)
    state.set("background", background)
    state.set("recent", recent)
    state.set("deep_dive", deep_dive)

    console.rule("Reconciler")
    findings = {"background": background, "recent_developments": recent, "deep_dive": deep_dive}
    reconciled = reconciler.reconcile(findings, fact_check_enabled=fact_check_enabled, console=console)

    # Hard-coded confidence floor: a worker's claims need fact_check
    # regardless of how the Reconciler feels about them - code decides the
    # guardrail, not the model. Only meaningful when fact_check ran at all.
    if fact_check_enabled:
        for name, finding in findings.items():
            if finding.get("confidence", 1.0) < CONFIDENCE_FLOOR:
                note = f"{name} confidence {finding.get('confidence')} below floor {CONFIDENCE_FLOOR} - forced into unresolved_conflicts"
                if not any(name in c for c in reconciled.get("unresolved_conflicts", [])):
                    reconciled.setdefault("unresolved_conflicts", []).append(note)
                    audit.record("orchestrator", IDENTITY["orchestrator"], "confidence_floor_override", finding, note)

    audit.record("reconciler", IDENTITY["reconciler"], "reconcile", findings, reconciled)
    state.set("reconciled", reconciled)
    console.print(f"[magenta]Reconciled:[/magenta] {reconciled}")

    report_text = report_writer.write_report(question, background, recent, deep_dive, reconciled)
    audit.record("report_writer", IDENTITY["report_writer"], "write_report", run_id, "generated")
    state.set("report", report_text)

    console.rule("Human gate")
    if interactive:
        console.print(report_text)
        answer = input("Publish this report? [y/N]: ").strip().lower()
        human_decision = "approved" if answer == "y" else "denied"
    else:
        human_decision = "needs_review"
    audit.record("human", IDENTITY["human"], "publish_decision", run_id, human_decision)
    state.set("human_decision", human_decision)

    if human_decision == "approved":
        result = publish_report(run_id, report_text)
    else:
        result = {"status": "held_back", "reason": human_decision}
    audit.record("orchestrator", IDENTITY["orchestrator"], "publish_report", run_id, result)
    state.set("publish_result", result)

    state.set("audit_log", audit.entries)
    runs_dir = Path(__file__).resolve().parent / "runs"
    state.save(runs_dir)

    return {"run_id": run_id, "state": state.data, "audit": audit}
