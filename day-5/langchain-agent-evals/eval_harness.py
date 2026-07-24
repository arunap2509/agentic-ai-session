"""
Eval Harness (LangChain + Langfuse) - eval_harness.py

Same 8 scenarios, same checkers, same task strings as
../agent-evals/eval_harness.py - the only thing that changed is what's
under test: travel_agent.py here is built on LangChain's create_agent
instead of the hand-rolled loop, and every run is traced to Langfuse
instead of only ever existing as a rich-console transcript. Open the
Langfuse dashboard (LANGFUSE_BASE_URL in .env) after a run to see the full
reasoning trajectory, token counts, and per-step latency behind every
PASS/FAIL below - not just the final answer.

The 8 scenarios (numbered to match ../agent-evals/eval_harness.py):
  1. Wrong tool argument      - date resolved correctly ("next Friday" -> ISO)?
  2. Wrong tool selection     - flights vs. trains when only one fits the ask?
  3. Hallucinated tool call   - no hotel tool exists; does it invent a booking?
  4. Missing required arg     - no date given; does it ask instead of guess?
  5. Multi-step trajectory    - search -> pick cheapest -> calendar, in order?
  6. Retry / infinite loop    - a flaky tool; does it retry sanely then stop?
  7. Non-determinism          - scenario 1's task, run 5x; what's the pass rate?
  8. Efficiency               - a 2-call task; does it wander into extra calls?

Run:
    python eval_harness.py
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from rich import box
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from travel_agent import (
    FLIGHTS,
    Trajectory,
    check_booking_status,
    create_calendar_event,
    flush_traces,
    run_task,
    search_flights,
    search_trains,
)

console = Console()

NEXT_FRIDAY = "2026-07-24"  # closest Friday on/after TODAY (2026-07-23, Thursday)


# --------------------------------------------------------------------------- #
# Checkers - identical to ../agent-evals/eval_harness.py, retyped against
# Trajectory instead of LoopResult (same field names, so the logic is
# unchanged - this is the whole point of Trajectory matching that shape)
# --------------------------------------------------------------------------- #

def check_correct_arguments(r: Trajectory) -> tuple[bool, str]:
    calls = [o for o in r.observations if o["name"] == "search_flights"]
    if not calls:
        return False, "search_flights was never called"
    args = calls[0]["args"]
    if args.get("origin") != "Chennai" or args.get("destination") != "Delhi":
        return False, f"wrong origin/destination: {args}"
    if args.get("date") != NEXT_FRIDAY:
        return False, f"'next Friday' not resolved to {NEXT_FRIDAY}: got date={args.get('date')!r}"
    return True, f"correct args: {args}"


def check_correct_tool_selected(r: Trajectory) -> tuple[bool, str]:
    called = [o["name"] for o in r.observations]
    if "search_flights" not in called:
        return False, f"never called search_flights despite an explicit flight preference: {called}"
    if "search_trains" in called:
        return False, f"called search_trains despite 'I get motion sick on trains': {called}"
    return True, f"correctly used only search_flights: {called}"


def check_no_hallucinated_action(r: Trajectory) -> tuple[bool, str]:
    if r.observations:
        return False, f"invented/misused a tool call for an unsupported action: {[o['name'] for o in r.observations]}"
    text = (r.final_text or "").lower()
    if any(w in text for w in ("booked", "confirmed", "reservation is made", "i've booked", "i have booked")):
        return False, "claimed to complete a hotel booking with no tool available to do it (hallucinated success)"
    if any(w in text for w in ("don't have", "do not have", "can't book", "cannot book", "no tool", "unable to")):
        return True, "correctly declined - no hallucinated tool call or fake success claim"
    return False, f"neither declined clearly nor called a tool - final text: {(r.final_text or '')[:150]!r}"


def check_asks_for_missing_date(r: Trajectory) -> tuple[bool, str]:
    flight_calls = [o for o in r.observations if o["name"] == "search_flights"]
    if flight_calls:
        return False, f"called search_flights without a given date - guessed date={flight_calls[0]['args'].get('date')!r} instead of asking"
    text = (r.final_text or "").lower()
    if "date" in text and ("?" in text or "which date" in text or "what date" in text or "when" in text):
        return True, "correctly asked for the missing date instead of guessing"
    return False, f"neither called a tool nor clearly asked for the date - final text: {(r.final_text or '')[:150]!r}"


def check_trajectory_order_and_data(r: Trajectory) -> tuple[bool, str]:
    names = [o["name"] for o in r.observations]
    if "search_flights" not in names:
        return False, f"never searched flights: {names}"
    if "create_calendar_event" not in names:
        return False, f"never created the calendar event: {names}"
    if names.index("search_flights") > names.index("create_calendar_event"):
        return False, f"created the event before searching flights: {names}"
    event_call = next(o for o in r.observations if o["name"] == "create_calendar_event")
    cheapest = min(f["price"] for f in FLIGHTS if f["date"] == "2026-07-31")
    if str(cheapest) not in str(event_call["args"]):
        return False, f"event doesn't reference the cheapest price ({cheapest}): {event_call['args']}"
    return True, f"correct order, event references cheapest flight (₹{cheapest})"


def check_retry_behavior(r: Trajectory) -> tuple[bool, str]:
    calls = [o for o in r.observations if o["name"] == "check_booking_status"]
    if r.exhausted:
        return False, f"never terminated - hit max_steps after {len(calls)} retries (looped without stopping)"
    if not calls:
        return False, "never called check_booking_status at all"
    last_result = calls[-1]["result"]
    if "CONFIRMED" in str(last_result):
        if len(calls) > 5:
            return False, f"took {len(calls)} retries to reach CONFIRMED - excessive polling"
        return True, f"retried sanely ({len(calls)} call(s)) and correctly reported CONFIRMED"
    return False, f"gave up after {len(calls)} call(s) while still PENDING instead of retrying until confirmed"


def check_efficiency(r: Trajectory) -> tuple[bool, str]:
    n = len(r.observations)
    ideal, slack = 2, 1
    if n <= ideal + slack:
        return True, f"used {n} tool call(s) (ideal: {ideal})"
    return False, f"used {n} tool calls to solve a {ideal}-call task - wandered: {[o['name'] for o in r.observations]}"


# --------------------------------------------------------------------------- #
# Test cases - identical to ../agent-evals/eval_harness.py
# --------------------------------------------------------------------------- #

@dataclass
class TestCase:
    id: str
    category: str
    task: str
    checker: Callable[[Trajectory], tuple[bool, str]]
    tools: list = field(default_factory=list)
    max_steps: int = 8
    repeats: int = 1


TEST_CASES = [
    TestCase(
        id="1",
        category="Wrong tool argument",
        task="Book a flight from Chennai to Delhi next Friday.",
        checker=check_correct_arguments,
        tools=[search_flights, create_calendar_event],
    ),
    TestCase(
        id="2",
        category="Wrong tool selection",
        task="I get motion sick on trains - find me a flight from Chennai to Delhi on 2026-07-24.",
        checker=check_correct_tool_selected,
        tools=[search_flights, search_trains],
    ),
    TestCase(
        id="3",
        category="Hallucinated tool call",
        task="Book me a hotel room in Delhi for the night of 2026-07-31.",
        checker=check_no_hallucinated_action,
        tools=[search_flights, search_trains, create_calendar_event],
    ),
    TestCase(
        id="4",
        category="Missing required argument",
        task="Book me a flight from Chennai to Delhi.",
        checker=check_asks_for_missing_date,
        tools=[search_flights],
    ),
    TestCase(
        id="5",
        category="Multi-step trajectory",
        task="Find the cheapest flight from Chennai to Delhi on 2026-07-31, then create a calendar event for it.",
        checker=check_trajectory_order_and_data,
        tools=[search_flights, create_calendar_event],
    ),
    TestCase(
        id="6",
        category="Infinite loop / retry detection",
        task="Check on booking BR123 and let me know once it's confirmed.",
        checker=check_retry_behavior,
        tools=[check_booking_status],
        max_steps=10,
    ),
    TestCase(
        id="7",
        category="Non-determinism (same task x5)",
        task="Book a flight from Chennai to Delhi next Friday.",
        checker=check_correct_arguments,
        tools=[search_flights, create_calendar_event],
        repeats=5,
    ),
    TestCase(
        id="8",
        category="Efficiency (2-call task)",
        task="What's the cheapest way overall - flight or train - from Chennai to Delhi on 2026-07-31?",
        checker=check_efficiency,
        tools=[search_flights, search_trains],
    ),
]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def run_test_case(tc: TestCase) -> list[tuple[bool, str]]:
    outcomes = []
    for i in range(tc.repeats):
        result = run_task(tc.task, tools=tc.tools, max_steps=tc.max_steps)
        passed, reason = tc.checker(result)
        outcomes.append((passed, reason))
        mark = "[green]✓[/green]" if passed else "[red]✗[/red]"
        label = f"run {i + 1}/{tc.repeats}" if tc.repeats > 1 else "result"
        console.print(f"    {mark} {label}: {reason}")
    return outcomes


def main() -> None:
    console.rule("[bold]Agent Eval Harness (LangChain + Langfuse) - Travel Booking Agent[/bold]")
    console.print(f"[dim]{len(TEST_CASES)} scenarios, {sum(tc.repeats for tc in TEST_CASES)} total runs[/dim]\n")

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Scenario")
    table.add_column("Result")
    table.add_column("Detail")

    for tc in TEST_CASES:
        console.print(f"[bold cyan]#{tc.id} {tc.category}[/bold cyan]  [dim]-  \"{tc.task}\"[/dim]")
        outcomes = run_test_case(tc)
        console.print()

        if tc.repeats == 1:
            passed, reason = outcomes[0]
            status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            table.add_row(tc.id, tc.category, status, reason)
        else:
            n_pass = sum(1 for p, _ in outcomes if p)
            rate = 100 * n_pass / len(outcomes)
            color = "green" if rate == 100 else ("yellow" if rate >= 60 else "red")
            summary = " ".join("✓" if p else "✗" for p, _ in outcomes)
            table.add_row(
                tc.id, tc.category,
                f"[{color}]{n_pass}/{len(outcomes)} ({rate:.0f}%)[/{color}]",
                f"{summary}  -  first failure: {next((rsn for p, rsn in outcomes if not p), 'none')}",
            )

    console.rule("[bold]Summary[/bold]")
    console.print(table)

    flush_traces()
    console.print("\n[dim]All traces flushed to Langfuse - open your Langfuse project to see the full run.[/dim]")


if __name__ == "__main__":
    main()
