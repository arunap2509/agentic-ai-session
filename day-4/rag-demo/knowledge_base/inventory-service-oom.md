---
service: inventory-service
doc_type: runbook
env: prod
updated: 2026-04-30
---
# Runbook: inventory-service — OOMKilled pods

**Symptoms**: pods in `inventory-service` are OOMKilled (exit code 137),
almost always during the nightly bulk SKU import.

**Root cause**: the importer loads the entire supplier catalog file into
memory before processing it instead of streaming it. Supplier catalogs have
grown past what fits in the pod's memory limit.

**Fix**:
1. Re-run the import with `--batch-size=500` to switch it to streaming
   batch mode instead of a whole-file load.
2. Restart the affected pods.
3. Longer-term fix (already ticketed): make streaming mode the default.

**Blast radius**: single-service, low risk. No approval required.
