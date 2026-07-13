"""policy_check - the Evaluator agent's tool. Checks a proposed remediation
against a static allow-list policy doc, not against the Evaluator's own
opinion - the point is that this check exists independent of whatever the
model feels about the proposal.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_BLAST_RADIUS_ORDER = ["single-instance", "single-service", "service-wide", "cross-service", "org-wide"]

_policy: dict | None = None


def _load() -> dict:
    global _policy
    if _policy is None:
        _policy = json.loads((FIXTURES / "policy.json").read_text())
    return _policy


def policy_check(action: str, target_service: str, alert_service: str, blast_radius_estimate: str, confidence: float) -> dict:
    """Check a proposed remediation action against the allow-list policy.

    Args:
        action: The proposed action, e.g. "restart", "rollback", "scale".
        target_service: The service the action would be applied to.
        alert_service: The service the original alert was about.
        blast_radius_estimate: One of single-instance/single-service/
            service-wide/cross-service/org-wide.
        confidence: The proposal's stated confidence, 0-1.
    """
    policy = _load()
    reasons = []

    if action not in policy["allowed_actions"]:
        reasons.append(f"action '{action}' is not in the allow-list {policy['allowed_actions']}")

    if target_service != alert_service:
        reasons.append(
            f"target service '{target_service}' does not match the alert's affected service "
            f"'{alert_service}' - {policy['target_scope_rule']}"
        )

    max_idx = _BLAST_RADIUS_ORDER.index(policy["auto_approve_max_blast_radius"])
    this_idx = _BLAST_RADIUS_ORDER.index(blast_radius_estimate) if blast_radius_estimate in _BLAST_RADIUS_ORDER else len(_BLAST_RADIUS_ORDER)
    blast_radius_exceeded = this_idx > max_idx
    confidence_too_low = confidence < policy["confidence_floor"]

    return {
        "policy_violations": reasons,
        "blast_radius_exceeded": blast_radius_exceeded,
        "confidence_below_floor": confidence_too_low,
    }
