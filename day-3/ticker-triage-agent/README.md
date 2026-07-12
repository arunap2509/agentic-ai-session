# Ticker Triaging Agent

The deliberate contrast to the Data Analyst Agent: that one is **depth** -
one agent adaptively deciding how many rounds of investigation a question
needs. This one is **breadth** - the same fixed five-step pipeline
(classify, enrich, route, execute, log) applied to many events, where only
one step is a judgment call at all. Nothing here decides its own control
flow - the sequence is fixed in code, on purpose, because for a repeatable
triage decision that's the correct design, not a lesser one. Recognizing
you *don't* need an adaptive loop is as much a design decision as building
one.

It's also not just a classifier that describes what should happen - it
acts. Once the final action is known, a real (mocked) EXECUTE tool runs:
`flag_for_analyst` notifies a human, `file_as_routine` auto-archives,
`hold_for_later` queues it for follow-up. Same RETRIEVE/EXECUTE split Day
2 taught and the Data Analyst Agent's `write_report` demonstrated - this
project only had the RETRIEVE half (`enrich_ticker`) until this was added.

One file, `triage_agent.py` - no separate stage scripts this time, because
there's no naive-vs-fixed progression to demonstrate the way there was for
the Data Analyst Agent. The separation of concerns lives at the function
level: `classify_event` (the one model call), `enrich_ticker` (a plain
lookup, not even routed through tool-calling since there's no judgment
about whether to enrich - it always happens), `decide_routing` (plain
code, not a model call), the three execute tools (also plain code
dispatch - which one runs is already fully decided by the time we get
there, so it isn't handed back to the model as a new choice), and
`log_rationale`.

## Run it

```bash
python triage_agent.py
```

Always asks the same four questions, in the same order, every time -
Ticker, Headline, Price change %, Volume ratio - no shortcuts, no
auto-fill. Predictability was worth more here than saving a few
keystrokes. Blank ticker to quit and see the audit summary.

## Events to try - full input for each, verified live

| Ticker | Headline | Price change % | Volume ratio | Outcome |
|---|---|---|---|---|
| `AAPL` | Apple reports record Q2 earnings, beats estimates by 15% | `8.2` | `3.5` | Auto-flagged - confident, real news |
| `TSLA` | Tesla recalls 200,000 vehicles over brake defect | `-6.5` | `4.2` | Auto-flagged - confident, real news |
| `XOM` | Exxon announces major offshore oil discovery | `5.7` | `2.9` | Auto-flagged - confident, real news |
| `MSFT` | Microsoft stock ticks up slightly in quiet trading | `0.3` | `0.9` | Auto-filed - confident, nothing happening |
| `KO` | Coca-Cola shares steady ahead of dividend date | `0.1` | `1.0` | Auto-filed - confident, nothing happening |
| `JPM` | JPMorgan shares dip amid broader banking sector weakness | `-1.2` | `1.3` | Auto-filed - confident, nothing happening |
| `GME` | Unusual options activity detected in GME, reason unclear | `2.1` | `2.8` | Escalates - notable move, no stated cause |
| `NFLX` | Reports circulate about possible executive changes at Netflix; company declines to comment | `2.4` | `1.6` | Escalates - notable move, no confirmed cause |
| `ZVXQ` | Speculative small-cap ZVXQ surges on takeover rumor | `12.3` | `6.1` | Escalates - ticker not in our lookup, regardless of confidence |

Two more, using tickers above but a *different* headline each time - worth
showing it's reading the new headline, not memorizing an outcome per
ticker:

| Ticker | Headline | Price change % | Volume ratio | Outcome |
|---|---|---|---|---|
| `AAPL` | Apple announces $50 billion stock buyback program | `4.5` | `2.2` | Auto-flagged - confident, real news |
| `TSLA` | Tesla shares move on unconfirmed rumor of production halt at Shanghai plant | `3.2` | `2.1` | Escalates - notable move, no confirmed cause |

Try `AAPL` right after `ZVXQ` - same shape of headline (big move,
exciting news), opposite outcome, because one of them we can actually
verify context for and one we can't.

## The two guardrails, and why they're both code, not prompts

- **Confidence below threshold -> escalate.** The threshold check itself
  is a plain `if`, not a model call - deterministic, guaranteed. What
  *is* a judgment call is the confidence score itself, which is why
  `CLASSIFY_INSTRUCTION` spends real effort calibrating it: a notable
  move with no stated cause must score low, a small move with nothing
  happening can score high even without a cause (there's nothing to
  explain) - getting this distinction wrong was the first bug caught
  while testing this (see below).
- **Unrecognized ticker -> escalate, no matter what.** Also plain code.
  If there's no context to check the classification against, the system
  doesn't get to decide it's confident anyway.

## Two real bugs this surfaced while testing (worth telling as the story, not hiding)

1. **Confidence meant the wrong thing at first.** The initial instruction
   asked "how confident are you this needs attention" - which meant a
   routine, nothing-happening event correctly scored near 0, and the
   routing logic then escalated it, backwards from what should happen.
   Confidence needs to mean "how sure am I in this call, whichever way it
   goes" - not "how urgent is this." A confidently-routine event should
   auto-file, not get bumped to a human.
2. **Once fixed, the model was too consistently confident to ever
   escalate on its own** - it took a concrete, checkable rule ("if there's
   a notable move with no named cause, confidence must be low") rather
   than an abstract "rate your certainty" ask, to get genuine, reproducible
   low-confidence cases. Same lesson as forcing Thought-narration in the
   Data Analyst Agent's ReAct demo: a model capable of expressing
   uncertainty won't reliably do it without a concrete rule for when to.
