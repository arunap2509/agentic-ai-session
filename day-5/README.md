# Day 5 — Self-Evolving Agents, Prompt Caching, Agent Evals, a Tiny LLM & LangChain/Langfuse

Six independent, small projects, each making one point with real
execution and detailed output rather than a summarized result.

## How to run

```
cd day-5
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY (same key as earlier days works), plus
                        # LANGFUSE_SECRET_KEY/PUBLIC_KEY/BASE_URL for langchain-agent-evals/
```

Then see each project's own README for what to run and what to expect:
`self-evolving-agent/README.md`, `prompt-caching/README.md`,
`agent-evals/README.md`, `tiny-llm/README.md`,
`langchain-agent-evals/README.md`, `langchain-chat-agent/README.md`.

## What each component does

### `self-evolving-agent/`
An agent that starts with almost no tools and writes its own at runtime -
call it with a task needing shell access and it writes and registers a
`run_bash_command` tool on the spot, then calls it on its very next turn.
Every tool it creates is saved to `tools/` and reloaded automatically next
time, so its capabilities only grow across sessions. Console output shows
every meta-tool invocation, the generated source, the loaded function
signature, and each step's thought/action/observation in full.

### `prompt-caching/`
Two scripts sharing one ~1,200-token system prompt and 5 questions:
`prompt_caching_demo.py` compares no caching vs. an explicit context cache,
reporting real token counts, per-call cost breakdown, cache hit rate, and
latency percentiles from live API calls. `dynamic_prompt_agent.py` shows
what happens when the prompt isn't actually static - a naive agent that
bakes the current timestamp into the cached prompt gets 0% cache reuse and
pays more than not caching at all, versus a fixed agent that keeps the
timestamp in the per-call message and gets 100% reuse.

### `agent-evals/`
Scores a small fixed-toolset travel-booking agent against 8 concrete
tool-use failure modes - wrong argument, wrong tool picked, hallucinated
action, missing-argument handling, multi-step trajectory correctness,
retry/infinite-loop behavior, non-determinism (same task run 5x), and
efficiency - by inspecting the full trajectory (every tool call, args,
result, in order), not just the final answer.

### `langchain-agent-evals/`
The exact same 8 scenarios and checkers as `agent-evals/`, ported onto
LangChain's `create_agent` instead of the hand-rolled loop, with every LLM
call and tool call traced to Langfuse instead of only ever existing as a
console transcript. Built to compare directly against `agent-evals/`: same
fixture data, same tasks, same fixed `TODAY`, same pass/fail logic - the
only variable is the framework and the added observability layer.

### `langchain-chat-agent/`
A simple multi-turn conversational agent (3 tools: current time, a safe
calculator, mocked weather) built to make the tool-calling loop visible
rather than to prove anything - each turn streams step by step (tool call
→ result → reply) instead of only showing the final answer, and it
genuinely remembers earlier turns via LangGraph's `MemorySaver`
checkpointer. Also traced to Langfuse. The one you actually chat with.

### `tiny-llm/`
The odd one out - not an API call to Gemini at all, but a small
decoder-only transformer, custom BPE tokenizer, and training loop built
from scratch on PyTorch, trained on synthetic addition and string-reversal
tasks so correctness is objectively checkable rather than eyeballed.
Reports held-out accuracy (same difficulty, unseen examples - the real
generalization check) against extrapolation accuracy (harder than
anything trained on - where plain transformers are known to break down).
Fully local and offline; `generate.py` runs inference anywhere PyTorch
installs, with no retraining needed.

### `common/` (shared by the three Gemini-backed projects)
- `llm.py` - Gemini client setup, including `CACHE_MODEL` (a model your API
  key actually has `createCachedContent` access to - see prompt-caching's
  README for a gotcha here).
- `agent_loop.py` - the fixed-toolset ReAct loop `agent-evals/` runs on
  (not used by `self-evolving-agent/`, whose toolset changes mid-run and
  needs its own loop - see that project's README).

`tiny-llm/` doesn't use `common/` at all - it doesn't call Gemini.

langfuse -> https://us.cloud.langfuse.com/project/cmrxtyxgv01jlad0jquotebry/traces