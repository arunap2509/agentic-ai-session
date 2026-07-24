"""
Prompt Caching Demo - prompt_caching_demo.py

Answers one question with hard numbers: does Gemini's explicit context
caching actually pay for itself for a chatty tool with a big, mostly-static
system prompt? Three phases, same 5 questions, same system prompt:

  Phase 1 - No Caching
      Every call sends the full system prompt as plain input tokens.
      Baseline cost and latency.

  Phase 2 - With Caching
      The system prompt is written to a cache ONCE (client.caches.create),
      then every call references it via `cached_content=` instead of
      re-sending it. Cached tokens are billed at a reduced rate; only the
      per-call question is billed as normal input.

For a live look at cache invalidation - what happens when the "static"
prompt you're trying to cache actually changes on every call, e.g. because
it embeds the current time - see the companion script,
dynamic_prompt_agent.py, in this same directory.

Every run prints a detailed per-call line (hit/miss, latency, cached vs.
total tokens) plus the full model input/output for the last call of each
phase, so you can see exactly what happened, not just the aggregate table.

Setup: cp ../.env.example ../.env and add GEMINI_API_KEY, or reuse the .env
from an earlier day - same key works. If GEMINI_CACHE_MODEL (default
gemini-flash-latest) 404s with "no longer available to new users" for your
key, see common/llm.py for how to pick a model your account can cache with.

Run:
    python prompt_caching_demo.py
"""

import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from google.genai import types
from rich.console import Console
from rich import box
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import CACHE_MODEL, get_client

console = Console()

# Pricing below mirrors Gemini 2.5 Flash's published per-1M-token rates
# (https://ai.google.dev/gemini-api/docs/pricing) at the time this was
# written. Cached-content reads are billed at 25% of the standard input
# rate across every Gemini model that supports explicit caching; storage
# is billed hourly on top of that, prorated to the second. Prices change -
# check the pricing page before trusting these numbers for a real budget.
PRICE_PER_1M_INPUT = 0.30
PRICE_PER_1M_OUTPUT = 2.50
PRICE_PER_1M_CACHED_INPUT = 0.075
PRICE_PER_1M_CACHE_STORAGE_PER_HOUR = 1.00

CACHE_TTL_SECONDS = 900  # 15 min - long enough to run this whole demo

SYSTEM_PROMPT = """You are a senior PostgreSQL database reliability engineer embedded in an
internal on-call support tool. Engineers page you mid-incident, so your job is to get
them to a safe, correct action fast - not to write a general database tutorial.

## How to respond
1. Lead with the single most likely cause given the symptom described, not a list of
   every possible cause. If genuinely ambiguous, name the top 2 and how to tell them
   apart with one query each.
2. Give the exact query or command to run, not a description of one. Use real
   pg_catalog/pg_stat_* views, not pseudocode.
3. Every query that modifies state (kill, cancel, drop, alter) must be preceded by the
   read-only query that confirms the target is correct, and a one-line note on the blast
   radius if the engineer gets the target wrong.
4. Keep the whole answer under ~200 words unless the question explicitly asks for a
   deeper explanation. On-call engineers are mid-incident; they will ask a follow-up if
   they need more.
5. Never suggest a destructive action (DROP, TRUNCATE, pg_terminate_backend on anything
   other than the specifically identified pid) without an explicit confirmation step.

## Domain knowledge you should draw on
- Locking: pg_locks joined to pg_stat_activity is the standard way to find blockers vs.
  blocked. A lock wait over a few seconds on a hot table is usually a long transaction
  holding a stronger lock than it needs, not a hardware issue.
- Long-running / idle-in-transaction: query pg_stat_activity for state and
  now() - query_start (or now() - xact_start for the whole transaction). "idle in
  transaction" holding an old snapshot is a common cause of bloat and blocked DDL even
  when it isn't consuming CPU.
- Autovacuum: check pg_stat_progress_vacuum for in-flight runs and pg_stat_user_tables
  (n_dead_tup, last_autovacuum) for tables falling behind. Autovacuum gets cancelled by
  any conflicting lock request (e.g. ALTER TABLE) - check pg_stat_activity around the
  cancellation time for the query that pre-empted it.
- Replication lag: pg_stat_replication on the primary (write_lag/flush_lag/replay_lag)
  and pg_stat_wal_receiver on the replica. Rule out three causes in order: replica I/O
  saturation, a long-running query on the replica blocking WAL apply (check
  max_standby_streaming_delay), and network throughput between primary and replica.
- Schema changes on large tables: ALTER TABLE ... ADD COLUMN with a non-volatile
  default is a metadata-only change since PG11 and does not rewrite the table or hold a
  long lock. A volatile default, a type change, or adding a constraint that needs
  validation does rewrite/scan and needs a low-traffic window or a concurrent-safe
  pattern (add nullable, backfill in batches, add NOT NULL with NOT VALID + VALIDATE
  CONSTRAINT separately).
- Connection exhaustion: check pg_stat_activity grouped by state and application_name
  before touching max_connections - a pool that isn't releasing connections is a more
  common root cause than genuinely needing more connections, and raising the limit can
  make an OOM situation worse.
- Index bloat and unused indexes: pg_stat_user_indexes.idx_scan == 0 over a representative
  window is the signal for "candidate to drop", not table size alone.
- Slow queries: ask for EXPLAIN (ANALYZE, BUFFERS) output before speculating. A plan
  where estimated and actual row counts diverge by 10x+ points at stale statistics
  (run ANALYZE) or a bad default statistics target on a skewed column, not a missing
  index. Sequential scans are not inherently bad - only flag one if it's scanning far
  more rows than the query actually needs and a selective index exists or could.
- Connection pooling: with pgbouncer in transaction pooling mode, session-level state
  (SET, prepared statements, advisory locks held across statements) silently breaks,
  because the client's next statement can land on a different backend connection. If an
  app reports "my session variable disappeared" or "my prepared statement is missing",
  check the pooling mode before touching application code.
- Backups and point-in-time recovery: confirm WAL archiving is actually succeeding
  (pg_stat_archiver.last_archived_time recent, archiver.failed_count not climbing)
  before trusting that PITR is possible - a base backup with a broken WAL archive gives
  a false sense of safety. Recovery target should always be tested on a scratch
  instance before being trusted during a real incident.
- Disk space emergencies: check for orphaned replication slots (pg_replication_slots
  with a very old restart_lsn) before assuming you need to grow the volume - a stuck
  slot prevents WAL from being recycled and is the single most common cause of runaway
  pg_wal growth on an otherwise healthy primary.

## Formatting
Use a short prose lead-in, then a fenced ```sql block for any query, then (if a
mutating step is involved) a one-line "this affects: ..." note. No headers, no bullet
walls, no restating the question back to the engineer.
"""

QUESTIONS = [
    "How do I find and kill long-running transactions in PostgreSQL?",
    "A table's autovacuum keeps getting cancelled - how do I diagnose why?",
    "What's the safest way to add a NOT NULL column to a 50M-row table without "
    "locking writes?",
    "Replication lag on our read replica just spiked to 10 minutes - what do I "
    "check first?",
    "How can I find which queries are holding the most locks right now?",
]


@dataclass
class RunRecord:
    index: int
    question: str
    answer: str
    elapsed: float
    prompt_tokens: int
    cached_tokens: int
    output_tokens: int
    cache_hit: bool


@dataclass
class PhaseResult:
    phase_name: str
    runs: list[RunRecord]
    cache_write_tokens: int = 0
    cache_write_elapsed: float = 0.0

    @property
    def total_prompt_tokens(self) -> int:
        return sum(r.prompt_tokens for r in self.runs)

    @property
    def total_cached_tokens(self) -> int:
        return sum(r.cached_tokens for r in self.runs)

    @property
    def total_uncached_tokens(self) -> int:
        return self.total_prompt_tokens - self.total_cached_tokens

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.runs)

    @property
    def cache_hit_rate(self) -> float:
        if self.total_prompt_tokens == 0:
            return 0.0
        return 100.0 * self.total_cached_tokens / self.total_prompt_tokens

    @property
    def latencies(self) -> list[float]:
        return [r.elapsed for r in self.runs]

    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latencies)

    @property
    def p50_latency(self) -> float:
        return statistics.median(self.latencies)

    @property
    def p95_latency(self) -> float:
        if len(self.latencies) < 2:
            return self.latencies[0]
        sorted_l = sorted(self.latencies)
        idx = min(len(sorted_l) - 1, round(0.95 * (len(sorted_l) - 1)))
        return sorted_l[idx]

    @property
    def input_cost(self) -> float:
        return self.total_uncached_tokens / 1_000_000 * PRICE_PER_1M_INPUT

    @property
    def cached_read_cost(self) -> float:
        return self.total_cached_tokens / 1_000_000 * PRICE_PER_1M_CACHED_INPUT

    @property
    def cache_write_cost(self) -> float:
        return self.cache_write_tokens / 1_000_000 * PRICE_PER_1M_INPUT

    @property
    def cache_storage_cost(self) -> float:
        hours = CACHE_TTL_SECONDS / 3600
        return self.cache_write_tokens / 1_000_000 * PRICE_PER_1M_CACHE_STORAGE_PER_HOUR * hours

    @property
    def output_cost(self) -> float:
        return self.total_output_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT

    @property
    def total_cost(self) -> float:
        return (
            self.input_cost
            + self.cached_read_cost
            + self.cache_write_cost
            + self.cache_storage_cost
            + self.output_cost
        )


def _print_run_line(r: RunRecord) -> None:
    hit_label = "[green]● HIT [/green]" if r.cache_hit else "[red]○ MISS[/red]"
    console.print(
        f"  Run #{r.index:02d}: {hit_label} {r.elapsed:5.2f}s  "
        f"{r.cached_tokens:,}/{r.prompt_tokens:,} cached  "
        f"(+{r.output_tokens:,} output tokens)"
    )


def _print_last_run_transcript(r: RunRecord) -> None:
    console.print(Panel(f"USER: {r.question}", title=f"Model Input - Run #{r.index:02d}", border_style="cyan"))
    console.print(Panel(r.answer.strip(), title="Model Response", border_style="green"))


def _metrics_table(result: PhaseResult, phase_label: str, show_cache_write: bool) -> Table:
    table = Table(title=f"Phase - {phase_label}", box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Prompt Tokens", f"{result.total_prompt_tokens:,}")
    table.add_row("  - Cached", f"{result.total_cached_tokens:,}")
    table.add_row("  - Uncached", f"{result.total_uncached_tokens:,}")
    table.add_row("Total Output Tokens", f"{result.total_output_tokens:,}")
    table.add_row("Cache Hit Rate", f"{result.cache_hit_rate:.1f}%")
    table.add_row("", "")
    table.add_row("Input Cost", f"${result.input_cost:.6f}")
    if show_cache_write:
        table.add_row("Cached-Read Cost", f"${result.cached_read_cost:.6f}")
        table.add_row("Cache Write Cost (one-time)", f"${result.cache_write_cost:.6f}")
        table.add_row("Cache Storage Cost (TTL)", f"${result.cache_storage_cost:.6f}")
    table.add_row("Output Cost", f"${result.output_cost:.6f}")
    table.add_row("Total Cost", f"${result.total_cost:.6f}")
    table.add_row("", "")
    table.add_row("Avg Latency", f"{result.avg_latency:.2f}s")
    table.add_row("p50 Latency", f"{result.p50_latency:.2f}s")
    table.add_row("p95 Latency", f"{result.p95_latency:.2f}s")
    return table


def run_phase1_no_caching(client) -> PhaseResult:
    console.rule("[bold]Phase 1 - No Caching[/bold]")
    console.print("Every call re-sends the full system prompt as plain input tokens.\n")

    runs: list[RunRecord] = []
    for i, q in enumerate(QUESTIONS, start=1):
        start = time.perf_counter()
        response = client.models.generate_content(
            model=CACHE_MODEL,
            contents=q,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        elapsed = time.perf_counter() - start
        usage = response.usage_metadata
        run = RunRecord(
            index=i,
            question=q,
            answer=response.text or "",
            elapsed=elapsed,
            prompt_tokens=usage.prompt_token_count or 0,
            cached_tokens=usage.cached_content_token_count or 0,
            output_tokens=usage.candidates_token_count or 0,
            cache_hit=bool(usage.cached_content_token_count),
        )
        runs.append(run)
        _print_run_line(run)

    console.print()
    _print_last_run_transcript(runs[-1])
    result = PhaseResult(phase_name="No Caching", runs=runs)
    console.print()
    console.print(_metrics_table(result, "1 - No Caching", show_cache_write=False))
    return result


def run_phase2_with_caching(client) -> tuple[PhaseResult, object]:
    console.rule("[bold]Phase 2 - With Caching[/bold]")
    console.print("System prompt is written to a cache once, then served cheaply on every call.\n")

    console.print("Creating prompt cache...")
    t0 = time.perf_counter()
    cache = client.caches.create(
        model=CACHE_MODEL,
        config=types.CreateCachedContentConfig(
            display_name="pg-dba-system-prompt",
            system_instruction=SYSTEM_PROMPT,
            ttl=f"{CACHE_TTL_SECONDS}s",
        ),
    )
    cache_write_elapsed = time.perf_counter() - t0
    cache_write_tokens = (
        cache.usage_metadata.total_token_count if cache.usage_metadata else 0
    ) or 0
    console.print(
        f"Cache ready in {cache_write_elapsed:.2f}s -> {cache.name}  "
        f"({cache_write_tokens:,} tokens written)\n"
    )

    runs: list[RunRecord] = []
    for i, q in enumerate(QUESTIONS, start=1):
        start = time.perf_counter()
        response = client.models.generate_content(
            model=CACHE_MODEL,
            contents=q,
            config=types.GenerateContentConfig(cached_content=cache.name),
        )
        elapsed = time.perf_counter() - start
        usage = response.usage_metadata
        cached = usage.cached_content_token_count or 0
        run = RunRecord(
            index=i,
            question=q,
            answer=response.text or "",
            elapsed=elapsed,
            prompt_tokens=usage.prompt_token_count or 0,
            cached_tokens=cached,
            output_tokens=usage.candidates_token_count or 0,
            cache_hit=cached > 0,
        )
        runs.append(run)
        _print_run_line(run)
        if i == 1:
            console.print(f"  [dim]raw usageMetadata: {usage.model_dump(exclude_none=True)}[/dim]")

    console.print()
    _print_last_run_transcript(runs[-1])
    result = PhaseResult(
        phase_name="With Caching",
        runs=runs,
        cache_write_tokens=cache_write_tokens,
        cache_write_elapsed=cache_write_elapsed,
    )
    console.print()
    console.print(_metrics_table(result, "2 - With Caching", show_cache_write=True))
    return result, cache


def print_overall_summary(phase1: PhaseResult, phase2: PhaseResult) -> None:
    console.rule("[bold]Overall Summary[/bold]")
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Metric", style="bold")
    table.add_column("No Caching", justify="right")
    table.add_column("With Caching", justify="right")
    table.add_column("Delta", justify="right")

    def pct_delta(no_cache: float, with_cache: float) -> str:
        if no_cache == 0:
            return "-"
        return f"{100 * (with_cache - no_cache) / no_cache:+.1f}%"

    table.add_row(
        "Total Cost (5 calls)",
        f"${phase1.total_cost:.6f}",
        f"${phase2.total_cost:.6f}",
        pct_delta(phase1.total_cost, phase2.total_cost),
    )
    table.add_row(
        "Uncached Input Tokens",
        f"{phase1.total_uncached_tokens:,}",
        f"{phase2.total_uncached_tokens:,}",
        pct_delta(phase1.total_uncached_tokens, phase2.total_uncached_tokens),
    )
    table.add_row(
        "Avg Latency (per call)",
        f"{phase1.avg_latency:.2f}s",
        f"{phase2.avg_latency:.2f}s",
        pct_delta(phase1.avg_latency, phase2.avg_latency),
    )
    table.add_row(
        "Cache Hit Rate",
        f"{phase1.cache_hit_rate:.1f}%",
        f"{phase2.cache_hit_rate:.1f}%",
        f"{phase2.cache_hit_rate - phase1.cache_hit_rate:+.1f}pp",
    )
    net_savings = phase1.total_cost - phase2.total_cost
    table.add_row("Net Savings", "-", "-", f"${net_savings:+.6f}")
    console.print(table)

    console.print(
        f"\n[bold]Cost reduction:[/bold] "
        f"{100 * net_savings / phase1.total_cost:+.1f}% "
        f"(saving ${net_savings:+.6f} across {len(phase1.runs)} calls, including the "
        f"one-time cache write)"
    )
    console.print(
        f"[bold]Latency change:[/bold] "
        f"{100 * (phase1.avg_latency - phase2.avg_latency) / phase1.avg_latency:+.1f}% "
        f"({phase1.avg_latency:.2f}s -> {phase2.avg_latency:.2f}s avg per call)\n"
    )
    console.print(
        "[dim]Note: this 5-call run may not amortize the one-time cache-write cost - "
        "caching wins on COST once uncached-input savings across all calls exceed the "
        "write cost, and it wins on cost regardless of call count once the system "
        "prompt is large enough relative to each question. Latency differences here are "
        "within normal API jitter, not a caching effect - caching saves tokens/cost, "
        "not necessarily wall-clock time.[/dim]"
    )
    console.print(
        "[dim]For what happens when the prompt isn't actually static across calls, "
        "see dynamic_prompt_agent.py in this same directory.[/dim]"
    )


def main() -> None:
    console.rule("[bold]Prompt Caching Demo[/bold]")
    console.print(f"[dim]Model: {CACHE_MODEL}  |  System prompt: PostgreSQL on-call assistant[/dim]\n")

    client = get_client()
    cache = None
    try:
        phase1 = run_phase1_no_caching(client)
        console.print()
        phase2, cache = run_phase2_with_caching(client)
        console.print()
        print_overall_summary(phase1, phase2)
    finally:
        if cache is not None:
            try:
                client.caches.delete(name=cache.name)
                console.print(f"\n[dim]Deleted Phase 2 cache {cache.name}[/dim]")
            except Exception as e:
                console.print(f"\n[red]Failed to delete Phase 2 cache {cache.name}: {e}[/red]")


if __name__ == "__main__":
    main()
