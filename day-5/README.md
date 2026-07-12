# Day 5 — RAG, LangChain, Observability, Evals

> Status: planning document only — nothing in this folder is built yet.

## Where this sits in the arc

Day 1 covered concepts, Day 2 covered patterns, Day 3 built one real agent,
Day 4 made agents collaborate. Day 5 is the production scaffolding a real
agent system needs around all of that: how it retrieves knowledge, whether
to hand-roll or use a framework, how you see what it's doing, and how you
know it still works after something changes.

Four substantial topics, 90 minutes total — that's tight enough that this
day is a **survey with one sharp demo per topic**, not four mini hands-on
builds like Days 3–4. Each segment below is designed around a single
before/after comparison rather than a from-scratch build, so it survives
the time budget.

Time budget: 90 minutes total.

## Agenda

| Segment | Time | The one moment that has to land |
|---|---|---|
| Framing | 5 min | Recap the arc: patterns → single agent → multi-agent → what production needs around all of it |
| RAG | 25 min | Naive retrieval gives a wrong/incomplete answer → improved retrieval fixes it |
| LangChain | 15 min | Same tool loop, hand-rolled vs. LangChain, side by side |
| Observability | 15 min | Same Day 4 multi-agent run, once opaque, once traced |
| Evals | 20 min | The real model-deprecation issue we hit this week → a golden-test suite that would have caught it |
| Close | 10 min | Tie the full 5-day arc together |

## RAG (25 min)

**Framing**: this is not a new concept — it's the RETRIEVE tool from Day 2
(Block 1), scaled from "look up one thing" to "search a document corpus."
Keep that link explicit; don't let RAG feel like a left-field new topic.

**Demo shape**: a small, self-referential document corpus — literally this
bootcamp's own Day 2/Day 3 READMEs — so the room already knows the right
answers and can immediately spot when retrieval gets it wrong.

1. Ask a question whose correct answer spans content that a naive
   approach (bad chunking, or just grabbing the top-1 nearest chunk) will
   answer wrong or incompletely.
2. Show the naive RAG pipeline confidently give that wrong/incomplete
   answer — same "confidently wrong" beat as Day 2's date-grounding demo
   and Day 3's no-data case.
3. Fix it (better chunking, more retrieved chunks, or a rerank step) and
   show the same question answered correctly.

**Implementation plan**: keep it dependency-free — Gemini's embedding
endpoint for vectors, plain numpy cosine similarity for retrieval, no
external vector DB. Consistent with the rest of the course's "no extra
infra to fail live" philosophy.

## LangChain (15 min)

**Framing**: "you've hand-rolled the tool-use loop for three days — here's
what a framework abstracts away, and the tradeoff." A build-vs-buy
comparison, not a framework tutorial. This framing matters because without
it, this segment risks feeling redundant after three days of doing it
manually by design.

**Demo shape**: rebuild one existing piece side by side —
`day-3`'s Data Analyst tool loop (hand-rolled, the real one from Day 3) next
to the same behavior in LangChain. Show both actually running. Talking
points: line count, what you get for free (retries, memory, output
parsing), what you lose (visibility into exactly what's being sent to the
model — the same schema/loop transparency Day 2 spent a whole block on).

## Observability (15 min)

**Framing**: this is Day 3/4's "log rationale" idea, reframed — the same
kind of record that serves an audit trail also serves a debugging session.

**Demo shape**: take one Day 4 multi-agent run and show it twice.

1. Unwrapped: just the final output. No way to tell why it was slow, which
   worker did what, how many calls it took.
2. Wrapped: a lightweight DIY trace — a decorator or context manager
   around each step that records step name, duration, and (if available)
   token usage, then prints or dumps a timeline. This formalizes the
   informal call-count/latency printout from Day 4's governance close into
   a small reusable module.

**Implementation plan**: DIY / dependency-free, confirmed — no hosted
observability tool, no external account needed live. Keeps this day
self-contained like everything before it.

## Evals (20 min)

**Framing**: open with the real story — a pinned model
(`gemini-2.0-flash`) actually got deprecated on us mid-build this project,
breaking a working demo with no warning. That's the concrete case for
evals: not a hypothetical, something that happened this week.

**Demo shape**: a small golden-test suite against the Day 3 Data Analyst
agent.
- Exact-checkable cases: does it correctly report no-data for the query
  we know is empty; does it correctly reuse memory on a scripted
  follow-up.
- One open-ended case graded by an LLM-judge, reusing Day 2's
  Evaluator-Optimizer critic shape (a second model call judging against
  explicit criteria — same lesson from Day 2 about vague criteria just
  rubber-stamping, so the judge prompt needs to be specific).
- Run the suite, print a pass/fail table.

## Close (10 min)

Tie the whole 5-day arc together: Day 1 concepts → Day 2 patterns (dummy) →
Day 3 one real single agent → Day 4 real multi-agent collaboration → Day 5
the production scaffolding (retrieval, framework tradeoffs, visibility,
correctness-over-time) that a system built from Days 1–4 actually needs to
survive contact with production.

## Architecture (planned)

```
day-5/
  README.md
  01-rag/
  02-langchain-comparison/
  03-observability/
  04-evals/
  common/                     (reused/adapted from earlier days)
```

## Open questions to resolve before building

- Which specific Day 2/3 README content the RAG demo's "gets it wrong"
  question should target — needs a question where naive retrieval
  genuinely fails, not one crafted to look like it fails.
- Whether the LangChain segment needs its own venv/dependency set or can
  share Day 3's — LangChain pulls in a fair amount, worth isolating so it
  can't destabilize the other segments' environment.
