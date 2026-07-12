"""
Pattern: Orchestrator-Workers
============================================

1. Orchestrator breaks the task into pieces - the split itself is a
   judgment call, decided at runtime (unlike Planning, where the step
   list is generic and fixed upfront).
2. Workers run independently, then report back.
3. Orchestrator synthesizes the final result.

Used when subtasks can't be predicted in advance - here the number and
nature of workers is decided by the orchestrator itself, not hardcoded.

Run:
    python 08_orchestrator_workers.py
"""

import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask, ask_async

console = Console()


def orchestrate(task: str) -> list[str]:
    raw = ask(
        f"Task: {task}\n\n"
        "Decide how many independent worker subtasks this genuinely needs "
        "(2-4, your judgment call) and what each worker should do. Keep each "
        "instruction to one short sentence. Reply with ONLY a JSON array of "
        'worker instructions, e.g. ["research X", "draft Y"].'
    )
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(cleaned)


async def run(task: str) -> None:
    console.rule("Orchestrator-Workers")
    console.print(f"[bold cyan]Task:[/bold cyan] {task}\n")

    worker_instructions = orchestrate(task)
    console.print(f"[yellow]Orchestrator delegated {len(worker_instructions)} workers:[/yellow]")
    for instr in worker_instructions:
        console.print(f"  - {instr}")
    console.print()

    worker_system = "You are a worker agent. Report back in 2-3 short sentences, no code, no headers."
    reports = await asyncio.gather(
        *(ask_async(instr, system=worker_system) for instr in worker_instructions)
    )
    for instr, report in zip(worker_instructions, reports):
        console.print(f"[blue]Worker report - {instr}:[/blue]\n  {report}\n")

    synthesis = ask(
        f"Original task: {task}\n\nWorker reports:\n"
        + "\n".join(f"- {i}: {r}" for i, r in zip(worker_instructions, reports))
        + "\n\nSynthesize these into one coherent final result."
    )
    console.print(f"[bold green]Orchestrator's synthesis:[/bold green]\n{synthesis}")


if __name__ == "__main__":
    asyncio.run(run("Prepare a launch checklist for a new internal Slack bot."))
