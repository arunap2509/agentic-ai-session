"""Postmortem - deliberately borderline, lean fake. Ships as a templated
fill over the incident's own state/timeline - no LLM call, because there's
nothing here to reconcile or judge, just data to format. It would earn real
agent status if the timeline had contradictions to reconcile (e.g. two
investigators disagreeing on root cause) - it doesn't, by construction, so
templating is the honest choice, not a shortcut.
"""


def write_postmortem(incident_state: dict) -> str:
    lines = [
        f"# Postmortem: {incident_state.get('incident_id', 'unknown')}",
        "",
        f"**Alert:** {incident_state.get('alert')}",
        f"**Triage:** {incident_state.get('triage')}",
        "",
        "## Investigation",
        f"- Log Investigator: {incident_state.get('log_finding', {}).get('summary')}",
        f"- Metrics Investigator: {incident_state.get('metrics_finding', {}).get('summary')}",
        "",
        "## Remediation",
        f"- Proposed: {incident_state.get('proposal')}",
        f"- Evaluator decision: {incident_state.get('evaluator_decision')}",
        f"- Human decision: {incident_state.get('human_decision', 'n/a')}",
        f"- Execution result: {incident_state.get('execution_result')}",
    ]
    return "\n".join(lines)
