"""Mocked notification channel (Slack/PagerDuty/email stand-in)."""


def notify(channel: str, message: str) -> dict:
    """EXECUTE: Send a notification to a channel.

    Args:
        channel: Destination, e.g. "#incidents" or "oncall-pager".
        message: The message body.
    """
    return {"status": "sent", "channel": channel}
