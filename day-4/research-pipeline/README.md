# Multi-Source Analyst (Research Pipeline)

Ask it any question. Three workers research it concurrently from
different angles, a Reconciler resolves tension between their findings
and verifies specific claims, a Report Writer formats the result, and a
human approves before publish.

## Setup

From `day-4/` (one level up):
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste in your GEMINI_API_KEY
```

## How to run

```
cd research-pipeline
python demo_broken.py   # no fact_check wired in
python demo_fixed.py    # fact_check + confidence floor + human gate
python research.py      # interactive - type any question
```

## Examples

Questions to try with `research.py`:

1. "What is the tallest building in the world?"
2. "Who is the current President of France?"
3. "Why is the sky blue?"
4. "What is the largest ocean on Earth?"
5. "What is the most popular programming language right now?"

## What each component does

- **Background Worker** (`agents/background_worker.py`) — searches for
  foundational facts: history, definitions, established background.
- **Recent Developments Worker** (`agents/recent_developments_worker.py`)
  — searches for what's changed or current right now.
- **Deep Dive Worker** (`agents/deep_dive_worker.py`) — searches for
  precise, checkable details: exact dates, numbers, named sources.
- **Reconciler** (`agents/reconciler.py`) — merges the three findings,
  resolves contradictions between them, and (when `fact_check_enabled`)
  independently verifies specific claims before they're allowed into the
  final summary.
- **Report Writer** (`agents/report_writer.py`) — a plain function that
  formats the reconciled findings into a report.
- **Orchestrator** (`orchestrator.py`) — runs the workers in parallel,
  then the Reconciler, then the Report Writer, then the human gate.

**Tools**: `common/web_search.py` (one level up) is a live web search
tool shared by all three workers. `tools/fact_check.py` verifies a single
claim with a fresh search. `tools/publish_report.py` publishes the final
report.
