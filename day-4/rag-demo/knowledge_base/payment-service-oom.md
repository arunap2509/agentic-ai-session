---
service: payment-service
doc_type: runbook
env: prod
updated: 2026-06-02
---
# Runbook: payment-service — OOMKilled pods

**Symptoms**: pods in `payment-service` are OOMKilled (exit code 137), usually
correlating with checkout traffic spikes. `kubectl get pods -n payment` shows
repeated restarts; `kubectl describe pod` shows `Reason: OOMKilled`.

**Root cause**: the fraud-scoring cache inside the request path grows
unbounded during traffic spikes because scored transactions aren't evicted
until a nightly batch job runs. Under sustained load the JVM heap exceeds
the container's memory limit before that job fires.

**Fix**:
1. Bump the container memory limit from `512Mi` to `1Gi` in the
   `payment-service` deployment manifest.
2. Set `-XX:MaxRAMPercentage=75.0` on the JVM so heap sizing stays
   proportional to the new limit.
3. Restart the affected pods
   (`kubectl rollout restart deployment/payment-service -n payment`).

**Blast radius**: single-service, low technical risk.
