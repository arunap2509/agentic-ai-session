# Runbook: Service Restart

Lowest blast-radius remediation available. Appropriate first response for:
connection pool exhaustion, memory leaks with rising heap usage, and stuck
worker threads.

A restart only affects the targeted service's own running instances - it
cannot resolve issues whose root cause lives in a different service.
