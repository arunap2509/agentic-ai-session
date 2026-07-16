# Day 3 — Building Real Agents

Four hands-on projects, three of them real, single-agent products
deliberately contrasting in shape: `data-analyst-agent/` is depth (one
agent, adaptive investigation), `ticker-triage-agent/` is breadth (a fixed
pipeline applied to many events), `coding-agent/` is side effects (tools
that write files and execute code, not just read data). The fourth,
`memory-classification-demo/`, is a standalone classification demo, not
an agent contrast - see its own README for what it's for.

## Setup (do this once)

```bash
cd day-3
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set GEMINI_API_KEY (get one free at https://aistudio.google.com/apikey)

python data/seed_orders_db.py
```

The seed script generates `data/orders.db` (gitignored) - run it once before
using any of the Data Analyst Agent scripts. It's deterministic (fixed
random seed), so it produces the same data - and the same planted anomaly -
every time.

## What's in `data-analyst-agent/`

Four scripts, each a self-contained stage that adds one capability on top
of the last. See `data-analyst-agent/README.md` for what each one
demonstrates and what to point at in the code.

```bash
source .venv/bin/activate
python data-analyst-agent/base_agent.py
python data-analyst-agent/failure_handling.py
python data-analyst-agent/memory.py
python data-analyst-agent/full_agent.py
```

`full_agent.py`'s `data_analyst_agent(question, session=None) -> (answer,
session)` function is also what Day 4 imports and calls as a worker
(passing `session=None` for a one-shot call). Passing back the returned
`Session` lets a caller continue the same conversation for a real
follow-up - see `data-analyst-agent/README.md` for how that's threaded.

## The dataset

One SQLite table, `orders` (region, category, product, quantity, revenue,
date), covering Q1 and Q2 2026. Two things are planted on purpose:

- **Q3 2026 has zero rows** - it hasn't happened yet. This is the
  guaranteed no-data case `failure_handling.py` uses.
- **LATAM's Electronics revenue drops ~60% from Q1 to Q2** while every
  other region/category grows normally. Invisible from a single top-line
  query - only findable by drilling overall -> region -> category -> (as
  it turns out, the model goes one level further on its own) product.
  This is what `full_agent.py`'s investigation is built to find.

## What's in `ticker-triage-agent/`

One file, no separate stages this time - see `ticker-triage-agent/README.md`
for why, and for which mock tickers to try.

```bash
source .venv/bin/activate
python ticker-triage-agent/triage_agent.py
```

No seed step needed - its mock data (`data/ticker_data.py`) is plain
Python, not a generated database.

## What's in `coding-agent/`

One file, `coding_agent.py` - a self-correcting agent: give it a task
(write something from scratch, or fix a buggy file you point it at), and
it writes code, runs it, reads its own stdout/stderr as the observation,
and rewrites if it failed. See `coding-agent/README.md` for the one rule
that keeps it from claiming success without actually verifying it, and for
scenarios worth trying.

```bash
source .venv/bin/activate
python coding-agent/coding_agent.py
```

## What's in `memory-classification-demo/`

One file, `memory_classifier.py` - reads a conversation transcript and,
in a single model call, extracts every distinct piece of information in
it and classifies each into one of five memory types (in-context,
key-value, vector, episodic, procedural) with a rationale. Classification
only - nothing is stored anywhere. Three demo conversations live in
`conversations/` so you can switch which one you're showing without
touching code. See `memory-classification-demo/README.md` for the five
category definitions and the answer key for each demo conversation.

```bash
source .venv/bin/activate
python memory-classification-demo/memory_classifier.py
```

## Notes for the live session

- `full_agent.py` is interactive - it runs one fixed comparison first (why
  the bounded instruction matters), then prompts you for real questions
  and follow-ups from the terminal. It's a real agent to talk to, not a
  scripted transcript. See `data-analyst-agent/README.md` for starter
  questions and natural follow-ups if you want them ready going in.
- `full_agent.py`'s HITL gate only pauses on `input()` when the agent's
  report includes a recommendation. In testing, the agent sometimes
  correctly leaves the recommendation blank (it knows revenue dropped, not
  *why*, and doesn't invent a cause) - if that happens live, the gate
  won't visibly fire. Worth knowing going in, not a bug.
- The grounding check is a real, working check, not a rubber stamp - in
  testing it has genuinely caught the model making claims it never
  verified (e.g. describing a monthly trend for a specific product it
  only ever queried at the category level). That means the report can
  come back "held back, not sent" instead of "sent" on any given run.
  That's the guardrail working, not a bug - worth narrating as a feature
  if it happens live rather than treating it as a failed demo.
- `failure_handling.py` and `memory.py` are non-interactive - they just
  run and print both sides of the comparison.
- `common/agent_loop.py` is the one real ReAct loop every script in
  `data-analyst-agent/` actually runs on - see that file's own docstring
  before `data-analyst-agent/README.md` if you want the mechanics first.
- `ticker-triage-agent/triage_agent.py` doesn't use `common/agent_loop.py`
  at all - deliberately. It's not an adaptive loop, so it doesn't need
  one; see that project's README for why that's the point, not a gap.
- For the compare-and-contrast segment: run `AAPL` then `ZVXQ` back to
  back in the ticker agent - same shape of dramatic headline, opposite
  routing outcome, because one has verifiable context and one doesn't.
