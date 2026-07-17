"""
Coding Agent - coding_agent.py

A third contrast in day-3, on top of the Data Analyst Agent (depth) and
Ticker Triaging Agent (breadth): this one has side-effecting tools, not
read-only ones. Give it a task - write something from scratch, or fix a
buggy file - and it writes code, executes it, reads its own stdout/stderr
as the observation, and rewrites if it failed. Same run_tool_loop ReAct
loop as data-analyst-agent, just with write_file/run_python instead of
run_query.

The one rule the system instruction enforces: it may not declare the task
done without a run_python observation showing exit_code 0 whose output
actually satisfies the task - same "don't confuse absence of a check for a
passing check" grounding as failure_handling.py's GROUNDED_INSTRUCTION.
Without that rule, nothing stops it from writing broken code, never
running it, and just claiming success.

Execution is real: whatever the model writes actually runs via subprocess,
confined to workspace/ with a timeout and no stdin. Fine for this local
demo, not a hardened sandbox - don't point it at untrusted input in
production without a real container/VM boundary.

The first task is detailed (task + optionally an existing buggy file);
after it finishes, the process stays open and keeps prompting for further
instructions, applied to the same file(s) in the same conversation -
run_tool_loop already mutates and returns `contents` in place for exactly
this, so a follow-up instruction is appended to the same history instead
of starting a fresh, context-free conversation each time.

run_bash is implemented (so the agent could `pip install` something it
wants to import) but deliberately NOT included in the tools list run_agent
passes to run_tool_loop - unlike run_python it isn't confined to
workspace/, so wiring it in is an intentional choice to make later, not
an oversight.

Run:
    python coding_agent.py
"""

import difflib
import subprocess
import sys
from pathlib import Path

from google.genai import types
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.agent_loop import run_tool_loop

console = Console()

# filename -> last-seen content, so write_file can diff against the
# previous version instead of just overwriting silently. Reset per
# run_agent() call, not per-process, so back-to-back runs don't leak state.
_file_versions: dict[str, str] = {}

WORKSPACE = Path(__file__).resolve().parent / "workspace"
WORKSPACE.mkdir(exist_ok=True)

RUN_TIMEOUT_SECONDS = 10
BASH_TIMEOUT_SECONDS = 30

SYSTEM_INSTRUCTION = (
    "You are a coding agent. You write code to solve the user's task, then "
    "verify it actually works before saying so.\n\n"
    "Loop: write_file the code, then run_python it, then read the "
    "observation. If exit_code is nonzero, or the output doesn't actually "
    "satisfy the task, fix the code and write_file + run_python again. "
    "Keep iterating until a run_python observation shows exit_code 0 AND "
    "output that genuinely satisfies the task.\n\n"
    "You must never call a tool silently - every response that includes a "
    "tool call MUST also include a plain-text sentence starting with "
    "'Thought:' explaining what you're about to do and why (e.g. what "
    "you're fixing, or what you're checking for). Skip the Thought only on "
    "your final response, when you report the result.\n\n"
    "Never declare the task done, and never stop calling tools, until "
    "you've seen a passing run_python observation with your own eyes - a "
    "successful write_file is not evidence the code works. Your final "
    "response must state what you verified and show the actual output."
)


def _resolve_workspace_path(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        return {"error": "filename must be a plain name with no path separators"}
    return WORKSPACE / filename


def _print_diff(filename: str, before: str, after: str) -> None:
    if before == after:
        console.print(Panel("(no change)", title=f"Diff: {filename}", border_style="dim"))
        return
    diff_lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"{filename} (before)",
        tofile=f"{filename} (after)",
    )
    text = Text()
    for line in diff_lines:
        style = "dim"
        if line.startswith("+") and not line.startswith("+++"):
            style = "green"
        elif line.startswith("-") and not line.startswith("---"):
            style = "red"
        elif line.startswith("@@"):
            style = "cyan"
        text.append(line if line.endswith("\n") else line + "\n", style=style)
    console.print(Panel(text, title=f"[bold]Diff: {filename}[/bold]", border_style="magenta"))


def write_file(filename: str, content: str) -> dict:
    """Write source code to a file in the agent's workspace.

    Args:
        filename: Plain filename, no directories or path separators
            (e.g. "solution.py"). Anything with '/', '\\', or '..' is
            rejected.
        content: The full file content to write (overwrites any existing
            file of the same name).
    """
    path = _resolve_workspace_path(filename)
    if isinstance(path, dict):
        return path
    before = _file_versions.get(filename, path.read_text() if path.exists() else "")
    _print_diff(filename, before, content)
    path.write_text(content)
    _file_versions[filename] = content
    return {"status": "written", "filename": filename, "bytes": len(content)}


def read_file(filename: str) -> dict:
    """Read an existing file from the agent's workspace - e.g. a buggy file
    the user asked you to fix, already placed there before the run started.

    Args:
        filename: Plain filename, no directories or path separators.
    """
    path = _resolve_workspace_path(filename)
    if isinstance(path, dict):
        return path
    if not path.exists():
        return {"error": f"{filename} does not exist in the workspace"}
    return {"content": path.read_text()}


def run_python(filename: str) -> dict:
    """Execute a Python file from the agent's workspace and report what
    actually happened - this is the only way to know whether code works.

    Args:
        filename: Plain filename of a file already written via write_file
            (e.g. "solution.py").
    """
    path = _resolve_workspace_path(filename)
    if isinstance(path, dict):
        return path
    if not path.exists():
        return {"error": f"{filename} does not exist in the workspace"}
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {RUN_TIMEOUT_SECONDS}s - likely an infinite loop or blocking input()"}
    return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}


def run_bash(command: str) -> dict:
    """Run a shell command (e.g. `pip install requests`) so the agent can
    install a package it wants to import. Not currently handed to the
    model - see the tools list in run_agent - wire it in when you want the
    agent able to install its own dependencies.

    Unlike run_python/write_file, this is NOT confined to the workspace -
    it's cwd=WORKSPACE but a shell command can still touch anything the
    absolute path or a package manager reaches. Fine for a local demo you
    control the prompt of, not something to expose to untrusted input.

    Args:
        command: A shell command, e.g. "pip install requests".
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=BASH_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {BASH_TIMEOUT_SECONDS}s"}
    return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}


DAY3_ROOT = WORKSPACE.parent.parent


def _find_existing_file(existing_path: str) -> Path | None:
    """Try a path several reasonable ways - editors' 'copy relative path'
    usually includes the day-3/ folder name itself regardless of what the
    terminal's actual cwd happens to be, so a single cwd-relative lookup
    isn't enough."""
    raw = Path(existing_path).expanduser()
    candidates = [raw, DAY3_ROOT / raw]

    parts = raw.parts
    if len(parts) > 1 and parts[0] == DAY3_ROOT.name:
        stripped = Path(*parts[1:])
        candidates += [stripped, DAY3_ROOT / stripped]

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def get_task_from_console() -> tuple[str, str | None]:
    existing_path = console.input(
        "[bold cyan]Existing buggy file to fix (blank to write from scratch):[/bold cyan] "
    ).strip()
    existing_filename = None
    if existing_path:
        source = _find_existing_file(existing_path)
        if source is None:
            console.print(f"[red]{existing_path} not found - continuing as a from-scratch task.[/red]")
        else:
            existing_filename = source.name
            (WORKSPACE / existing_filename).write_text(source.read_text())
            console.print(f"[green]Copied into workspace as {existing_filename}[/green]")

    task = console.input("[bold cyan]Task (what it should do / what's wrong):[/bold cyan] ").strip()
    return task, existing_filename


def build_prompt(task: str, existing_filename: str | None) -> str:
    if existing_filename:
        return (
            f"There's a buggy file already in your workspace: {existing_filename}. "
            f"Read it, then fix it. Task/what's wrong: {task}"
        )
    return f"Write code from scratch for this task: {task}"


def build_followup_prompt(instruction: str) -> str:
    return (
        "New instruction for a follow-up change - apply it to the file(s) "
        f"already in your workspace from earlier in this conversation, then "
        f"re-verify with run_python the same way as before: {instruction}"
    )


def run_agent(
    task: str,
    existing_filename: str | None = None,
    max_steps: int = 10,
    contents: list[types.Content] | None = None,
) -> tuple[str, list[types.Content]]:
    """Runs one task/instruction. Pass the `contents` returned from a prior
    call back in to continue the same conversation (a follow-up instruction
    applied to the same file, with full memory of what was already done)
    instead of starting a fresh, context-free one."""
    console.rule("Coding Agent")

    if contents is None:
        _file_versions.clear()
        if existing_filename:
            existing_path = WORKSPACE / existing_filename
            if existing_path.exists():
                _file_versions[existing_filename] = existing_path.read_text()
        prompt = build_prompt(task, existing_filename)
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    else:
        prompt = build_followup_prompt(task)
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

    console.print(f"[bold cyan]Task:[/bold cyan] {prompt}\n")

    result = run_tool_loop(
        contents,
        [write_file, read_file, run_python],  # run_bash exists but isn't wired in yet - see module docstring
        terminal_tools=set(),
        system_instruction=SYSTEM_INSTRUCTION,
        max_steps=max_steps,
        console=console,
    )
    if result.exhausted:
        console.print(f"\n[bold red]Did not finish within {max_steps} steps.[/bold red]")
        return f"exhausted after {max_steps} steps without a verified passing run", contents

    attempts = sum(1 for obs in result.observations if obs["name"] == "run_python")
    console.print(f"\n[bold green]Result:[/bold green] {result.final_text}")
    console.print(f"[dim]({attempts} run_python attempt(s) across this instruction)[/dim]")
    return result.final_text, contents


if __name__ == "__main__":
    task, existing_filename = get_task_from_console()
    if not task:
        console.print("[red]No task given, exiting.[/red]")
    else:
        _, contents = run_agent(task, existing_filename)
        while True:
            followup = console.input(
                "\n[bold cyan]Next instruction, applied to the same file(s) (blank to quit):[/bold cyan] "
            ).strip()
            if not followup:
                break
            _, contents = run_agent(followup, contents=contents)
