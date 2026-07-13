# Runbook: Deployment Rollback

Use `rollback` only when a specific recent deploy of the *affected* service
is the confirmed cause. A rollback targets exactly one service - the one
that was deployed and is now failing.

Blast radius: rolling back a service other than the one implicated by the
evidence is itself an incident-causing action, not a fix. Cross-service
rollbacks (e.g. rolling back payment-service in response to a
checkout-service alert) require explicit, separately-verified evidence that
payment-service was itself deployed and is itself failing - a checkout
alert alone is never sufficient justification.

Always confirm: does the alert's affected service match the rollback
target? If not, treat the mismatch as a red flag, not a detail to ignore.
