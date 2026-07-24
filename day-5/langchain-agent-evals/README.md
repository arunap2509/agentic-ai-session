# Agent Eval Harness — LangChain + Langfuse

Same travel-booking agent, same 8 tool-use failure modes as
[`../agent-evals/`](../agent-evals/README.md) — this version swaps the
hand-rolled ReAct loop for LangChain's `create_agent`, and adds real
observability: every LLM call and tool call for every scenario shows up as
a trace in Langfuse, not just a rich-console transcript that disappears
when the terminal scrolls.

## What's actually different from `../agent-evals/`

| | `../agent-evals/` | This project |
|---|---|---|
| Agent loop | Hand-rolled (`../common/agent_loop.py`) | `langchain.agents.create_agent` (LangGraph under the hood) |
| Tool definitions | Plain Python functions + docstrings | Same functions, `@tool`-decorated |
| Trajectory format | `LoopResult.observations` | LangGraph's message list, adapted to the same shape (see `Trajectory` in `travel_agent.py`) |
| Observability | None beyond the console output | Every run traced to Langfuse (`LANGFUSE_BASE_URL`) |
| Scenarios, tasks, checkers, fixture data | — | **Identical** — copied over, not redesigned |

The 8 checkers in `eval_harness.py` are the exact same logic as the
original, just retyped against `Trajectory` instead of `LoopResult` - the
point of keeping `Trajectory`'s fields (`observations`, `final_text`,
`exhausted`) name-for-name identical to the original `LoopResult` is that
the scoring logic shouldn't care which framework produced the trajectory.
That's also what makes the two projects' results genuinely comparable.

## The framework substitution, concretely

- **Agent construction**: `create_agent(model=ChatGoogleGenerativeAI(...), tools=[...], system_prompt=SYSTEM_INSTRUCTION)` — a few lines, no manual prompt templating.
- **Trajectory extraction**: LangGraph returns a flat list of `HumanMessage` / `AIMessage` (with `.tool_calls`) / `ToolMessage` objects. `_to_observations()` in `travel_agent.py` matches each `ToolMessage` back to the `AIMessage.tool_calls` entry that produced it (via `tool_call_id`) to rebuild the same `{name, args, result}` shape the checkers expect.
- **Step limits**: LangGraph's `recursion_limit` counts graph-node executions (roughly 2x our old "loop iteration" count - one node for the model call, one for tool execution), and critically, **exceeding it raises `GraphRecursionError`** rather than returning a partial result the way the old loop's `max_steps` did. That exception doesn't carry the partial trajectory, so `run_task` catches it and reports `exhausted=True` with an empty trajectory - the retry-detection checker (scenario 6) already treats `exhausted` as an automatic fail, so the verdict is still correct even though the retry *count* in that specific failure message is lost.

## Langfuse observability

Every call to `run_task` creates a fresh `CallbackHandler()` and passes it
via `config={"callbacks": [handler]}` - LangChain's standard tracing
integration point, no manual span creation. `flush_traces()` is called
once at the very end of the whole harness run (not per-task) because the
Langfuse SDK batches and exports asynchronously; without an explicit flush
a short-lived script can exit before its last few traces are actually sent.

Open your Langfuse project after a run to see, per scenario: the full
message trajectory, every individual LLM call's token usage and latency,
and every tool call's exact arguments and return value - the same
information the checkers use to grade, but browsable instead of only ever
existing as a one-line PASS/FAIL.

## Run it

```
cd day-5
python3 -m venv .venv && source .venv/bin/activate   # if not already set up
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY + LANGFUSE_SECRET_KEY/PUBLIC_KEY/BASE_URL

cd langchain-agent-evals
python eval_harness.py
```

Makes the same ~12-20 real, billed Gemini API calls as `../agent-evals/`
(one run per scenario, 5 for scenario 7), plus writes traces to Langfuse -
don't loop this in CI.
