---
service: none
doc_type: policy
env: prod
updated: 2026-01-10
---
# Policy: general on-call escalation ladder

Applies to all services **except** where a service-specific policy
overrides it — payment-service's PCI approval policy is the one override
that exists today.

**Ladder**: primary on-call (0–15 min) → secondary on-call (15–30 min) →
engineering manager (30–45 min) → VP Engineering (45+ min, sev-1 only).

Restarts and rollbacks classified as `single-service` blast radius are
pre-approved for the primary on-call to execute immediately, without
waiting for escalation, for every service governed only by this general
policy.
