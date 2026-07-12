"""
Pattern: Reflection - one agent, two hats
======================================================

1. Draft: produce an answer.
2. Self-critique: the SAME model checks its own work.
3. Not good enough -> revise (capped at 2-3 rounds). Good enough -> done.

Run:
    python 02_reflection.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask

console = Console()

MAX_REVISIONS = 3

# A few ready-to-run tasks. TASK_1 is easy - the model usually nails it on
# the first draft, so the critique passes immediately and the revise branch
# never runs. TASK_2 and TASK_3 pack several required, checkable facts into
# a tight word budget, which is much more likely to trip up the first draft
# and actually exercise the FAIL -> revise path.
TASK_1 = "Explain what is dynamic programming, in exactly two sentences, for a junior developer."
TASK_2 = (
    "Explain what a hash table is. Your answer must explicitly address all four of: "
    "(1) average-case lookup time complexity, (2) worst-case lookup time complexity, "
    "(3) what specifically causes the worst case, (4) one common technique to mitigate it. "
    "Do this in exactly 40 words."
)
TASK_3 = (
    "Explain how TLS establishes a secure connection. Your answer must explicitly name "
    "all four of: (1) the initial handshake step, (2) how the server proves its identity, "
    "(3) how a shared symmetric key gets established, (4) what protects data after the "
    "handshake. Exactly 45 words."
)
TASK_4 = (
    "Explain what a Bloom filter is, in exactly two sentences. Then, on a new "
    "line, state exactly how many times the letter 'f' appears in the two "
    "sentences you just wrote, counting only that text."
)
TASK_5 = (
    "Write a single, grammatically correct sentence explaining what a computer is.\n"
    "CRITICAL RULE: The words in your sentence must be in strict alphabetical order "
    "(e.g., 'A computer calculates data efficiently...')."
)

TASK_6 = (
    "Write a detailed summary explaining how a computer works.\n"
    "CRITICAL CONSTRAINT: You are strictly forbidden from using the letter 'e' "
    "anywhere in your response. Every single word must be completely devoid of the letter 'e'."
)

TASK = TASK_6


def run(task: str) -> str:
    console.rule("Reflection loop")
    console.print(f"[bold cyan]Task:[/bold cyan] {task}\n")

    draft = ask(f"Write a short answer to this: {task}")
    console.print(f"[yellow]Draft:[/yellow] {draft}\n")

    for round_num in range(1, MAX_REVISIONS + 1):
        critique = ask(
            "You are reviewing your own previous answer as a strict critic.\n"
            f"Task: {task}\nAnswer: {draft}\n\n"
            "If it is correct, concise, and complete, reply with exactly PASS. "
            "Otherwise reply with exactly FAIL followed by a one-sentence reason."
        )
        console.print(f"[magenta]Self-critique (round {round_num}):[/magenta] {critique}")

        if critique.strip().upper().startswith("PASS"):
            console.print(f"\n[bold green]Final answer:[/bold green] {draft}")
            return draft

        draft = ask(
            f"Task: {task}\nPrevious answer: {draft}\nCritique: {critique}\n\n"
            "Write a revised answer that addresses the critique."
        )
        console.print(f"[yellow]Revised draft:[/yellow] {draft}\n")

    console.print(f"\n[bold green]Final answer (revision cap reached):[/bold green] {draft}")
    return draft


if __name__ == "__main__":
    run(TASK)
