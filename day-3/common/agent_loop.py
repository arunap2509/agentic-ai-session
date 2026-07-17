"""The one real ReAct loop, shared by every stage in data-analyst-agent.

Every stage was reimplementing this with small variations - that's
duplication, not separation of concerns, and it's exactly how full_agent.py
could silently drift away from earlier stages' fixes without anyone
noticing. Every script in this folder should call run_tool_loop, not write
its own version of it.
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


@dataclass
class Session:
    """Conversation state a caller threads across multiple calls for a real
    follow-up: both the turn history (contents) and every tool observation
    gathered so far (observations). Both need to accumulate across turns,
    not just contents - a fact verified two turns ago is still grounded,
    it shouldn't need to be re-queried every turn just to stay provable."""

    contents: list[types.Content] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)


def run_tool_loop(
    contents: list[types.Content],
    tools: list[Callable],
    terminal_tools: set[str],
    system_instruction: str,
    max_steps: int,
    console: Console | None = None,
    observations: list[dict] | None = None,
) -> LoopResult:
    """Model decides -> tool executes -> result becomes context -> repeat.

    `tools` is a plain list of callables - the tool name Gemini uses is each
    function's own __name__, taken directly from the function rather than a
    separately-typed string key, so the two can never drift out of sync.

    Mutates and returns `contents` in place, so a caller can thread the same
    list into a follow-up call to continue the conversation.

    Stops when: the model responds with no tool call (final_text set), the
    model calls a tool named in `terminal_tools` (terminal_call set, NOT
    executed - the caller decides what to do with it), or max_steps runs out
    (exhausted=True) - a hard ceiling that always wins regardless of what
    any prompt says.

    `observations` can be seeded with prior-turn observations (e.g. from
    Session.observations) so a caller checking groundedness sees the whole
    conversation's verified facts, not just this call's new ones.
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
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(tools=[tool], system_instruction=system_instruction),
        )
        raw_candidate = response.candidates[0]
        candidate = raw_candidate.content
        if candidate is None or candidate.parts is None:
            raise RuntimeError(
                f"Model returned no content on step {step_num} "
                f"(finish_reason={raw_candidate.finish_reason!r}) - this means a safety "
                "filter blocked the response or it hit the output token limit, not a bug "
                "in the loop itself. Try rephrasing the task/instruction, or shortening "
                "what's being sent (a large buggy file, or a long-running follow-up "
                "conversation, can both push toward the token limit)."
            )
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
