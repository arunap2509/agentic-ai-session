# Runbook: Scaling

Use `scale` when CPU or request-queue depth is elevated but error rate is
low - i.e. the service is healthy but under-provisioned for current load.

Scaling is not a fix for connection pool exhaustion, deploy-induced
regressions, or any error caused by application logic - adding instances
does not change the code that's failing.
