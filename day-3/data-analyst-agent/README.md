# Data Analyst Agent

Four stages, each one a before/after pair: show the gap first, then the
fix. Every capability here got added because testing showed a specific
failure, not because it seemed like a good idea to include - and every
fix genuinely carries forward into `full_agent.py`, not just its lesson.

## The real import graph

```
common/agent_loop.py        the one real ReAct loop (run_tool_loop, Session)
        ^
        |
base_agent.py                defines run_query, SYSTEM_INSTRUCTION
        ^
        |
failure_handling.py           defines run_query_grounded, GROUNDED_INSTRUCTION
        ^                     (imports run_query, SYSTEM_INSTRUCTION from base_agent)
        |
full_agent.py                 imports run_query_grounded + GROUNDED_INSTRUCTION from
                               failure_handling, SYSTEM_INSTRUCTION + run_query from
                               base_agent, run_tool_loop + Session from common.agent_loop
```

`memory.py` also imports from `base_agent.py` and calls `run_tool_loop`
directly - it's a lateral demo, not part of the chain toward `full_agent.py`.

This used to not be true: `full_agent.py` originally re-implemented its own
version of the loop and used the plain, ungrounded `run_query`, meaning the
"complete" agent had silently dropped two of the three earlier fixes. Fixed
by pulling the loop into `common/agent_loop.py` (one real implementation,
not four copies with drift) and having `full_agent.py` actually import
`failure_handling.py`'s grounded tool instead of re-deriving the concept.

| Script | What it shows | What to point at in the code |
|---|---|---|
| `base_agent.py` | One tool, one question, one answer - the floor, not the ceiling | The tool's docstring (= the schema contract) and `run_tool_loop` in `common/agent_loop.py` |
| `failure_handling.py` | Naive vs. grounded on "What was Q3 2026 revenue?" (Q3 has zero rows - it hasn't happened yet) | The naive agent doesn't fabricate a wild number - it does something subtler and more realistic: it correctly notices there's no data, then still states "$0.00" as if that were an observed fact, conflating absence of data with a zero value. The grounded tool returns an explicit `row_count: 0` signal instead of an ambiguous SQL NULL, plus an instruction that a zero row count is not the same as zero revenue |
| `memory.py` | Stateful vs. stateless on a follow-up ("Now break that down by region" - no quarter restated) | The `contents` list threaded into `run_tool_loop`. Stateful carries Turn 1 forward so "that" resolves to Q1; the numbers prove it (stateful breakdown sums to exactly Q1's total). Stateless doesn't ask for clarification - it silently answers a different question (all-time revenue instead of Q1), which is a more dangerous failure than asking a question would be |
| `full_agent.py` | Unbounded vs. bounded investigation depth, plus the full, real report pipeline | See below - this is the centerpiece |

## `full_agent.py` in detail

**Unbounded vs. bounded** - tested, not assumed: this model doesn't need
forcing to investigate thoroughly. Left with no guidance on an open-ended
question ("how did Q2 go, anything to worry about?"), it drills all the
way to product-level detail across every region and category, most of it
irrelevant, and can burn its entire step budget without ever reaching a
conclusion. The failure isn't laziness, it's waste. `BOUNDED_INSTRUCTION`
- "stop once you've found the specific driver, don't keep checking
everything" - turns that into a focused investigation that correctly
isolates LATAM -> Electronics -> Laptop and nothing else.

`max_steps` stays as a hard, deterministic ceiling in both cases - the
instruction shapes whether that budget gets spent well, it doesn't replace
having a budget. If the instruction fails, the ceiling still catches it.

**The report pipeline** - `data_analyst_agent()` uses `run_query_grounded`
(imported, not reimplemented) for the entire investigation, so it's
protected from the "no data means $0" failure the whole time, not just
checked for it after the fact. Its instruction chains from
`GROUNDED_INSTRUCTION`, adding only the bounded-investigation and
report-writing clauses on top - a legible composition that mirrors the
stage progression instead of hiding it.

Once the agent has a finding, it calls the `write_report` EXECUTE tool,
gated by two independent checks before anything "sends":

1. **Grounding check** - a second, separate model call: does every claim
   in the findings/recommendation trace back to an actual query result
   gathered *anywhere in the conversation so far*, not just this turn?
   That last part matters and was a real bug during development: a
   follow-up's report can legitimately reference a fact established two
   turns ago without re-querying it (re-verifying everything every turn
   would just be the wasteful-investigation problem again) - so
   observations accumulate across the whole `Session`, not per-call.
   Caught fabrications in real testing (a claim about monthly product
   trends the model never actually queried for), so this isn't a
   theoretical safeguard.
2. **Human-in-the-loop gate** - a plain Python check, not an LLM call:
   `if report_args["recommendation"].strip()`. A report with only factual
   numbers sends automatically; a report with a recommendation (an
   interpretive claim, not just a fact) pauses on `input()` for approval.

**Follow-ups** - `data_analyst_agent(question, session=None)` returns
`(answer, session)`. Pass `session=None` for a one-shot call (what Day 4's
Orchestrator does); pass the `Session` returned from a previous call to
continue the same conversation - the same memory mechanism `memory.py`
demonstrates, actually present in the finished agent rather than dropped
at the last stage.

**Running it** - `python full_agent.py` runs the fixed unbounded-vs-bounded
comparison once (a controlled demonstration, not "talking to the agent"),
then hands control to you: a real interactive prompt, your questions and
follow-ups, not scripted ones. Blank line to quit.

## Things to try when it's your turn

Roughly ordered simple -> deep, so a demo can start trivial and escalate
live rather than jumping straight to the hard case.

**Tier 1 - raw lookups, one query, no math** (good opener - proves it can
just fetch data like a database client, before doing anything clever):

- "Show me 5 orders from LATAM."
- "What's the most recent order in the database?"
- "List every order for the product Laptop placed in January 2026."
- "What products do we sell, by category?"
- "Show me one example order from the Software category."
- "What regions do we have data for?"

**Tier 2 - simple counts and totals** (one number, still one query):

- "How many orders are in the database?"
- "What was total revenue in Q1 2026?"
- "How many orders came from Europe in Q2 2026?"
- "What's the average revenue per order?"
- "How many Laptops did we sell in Q1 2026?"

**Tier 3 - breakdowns** (group by one dimension, still a single query,
just more useful than a raw total):

- "Break down Q2 2026 revenue by region."
- "Which category sold the most units in Q1 2026?"
- "How does LATAM's Q2 compare to the other regions?"
- "Break down Q1 2026 revenue by product category."

**Tier 4 - open-ended investigation** (multi-step, the actual centerpiece):

- "How did Q2 2026 go? Anything I should be worried about?" - should land
  on LATAM -> Electronics -> Laptop.
- "What was total revenue in Q3 2026?" - the no-data case; watch it say so
  plainly instead of stating a number.

**Follow-ups** to try after any of the above (no need to restate context -
that's the point):

- "Now break that down by region." (after a Q1 total)
- "Was that decline already happening in Q1, or is it new this quarter?"
- "Which specific product is driving that?"
- "How does that compare to how Electronics did in the other regions?"
- "Show me a few example orders from that segment." (mixes a Tier-4
  finding with a Tier-1-style raw lookup, as a follow-up)
- "What should we do about it?" - tends to actually produce a
  recommendation, worth trying at least once to see the human-in-the-loop
  pause fire for real.

## What's actually a guardrail vs. what's a prompt instruction

Worth being precise about this distinction rather than lumping everything
under "safety":

- **Restrictive (code, guaranteed):** SQL validation blocks anything but
  SELECT, regardless of what the model tries to write. The HITL gate is a
  deterministic field check, not a model judgment call.
- **Anti-hallucination (mixed):** the explicit `row_count: 0` signal is a
  tool/data design change; the "don't guess" instruction is a prompt. Both
  needed - the signal removes the ambiguity, the instruction tells the
  model what to do about it.
- **Operational (code, guaranteed):** `max_steps` is a hard ceiling on
  every loop in this project.
- **Directive, not restrictive (prompt):** the bounded-investigation
  instruction doesn't prevent something bad, it prevents something
  *wasteful*. A model capable of stopping at the right point won't
  reliably do it without being told what "the right point" means.

The rule of thumb: if a problem has a deterministic answer (never allow a
write query, always require sign-off on a recommendation, never run past N
steps), put it in code, where it's guaranteed. If the problem requires
judgment about the actual content of a result (has this investigation
found enough to stop), it has to live in the prompt, because code can't
inspect the meaning of an arbitrary query result without re-implementing
the same judgment.
