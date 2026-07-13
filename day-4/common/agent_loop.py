"""The one real ReAct loop, shared by every real agent in both Day 4 projects.

Each call gets its own fresh `contents` list and its own `tools` list - that's
what makes per-agent context isolation real rather than asserted: there is no
shared state between two calls to this function unless a caller explicitly
threads one in.
"""

from dataclasses import dataclass, field
from typing import Callable

from google.genai import types
from rich.console import Console, Group
from rich.panel import Panel

from common.llm import MODEL, get_client


@dataclass
class LoopResult:
    contents: list[types.Content]
    final_text: str | None = None
    terminal_call: dict | None = None
    observations: list[dict] = field(default_factory=list)
    exhausted: bool = False


def run_tool_loop(
    contents: list[types.Content],
    tools: list[Callable],
    terminal_tools: set[str],
    system_instruction: str,
    max_steps: int,
    console: Console | None = None,
    observations: list[dict] | None = None,
    model: str | None = None,
) -> LoopResult:
    """Model decides -> tool executes -> result becomes context -> repeat.

    `tools` is a plain list of callables - the tool name Gemini uses is each
    function's own __name__, taken directly from the function rather than a
    separately-typed string key, so the two can never drift out of sync.

    Stops when: the model responds with no tool call (final_text set), the
    model calls a tool named in `terminal_tools` (terminal_call set, NOT
    executed - the caller decides what to do with it), or max_steps runs out
    (exhausted=True) - a hard ceiling that always wins regardless of what any
    prompt says.
    """
    client = get_client()
    tool_funcs = {fn.__name__: fn for fn in tools}
    tool = types.Tool(
        function_declarations=[
            types.FunctionDeclaration.from_callable(client=client, callable=fn)
            for fn in tools
        ]
    )
    observations = observations if observations is not None else []
    step_num = 0

    for _ in range(max_steps):
        step_num += 1
        response = client.models.generate_content(
            model=model or MODEL,
            contents=contents,
            config=types.GenerateContentConfig(tools=[tool], system_instruction=system_instruction),
        )
        candidate = response.candidates[0].content
        contents.append(candidate)
        calls = [p.function_call for p in candidate.parts if p.function_call]

        text = "".join(p.text for p in candidate.parts if p.text).strip()
        if text.lower().startswith("thought:"):
            text = text[len("thought:"):].strip()

        if not calls:
            return LoopResult(contents=contents, final_text=response.text, observations=observations)

        step_panels = []
        if text:
            step_panels.append(Panel(text, title="Thought", border_style="yellow"))

        response_parts = []
        for call in calls:
            args = dict(call.args)
            if call.name in terminal_tools:
                if console and step_panels:
                    console.print(
                        Panel(Group(*step_panels), title=f"[bold]Loop {step_num}[/bold]", border_style="white")
                    )
                return LoopResult(
                    contents=contents,
                    terminal_call={"name": call.name, "args": args},
                    observations=observations,
                )

            result = tool_funcs[call.name](**args)
            step_panels.append(Panel(f"{call.name}({args})", title="Action", border_style="blue"))
            step_panels.append(Panel(str(result), title="Observation", border_style="magenta"))
            observations.append({"name": call.name, "args": args, "result": result})
            response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )

        if console:
            console.print(
                Panel(Group(*step_panels), title=f"[bold]Loop {step_num}[/bold]", border_style="white")
            )
        contents.append(types.Content(role="user", parts=response_parts))

    return LoopResult(contents=contents, observations=observations, exhausted=True)
