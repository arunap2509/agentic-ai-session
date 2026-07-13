"""RETRIEVE: log_search tool for the Log Investigator agent.

Deliberately caps how many lines a single call can return, the same way a
real log platform (Splunk, Datadog) does - this is what forces genuine
multi-turn investigation instead of one broad query dumping everything.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MAX_RESULTS = 40

_logs: list[dict] | None = None


def _load() -> list[dict]:
    global _logs
    if _logs is None:
        _logs = json.loads((FIXTURES / "fake_logs.json").read_text())
    return _logs


def _parse_range(time_range: str) -> tuple[str, str]:
    """"start/end" ISO8601 strings, or a bare keyword meaning "everything"."""
    if "/" in time_range:
        start, end = time_range.split("/", 1)
        return start.strip(), end.strip()
    return "0000-01-01T00:00:00Z", "9999-12-31T23:59:59Z"


def log_search(service: str, time_range: str, severity: str | None = None, query: str | None = None) -> dict:
    """RETRIEVE: Search production logs for one service over a time window.

    Args:
        service: Exact service name, e.g. "checkout-service".
        time_range: Either "<start_iso>/<end_iso>" (e.g.
            "2026-07-13T03:30:00Z/2026-07-13T04:30:00Z") to narrow to a
            specific window, or any other string to search the full
            available history (broad - likely to be truncated).
        severity: Optional exact match, one of INFO/WARN/ERROR.
        query: Optional case-insensitive substring match against the log
            message text.

    Returns a dict with total_matches, returned count, truncated flag, and
    up to 40 matching lines. If truncated is true, narrow time_range and/or
    severity/query and search again - do not treat a truncated result as
    the complete picture.
    """
    start, end = _parse_range(time_range)
    matches = []
    for line in _load():
        if line["service"] != service:
            continue
        if not (start <= line["time"] <= end):
            continue
        if severity and line["severity"] != severity.upper():
            continue
        if query and query.lower() not in line["message"].lower():
            continue
        matches.append(line)

    matches.sort(key=lambda l: l["time"])
    total = len(matches)
    truncated = total > MAX_RESULTS
    shown = matches[-MAX_RESULTS:] if truncated else matches
    return {
        "total_matches": total,
        "returned": len(shown),
        "truncated": truncated,
        "lines": [f"[{l['time']}] {l['severity']} {l['service']}: {l['message']}" for l in shown],
    }
