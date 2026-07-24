"""
Self-Evolving Agent - agent.py

The contrast with day-3/coding-agent: that agent has a fixed toolset
(write_file/read_file/run_python) it uses to solve tasks. This one starts
with almost nothing - three small meta-tools - and writes its OWN tools at
runtime when a task needs a capability it doesn't have yet. Ask it to do
something that needs shell access, and it doesn't fail or ask you to add a
tool; it calls `create_and_register_new_tool` with a hand-written
`run_bash_command` implementation, gets it loaded and active in the same
process, and calls it on its very next turn.

Three tools it's seeded with:
  - create_and_register_new_tool: writes a Python function to tools/<name>.py,
    imports it with importlib, and adds it to self.active_tools. This is the
    one that makes the agent "self-evolving" - every tool it creates is saved
    to disk and reloaded automatically the next time this script runs, so the
    toolset only ever grows across sessions.
  - execute_one_time_script: runs a throwaway script and returns its output
    without persisting anything, for one-off problems that don't deserve a
    reusable tool (e.g. "what's 47 * sqrt(193)?").
  - fetch_webpage_content: the one ordinary, pre-built tool, included so
    there's a visible contrast between "tool I shipped with" and "tool the
    model wrote for itself five seconds ago".

The tool list handed to Gemini is rebuilt from self.active_tools on EVERY
step of the loop (see run(), _build_tool()) rather than once before it -
that's the one structural difference from common/agent_loop.py used in
day-4, and it's the whole point: a tool registered on step N must be
callable on step N+1 within the same run() call, not just on the next
top-level task.

SAFETY: create_and_register_new_tool and execute_one_time_script both
execute model-written Python with no sandboxing beyond a subprocess
timeout - same posture as day-3/coding-agent's run_bash. Fine for a local
demo where you control what you ask it to do; do not point this at
untrusted input or run it anywhere with access to something you'd mind
losing.

Run:
    python main.py
"""

import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path
from typing import Callable

from google.genai import types
from rich.console import Console, Group
from rich.panel import Panel

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

TOOLS_DIR = Path(__file__).resolve().parent / "tools"
TOOLS_DIR.mkdir(exist_ok=True)
(TOOLS_DIR / "__init__.py").touch(exist_ok=True)

SCRATCH_DIR = Path(__file__).resolve().parent / "scratch"

ONE_TIME_SCRIPT_TIMEOUT_SECONDS = 15
MAX_ACTION_ECHO_CHARS = 400   # how much of a call's args we echo in the Action panel
MAX_OBSERVATION_CHARS = 1200  # how much of a tool result we echo in the Observation panel

SYSTEM_INSTRUCTION_LONG_TERM = """You are a self-evolving AI agent operating in an autonomous, long-term mode.

Your primary objective is to solve the user's request.
You have access to a small set of pre-defined tools.
If you realize you need a tool that you do not currently have (such as executing shell
commands, doing file system operations, compiling code, etc.), you have a special
meta-tool called `create_and_register_new_tool`.

Guidelines for creating new tools:
1. Before creating a tool, design it conceptually. Ensure it is focused, simple, and safe.
2. The Python code you provide must define a single, standard, self-contained Python
   function with the exact name you specified.
3. The function MUST include:
   - Proper Python type annotations/hints for all its arguments and return types.
   - A complete docstring describing what the tool does, its arguments, and its return
     value. The SDK uses these type hints and docstring to automatically generate the
     JSON schema.
   - Any necessary imports inside the function itself or at the top of the code.
4. An excellent example of a tool you should write when you need terminal or shell
   execution capability is a bash command executor tool named `run_bash_command` which
   takes a `command` string and returns the command's stdout and stderr.
5. Once a tool is created and registered successfully, you will receive a success
   response. In your very next turn, the new tool will be available to you as an active
   tool, and you can call it immediately!
6. If a tool you created raises an error or fails, don't worry! Analyze the error,
   rewrite the tool using `create_and_register_new_tool` to patch/fix it, and try again.

Deciding between `create_and_register_new_tool` and `execute_one_time_script`: do not
wait for the user to say "make this reusable" - decide yourself, based on the
capability, not the phrasing of the request. Ask: could this same function, completely
unchanged, plausibly be called again later with different arguments to solve a
different task? If yes, write it as a permanent tool via `create_and_register_new_tool`
even if the current request only needs it once - general capabilities like shell
execution, file I/O, HTTP calls, unit conversions, date math, and parsing almost always
qualify. Reserve `execute_one_time_script` for logic that is inherently single-use: a
calculation whose result only makes sense for these exact numbers, or glue code that
only makes sense in the context of this one request.

Be autonomous, professional, and clear in your reasoning. Every response that includes
a tool call must also include a plain-text sentence starting with "Thought:" explaining
what you're about to do and why.
"""


def _load_tool_module(name: str, file_path: Path) -> Callable:
    """Import a single-function module from disk and return that function.

    Shared by create_and_register_new_tool (a brand new file) and
    _restore_persisted_tools (files left over from a previous run) so both
    paths validate the same way: the module must define a callable with
    exactly the given name.
    """
    spec = importlib.util.spec_from_file_location(f"tools.{name}", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for module {name} at {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[f"tools.{name}"] = module
    spec.loader.exec_module(module)

    if not hasattr(module, name):
        raise AttributeError(f"Generated code for '{name}' does not define a function named '{name}'")

    func = getattr(module, name)
    if not callable(func):
        raise TypeError(f"'{name}' extracted from module is not callable")
    return func


def _format_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = repr(v)
        if len(s) > MAX_ACTION_ECHO_CHARS:
            s = s[:MAX_ACTION_ECHO_CHARS] + f"... ({len(s)} chars total)"
        parts.append(f"{k}={s}")
    return ", ".join(parts)


def _truncate(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more chars truncated)"


class SelfEvolvingAgent:
    def __init__(self, model: str | None = None):
        self.client = get_client()
        self.model = model or MODEL
        self.contents: list[types.Content] = []
        self.tools_created_this_session: list[str] = []

        self.active_tools: dict[str, Callable] = {
            "create_and_register_new_tool": self.create_and_register_new_tool,
            "execute_one_time_script": self.execute_one_time_script,
            "fetch_webpage_content": self.fetch_webpage_content,
        }
        self._restore_persisted_tools()

        console.print(
            f"[dim]Active tools: {', '.join(sorted(self.active_tools))}[/dim]"
        )

    # ------------------------------------------------------------------ #
    # Meta-tools - these are what make the agent "self-evolving"
    # ------------------------------------------------------------------ #

    def create_and_register_new_tool(self, name: str, code: str, description: str) -> str:
        """
        Creates and registers a new tool for the agent by writing its Python
        implementation, dynamically loading it into the environment, and making it
        available in the agent's toolset.

        Args:
            name: The name of the function to create. Must be a valid Python identifier.
            code: The complete Python code defining the function. The function MUST:
                - Use the exact name specified in the 'name' parameter.
                - Include all necessary imports inside the function or at the module level.
                - Include proper Python type hints for all parameters and return types.
                - Include a comprehensive docstring describing its behavior, arguments,
                  and return value.
            description: A short, clear explanation of what this tool does.

        Returns:
            str: A success message once the tool is loaded and active, or a failure
                message with the error so you can patch the code and try again.
        """
        console.print(
            f"\n[bold magenta]\U0001f6e0  Meta-tool Invoked: Creating and Registering "
            f"'{name}'...[/bold magenta]"
        )
        if description:
            console.print(f"  [dim]{description}[/dim]")

        if not name.isidentifier():
            return f"Error: '{name}' is not a valid Python identifier."

        file_path = TOOLS_DIR / f"{name}.py"

        try:
            with open(file_path, "w") as f:
                f.write(code)
            console.print(f"  [dim]Saved Python source file to {file_path}[/dim]")

            func = _load_tool_module(name, file_path)

            self.active_tools[name] = func
            if name not in self.tools_created_this_session:
                self.tools_created_this_session.append(name)
            console.print(
                f"  [bold green]✓ Tool '{name}' has been dynamically loaded and "
                f"registered![/bold green]"
            )

            sig = inspect.signature(func)
            console.print(f"  [dim]Signature: {name}{sig}[/dim]")

            return (
                f"Success: Tool '{name}' has been successfully written, loaded, and "
                f"registered. You can now call '{name}' in your next turn with correct "
                f"arguments!"
            )

        except Exception as e:
            console.print(f"[bold red]✗ Failed to register tool '{name}': {str(e)}[/bold red]")
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            return f"Failure: Could not create and register tool '{name}'. Error: {str(e)}"

    def execute_one_time_script(self, code: str, description: str = "") -> str:
        """
        Executes a self-contained Python script to solve a specific, immediate problem
        and captures its output. Use this when you do not need a permanent, reusable tool.

        Args:
            code: The complete Python script to run. It must print its results to
                stdout/stderr.
            description: A short description of what this one-time script does.

        Returns:
            str: The exit code, stdout, and stderr of the executed script.
        """
        console.print(f"\n[bold magenta]⚡ Meta-tool Invoked: Executing One-Time Script...[/bold magenta]")
        if description:
            console.print(f"  [dim]{description}[/dim]")

        SCRATCH_DIR.mkdir(exist_ok=True)
        temp_path = SCRATCH_DIR / "one_time_script.py"
        try:
            temp_path.write_text(code)
            console.print(f"  [dim]Wrote script to {temp_path}[/dim]")
            result = subprocess.run(
                [sys.executable, str(temp_path)],
                capture_output=True,
                text=True,
                timeout=ONE_TIME_SCRIPT_TIMEOUT_SECONDS,
                stdin=subprocess.DEVNULL,
            )
            output = f"exit_code: {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            style = "green" if result.returncode == 0 else "red"
            console.print(Panel(output.strip() or "(no output)", title="Script Output", border_style=style))
            return output
        except subprocess.TimeoutExpired:
            msg = f"Error: script timed out after {ONE_TIME_SCRIPT_TIMEOUT_SECONDS}s"
            console.print(f"[bold red]{msg}[/bold red]")
            return msg
        except Exception as e:
            msg = f"Error executing script: {e}"
            console.print(f"[bold red]{msg}[/bold red]")
            return msg
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # One ordinary, pre-built tool - contrast against the two above
    # ------------------------------------------------------------------ #

    def fetch_webpage_content(self, url: str) -> str:
        """
        Fetches the raw text content of a webpage, truncated to the first 1000
        characters. Use this for quick lookups when a task references a URL.

        Args:
            url: The full URL to fetch, including scheme (e.g. "https://example.com").

        Returns:
            str: The first 1000 characters of the page's text, or an error message.
        """
        try:
            headers = {"User-Agent": "SelfEvolvingAgent/1.0"}
            response = requests.get(url, headers=headers, timeout=5)
            return response.text[:1000]
        except Exception as e:
            return f"Error fetching {url}: {str(e)}"

    # ------------------------------------------------------------------ #
    # Persistence across runs
    # ------------------------------------------------------------------ #

    def _restore_persisted_tools(self) -> None:
        """Reload every tool a previous run created, so the agent's toolset
        only ever grows across sessions instead of resetting each time."""
        existing = sorted(p for p in TOOLS_DIR.glob("*.py") if p.stem != "__init__")
        if not existing:
            return
        console.print(f"[dim]Restoring {len(existing)} previously self-created tool(s) from disk...[/dim]")
        for path in existing:
            name = path.stem
            try:
                func = _load_tool_module(name, path)
                self.active_tools[name] = func
                console.print(f"  [green]✓[/green] {name}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {name}: failed to reload ({e})")

    # ------------------------------------------------------------------ #
    # The loop
    # ------------------------------------------------------------------ #

    def _build_tool(self) -> types.Tool:
        """Rebuilt from self.active_tools on every step (not once before the
        loop) so a tool registered mid-run is callable on the very next
        step, within the same run() call."""
        return types.Tool(
            function_declarations=[
                types.FunctionDeclaration.from_callable(client=self.client, callable=fn)
                for fn in self.active_tools.values()
            ]
        )

    def run(self, task: str, max_steps: int = 12) -> str:
        console.rule("[bold]New Task[/bold]")
        console.print(f"[bold cyan]Task:[/bold cyan] {task}\n")
        self.contents.append(types.Content(role="user", parts=[types.Part(text=task)]))

        for step_num in range(1, max_steps + 1):
            tool = self._build_tool()
            response = self.client.models.generate_content(
                model=self.model,
                contents=self.contents,
                config=types.GenerateContentConfig(
                    tools=[tool],
                    system_instruction=SYSTEM_INSTRUCTION_LONG_TERM,
                ),
            )
            candidate = response.candidates[0].content
            self.contents.append(candidate)
            calls = [p.function_call for p in candidate.parts if p.function_call]

            text = "".join(p.text for p in candidate.parts if p.text).strip()
            if text.lower().startswith("thought:"):
                text = text[len("thought:"):].strip()

            if not calls:
                console.print(
                    Panel(
                        text or "(no output)",
                        title=f"[bold green]Final Answer - step {step_num}[/bold green]",
                        border_style="green",
                    )
                )
                return response.text or ""

            step_panels = []
            if text:
                step_panels.append(Panel(text, title="Thought", border_style="yellow"))

            response_parts = []
            for call in calls:
                args = dict(call.args)
                step_panels.append(
                    Panel(f"{call.name}({_format_args(args)})", title="Action", border_style="blue")
                )

                if call.name not in self.active_tools:
                    result = (
                        f"Error: tool '{call.name}' is not registered. "
                        f"Active tools: {sorted(self.active_tools)}"
                    )
                else:
                    try:
                        result = self.active_tools[call.name](**args)
                    except Exception as e:
                        result = f"Error while executing '{call.name}': {e}"

                step_panels.append(
                    Panel(_truncate(str(result)), title="Observation", border_style="magenta")
                )
                response_parts.append(
                    types.Part.from_function_response(name=call.name, response={"result": result})
                )

            console.print(
                Panel(Group(*step_panels), title=f"[bold]Step {step_num}[/bold]", border_style="white")
            )
            self.contents.append(types.Content(role="user", parts=response_parts))

        console.print(f"[bold red]Stopped after {max_steps} steps without a final answer.[/bold red]")
        return f"(stopped after {max_steps} steps without a final answer)"
