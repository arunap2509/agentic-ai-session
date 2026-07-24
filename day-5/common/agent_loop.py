"""The one real ReAct loop, shared by day-5's eval harness.

Same file as day-4/common/agent_loop.py, copied rather than imported across
day-N boundaries since each day is a self-contained venv/project. Not used
by self-evolving-agent (its toolset changes mid-run, so it needs its own
loop that rebuilds tool declarations every step - see that project's
README) - this version assumes a fixed toolset, which is exactly what an
eval harness needs to score consistently.

LoopResult.observations is the trajectory an eval checker inspects: tool
name, args, and result, in the order they were actually called.
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
        finish_reason = response.candidates[0].finish_reason

        # candidate.parts is Optional and can be None (not just empty) when
        # the API returns no actual content - e.g. a safety-filter block or
        # hitting max output tokens before producing anything. Treat that
        # as a content-free turn instead of crashing trying to iterate None.
        parts = candidate.parts if candidate is not None and candidate.parts else []
        if candidate is not None:
            contents.append(candidate)

        calls = [p.function_call for p in parts if p.function_call]
        text = "".join(p.text for p in parts if p.text).strip()
        if text.lower().startswith("thought:"):
            text = text[len("thought:"):].strip()

        if not calls:
            final_text = text or f"(model returned no content - finish_reason={finish_reason})"
            return LoopResult(contents=contents, final_text=final_text, observations=observations)

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
