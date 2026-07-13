# Runbook: Connection Pool Exhaustion

Symptoms: ERROR logs containing "connection pool exhausted", rising latency
p99 and error rate on the affected service immediately following a deploy.

Likely cause: a new deploy shipped with a lowered pool size or a connection
leak. This is almost always local to the service that was just deployed -
it is not evidence of a problem in any other service, even if error volume
is high.

Recommended action: `restart` the affected service first (clears leaked
connections immediately, low blast radius). If the error recurs within 15
minutes of restart, `rollback` the affected service's own most recent
deploy - never a different service's deploy.

Do not `scale` in response to this symptom alone - adding pool-starved
instances does not fix a leak, it just delays exhaustion.
