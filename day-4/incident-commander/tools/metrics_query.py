"""RETRIEVE: metrics_query tool for the Metrics Investigator agent."""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

_metrics: dict | None = None


def _load() -> dict:
    global _metrics
    if _metrics is None:
        _metrics = json.loads((FIXTURES / "fake_metrics.json").read_text())
    return _metrics


def _parse_range(time_range: str) -> tuple[str, str]:
    if "/" in time_range:
        start, end = time_range.split("/", 1)
        return start.strip(), end.strip()
    return "0000-01-01T00:00:00Z", "9999-12-31T23:59:59Z"


def metrics_query(metric: str, service: str, time_range: str) -> dict:
    """RETRIEVE: Query a timeseries metric for one service over a time window.

    Args:
        metric: One of "latency_p99_ms", "error_rate_pct", "cpu_usage_pct",
            "deploy_events".
        service: Exact service name, e.g. "checkout-service".
        time_range: "<start_iso>/<end_iso>", e.g.
            "2026-07-13T03:00:00Z/2026-07-13T05:00:00Z".

    Correlating two different metrics (e.g. latency vs. deploy_events) over
    the same window, rather than reading one in isolation, is what turns a
    single number into an actual finding.
    """
    data = _load()
    if service not in data:
        return {"error": f"no data for service '{service}'"}
    if metric not in data[service]:
        return {"error": f"unknown metric '{metric}' for {service}"}

    start, end = _parse_range(time_range)
    points = [p for p in data[service][metric] if start <= p["time"] <= end]
    return {"metric": metric, "service": service, "points": points}
