---
service: auth-service
doc_type: runbook
env: prod
updated: 2026-05-20
---
# Runbook: auth-service — OOMKilled pods

**Symptoms**: pods in `auth-service` are OOMKilled (exit code 137). Usually
follows a period of elevated login traffic, e.g. after a marketing push.

**Root cause**: the JWT revocation blacklist is held in an in-process cache
with no size bound or TTL, so every token revoked since the last deploy
stays resident in memory.

**Fix**:
1. Flush the in-process blacklist cache by calling the internal
   `/admin/cache/blacklist/flush` endpoint (safe — revoked tokens re-sync
   from Redis on the next read).
2. Restart the affected pods.
3. Longer-term fix (already ticketed): move the blacklist to Redis-backed
   storage with a TTL matching token expiry.

**Blast radius**: single-service, low risk. No approval required.
