"""
Self-Evolving Agent - main.py

REPL entry point. Keeps one SelfEvolvingAgent alive across turns (same
`contents` conversation history, same `active_tools` dict) so a follow-up
task can use a tool the agent wrote for an earlier task in this same
session - and any tool it writes is also saved to tools/ and reloaded
automatically the next time you run this script.

Run:
    python main.py

Things to try, in order (each builds on the last):
    1. "List the files in this directory using a real shell command."
       -> it has no shell tool yet, so it writes run_bash_command via
          create_and_register_new_tool, then calls it.
    2. "Now use that same tool to print the first 5 lines of agent.py."
       -> reuses the tool it just created, no re-creation needed.
    3. "What's 47 * sqrt(193), rounded to 2 decimal places?"
       -> doesn't deserve a permanent tool; uses execute_one_time_script.
    4. Quit and run `python main.py` again - it restores run_bash_command
       from tools/run_bash_command.py before you type anything.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rich.console import Console

from agent import SelfEvolvingAgent

console = Console()


def main() -> None:
    console.rule("[bold]Self-Evolving Agent[/bold]")
    console.print(
        "Give it a task. If it doesn't have the right tool, it will write one, "
        "register it, and use it - in this same turn or the next.\n"
        "[dim]Tools it creates are saved under tools/ and reloaded automatically "
        "the next time you run this script.[/dim]"
    )

    agent = SelfEvolvingAgent()

    while True:
        task = console.input("\n[bold cyan]Task (blank to quit):[/bold cyan] ").strip()
        if not task:
            break
        agent.run(task)

    console.rule("[bold]Session Summary[/bold]")
    console.print(f"[dim]Steps of conversation history kept: {len(agent.contents)}[/dim]")
    if agent.tools_created_this_session:
        console.print(
            f"[bold green]Created {len(agent.tools_created_this_session)} new tool(s) "
            f"this session:[/bold green]"
        )
        for name in agent.tools_created_this_session:
            console.print(f"  - {name}  (tools/{name}.py)")
    else:
        console.print("[dim]No new tools were created this session.[/dim]")
    console.print(f"[dim]All active tools now: {', '.join(sorted(agent.active_tools))}[/dim]")


if __name__ == "__main__":
    main()
