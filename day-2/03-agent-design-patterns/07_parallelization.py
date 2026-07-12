"""
Pattern: Parallelization
======================================

Independent subtasks run at the same time; results get combined.
Task -> {Search agent, Analysis agent, Summary agent} run concurrently ->
Merge / Vote combines the outputs into one final result.

Run:
    python 07_parallelization.py
"""

import asyncio
import sys
import time
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask, ask_async

console = Console()


async def run(topic: str) -> None:
    console.rule("Parallelization")
    console.print(f"[bold cyan]Task:[/bold cyan] {topic}\n")

    subtasks = {
        "search agent": f"List 3 known facts about: {topic}. Be terse.",
        "analysis agent": f"Give one risk and one opportunity related to: {topic}. Be terse.",
        "summary agent": f"Summarize '{topic}' in a single sentence.",
    }

    start = time.perf_counter()
    results = await asyncio.gather(*(ask_async(p) for p in subtasks.values()))
    elapsed = time.perf_counter() - start

    for name, result in zip(subtasks, results):
        console.print(f"[yellow]{name}:[/yellow] {result}\n")
    console.print(f"[dim]{len(subtasks)} calls ran concurrently in {elapsed:.1f}s[/dim]\n")

    merged = ask(
        "Combine these independent outputs into one short final answer:\n\n"
        + "\n\n".join(f"{name}: {result}" for name, result in zip(subtasks, results))
    )
    console.print(f"[bold green]Merged result:[/bold green] {merged}")


if __name__ == "__main__":
    asyncio.run(run("switching a team from REST to GraphQL"))
