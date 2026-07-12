"""
Ticker Triaging Agent

Contrast with the Data Analyst Agent on purpose: that one is depth - a
single agent adaptively deciding how many rounds of investigation a
question needs. This one is breadth - the same fixed five-step pipeline
(classify, enrich, route, execute, log) applied to many events, where only
ONE step (classification) is a judgment call at all. Nothing here decides
its own control flow - the sequence is fixed in code, because for a
repeatable triage decision, that's the correct design, not a lesser one.

The pipeline doesn't just describe what should happen - it acts. Once the
final action is known (auto-decided, or decided by a human), a real
(mocked) EXECUTE tool runs: flag_for_analyst, file_as_routine, or
hold_for_later. Which one runs is a plain lookup on the already-decided
action, not a new model choice - that decision was already made by the
confidence gate or the human, re-litigating it with another model call
would just add risk for no reason.

The two guardrails are both deterministic (plain code, not model
judgment):
  - confidence below threshold -> escalate to a human instead of acting
  - ticker not found during enrichment -> escalate regardless of
    confidence, because there's no context to trust the classification
    against, no matter how dramatic the event looks (see ZVXQ)

Run:
    python triage_agent.py

Always asks the same four questions, in the same order, every time -
ticker, headline, price change %, volume ratio - no auto-fill shortcuts.
See README.md for example events with full input to try. Blank ticker to
quit and see the audit summary.
"""

import sys
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client
from data.ticker_data import TICKER_LOOKUP

console = Console()

CONFIDENCE_THRESHOLD = 0.7

CLASSIFY_INSTRUCTION = (
    "You are a financial ticker triage assistant. Given a market event, "
    "classify it. Reply in exactly this four-line format, nothing else:\n"
    "TYPE: <Earnings, M&A/Legal, Analyst Rating, Technical/Volume, Routine, or Other>\n"
    "CONFIDENCE: <a number from 0.0 to 1.0. First check: is there actually a "
    "notable move here (price change over ~2%, or volume over ~1.5x normal)? "
    "If NO - the move is small and volume is close to normal - there's "
    "nothing that needs explaining, so confidence should be HIGH (this is "
    "confidently Routine even with no stated cause). If YES there's a "
    "notable move, then check whether the headline gives a clear, specific, "
    "named cause for it. If it doesn't (cause unclear, declined to comment, "
    "no catalyst identified, vague speculation/rumor), confidence MUST be "
    "below 0.5 - a big move with no known cause is not something you can "
    "confidently classify. Only use 0.7 or higher when either nothing "
    "notable is happening, or a notable move has a specific, named cause.>\n"
    "ACTION: <Flag for Review if this is a significant event an analyst "
    "should see, or Routine No Action if it isn't - a large,"
    "confidently-explained move (like a big earnings beat) should still be "
    "Flag for Review; confidence and significance are separate questions.>\n"
    "RATIONALE: <one short sentence>"
)


def classify_event(event: dict) -> dict:
    """Judgment call: what kind of event is this, and how confident are we
    it matters. The only step in this pipeline that's a model call."""
    prompt = (
        f"Ticker: {event['ticker']}\nHeadline: {event['headline']}\n"
        f"Price change: {event['price_change_pct']}%\n"
        f"Volume vs normal: {event['volume_ratio']}x"
    )
    response = get_client().models.generate_content(
        model=MODEL, contents=prompt, config={"system_instruction": CLASSIFY_INSTRUCTION}
    )
    result = {"type": "Other", "confidence": 0.5, "action": "Flag for Review", "rationale": response.text.strip()}
    for line in response.text.strip().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().upper(), value.strip()
        if key == "TYPE":
            result["type"] = value
        elif key == "CONFIDENCE":
            try:
                result["confidence"] = max(0.0, min(1.0, float(value)))
            except ValueError:
                pass
        elif key == "ACTION":
            result["action"] = value
        elif key == "RATIONALE":
            result["rationale"] = value
    return result


def flag_for_analyst(ticker: str, rationale: str) -> dict:
    """EXECUTE: mocked - in a real system this notifies a human analyst
    (Slack, email, a queue). This is what actually happens as a result of
    the triage decision, not just a description of what should happen."""
    console.print(
        Panel(
            f"Analyst notified for {ticker}.\nReason: {rationale}",
            title="[green]ALERT SENT: Analyst Review Queue[/green]",
            border_style="green",
        )
    )
    return {"status": "alert_sent"}


def file_as_routine(ticker: str) -> dict:
    """EXECUTE: mocked - in a real system this auto-archives the event."""
    console.print(
        Panel(f"{ticker} filed, no action needed.", title="[green]FILED: Routine[/green]", border_style="green")
    )
    return {"status": "filed"}


def hold_for_later(ticker: str) -> dict:
    """EXECUTE: mocked - in a real system this creates a follow-up task."""
    console.print(
        Panel(f"{ticker} held for later review.", title="[green]HELD: Follow-up Queue[/green]", border_style="green")
    )
    return {"status": "held"}


def enrich_ticker(ticker: str) -> dict | None:
    """Deterministic lookup, not a model call - there's no judgment about
    whether to enrich, it always happens, so it doesn't need to be a tool
    the model decides to invoke."""
    return TICKER_LOOKUP.get(ticker)


def decide_routing(classification: dict, enrichment: dict | None) -> dict:
    """Both rules here are plain code, not model judgment - deliberately:
    a threshold and a lookup-miss are deterministic facts, not things that
    benefit from being re-litigated by a prompt."""
    if enrichment is None:
        return {
            "escalate": True,
            "reason": "Unrecognized ticker - no context available to trust this classification against.",
        }
    if classification["confidence"] >= CONFIDENCE_THRESHOLD:
        return {
            "escalate": False,
            "reason": f"Confidence {classification['confidence']:.2f} meets the {CONFIDENCE_THRESHOLD} threshold.",
        }
    return {
        "escalate": True,
        "reason": f"Confidence {classification['confidence']:.2f} is below the {CONFIDENCE_THRESHOLD} threshold.",
    }


def get_event_from_console() -> dict | None:
    """Always asks all four fields, in the same order, every time - no
    preset auto-fill. That shortcut made the flow unpredictable (sometimes
    one question, sometimes four, depending on what you typed) and was the
    actual source of confusion, not the number of fields itself."""
    ticker = console.input("[bold cyan]Ticker (blank to quit):[/bold cyan] ").strip().upper()
    if not ticker:
        return None
    headline = console.input("Headline: ").strip()
    try:
        price_change_pct = float(console.input("Price change % (e.g. 5.2 or -3.1): ").strip() or 0)
    except ValueError:
        price_change_pct = 0.0
    try:
        volume_ratio = float(console.input("Volume ratio vs normal (e.g. 2.5, 1.0 = normal): ").strip() or 1.0)
    except ValueError:
        volume_ratio = 1.0
    return {"ticker": ticker, "headline": headline, "price_change_pct": price_change_pct, "volume_ratio": volume_ratio}


def triage(event: dict, audit_log: list) -> None:
    classification = classify_event(event)
    classify_panel = Panel(
        f"Type: {classification['type']}\n"
        f"Confidence: {classification['confidence']:.2f}\n"
        f"Suggested action: {classification['action']}\n"
        f"Rationale: {classification['rationale']}",
        title="Classify",
        border_style="yellow",
    )

    enrichment = enrich_ticker(event["ticker"])
    enrich_text = (
        f"{enrichment['company_name']} - {enrichment['sector']} sector"
        if enrichment
        else "No data found for this ticker."
    )
    enrich_panel = Panel(enrich_text, title="Enrich", border_style="blue")

    routing = decide_routing(classification, enrichment)
    next_step = (
        "-> Escalating to human review."
        if routing["escalate"]
        else f"-> Auto-routing: {classification['action']}"
    )
    route_panel = Panel(
        f"{routing['reason']}\n{next_step}",
        title="Route",
        border_style="red" if routing["escalate"] else "green",
    )

    console.print(
        Panel(
            Group(classify_panel, enrich_panel, route_panel),
            title=f"[bold]{event['ticker']}[/bold] - {event['headline']}",
            border_style="white",
        )
    )

    final_action = classification["action"]
    human_decision = None
    if routing["escalate"]:
        other_action = "Routine No Action" if classification["action"] == "Flag for Review" else "Flag for Review"
        human_decision = console.input(
            f"Approve '{classification['action']}', override to '{other_action}', or hold? (a/o/h): "
        ).strip().lower()
        if human_decision == "o":
            final_action = other_action
        elif human_decision == "h":
            final_action = "Held for later review"
        console.print()

    # EXECUTE: which tool runs is a plain lookup on final_action, already
    # fully decided above - not a new model choice.
    if final_action == "Flag for Review":
        flag_for_analyst(event["ticker"], classification["rationale"])
    elif final_action == "Routine No Action":
        file_as_routine(event["ticker"])
    else:
        hold_for_later(event["ticker"])
    console.print()

    audit_log.append(
        {
            "ticker": event["ticker"],
            "type": classification["type"],
            "confidence": classification["confidence"],
            "escalated": routing["escalate"],
            "human_decision": human_decision or "-",
            "final_action": final_action,
        }
    )


def print_audit_summary(audit_log: list) -> None:
    if not audit_log:
        return
    table = Table(title="Audit Log")
    for col in ("Ticker", "Type", "Confidence", "Escalated", "Human", "Final Action"):
        table.add_column(col)
    for row in audit_log:
        table.add_row(
            row["ticker"],
            row["type"],
            f"{row['confidence']:.2f}",
            "yes" if row["escalated"] else "no",
            row["human_decision"],
            row["final_action"],
        )
    console.print(table)


if __name__ == "__main__":
    console.rule("Ticker Triaging Agent")
    console.print("Enter a ticker. Blank line to quit.\n")
    audit_log = []
    while True:
        try:
            event = get_event_from_console()
        except (EOFError, KeyboardInterrupt):
            break
        if event is None:
            break
        console.print()
        triage(event, audit_log)

    console.print()
    print_audit_summary(audit_log)
