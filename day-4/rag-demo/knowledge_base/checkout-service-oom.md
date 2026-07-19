---
service: checkout-service
doc_type: runbook
env: prod
updated: 2026-06-10
---
# Runbook: checkout-service — OOMKilled pods

**Symptoms**: pods in `checkout-service` are OOMKilled (exit code 137)
during high-traffic windows such as flash sales or holiday spikes.

**Root cause**: abandoned cart sessions are cached in-process and only
evicted on checkout completion — sessions from users who add to cart and
leave never expire, so memory grows with traffic instead of settling.

**Fix**:
1. Set the `SESSION_TTL_SECONDS` config value (currently unset, defaults to
   "never expire") to `1800` so idle cart sessions evict automatically.
2. Restart the affected pods to pick up the new config.
3. No code change needed — this is a config-only fix.

**Blast radius**: single-service, low risk. No approval required.
