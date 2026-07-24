# Agent Eval Harness

A single pass/fail run tells you almost nothing about whether an agent's
tool use is trustworthy. This scores a small travel-booking agent
(`travel_agent.py`) against 8 concrete tool-use failure modes, with a
harness (`eval_harness.py`) that inspects the actual trajectory - every
tool call, its arguments, its result, in order - not just the final answer.

## The system under test

`travel_agent.py` is a fixed-toolset agent (unlike
`../self-evolving-agent/`, which grows its own tools - an eval needs a
stable action space to score consistently against) with 4 tools over
synthetic, in-memory data: `search_flights`, `search_trains`,
`create_calendar_event`, `check_booking_status`. No network calls, no
flaky third-party API - failures you see are the model's, not a dependency's.

`TODAY` is a fixed constant (2026-07-23, a Thursday), not `datetime.now()`,
so "did it resolve 'next Friday' correctly" is checked against a value that
never changes between runs.

## The 8 scenarios

| # | Scenario | Task | What the checker looks for |
|---|---|---|---|
| 1 | Wrong tool argument | "Book a flight ... next Friday" | Did it resolve the relative date to the correct ISO date before calling the tool, not pass the phrase through literally? |
| 2 | Wrong tool selection | "I get motion sick on trains - find me a flight..." | Did it call `search_flights`, not `search_trains`, when the two look interchangeable but the request clearly picks one? |
| 3 | Hallucinated tool call | "Book me a hotel room..." (no hotel tool exists) | Did it decline outright, or did it fake success / misuse an unrelated tool to pretend it booked something? |
| 4 | Missing required argument | "Book me a flight from Chennai to Delhi." (no date) | Did it ask for the date, or guess one and call the tool anyway? |
| 5 | Multi-step trajectory | "Find the cheapest flight... then create a calendar event for it." | Right tools, right order (search before scheduling), and does the created event actually reference the cheapest flight found? |
| 6 | Infinite loop / retry detection | "Check on booking BR123... let me know once it's confirmed." | `check_booking_status` is flaky (PENDING x2, then CONFIRMED) and is the *only* tool available - does it retry a sane number of times and report CONFIRMED, give up too early, or loop until `max_steps`? |
| 7 | Non-determinism | Scenario 1's exact task, run 5 times | Pass rate across 5 fresh runs, not one - the point being that a single green checkmark proves nothing about reliability |
| 8 | Efficiency | "What's the cheapest way overall - flight or train..." | Solvable in 2 tool calls (`search_flights` + `search_trains`) - did it stop there, or wander into extra calls? |

## The contract (`TestCase` / checker)

```python
@dataclass
class TestCase:
    id: str
    category: str
    task: str
    checker: Callable[[LoopResult], tuple[bool, str]]
    tools: list          # the action space available for this scenario
    max_steps: int = 8
    repeats: int = 1     # >1 for scenario 7's non-determinism check
```

A checker receives the full `LoopResult` (see `common/agent_loop.py`) -
`observations` (list of `{name, args, result}` in call order), `final_text`,
and `exhausted` (True if it hit `max_steps` without finishing) - and returns
`(passed: bool, reason: str)`. All 8 checkers in `eval_harness.py` follow
this same shape, so adding a 9th scenario is just one more `TestCase` entry
plus one more checker function.

## Run it

```
cd day-5
source .venv/bin/activate     # or: python3 -m venv .venv && pip install -r requirements.txt
cp .env.example .env          # paste in your GEMINI_API_KEY, if not already done

cd agent-evals
python eval_harness.py
```

Makes ~12-20 real, billed API calls (one run per scenario, 5 for scenario
7) - don't loop this in CI. Every scenario passed in testing with
`gemini-flash-latest`, including 5/5 on the non-determinism check - a
genuinely strong result, not a scripted one. That's not a reason to skip
scenario 7 in a demo: the whole point is that you can't know a model is
that reliable without running it more than once. To see the harness catch
something, try a weaker/cheaper model via `GEMINI_MODEL` in `.env`, or add
a harder task (e.g. an ambiguous city name, or a date phrase like "the
Friday after next").

## Suggested demo order

Highest-impact for a live walkthrough, in this order: **#7** (the "why
can't we just test once" moment - run it live and watch the pass rate),
**#1** (concrete, easy to show as an argument diff), **#3** (dramatic
failure mode - a fabricated booking is the kind of bug that actually hurts
someone), **#5** (ties it together - shows correctness spans the whole
trajectory, not just the last tool call).
