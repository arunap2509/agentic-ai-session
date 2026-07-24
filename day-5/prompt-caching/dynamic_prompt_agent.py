"""
Dynamic Prompt Agent - dynamic_prompt_agent.py

Companion to prompt_caching_demo.py, answering a narrower but very common
real-world question: what happens when the "static" system prompt you want
to cache isn't actually static, because it embeds something regenerated on
every call - like the current server time?

Two agents, same base persona (prompt_caching_demo.SYSTEM_PROMPT), same 5
questions. The only difference is where the live timestamp goes.

  Naive Agent
      Prepends "Current server time: <now>" to the system prompt on every
      call, then creates a brand new cache for that exact prompt before
      each generate_content call. Since the timestamp differs call to call,
      so does the prompt text, so Gemini can never match it to a previous
      cache - every "cache" is written once and read exactly once, by the
      same call that just wrote it. Net effect: caching returns ZERO
      cross-call reuse, but you still pay full write + storage cost on top
      of the read cost - worse than not caching at all.

  Fixed Agent
      Keeps the timestamp OUT of the cached content entirely. The cache is
      written once from the static persona alone; the current time is
      passed as part of each call's (uncached) user message instead. One
      cache write serves all 5 calls, and each one still gets the real
      current time, because it's fresh input every call rather than frozen
      at cache-creation time.

The fix, in one line: anything that changes per call belongs in the
per-call message, not in the content you hand to client.caches.create.
Gemini caches match on exact byte content - there is no partial reuse, no
fuzzy matching, nothing that rescues a "mostly the same" prompt.

Setup: same as prompt_caching_demo.py - cp ../.env.example ../.env (or
reuse an earlier day's key), and see common/llm.py if GEMINI_CACHE_MODEL
404s for your key.

Run:
    python dynamic_prompt_agent.py
"""

import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from google.genai import types
from rich import box
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prompt_caching_demo import (
    CACHE_TTL_SECONDS,
    PRICE_PER_1M_CACHE_STORAGE_PER_HOUR,
    PRICE_PER_1M_CACHED_INPUT,
    PRICE_PER_1M_INPUT,
    PRICE_PER_1M_OUTPUT,
    QUESTIONS,
    SYSTEM_PROMPT,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import CACHE_MODEL, get_client

console = Console()

SECONDS_BETWEEN_CALLS = 2  # guarantees each call's timestamp actually differs


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class CallRecord:
    index: int
    elapsed: float
    prompt_tokens: int
    cached_tokens: int
    output_tokens: int
    wrote_new_cache: bool
    cache_write_tokens: int  # 0 unless this call is the one that wrote the cache it used


def run_naive_agent(client) -> list[CallRecord]:
    console.rule("[bold]Naive Agent - timestamp baked into the cached prompt[/bold]")
    console.print(
        "Every call prepends the current time to the system prompt, then creates a "
        "fresh cache for it before answering. Watch: every single call writes a "
        "brand-new cache - none of them ever get reused.\n"
    )

    records: list[CallRecord] = []
    for i, q in enumerate(QUESTIONS, start=1):
        timestamp = _now()
        dynamic_prompt = f"Current server time: {timestamp}\n\n{SYSTEM_PROMPT}"

        cache = client.caches.create(
            model=CACHE_MODEL,
            config=types.CreateCachedContentConfig(
                display_name=f"naive-agent-call-{i}",
                system_instruction=dynamic_prompt,
                ttl=f"{CACHE_TTL_SECONDS}s",
            ),
        )
        write_tokens = (cache.usage_metadata.total_token_count if cache.usage_metadata else 0) or 0

        t0 = time.perf_counter()
        response = client.models.generate_content(
            model=CACHE_MODEL,
            contents=q,
            config=types.GenerateContentConfig(cached_content=cache.name),
        )
        elapsed = time.perf_counter() - t0
        usage = response.usage_metadata

        console.print(
            f"  Call #{i}: prompt stamped '{timestamp}' -> wrote NEW cache "
            f"{cache.name.split('/')[-1]} ({write_tokens:,} tokens) -> {elapsed:.2f}s, "
            f"{usage.cached_content_token_count or 0:,} cached tokens "
            f"(all from the cache THIS call just wrote - never a previous one)"
        )

        records.append(
            CallRecord(
                index=i,
                elapsed=elapsed,
                prompt_tokens=usage.prompt_token_count or 0,
                cached_tokens=usage.cached_content_token_count or 0,
                output_tokens=usage.candidates_token_count or 0,
                wrote_new_cache=True,
                cache_write_tokens=write_tokens,
            )
        )

        try:
            client.caches.delete(name=cache.name)
        except Exception as e:
            console.print(f"  [red]Failed to delete {cache.name}: {e}[/red]")

        if i < len(QUESTIONS):
            time.sleep(SECONDS_BETWEEN_CALLS)

    return records


def run_fixed_agent(client) -> list[CallRecord]:
    console.rule("[bold]Fixed Agent - timestamp kept out of the cached prompt[/bold]")
    console.print(
        "The persona is cached ONCE, with nothing dynamic in it. The current time is "
        "passed fresh as part of each call's (uncached) user message instead - still "
        "accurate every call, but now the cache actually gets reused.\n"
    )

    console.print("Creating cache from the static persona only...")
    cache = client.caches.create(
        model=CACHE_MODEL,
        config=types.CreateCachedContentConfig(
            display_name="fixed-agent-persona",
            system_instruction=SYSTEM_PROMPT,
            ttl=f"{CACHE_TTL_SECONDS}s",
        ),
    )
    write_tokens = (cache.usage_metadata.total_token_count if cache.usage_metadata else 0) or 0
    console.print(f"  -> {cache.name}  ({write_tokens:,} tokens written, ONCE for all {len(QUESTIONS)} calls)\n")

    records: list[CallRecord] = []
    try:
        for i, q in enumerate(QUESTIONS, start=1):
            timestamp = _now()
            question_with_time = f"[Current server time: {timestamp}]\n{q}"

            t0 = time.perf_counter()
            response = client.models.generate_content(
                model=CACHE_MODEL,
                contents=question_with_time,
                config=types.GenerateContentConfig(cached_content=cache.name),
            )
            elapsed = time.perf_counter() - t0
            usage = response.usage_metadata

            console.print(
                f"  Call #{i}: prompt stamped '{timestamp}' -> REUSED existing cache -> "
                f"{elapsed:.2f}s, {usage.cached_content_token_count or 0:,}/"
                f"{usage.prompt_token_count or 0:,} cached"
            )

            records.append(
                CallRecord(
                    index=i,
                    elapsed=elapsed,
                    prompt_tokens=usage.prompt_token_count or 0,
                    cached_tokens=usage.cached_content_token_count or 0,
                    output_tokens=usage.candidates_token_count or 0,
                    wrote_new_cache=(i == 1),
                    cache_write_tokens=write_tokens if i == 1 else 0,
                )
            )

            if i < len(QUESTIONS):
                time.sleep(SECONDS_BETWEEN_CALLS)
    finally:
        try:
            client.caches.delete(name=cache.name)
            console.print(f"\n  [dim]Deleted {cache.name}[/dim]")
        except Exception as e:
            console.print(f"\n  [red]Failed to delete {cache.name}: {e}[/red]")

    return records


def summarize(records: list[CallRecord], label: str) -> tuple[Table, float]:
    total_prompt = sum(r.prompt_tokens for r in records)
    total_cached = sum(r.cached_tokens for r in records)
    total_uncached = total_prompt - total_cached
    total_output = sum(r.output_tokens for r in records)
    cache_writes = sum(1 for r in records if r.wrote_new_cache)
    total_write_tokens = sum(r.cache_write_tokens for r in records)
    avg_latency = statistics.mean(r.elapsed for r in records)

    reuse_opportunities = len(records) - 1
    reused = len(records) - cache_writes
    reuse_rate = 100.0 * reused / reuse_opportunities if reuse_opportunities else 0.0

    input_cost = total_uncached / 1_000_000 * PRICE_PER_1M_INPUT
    cached_read_cost = total_cached / 1_000_000 * PRICE_PER_1M_CACHED_INPUT
    write_cost = total_write_tokens / 1_000_000 * PRICE_PER_1M_INPUT
    storage_cost = (
        total_write_tokens / 1_000_000 * PRICE_PER_1M_CACHE_STORAGE_PER_HOUR * (CACHE_TTL_SECONDS / 3600)
    )
    output_cost = total_output / 1_000_000 * PRICE_PER_1M_OUTPUT
    total_cost = input_cost + cached_read_cost + write_cost + storage_cost + output_cost

    table = Table(title=label, box=box.SIMPLE_HEAVY)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Calls made", str(len(records)))
    table.add_row("New caches written", f"{cache_writes} / {len(records)} calls")
    table.add_row("Cache reuse rate", f"{reuse_rate:.0f}%  ({reused}/{reuse_opportunities} opportunities)")
    table.add_row("Total Prompt Tokens", f"{total_prompt:,}")
    table.add_row("  - Cached", f"{total_cached:,}")
    table.add_row("  - Uncached", f"{total_uncached:,}")
    table.add_row("Total Output Tokens", f"{total_output:,}")
    table.add_row("", "")
    table.add_row("Input Cost", f"${input_cost:.6f}")
    table.add_row("Cached-Read Cost", f"${cached_read_cost:.6f}")
    table.add_row("Cache Write Cost (all writes)", f"${write_cost:.6f}")
    table.add_row("Cache Storage Cost", f"${storage_cost:.6f}")
    table.add_row("Output Cost", f"${output_cost:.6f}")
    table.add_row("Total Cost", f"${total_cost:.6f}")
    table.add_row("", "")
    table.add_row("Avg Latency", f"{avg_latency:.2f}s")

    return table, total_cost


def main() -> None:
    console.rule("[bold]Dynamic Prompt Agent - Does Caching Survive a Changing Prompt?[/bold]")
    console.print(f"[dim]Model: {CACHE_MODEL}[/dim]\n")

    client = get_client()

    naive_records = run_naive_agent(client)
    console.print()
    naive_table, naive_cost = summarize(naive_records, "Naive Agent - Timestamp Baked Into Cached Prompt")
    console.print(naive_table)

    console.print()
    fixed_records = run_fixed_agent(client)
    console.print()
    fixed_table, fixed_cost = summarize(fixed_records, "Fixed Agent - Timestamp Kept Out of Cached Prompt")
    console.print(fixed_table)

    console.print()
    console.rule("[bold]Verdict[/bold]")
    naive_writes = sum(1 for r in naive_records if r.wrote_new_cache)
    fixed_writes = sum(1 for r in fixed_records if r.wrote_new_cache)
    delta_pct = 100 * (fixed_cost - naive_cost) / naive_cost if naive_cost else 0.0

    console.print(
        f"Naive agent: {naive_writes}/{len(naive_records)} calls wrote a brand-new cache - "
        f"${naive_cost:.6f} total, and it NEVER once served a cached read from a previous call.\n"
        f"Fixed agent: {fixed_writes}/{len(fixed_records)} call wrote a cache - ${fixed_cost:.6f} "
        f"total, reused on every other call.\n"
    )
    winner = "Fixed agent is cheaper" if fixed_cost < naive_cost else "Naive agent is (surprisingly) cheaper here"
    console.print(f"[bold]{winner} by {abs(delta_pct):.1f}%.[/bold]\n")
    console.print(
        "The lesson isn't 'caching is broken' - it's that Gemini caches match on exact "
        "byte content. The moment anything volatile (a timestamp, a request ID, a random "
        "ordering) is part of what you hand to client.caches.create, every 'cache' you "
        "write is unique, and you pay full write price on every call for a discount you'll "
        "never collect. Keep the volatile part in the per-call message; cache only what's "
        "genuinely constant across calls."
    )


if __name__ == "__main__":
    main()
