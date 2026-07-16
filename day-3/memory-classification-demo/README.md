# Memory Classification Demo

A standalone day-3 project - not part of Data Analyst Agent, Ticker
Triaging Agent, or Coding Agent, and doesn't reuse anything from them.
One model call reads a conversation transcript, extracts every distinct
piece of information in it, and classifies each into one of five memory
types with a one-line rationale. Pure classification - nothing here
writes to a database, a vector store, or a file. The output is a table,
not a stored memory.

## The five categories

| Category | What it means |
|---|---|
| **In-Context Memory** | Only matters for finishing the current exchange - not worth remembering once the conversation ends. |
| **Key-Value Store** | A small, stable, durable fact about the user (name, role, a stated preference, a config-like value) - cheap to store as a single fact, looked up later by key. |
| **Vector Memory** | Part of a larger, growing body of content, better retrieved later by meaning/similarity than by exact key - a note, an explanation, something searchable by paraphrase. |
| **Episodic Memory** | A specific past event, decision, or interaction referenced in time ("last time", "we decided", "I told you before") - tied to a moment, not a standalone fact. |
| **Procedural Memory** | A repeated pattern of behavior or a preferred way of doing a recurring task, inferred from the user doing/asking for the same shape of thing more than once. |

`memory_classifier.py`'s system instruction carries these same five
definitions verbatim into the model call, plus one explicit rule:
procedural requires a real repeat in the transcript to earn the label,
not a single request - otherwise every one-off preference would get
tagged procedural.

## Run it

```bash
cd day-3
source .venv/bin/activate
python memory-classification-demo/memory_classifier.py
```

Picks interactively from whatever's in `conversations/`. To jump straight
to one (useful mid-demo, to switch without the picker):

```bash
python memory-classification-demo/memory_classifier.py conversation_2_customer_support.md
```

## The three demo conversations, and the answer key for each

Three different domains so the same five categories show up in different
clothing each time - useful for showing this isn't keyed to one script's
wording. Each was written with a specific intended classification per
item; use this table to sanity-check the model's output live, and to
have something ready to point at if it's asked "why did it call that
one X?"

### `conversation_1_general_assistant.md`

| Extracted info | Intended type | Why |
|---|---|---|
| Formal tone + exact spelling of "Nordisk & Vance LLP" for this one email | In-Context | Only matters for finishing this specific email |
| "I'm Priya, backend engineer at a fintech startup" | Key-Value | Small, stable fact about the user |
| The postmortem write-up on the payment-retry outage | Vector | Long explanatory note, kept "in case I need to search back through it" |
| "Like we discussed last Tuesday, we decided on Northwind Analytics" | Episodic | Specific past decision, tied to a moment |
| "Keep it to 3 bullet points max" - stated once, then repeated on the next request | Procedural | Repeated across two separate turns - a real pattern, not a one-off |

### `conversation_2_customer_support.md`

| Extracted info | Intended type | Why |
|---|---|---|
| Order number #48213 | In-Context | Only matters for resolving this one ticket |
| "Enterprise plan, timezone IST" | Key-Value | Small, stable account facts |
| The multi-month carrier-delay pattern write-up (Hub 12, weekend holds) | Vector | Long explanatory note kept so it "doesn't have to be re-explained each time" |
| "Like the agent I spoke to last month told me..." | Episodic | Specific past interaction, tied to a moment |
| "Always cc my manager on tickets like this" - stated, then repeated/reconfirmed | Procedural | Repeated instruction, framed explicitly as standing policy |

### `conversation_3_coding_assistant.md`

| Extracted info | Intended type | Why |
|---|---|---|
| "Write a CSV parser that returns total revenue" | In-Context | The one-off task itself |
| "For this function, use snake_case, just double-checking" | In-Context (model called this Procedural in testing - see below) | Framed as a one-off double-check, not a new standing rule |
| "I mainly write Python, 4-space indentation" | Key-Value | Small, stable fact about the user |
| The order-processing architecture design note | Vector | Long note kept to "reference specific parts of it later" |
| "Remember last week we decided REST → GraphQL" | Episodic | Specific past decision, tied to a moment |
| "Add type hints to every function" - stated, then repeated ("same as I mentioned before") | Procedural | Repeated across two turns, explicitly called a "standing thing" |

**Worth knowing going in:** in testing, the model classified the
snake_case line as Procedural, not In-Context as intended - its
reasoning was that a style correction implicitly sets an ongoing
preference, not just a one-off fix. That's a legitimate alternate read,
not a wrong answer - the line between "correcting this one output" and
"establishing a standing preference" is genuinely fuzzy, and it's good
live material: ask the room which read they'd have picked, rather than
treating it as the model getting it wrong.

## Things worth trying live

- **Same categories, different domain** - run all three back to back to
  show the classification logic isn't keyed to one script's phrasing.
- **Point at the disagreement above** - a real case where reasonable
  people (and the model) can land on different categories for the same
  line, and why that ambiguity is inherent to the task, not a bug.
- **Write a fourth conversation on the spot** - drop a new `.md` file into
  `conversations/` (or just edit one of these) and rerun; no code changes
  needed to demo a new scenario.
