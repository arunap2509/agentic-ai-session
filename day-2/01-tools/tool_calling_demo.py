"""
Tools & Agent SDK
=================

Demo goals:
  - A tool is just a function with a name, description, input schema, and handler.
  - The schema is a contract the model relies on to call correctly.
  - Two kinds of tools: RETRIEVE (low stakes, look something up) and
    EXECUTE (higher stakes, change something in the world).
  - The tool-use loop: model decides -> system executes -> result returns
    as new context -> repeat until done.

We deliberately do NOT use the SDK's automatic function calling here, so we
can print every step of that loop for the audience to see.

Run:
    python tool_calling_demo.py
"""

import json
import sys
from pathlib import Path

from google.genai import types
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()


# ---------------------------------------------------------------------------
# Tools. Each one is: name (function name) + description (docstring) +
# input schema (type hints) + handler (function body).
# ---------------------------------------------------------------------------

FAKE_WEATHER = {
    "paris": {"condition": "light rain", "temp_c": 17},
    "london": {"condition": "overcast", "temp_c": 15},
    "bengaluru": {"condition": "sunny", "temp_c": 29},
}


def get_weather(city: str) -> dict:
    """RETRIEVE: Look up the current weather for a city.

    Args:
        city: The city to check, e.g. "Paris".
    """
    data = FAKE_WEATHER.get(city.strip().lower())
    if data is None:
        return {"error": f"no weather data for '{city}'"}
    return {"city": city, **data}


def send_email(to: str, subject: str, body: str) -> dict:
    """EXECUTE: Immediately sends a real email to exactly one recipient. The
    email goes out the moment this tool is called - there is no draft, no
    preview, and no undo. It does NOT support cc, bcc, multiple recipients,
    or attachments, and it does NOT ask the user for confirmation before
    sending - that check must happen before you call this tool, not after.
    Only call this when the user has explicitly asked for an email to be sent.

    Args:
        to: A single recipient email address (not a list, not comma-separated).
        subject: Email subject line.
        body: Plain-text email body.
    """
    # Mocked on purpose for the demo - a real handler would call an email API.
    console.print(
        Panel(
            f"[bold]To:[/bold] {to}\n[bold]Subject:[/bold] {subject}\n\n{body}",
            title="[green]MOCK EMAIL SENT[/green]",
            border_style="green",
        )
    )
    return {"status": "sent", "to": to}


TOOL_REGISTRY = {"get_weather": get_weather, "send_email": send_email}


def build_tool_schemas(client) -> types.Tool:
    declarations = [
        types.FunctionDeclaration.from_callable(client=client, callable=fn)
        for fn in TOOL_REGISTRY.values()
    ]
    return types.Tool(function_declarations=declarations)


def show_schema_contract(tool: types.Tool) -> None:
    console.rule("The schema is a contract")
    for decl in tool.function_declarations:
        console.print_json(
            json.dumps(
                {
                    "name": decl.name,
                    "description": decl.description,
                    "parameters": decl.parameters.model_dump(exclude_none=True)
                    if decl.parameters
                    else {},
                }
            )
        )


# ---------------------------------------------------------------------------
# The tool-use loop: Model decides -> System executes -> Result returns as
# new context -> repeat until done.
# ---------------------------------------------------------------------------


def run_tool_loop(prompt: str, max_steps: int = 6) -> str:
    client = get_client()
    tool = build_tool_schemas(client)
    show_schema_contract(tool)

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=prompt)])
    ]

    console.rule("Tool-use loop")
    console.print(f"[bold cyan]User:[/bold cyan] {prompt}\n")

    for step in range(1, max_steps + 1):
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(tools=[tool]),
        )
        candidate_content = response.candidates[0].content
        contents.append(candidate_content)

        function_calls = [
            part.function_call for part in candidate_content.parts if part.function_call
        ]

        if not function_calls:
            final_text = response.text or ""
            console.print(f"\n[bold green]Final answer:[/bold green] {final_text}")
            return final_text

        response_parts = []
        for call in function_calls:
            console.print(
                f"[yellow]Step {step} - Action:[/yellow] {call.name}({dict(call.args)})"
            )
            handler = TOOL_REGISTRY[call.name]
            result = handler(**call.args)
            console.print(f"[magenta]Step {step} - Observation:[/magenta] {result}\n")
            response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )

        contents.append(types.Content(role="user", parts=response_parts))

    raise RuntimeError(f"did not finish within {max_steps} steps")


if __name__ == "__main__":
    run_tool_loop(
        "What's the weather in bengaluru? If it's raining, email a heads-up "
        "to team@example.com with the forecast."
    )
