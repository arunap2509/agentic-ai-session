"""
Data Analyst Agent - failure_handling.py

Runs the same question - "what was Q3 2026 revenue" - twice. Q3 2026 has
no rows at all (it hasn't happened yet). The naive agent below doesn't
fabricate a wild number, which is what makes it a good example: it
correctly investigates (checks the date range), then concludes "revenue
was $0.00" - conflating no data recorded with zero revenue actually
happened. That's a subtler, more realistic mistake than a wild guess, and
arguably more dangerous, because it reads as a confident, specific fact.

The grounded agent gets an explicit no-data signal from the tool itself
(not left for the model to infer from a SQL NULL) plus an instruction to
never state a dollar figure when there's no data.

Run:
    python failure_handling.py
"""

import sys
from pathlib import Path

from google.genai import types
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from base_agent import DB_PATH, SYSTEM_INSTRUCTION, run_query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.agent_loop import run_tool_loop

console = Console()

QUESTION = "What was total revenue in Q3 2026?"

GROUNDED_INSTRUCTION = SYSTEM_INSTRUCTION + (
    " If a query's result has row_count 0, there is NO data for that period - "
    "it does not mean revenue was zero. State plainly that no data is available "
    "and say why (e.g. the period hasn't happened yet). Never state a specific "
    "dollar figure, including $0, for a period with no data."
)


def run_query_grounded(sql: str) -> dict:
    """RETRIEVE: Run a read-only SQL query against the sales database.

    The database has one table, orders, with columns:
    order_id (integer), date (text, ISO format e.g. "2026-04-15"),
    region (text: "North America", "Europe", "APAC", or "LATAM"),
    category (text: "Electronics", "Furniture", "Apparel", or "Software"),
    product (text), quantity (integer), revenue (real, in USD).

    Only SELECT statements are allowed. The result always includes a
    row_count: if it's 0, no matching orders exist for that query - that
    is different from revenue being zero, it means the data doesn't exist.

    Args:
        sql: A single SELECT statement, e.g.
            "SELECT SUM(revenue) FROM orders WHERE date BETWEEN '2026-01-01' AND '2026-03-31'"
    """
    result = run_query(sql)
    if "error" in result:
        return result
    rows = result["rows"]
    is_empty = len(rows) == 0 or all(v is None for row in rows for v in row.values())
    if is_empty:
        return {"row_count": 0, "message": "No matching orders exist for this query."}
    return {"row_count": len(rows), "rows": rows}


def run_naive(question: str, max_steps: int = 4) -> None:
    console.rule("Naive agent - ungrounded")
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    result = run_tool_loop(
        contents, [run_query], set(), SYSTEM_INSTRUCTION, max_steps, console
    )
    console.print(f"[red]Answer:[/red] {result.final_text}")


def run_grounded(question: str, max_steps: int = 4) -> None:
    console.rule("Grounded agent - explicit no-data signal + instruction")
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    result = run_tool_loop(
        contents, [run_query_grounded], set(), GROUNDED_INSTRUCTION, max_steps, console
    )
    console.print(f"[green]Answer:[/green] {result.final_text}")


if __name__ == "__main__":
    console.print(f"[bold cyan]Question:[/bold cyan] {QUESTION}\n")
    run_naive(QUESTION)
    console.print()
    run_grounded(QUESTION)
