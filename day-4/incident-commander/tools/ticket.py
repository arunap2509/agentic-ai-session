"""Mocked ticketing system - an in-memory store standing in for a real
incident-management API (PagerDuty/Jira/etc).
"""

_TICKETS: dict[str, dict] = {}


def ticket_create_update(incident_id: str, action: str, fields: dict) -> dict:
    """EXECUTE: Create or update the ticket tracking this incident.

    Args:
        incident_id: The incident this ticket belongs to.
        action: "create" or "update".
        fields: Fields to set/merge onto the ticket, e.g.
            {"status": "investigating", "severity": "high"}.
    """
    if action == "create" or incident_id not in _TICKETS:
        _TICKETS[incident_id] = {"incident_id": incident_id, **fields}
    else:
        _TICKETS[incident_id].update(fields)
    return dict(_TICKETS[incident_id])
