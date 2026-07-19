---
service: payment-service
doc_type: runbook
env: prod
updated: 2026-06-15
---
# Runbook: payment-service — p99 latency spikes

**Symptoms**: `payment-service` p99 latency exceeds 2s while error rate
stays low. Logs show `Stripe gateway timeout code 504` entries clustering
in the same window.

**Root cause**: the upstream card-network provider (Stripe) is slow to
respond. This is an upstream dependency issue, not a payment-service
defect.

**Fix**:
1. Confirm via Stripe's status page that the gateway is degraded.
2. Enable the circuit breaker fallback flag `PAYMENT_CB_FALLBACK=true` to
   route new charges through the secondary processor while Stripe recovers.
3. Do not `scale` payment-service in response to this — added instances
   don't reduce Stripe's response time.

**Blast radius**: single-service. Flipping `PAYMENT_CB_FALLBACK` is
pre-approved for exactly this scenario — see the payment-service PCI
approval policy for why this flag is called out as an exception.
