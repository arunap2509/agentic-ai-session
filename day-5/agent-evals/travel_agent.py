"""
Travel Agent - travel_agent.py

The system-under-test for eval_harness.py: a small travel-booking agent with
a FIXED toolset (search_flights, search_trains, create_calendar_event,
check_booking_status) over synthetic, in-memory data. Deterministic and free
of network calls on purpose - an eval should score the model's tool-use
behavior, not a flaky third-party API.

Deliberately NOT self-evolving like day-5/self-evolving-agent - an eval
harness needs a stable, fixed action space to score consistent trajectories
against; a toolset that can grow mid-run would make "did it call the right
tool" an unanswerable question.

TODAY is a fixed constant, not datetime.now() - so "resolve 'next Friday'"
checks are reproducible across every run, not dependent on when you happen
to execute the script.
"""

import sys
from datetime import date
from pathlib import Path

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.agent_loop import LoopResult, run_tool_loop

TODAY = date(2026, 7, 23)  # Thursday

SYSTEM_INSTRUCTION = f"""You are a travel booking assistant.

Today's date is {TODAY.isoformat()} ({TODAY.strftime('%A')}). Resolve any relative date
(e.g. "next Friday", "tomorrow") to an ISO date (YYYY-MM-DD) yourself before calling a
tool - tools only accept ISO dates, never phrases like "next Friday". When resolving a
weekday name, use the closest upcoming occurrence of that day.

You have tools for flights, trains, calendar events, and checking booking status. You do
not have a tool for hotels, cars, or anything else - if asked for something you have no
tool for, say so directly instead of pretending to book it.

If a required detail (such as a date) is missing from the request and you cannot
reasonably infer it, ask the user for it instead of guessing.
"""

FLIGHTS = [
    {"id": "AI101", "origin": "Chennai", "destination": "Delhi", "date": "2026-07-24", "price": 4200, "airline": "Air India", "depart": "06:00"},
    {"id": "6E202", "origin": "Chennai", "destination": "Delhi", "date": "2026-07-24", "price": 3800, "airline": "IndiGo", "depart": "09:15"},
    {"id": "UK303", "origin": "Chennai", "destination": "Delhi", "date": "2026-07-24", "price": 5100, "airline": "Vistara", "depart": "14:30"},
    {"id": "AI102", "origin": "Chennai", "destination": "Delhi", "date": "2026-07-31", "price": 4400, "airline": "Air India", "depart": "06:00"},
    {"id": "6E203", "origin": "Chennai", "destination": "Delhi", "date": "2026-07-31", "price": 3900, "airline": "IndiGo", "depart": "09:15"},
]

TRAINS = [
    {"id": "12615", "origin": "Chennai", "destination": "Delhi", "date": "2026-07-24", "name": "Grand Trunk Express", "price": 1800, "duration_hours": 28},
    {"id": "12615", "origin": "Chennai", "destination": "Delhi", "date": "2026-07-31", "name": "Grand Trunk Express", "price": 1800, "duration_hours": 28},
]

# booking_ref -> number of times check_booking_status has been called for it.
# Reset per eval run (see eval_harness.reset_state) so repeats don't leak state.
_booking_status_calls: dict[str, int] = {}


def reset_state() -> None:
    _booking_status_calls.clear()


def search_flights(origin: str, destination: str, date: str) -> list[dict]:
    """Search available flights between two cities on an exact date.

    Args:
        origin: Departure city name, e.g. "Chennai".
        destination: Arrival city name, e.g. "Delhi".
        date: Travel date in ISO format (YYYY-MM-DD). Relative phrases like
            "next Friday" are not accepted - resolve them to an ISO date first.

    Returns:
        list[dict]: Matching flights (id, airline, price, depart time), or an
            empty list if none match.
    """
    return [f for f in FLIGHTS if f["origin"] == origin and f["destination"] == destination and f["date"] == date]


def search_trains(origin: str, destination: str, date: str) -> list[dict]:
    """Search available trains between two cities on an exact date.

    Args:
        origin: Departure city name, e.g. "Chennai".
        destination: Arrival city name, e.g. "Delhi".
        date: Travel date in ISO format (YYYY-MM-DD).

    Returns:
        list[dict]: Matching trains (id, name, price, duration_hours), or an
            empty list if none match.
    """
    return [t for t in TRAINS if t["origin"] == origin and t["destination"] == destination and t["date"] == date]


def create_calendar_event(title: str, date: str, details: str) -> dict:
    """Create a calendar event.

    Args:
        title: Short event title.
        date: Event date in ISO format (YYYY-MM-DD).
        details: Longer description of the event (e.g. booking reference,
            price, airline/train name).

    Returns:
        dict: The created event's status, a generated event_id, and the
            title/date/details it was created with.
    """
    return {
        "status": "created",
        "event_id": f"evt_{abs(hash((title, date))) % 10000}",
        "title": title,
        "date": date,
        "details": details,
    }


def check_booking_status(booking_ref: str) -> str:
    """Check the status of a previously made booking.

    Args:
        booking_ref: The booking reference code, e.g. "BR123".

    Returns:
        str: "PENDING - please check again shortly" for the first two checks
            on a given reference, then "CONFIRMED" from the third check
            onward - simulates a real booking system where status settles
            after a short delay.
    """
    _booking_status_calls[booking_ref] = _booking_status_calls.get(booking_ref, 0) + 1
    if _booking_status_calls[booking_ref] < 3:
        return "PENDING - please check again shortly"
    return "CONFIRMED"


ALL_TOOLS = [search_flights, search_trains, create_calendar_event, check_booking_status]


def run_task(task: str, tools: list | None = None, max_steps: int = 8) -> LoopResult:
    """Runs one task against the travel agent with a fresh, isolated
    conversation and returns the full trajectory for a checker to inspect.
    `tools` lets a test case restrict the action space (e.g. only
    check_booking_status, to force retry behavior with nothing else to do).
    """
    reset_state()
    contents = [types.Content(role="user", parts=[types.Part(text=task)])]
    return run_tool_loop(
        contents,
        tools if tools is not None else ALL_TOOLS,
        terminal_tools=set(),
        system_instruction=SYSTEM_INSTRUCTION,
        max_steps=max_steps,
    )
