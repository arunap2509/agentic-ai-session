"""
Pattern: Evaluator-Optimizer
===========================================

Two SEPARATE agents, not one (contrast with Reflection, which is one
agent wearing two hats):
  1. Generator produces an attempt.
  2. Evaluator checks it against explicit criteria - it only judges, it
     never edits the attempt itself.
  3. Fails -> feedback goes back to the Generator. Meets criteria -> done.

Run:
    python 09_evaluator_optimizer.py
"""

import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import ask

console = Console()

CRITERIA = "Must be under 20 words, must not use the word 'leverage', must mention the word 'API'."
MAX_ROUNDS = 3


def generate(task: str, feedback: str | None) -> str:
    prompt = f"Task: {task}"
    if feedback:
        prompt += f"\n\nPrevious attempt was rejected. Evaluator feedback: {feedback}"
    return ask(prompt, system="You are the Generator. Produce one attempt at the task. Output only the attempt, nothing else.")


def evaluate(task: str, attempt: str) -> tuple[bool, str]:
    verdict = ask(
        f"Task: {task}\nCriteria: {CRITERIA}\nAttempt: {attempt}\n\n"
        'Check the attempt against the criteria. Reply with ONLY '
        '"PASS" or "FAIL: <short reason>". Do not rewrite the attempt yourself.',
        system="You are the Evaluator. You judge, you never edit.",
    )
    passed = verdict.strip().upper().startswith("PASS")
    return passed, verdict


def run(task: str) -> None:
    console.rule("Evaluator-Optimizer")
    console.print(f"[bold cyan]Task:[/bold cyan] {task}")
    console.print(f"[dim]Criteria: {CRITERIA}[/dim]\n")

    feedback = None
    for round_num in range(1, MAX_ROUNDS + 1):
        attempt = generate(task, feedback)
        console.print(f"[yellow]Generator (round {round_num}):[/yellow] {attempt}")

        passed, verdict = evaluate(task, attempt)
        console.print(f"[magenta]Evaluator:[/magenta] {verdict}\n")

        if passed:
            console.print(f"[bold green]Accepted:[/bold green] {attempt}")
            return
        feedback = verdict

    console.print("[red]Hit max rounds without a passing attempt.[/red]")


if __name__ == "__main__":
    run("Write a one-line product tagline for a developer API gateway.")
