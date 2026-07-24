# Prompt Caching Demo

Answers one question with real numbers from live API calls: does Gemini's
explicit context caching actually pay for itself for a chatty tool with a
large, mostly-static system prompt?

The scenario: a PostgreSQL on-call assistant with a ~1,200-token system
prompt (real operational guidance - locking, autovacuum, replication lag,
schema changes, connection pooling, backups, EXPLAIN plans), asked 5
different on-call questions. Two scripts, sharing that same prompt and
question set:

- `prompt_caching_demo.py` - no caching vs. caching, on a genuinely static
  prompt.
- `dynamic_prompt_agent.py` - what happens when the prompt *isn't* actually
  static, because it embeds something that changes every call (the current
  time). See that file's own section below.

## Phase 1 - No Caching

Every call sends the full system prompt as plain input tokens via
`system_instruction=`. This is the baseline - what you pay and how long you
wait without doing anything special.

## Phase 2 - With Caching

The system prompt is written to a cache **once** via `client.caches.create`,
then every call references it with `cached_content=<cache name>` instead of
resending it. Gemini bills cached tokens at a reduced rate (this demo uses
25% of the standard input rate, matching Gemini's published cached-input
pricing) - only the per-call question is billed as ordinary input.

The per-call summary line shows the hit/miss and the cached/total token
split for every run, e.g.:

```
Run #01: ● HIT   4.51s  1,218/1,232 cached  (+266 output tokens)
```

## What gets reported (`prompt_caching_demo.py`)

For each phase: total/cached/uncached prompt tokens, output tokens, cache
hit rate, a full cost breakdown (input, cached-read, one-time cache write,
cache storage for the TTL window, output, total), and latency (avg/p50/p95).
An **Overall Summary** table diffs Phase 1 vs. Phase 2 directly - total cost,
uncached tokens, latency, hit rate, net savings - plus the full model
input/output transcript for the last call of each phase, so you can see
exactly what was asked and answered, not just the aggregate numbers.

All caches created by the script are deleted before it exits, including on
error (`try`/`finally`), so nothing keeps accruing storage cost after a run.

## `dynamic_prompt_agent.py` - cache invalidation from a naturally-changing prompt

Rather than manually editing a sentence, this script demonstrates
invalidation the way it actually happens in production: the system prompt
embeds the current server time, which is different on every call by
definition. Two agents, same persona, same 5 questions:

- **Naive agent** - prepends the timestamp to the system prompt and calls
  `client.caches.create` fresh before every single question. Because the
  timestamp differs each time, so does the prompt text, so no cache is ever
  reused - every one is written once and read exactly once, by the same
  call that just wrote it.
- **Fixed agent** - keeps the timestamp out of the cached content. The
  persona is cached **once**; the current time is passed as part of each
  call's uncached user message instead, so answers are still accurate but
  the cache actually gets reused on every subsequent call.

Each agent reports calls made, new caches written, cache reuse rate, token
split, and full cost breakdown, then a verdict comparing total cost. In
testing, the naive agent wrote 5/5 caches with a 0% reuse rate and cost
**~41% more** than the fixed agent, which wrote 1 cache and reused it on
all 4 remaining calls (100% reuse rate) - a direct illustration that baking
anything volatile into a cached prompt doesn't just fail to save money, it
actively costs more than not caching at all (you still pay write + storage
on top of the read, for a discount you never collect).

## Pricing constants

`PRICE_PER_1M_INPUT`, `PRICE_PER_1M_OUTPUT`, `PRICE_PER_1M_CACHED_INPUT`, and
`PRICE_PER_1M_CACHE_STORAGE_PER_HOUR` near the top of
`prompt_caching_demo.py` mirror Gemini 2.5 Flash's published rates at the
time this was written. Prices change - check
[ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing)
before trusting these for a real budget, and edit the constants if you're
pointed at a different model tier.

## Run it

```
cd day-5
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste in your GEMINI_API_KEY

cd prompt-caching
python prompt_caching_demo.py       # no caching vs. caching
python dynamic_prompt_agent.py      # cache invalidation from a live-changing prompt
```

Each script takes about a minute and makes real, billed API calls
(`prompt_caching_demo.py`: 5 uncached + 1 cache write + 5 cached;
`dynamic_prompt_agent.py`: 5 cache writes + 5 cached calls for the naive
agent, 1 cache write + 5 cached calls for the fixed agent) - non-trivial
cost each time, so don't loop either of these in CI.

**Model note:** explicit caching needs a model your API key is actually
granted `createCachedContent` access to. `models.list()` can advertise the
capability for a model version that still 404s with "no longer available to
new users" for newer keys (this happened with `gemini-2.5-flash` while
building this demo) - `gemini-flash-latest` (the default) worked reliably in
testing. Override with `GEMINI_CACHE_MODEL` in `.env` if yours doesn't.
