"""THE DANGEROUS ONE. Called only by orchestrator.py as a plain Python
function - it is never registered as a tool on any agent's tool-loop. That's
deliberate and load-bearing: `evaluator_approval` must only be settable by
the orchestrator after a real Evaluator decision, and the only way to
guarantee a model can never set it itself is to never let a model see this
function as something it can call with arbitrary arguments.

`allow_list_enabled=True` is the fixed version. `allow_list_enabled=False`
is the broken version demo_broken.py uses on purpose.
"""

ALLOWED_ACTIONS = {"restart", "rollback", "scale"}

_EXECUTION_LOG: list[dict] = []


def remediation_execute(
    action: str,
    target: str,
    params: dict,
    evaluator_approval: bool = False,
    allow_list_enabled: bool = True,
) -> dict:
    """EXECUTE: Apply a remediation action to a service. Not reversible.

    Args:
        action: restart | rollback | scale (enforced when allow_list_enabled).
        target: The service to apply the action to.
        params: Action-specific parameters.
        evaluator_approval: Must be True, set only by the orchestrator after
            the Evaluator agent approves - never accept this from a model.
        allow_list_enabled: True = fixed guardrails on. False = broken demo.
    """
    if allow_list_enabled:
        if action not in ALLOWED_ACTIONS:
            result = {"status": "rejected", "reason": f"action '{action}' not in allow-list {sorted(ALLOWED_ACTIONS)}"}
            _EXECUTION_LOG.append({"action": action, "target": target, **result})
            return result
        if not evaluator_approval:
            result = {"status": "rejected", "reason": "evaluator_approval is required and was not granted"}
            _EXECUTION_LOG.append({"action": action, "target": target, **result})
            return result

    result = {"status": "executed", "action": action, "target": target, "params": params}
    _EXECUTION_LOG.append(result)
    return result


def execution_log() -> list[dict]:
    return list(_EXECUTION_LOG)
