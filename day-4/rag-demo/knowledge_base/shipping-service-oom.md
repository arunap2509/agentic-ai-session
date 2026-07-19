---
service: shipping-service
doc_type: runbook
env: prod
updated: 2026-05-05
---
# Runbook: shipping-service — OOMKilled pods

**Symptoms**: pods in `shipping-service` are OOMKilled (exit code 137)
after carrier rate lookups spike, e.g. during a rate-shopping promotion.

**Root cause**: carrier rate-lookup responses are cached in-process with no
upper bound on entry count, so a promotion that triggers many distinct
origin/destination pairs fills memory with cache entries that are each used
exactly once.

**Fix**:
1. Set `RATE_CACHE_MAX_ENTRIES` to `10000` (currently unbounded) to cap
   cache size with LRU eviction.
2. Restart the affected pods.

**Blast radius**: single-service, low risk. No approval required.
