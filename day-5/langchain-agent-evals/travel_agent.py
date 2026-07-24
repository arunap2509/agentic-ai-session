"""
Travel Agent (LangChain) - travel_agent.py

Same domain and same fixture data as ../agent-evals/travel_agent.py, on a
different foundation: LangChain's `create_agent` (LangGraph under the hood)
instead of the hand-rolled loop in ../common/agent_loop.py, with every LLM
call and tool call traced to Langfuse (LANGFUSE_BASE_URL from .env). Point
is the same 8 eval scenarios can compare "our own ReAct loop" against a
standard framework, and instead of a rich-console transcript being the only
record of what happened, every run shows up in the Langfuse dashboard with
full token counts, latency, and step-by-step reasoning.

Deliberately NOT self-evolving like day-5/self-evolving-agent - an eval
harness needs a stable, fixed action space to score consistent trajectories
against.

TODAY is a fixed constant, not datetime.now() - matches
../agent-evals/travel_agent.py exactly, so "resolve 'next Friday'" checks
are reproducible and the two harnesses' results are directly comparable.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langgraph.errors import GraphRecursionError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "gemini-flash-latest"
TODAY = date(2026, 7, 23)  # Thursday - fixed, matches ../agent-evals/travel_agent.py

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
# Reset per eval run (see reset_state) so repeats don't leak state.
_booking_status_calls: dict[str, int] = {}


def reset_state() -> None:
    _booking_status_calls.clear()


@tool
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


@tool
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


@tool
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


@tool
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

_model = ChatGoogleGenerativeAI(model=MODEL)
_langfuse_client = get_client()  # reads LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL from .env


@dataclass
class Trajectory:
    """Same shape as ../agent-evals/common/agent_loop.py's LoopResult -
    just enough (observations, final_text, exhausted) for eval_harness.py's
    checkers to work completely unchanged regardless of which agent
    framework actually produced the trajectory."""

    observations: list[dict] = field(default_factory=list)
    final_text: str = ""
    exhausted: bool = False


def _extract_final_text(message) -> str:
    """A LangChain AIMessage's .content is either a plain string or (with
    this Gemini integration) a list of content blocks - handle both."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(block["text"] for block in content if isinstance(block, dict) and block.get("type") == "text")


def _to_observations(messages: list) -> list[dict]:
    """Converts LangGraph's message list into the same
    [{"name", "args", "result"}, ...] shape the checkers expect - matches a
    ToolMessage back to the AIMessage tool_call that produced it via the
    shared tool_call_id."""
    pending_calls: dict[str, dict] = {}
    observations = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            pending_calls[call["id"]] = {"name": call["name"], "args": call["args"]}
        if type(message).__name__ == "ToolMessage":
            call_info = pending_calls.get(message.tool_call_id)
            if call_info:
                observations.append({**call_info, "result": message.content})
    return observations


def run_task(task: str, tools: list | None = None, max_steps: int = 8) -> Trajectory:
    """Runs one task against the LangChain travel agent, traced to Langfuse.
    `tools` lets a test case restrict the action space (e.g. only
    check_booking_status, to force retry behavior with nothing else to do).

    LangGraph counts graph-node executions, not "loop iterations" the way
    ../agent-evals/common/agent_loop.py does (each iteration there is one
    model call + one tool-execution node here) - max_steps * 2 plus a
    little headroom keeps the two roughly comparable. Exceeding it raises
    GraphRecursionError rather than returning a partial result, and that
    exception doesn't carry the trajectory - so on that path we report
    exhausted=True with an empty trajectory rather than guessing at it.
    """
    reset_state()
    agent = create_agent(model=_model, tools=tools if tools is not None else ALL_TOOLS, system_prompt=SYSTEM_INSTRUCTION)
    handler = CallbackHandler()
    config = {"callbacks": [handler], "recursion_limit": max_steps * 2 + 2}

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": task}]}, config=config)
    except GraphRecursionError:
        return Trajectory(exhausted=True)

    messages = result["messages"]
    final_ai_messages = [m for m in messages if type(m).__name__ == "AIMessage" and m.content]
    final_text = _extract_final_text(final_ai_messages[-1]) if final_ai_messages else ""
    return Trajectory(observations=_to_observations(messages), final_text=final_text, exhausted=False)


def flush_traces() -> None:
    """The Langfuse SDK batches and exports asynchronously - a short-lived
    script can otherwise exit before its last few traces are sent. Call
    this once at the end of a run, not after every task."""
    _langfuse_client.flush()
