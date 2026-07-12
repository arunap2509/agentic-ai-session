"""
Pattern: ReAct - the atomic loop
=============================================

Thought -> Action -> Observation -> repeat until done.
"Every pattern that follows is ReAct plus one more idea."

This reuses the same tool-use loop shape as 01-tools/tool_calling_demo.py,
but here the print statements literally use the words Thought / Action /
Observation so the loop shape is obvious.

Run:
    python 01_react.py
"""

import sys
from pathlib import Path

from google.genai import types
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()


def calculator(expression: str) -> dict:
    """Evaluate a basic arithmetic expression, e.g. "23 * 47 + 19".

    Args:
        expression: A Python-syntax arithmetic expression using + - * / ().
    """
    try:
        # eval is fine here: demo-only, single hardcoded expression grammar.
        return {"expression": expression, "result": eval(expression, {"__builtins__": {}})}
    except Exception as exc:
        return {"error": str(exc)}


def run(question: str, max_steps: int = 5) -> None:
    client = get_client()
    tool = types.Tool(
        function_declarations=[
            types.FunctionDeclaration.from_callable(client=client, callable=calculator)
        ]
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]

    console.rule("ReAct loop")
    console.print(f"[bold cyan]Question:[/bold cyan] {question}\n")

    for step in range(1, max_steps + 1):
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[tool],
                system_instruction=(
                    "You must never call a tool silently. Every response that "
                    "includes a tool call MUST also include a plain-text sentence "
                    "starting with 'Thought:' explaining why you're about to call "
                    "it - no exceptions, even for simple steps. Skip the Thought "
                    "only on your final response, when you are giving the answer "
                    "and not calling any more tools."
                ),
            ),
        )
        candidate = response.candidates[0].content
        contents.append(candidate)

        calls = [p.function_call for p in candidate.parts if p.function_call]
        if not calls:
            console.print(f"\n[bold green]Done:[/bold green] {response.text}")
            return

        text = "".join(p.text for p in candidate.parts if p.text).strip()
        if text.lower().startswith("thought:"):
            text = text[len("thought:"):].strip()
        if text:
            console.print(f"[yellow]Thought:[/yellow] {text}")

        response_parts = []
        for call in calls:
            console.print(f"[blue]Action:[/blue] {call.name}({dict(call.args)})")
            result = calculator(**call.args)
            console.print(f"[magenta]Observation:[/magenta] {result}\n")
            response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=response_parts))

    console.print("[red]Stopped: hit max_steps without a final answer.[/red]")


if __name__ == "__main__":
    run("What is (23 * 47) + 19, and then what's that number divided by 3?")
