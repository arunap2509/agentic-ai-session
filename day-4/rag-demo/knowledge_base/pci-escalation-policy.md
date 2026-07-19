---
service: payment-service
doc_type: policy
env: prod
updated: 2026-03-01
---
# Policy: PCI-scoped change approval for payment-service

`payment-service` runs inside the cardholder data environment (CDE) and is
in PCI DSS scope. This changes the approval bar for **any** production
action taken against it, including actions that would otherwise be
pre-approved low-blast-radius fixes elsewhere in the stack.

**Rule**: any `restart`, `rollback`, or config change applied to
`payment-service` in `prod` requires sign-off from a Compliance-tagged
approver recorded on the incident ticket *before* the action is taken.
This applies even to a plain pod restart — there is no "single-service,
low risk, skip approval" exception for this service, unlike every other
service in this table.

**Exception**: flipping the `PAYMENT_CB_FALLBACK` flag (see the
payment-service latency runbook) is pre-approved and does not require this
sign-off — it was reviewed and blanket-approved by Compliance in Q1 2026.

**Why**: CDE changes are subject to audit. An unlogged production change to
a PCI-scoped service is itself a compliance finding, independent of
whether the change was technically correct.
