"""Deterministic control flow, not a prompted "meta-agent". Every handoff
between agents passes through this file's state and gets logged here -
agents never call each other directly. This is itself the Day 1 teaching
point: an orchestrator is a workflow that calls agents, not an agent itself.

Pipeline: alert -> triage -> investigators -> runbook lookup -> planner ->
[broken: execute immediately] | [fixed: evaluator -> threshold override ->
human gate -> execute] -> postmortem.
"""

import sys
import uuid
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents import evaluator, log_investigator, metrics_investigator, postmortem, remediation_planner
from agents.triage import triage
from tools.notify import notify
from tools.remediation_execute import remediation_execute
from tools.runbook_retrieval import runbook_retrieval
from tools.ticket import ticket_create_update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.audit_log import AuditLog
from common.state_store import RunState

IDENTITY = {
    "triage": "triage-fn@incident-commander",
    "log_investigator": "log-investigator-agent@incident-commander",
    "metrics_investigator": "metrics-investigator-agent@incident-commander",
    "runbook_retrieval": "runbook-lookup@incident-commander",
    "remediation_planner": "remediation-planner-agent@incident-commander",
    "evaluator": "evaluator-agent@incident-commander",
    "orchestrator": "orchestrator@incident-commander",
    "human": "human-reviewer",
    "postmortem": "postmortem-fn@incident-commander",
}

HARD_BLAST_RADIUS_ESCALATION = {"service-wide", "cross-service", "org-wide"}
HARD_CONFIDENCE_FLOOR = 0.8


def run_incident(
    alert: dict,
    mode: str = "fixed",
    guarded: bool = True,
    real_metrics_mode: bool = True,
    interactive: bool = True,
    console: Console | None = None,
) -> dict:
    """mode: "broken" (no evaluator, no allow-list, no human gate) or "fixed".
    guarded: whether agents get the untrusted-data-envelope instruction.
    interactive: if False, a human gate returns needs_review instead of
    blocking on input() - required for any non-interactive/scripted run.
    """
    console = console or Console()
    incident_id = f"inc-{uuid.uuid4().hex[:8]}"
    audit = AuditLog(run_id=incident_id)
    state = RunState(run_id=incident_id)
    state.set("alert", alert)
    state.set("mode", mode)

    console.rule(f"[bold]Incident {incident_id}[/bold] - mode={mode} guarded={guarded}")

    # 1. Triage - plain function, one shot
    triage_result = triage(alert)
    audit.record("triage", IDENTITY["triage"], "classify_alert", alert, triage_result)
    state.set("triage", triage_result)
    console.print(f"[cyan]Triage:[/cyan] {triage_result}")

    ticket = ticket_create_update(incident_id, "create", {
        "status": "investigating", "severity": triage_result.get("severity"), "category": triage_result.get("category"),
    })
    audit.record("orchestrator", IDENTITY["orchestrator"], "ticket_create", alert, ticket)

    # 2. Investigators - real agents, sequential for readable live output
    console.rule("Log Investigator")
    log_finding = log_investigator.investigate(alert, guarded=guarded, console=console)
    audit.record("log_investigator", IDENTITY["log_investigator"], "investigate", alert, log_finding)
    state.set("log_finding", log_finding)

    console.rule("Metrics Investigator")
    metrics_finding = metrics_investigator.investigate(alert, real_mode=real_metrics_mode, console=console)
    audit.record("metrics_investigator", IDENTITY["metrics_investigator"], "investigate", alert, metrics_finding)
    state.set("metrics_finding", metrics_finding)

    findings = {"log_investigator": log_finding, "metrics_investigator": metrics_finding}

    # 3. Runbook lookup - not an agent, plain orchestrator call. Broken mode
    # skips it for the Planner: a genuinely naive first build didn't wire up
    # retrieval grounding either, it's not just the data envelope/gates that
    # are missing - that's what "broken" means here, not an artificial
    # handicap layered on top of an otherwise-complete pipeline.
    runbook_snippets = runbook_retrieval(f"{alert['category']} {log_finding.get('summary', '')}")
    audit.record("orchestrator", IDENTITY["orchestrator"], "runbook_retrieval", alert["category"], [r["runbook"] for r in runbook_snippets])
    planner_runbook_snippets = runbook_snippets if mode == "fixed" else []

    # 4. Remediation Planner - real agent, proposes only, no tools.
    # In broken mode, hand it raw, unfiltered log lines instead of the
    # curated finding - this is the actual vulnerability: no data envelope,
    # no compression before handoff, so anything embedded in raw log text
    # reaches the Planner's context verbatim. Fixed mode only ever hands it
    # the curated summary+cited-evidence, never raw tool output.
    planner_findings = dict(findings)
    if mode == "broken":
        planner_findings["log_investigator"] = {
            "summary": log_finding.get("summary"),
            "raw_log_lines": log_finding.get("raw_observations", []),
        }
    console.rule("Remediation Planner")
    proposal = remediation_planner.plan(alert, planner_findings, planner_runbook_snippets, guarded=guarded)
    audit.record("remediation_planner", IDENTITY["remediation_planner"], "propose", findings, proposal)
    state.set("proposal", proposal)
    console.print(f"[yellow]Proposal:[/yellow] {proposal}")

    if mode == "broken":
        result = _execute_broken(alert, proposal, audit, state, console)
    else:
        result = _execute_fixed(alert, proposal, findings, guarded, interactive, audit, state, console)

    # 5. Postmortem - templated, not an agent
    doc = postmortem.write_postmortem(state.data)
    audit.record("postmortem", IDENTITY["postmortem"], "write_postmortem", incident_id, "generated")
    state.set("postmortem", doc)

    notify_result = notify("#incidents", f"Incident {incident_id} postmortem ready.")
    audit.record("orchestrator", IDENTITY["orchestrator"], "notify", "#incidents", notify_result)

    state.set("audit_log", audit.entries)
    runs_dir = Path(__file__).resolve().parent / "runs"
    state.save(runs_dir)

    return {"incident_id": incident_id, "state": state.data, "audit": audit}


def _execute_broken(alert: dict, proposal: dict, audit: AuditLog, state: RunState, console: Console) -> dict:
    """No evaluator, no allow-list, no human gate - executes the Planner's
    proposal immediately. This is the vulnerable path demo_broken.py uses."""
    console.rule("[red]EXECUTE (broken - no gate)[/red]")
    result = remediation_execute(
        action=proposal.get("proposed_action", ""),
        target=proposal.get("target_service", ""),
        params={},
        evaluator_approval=True,
        allow_list_enabled=False,
    )
    audit.record("orchestrator", IDENTITY["orchestrator"], "remediation_execute", proposal, result)
    state.set("execution_result", result)
    console.print(f"[bold red]Executed:[/bold red] {result}")
    return result


def _execute_fixed(alert, proposal, findings, guarded, interactive, audit, state, console) -> dict:
    console.rule("Evaluator")
    decision = evaluator.evaluate(alert, proposal, findings, guarded=guarded, console=console)
    audit.record("evaluator", IDENTITY["evaluator"], "evaluate", proposal, decision)
    state.set("evaluator_decision", decision)
    console.print(f"[magenta]Evaluator decision:[/magenta] {decision}")

    blast_radius = proposal.get("blast_radius_estimate", "org-wide")
    confidence = proposal.get("confidence", 0.0)
    forced_human = blast_radius in HARD_BLAST_RADIUS_ESCALATION or confidence < HARD_CONFIDENCE_FLOOR
    requires_human = decision.get("requires_human", True) or forced_human

    if forced_human:
        audit.record(
            "orchestrator", IDENTITY["orchestrator"], "hard_threshold_override",
            {"blast_radius": blast_radius, "confidence": confidence},
            "requires_human forced True by code, independent of evaluator/model",
        )

    human_decision = None
    if requires_human:
        if interactive:
            console.print(
                f"[bold red]Human review required[/bold red] - blast_radius={blast_radius}, "
                f"confidence={confidence}, evaluator_approved={decision.get('approved')}"
            )
            answer = input(f"Approve {proposal.get('proposed_action')} on {proposal.get('target_service')}? [y/N]: ").strip().lower()
            human_decision = "approved" if answer == "y" else "denied"
        else:
            human_decision = "needs_review"
        audit.record("human", IDENTITY["human"], "review_decision", proposal, human_decision)
        state.set("human_decision", human_decision)

    should_execute = decision.get("approved", False) and (not requires_human or human_decision == "approved")

    if not should_execute:
        reason = decision.get("reason", "not approved")
        if requires_human and human_decision != "approved":
            reason = f"held for human review ({human_decision})" if human_decision else "held for human review"
        result = {"status": "held_back", "reason": reason}
        audit.record("orchestrator", IDENTITY["orchestrator"], "remediation_execute_skipped", proposal, result)
        state.set("execution_result", result)
        console.print(f"[bold yellow]Not executed:[/bold yellow] {result}")
        return result

    console.rule("[green]EXECUTE (fixed - gated)[/green]")
    result = remediation_execute(
        action=proposal.get("proposed_action", ""),
        target=proposal.get("target_service", ""),
        params={},
        evaluator_approval=True,
        allow_list_enabled=True,
    )
    audit.record("orchestrator", IDENTITY["orchestrator"], "remediation_execute", proposal, result)
    state.set("execution_result", result)
    console.print(f"[bold green]Executed:[/bold green] {result}")
    return result
