# Day 4 — Multi-Agent Systems

> Status: planning document only — nothing in this folder is built yet.
> **See `PLAN.md` first** — it supersedes this file's planning content with
> the real, verified Day 3 interfaces and a revised agenda. This file has
> some stale guesses (e.g. the Ticker Triaging Agent's signature below
> isn't what actually got built).

## Where this sits in the arc

- Day 2 taught the multi-agent patterns (Sequential, Routing, Parallelization,
  Orchestrator-Workers, Evaluator-Optimizer) as dummy, standalone examples.
- Day 3 builds two real, single-agent products: the Data Analyst Agent and
  the Ticker Triaging Agent.
- Day 4 stops being hypothetical: it takes those two real Day 3 agents and
  makes them collaborate as workers under an Orchestrator, with an Evaluator
  checking the combined output. Every claim Day 2 made about multi-agent
  systems (cost, latency, debugging surface, trust boundaries, agent
  identity) gets demonstrated for real instead of asserted on a slide.

Time budget: ~90 minutes.

## Agenda

| Segment | Time | What happens |
|---|---|---|
| Framing | 10 min | Recap Day 2's "is the task genuinely separable by specialty?" test and "what multi-agent costs you" (more calls, more latency, harder to debug) — today we get real numbers instead of a claim |
| Build: Orchestrator-Workers | 35–40 min | Orchestrator takes one request, delegates to the Data Analyst and Ticker Triaging agents as workers, synthesizes a combined report |
| Build: Evaluator-Optimizer | 15–20 min | A separate Evaluator agent checks the combined report against an explicit checklist and kicks it back for revision on failure |
| Governance close | 15 min | Per-worker tool scoping, agent identity, inter-agent trust boundaries — Day 2's unresolved threads, paid off |
| Buffer / optional Sequential aside | 5–10 min | If time remains: a small 2-agent Sequential handoff for contrast |

## What Day 3 needs to hand off

For Day 4 to reuse the Day 3 agents cleanly (not copy-paste them), each Day 3
agent's core logic is a plain importable function, separate from its
`__main__` CLI runner. This is now built and tested for the Data Analyst
Agent, so the real (not guessed) signature is:

- `data_analyst_agent(question: str, session: Session | None = None) -> tuple[str, Session]`
  — pass `session=None` for the one-shot call Day 4's Orchestrator will
  make; the returned `Session` is only needed if something wants to
  continue the conversation with a follow-up, which the Orchestrator
  won't. `Session` is defined in `day-3/common/agent_loop.py`.
- `ticker_triage_agent(request: str) -> str` — same one-shot shape, for the
  ticker side, not yet built.

Also worth reusing directly rather than reimplementing: `day-3/common/agent_loop.py`'s
`run_tool_loop` is the one real ReAct loop every Day 3 script runs on. If
the Ticker Triaging Agent (Day 3, project 2) is built on it too, Day 4's
workers share the same underlying mechanics, which matters for the
governance section below — the same tool-scoping guarantee applies
identically to both workers rather than being reimplemented per-agent.

Each keeps its own tool registry internal to itself — Day 4 never reaches
into either agent's tools directly, only calls the function. That boundary
*is* the least-privilege point made concrete: the Orchestrator can't
accidentally let the Ticker worker touch the internal sales DB, because it
has no handle to that tool at all.

## Architecture

```
day-4/
  README.md
  .env, .env.example, requirements.txt
  common/                     (reused/adapted from day-3)
  workers/
    data_analyst_worker.py    (imports day-3's data_analyst_agent)
    ticker_triage_worker.py   (imports day-3's ticker_triage_agent)
  orchestrator.py             (Orchestrator-Workers build)
  evaluator.py                (Evaluator-Optimizer close loop)
```

**Orchestrator-Workers build:**
1. Orchestrator receives one top-level request (e.g. "give me a morning
   briefing" or "just check AAPL for me").
2. Orchestrator decides *at runtime* which worker(s) are actually needed —
   not always both. A ticker-only question shouldn't wake the Data Analyst
   worker. This is the same dynamic-delegation shape as Day 2's
   `08_orchestrator_workers.py`, now deciding between two real agents
   instead of two prompted sub-tasks.
3. Needed workers run concurrently (`asyncio.gather`, same pattern as Day
   2's `07_parallelization.py`) when more than one is required.
4. Orchestrator synthesizes a single combined report from whatever worker
   output(s) came back.

**Evaluator-Optimizer close:**
1. Evaluator agent (separate from the Orchestrator) checks the synthesized
   report against an explicit checklist: does it cover what was asked, does
   it flag any low-confidence ticker items appropriately, is it within a
   reasonable length.
2. On FAIL, feedback goes back to the Orchestrator's synthesis step (not
   back to the workers — keep the retry cheap) for one revision, capped at
   2–3 rounds, same cap style as Day 2's `09_evaluator_optimizer.py`.

## Governance close — what actually gets demonstrated

- **Tool scoping / least privilege**: each worker's Gemini call only ever
  registers its own tools (Data Analyst worker never sees the market-data
  tool; Ticker worker never sees the internal DB tool). This is Day 2's
  allowlist/blocklist slide, applied at the worker boundary instead of a
  single agent's tool list.
- **Agent identity**: each worker is framed as its own scoped principal
  (Day 2's "Agent Identity: A New IAM Principal" slide) — worth literally
  naming/tagging each worker's identity in logs, so a compromised or
  misbehaving worker's blast radius is visibly contained to its own tools.
- **Trust boundary, one level up**: Day 2 covered "every MCP server is a new
  trust boundary" — here the same idea applies to the Orchestrator trusting
  worker output. What happens if a worker returns something wrong or
  malformed? The Evaluator step is partly this answer.
- **Real cost/latency numbers**: print how many model calls the whole run
  took and how long it took end to end, and compare that honestly against
  what a single Day 3 agent call costs. This makes Day 2's "what
  multi-agent costs you" slide concrete instead of asserted — and sets up
  Day 5's Observability segment, which formalizes this same measurement
  into a reusable trace wrapper.

## Open questions to resolve before building

- Exact checklist criteria for the Evaluator (needs to be specific enough
  to reliably catch a real gap, same lesson learned building Day 2's
  Reflection demo — vague criteria just rubber-stamp).
- Whether the optional Sequential-handoff aside is worth the time or better
  cut in favor of a longer governance close.
