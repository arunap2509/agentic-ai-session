"""Mocked publish - human-gated EXECUTE tool, no undo."""


def publish_report(report_id: str, content: str) -> dict:
    """EXECUTE: Publish the finished research brief. Not reversible.

    Args:
        report_id: Identifier for this report/run.
        content: The full formatted brief text.
    """
    return {"status": "published", "doc_id": f"doc-{report_id}"}
