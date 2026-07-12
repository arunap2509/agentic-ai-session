"""
Data Analyst Agent - base_agent.py

The floor, not the ceiling: one tool, one question, one answer. This is
table stakes - if this were the whole agent, you wouldn't need an agent,
you'd need a search box. Each later stage in this folder adds one specific
capability by first showing the gap it fixes.

Run:
    python base_agent.py
"""

import sqlite3
import sys
from pathlib import Path

from google.genai import types
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.agent_loop import run_tool_loop

console = Console()

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "orders.db"

SYSTEM_INSTRUCTION = (
    "You are a data analyst agent with read access to a sales database. "
    "You must never call a tool silently - every response that includes a "
    "tool call MUST also include a plain-text sentence starting with "
    "'Thought:' explaining why you're about to call it. Skip the Thought "
    "only on your final response, when you're giving the answer."
)

FORBIDDEN_KEYWORDS = ("insert", "update", "delete", "drop", "alter", "create", "replace")


def run_query(sql: str) -> dict:
    """RETRIEVE: Run a read-only SQL query against the sales database.

    The database has one table, orders, with columns:
    order_id (integer), date (text, ISO format e.g. "2026-04-15"),
    region (text: "North America", "Europe", "APAC", or "LATAM"),
    category (text: "Electronics", "Furniture", "Apparel", or "Software"),
    product (text), quantity (integer), revenue (real, in USD).

    Only SELECT statements are allowed - this tool will refuse anything else.

    Args:
        sql: A single SELECT statement, e.g.
            "SELECT SUM(revenue) FROM orders WHERE date BETWEEN '2026-01-01' AND '2026-03-31'"
    """
    normalized = sql.strip().lower()
    if not normalized.startswith("select"):
        return {"error": "only SELECT statements are allowed"}
    if any(word in normalized for word in FORBIDDEN_KEYWORDS):
        return {"error": "query contains a disallowed keyword"}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute(sql).fetchall()]
    except sqlite3.Error as exc:
        return {"error": str(exc)}
    finally:
        conn.close()
    return {"rows": rows}


def run_agent(question: str, max_steps: int = 6) -> str:
    console.rule("Data Analyst Agent")
    console.print(f"[bold cyan]Question:[/bold cyan] {question}\n")

    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    result = run_tool_loop(
        contents,
        [run_query],
        terminal_tools=set(),
        system_instruction=SYSTEM_INSTRUCTION,
        max_steps=max_steps,
        console=console,
    )
    if result.exhausted:
        raise RuntimeError(f"did not finish within {max_steps} steps")

    console.print(f"\n[bold green]Answer:[/bold green] {result.final_text}")
    return result.final_text


if __name__ == "__main__":
    run_agent("What was total revenue in Q1 2026?")
