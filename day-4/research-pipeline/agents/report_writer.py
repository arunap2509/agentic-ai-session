"""Report Writer - thin, mostly formatting. Built as a plain function, not an
LLM agent: there's no judgment left to exercise once the Reconciler has
already resolved conflicts - only presentation. Low stakes either way, but
formatting deterministically means flagged/unresolved items can never be
silently dropped by a rewrite.
"""


def write_report(question: str, background: dict, recent: dict, deep_dive: dict, reconciled: dict) -> str:
    lines = [
        f"# Research Brief: {question}",
        "",
        "## Background",
        f"{background.get('summary')}",
        "",
        "## Recent Developments",
        f"{recent.get('summary')}",
        "",
        "## Deep Dive",
        f"{deep_dive.get('summary')}",
        "",
        "## Reconciled View",
        f"{reconciled.get('reconciled_summary')}",
    ]
    if reconciled.get("flagged_conflicts"):
        lines += ["", "## Flagged (resolved with a caveat)"]
        lines += [f"- {c}" for c in reconciled["flagged_conflicts"]]
    if reconciled.get("unresolved_conflicts"):
        lines += ["", "## Unresolved / Could Not Verify"]
        lines += [f"- {c}" for c in reconciled["unresolved_conflicts"]]
    return "\n".join(lines)
