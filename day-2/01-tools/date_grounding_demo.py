"""
Tools & Agent SDK - grounding demo: the model doesn't know today's date
==========================================================================

An LLM's only sense of "now" is whatever its training data implied - it has
no clock. Ask something whose answer depends on today's date and, left
alone, it will confidently state an answer anyway instead of admitting it
doesn't know. Give it a get_current_date tool and the guessing stops.

Run:
    python date_grounding_demo.py
"""

import sys
from datetime import date
from pathlib import Path

from google.genai import types
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

QUESTION = "How many days from today until December 25th? Answer in one line."


def get_current_date() -> dict:
    """RETRIEVE: Get today's real, current date and day of week. Call this
    any time a question depends on "today", "now", "this year", or requires
    computing a duration from the present moment. Your training data has a
    fixed cutoff and does NOT tell you what today's date is - never guess
    it, always call this instead.
    """
    today = date.today()
    return {"date": today.isoformat(), "weekday": today.strftime("%A")}


def without_tool() -> None:
    console.rule("Without a date tool - the model has to guess")
    console.print(f"[bold cyan]Question:[/bold cyan] {QUESTION}")
    response = get_client().models.generate_content(model=MODEL, contents=QUESTION)
    console.print(f"[red]Model's answer (ungrounded):[/red] {response.text}")


def with_tool() -> None:
    console.rule("With a get_current_date tool - grounded, not guessed")
    console.print(f"[bold cyan]Question:[/bold cyan] {QUESTION}")

    client = get_client()
    tool = types.Tool(
        function_declarations=[
            types.FunctionDeclaration.from_callable(client=client, callable=get_current_date)
        ]
    )
    contents = [types.Content(role="user", parts=[types.Part(text=QUESTION)])]

    for _ in range(3):
        response = client.models.generate_content(
            model=MODEL, contents=contents, config=types.GenerateContentConfig(tools=[tool])
        )
        candidate = response.candidates[0].content
        contents.append(candidate)

        calls = [p.function_call for p in candidate.parts if p.function_call]
        if not calls:
            console.print(f"[green]Model's answer (grounded):[/green] {response.text}")
            return

        response_parts = []
        for call in calls:
            result = get_current_date()
            console.print(f"[yellow]Action:[/yellow] {call.name}() -> [magenta]{result}[/magenta]")
            response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=response_parts))


if __name__ == "__main__":
    without_tool()
    console.print()
    with_tool()
