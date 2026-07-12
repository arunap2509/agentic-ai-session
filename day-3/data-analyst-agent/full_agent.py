"""
Data Analyst Agent - full_agent.py

Three things happen here:

1. An unbounded-vs-bounded contrast on an open-ended question ("how did
   Q2 go, anything to worry about?"). Tested empirically: this model
   doesn't need forcing to be thorough - left with no guidance, it drills
   all the way to product-level detail across every region and category,
   most of it irrelevant, and can burn its entire step budget without
   ever reaching a conclusion. The failure here isn't laziness, it's
   waste. A bounding instruction ("stop once you've found the specific
   driver, don't keep checking everything") turns that into a focused
   investigation that correctly isolates the real story.

   max_steps stays as a hard, deterministic ceiling either way - the
   instruction shapes whether that budget gets spent well, it doesn't
   replace having a budget at all.

2. data_analyst_agent() - the full pipeline, actually built on the earlier
   stages instead of re-deriving them:
     - uses run_query_grounded from failure_handling.py (not a plain
       run_query) - so the investigation itself is protected from the
       "no data means $0" failure the whole time, not just checked for it
       after the fact
     - its instruction chains from GROUNDED_INSTRUCTION, adding only the
       bounded-investigation and report-writing clauses on top
     - supports real multi-turn follow-ups (history in, history out) -
       the same conversation-memory mechanism memory.py demonstrated,
       now actually present in the finished agent instead of dropped
     - the EXECUTE tool write_report is gated by two independent checks:
       a grounding check (does every claim trace back to an actual query
       result) and a human-in-the-loop pause if the report makes a
       recommendation (an interpretive claim, not just a fact)

This is also the function Day 4 imports and calls as a worker (passing
session=None for a one-shot call).

Run:
    python full_agent.py

Then just ask it things - it's a real agent, not a scripted transcript.
See README.md for a few starter questions and natural follow-ups to try.
"""

import sys
from pathlib import Path

from google.genai import types
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from base_agent import DB_PATH, SYSTEM_INSTRUCTION, run_query
from failure_handling import GROUNDED_INSTRUCTION, run_query_grounded

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.agent_loop import Session, run_tool_loop
from common.llm import MODEL, get_client

console = Console()

BOUNDED_INSTRUCTION = GROUNDED_INSTRUCTION + (
    " When investigating an open-ended question, drill down (overall -> region "
    "-> category) only as far as needed to find the single most significant "
    "driver. The moment you find a specific region+category combination that "
    "clearly explains the pattern, stop investigating and report it - do not "
    "keep checking every other segment once you have a clear answer. Once you "
    "have a specific, data-backed finding, call write_report with it - only "
    "fill in a recommendation if you have a specific, evidence-backed "
    "suggestion, otherwise leave it blank."
)


def write_report(title: str, findings: str, recommendation: str) -> dict:
    """EXECUTE: Finalizes and sends a report to stakeholders. This is not a
    draft - once called, the report goes out, there is no undo. Only call
    this once you have a specific, data-backed finding ready to share.

    Args:
        title: Short report title.
        findings: The data-backed findings, in plain language.
        recommendation: What to do about it, if there's a specific,
            evidence-backed suggestion. Leave blank if there isn't one.
    """
    body = findings
    if recommendation.strip():
        body += f"\n\n[bold]Recommendation:[/bold] {recommendation}"
    console.print(Panel(body, title=f"[green]REPORT SENT: {title}[/green]", border_style="green"))
    return {"status": "sent"}


def run_unbounded(question: str, max_steps: int = 6) -> None:
    console.rule("Unbounded - no guidance on when to stop investigating")
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    result = run_tool_loop(contents, [run_query], set(), SYSTEM_INSTRUCTION, max_steps, console)
    if result.final_text is not None:
        console.print(f"[red]Answer:[/red] {result.final_text}")
    else:
        console.print(
            f"[red]Ran out of its {max_steps}-step budget after checking "
            f"{len(result.observations)} segments, several of them irrelevant, "
            "without ever reaching a conclusion.[/red]"
        )


def fact_check_report(findings: str, recommendation: str, observations: list) -> tuple[bool, str]:
    """Checks the report's claims against the query results and the tool's
    documented schema."""
    obs_text = "\n".join(f"- {o['args'].get('sql')} -> {o['result']}" for o in observations)
    verdict = get_client().models.generate_content(
        model=MODEL,
        contents=(
            f"Tool documentation available to the agent (a legitimate source of "
            f"truth about the data, not just query results):\n{run_query_grounded.__doc__}\n\n"
            f"Query results gathered during this investigation:\n{obs_text}\n\n"
            f"Proposed report:\nFindings: {findings}\nRecommendation: {recommendation}\n\n"
            "Does every factual claim in the findings and recommendation trace back "
            "to either the tool documentation or one of the query results above? "
            "Reply with exactly 'PASS' or 'FAIL: <reason>'."
        ),
    ).text.strip()
    passed = verdict.upper().startswith("PASS")
    reason = verdict.split(":", 1)[1].strip() if not passed and ":" in verdict else verdict
    return passed, reason


def data_analyst_agent(question: str, session: Session | None = None) -> tuple[str, Session]:
    """The full pipeline: investigate (bounded, grounded), propose a report,
    verify it, pause for human approval if it makes a recommendation, send it.

    Pass session=None (the default) for a one-shot call. Pass the Session
    returned from a previous call to continue the same conversation - a
    follow-up question can then reference "that" the same way memory.py
    demonstrated, because this is genuinely the same mechanism, not a
    separate reimplementation of it. The grounding check sees every
    observation gathered across the whole conversation, not just this call's
    new ones - a fact verified two turns ago is still grounded, it
    shouldn't need to be re-queried every turn just to stay provable.
    """
    console.rule("Bounded + grounded - stops once it has the driver, full pipeline")
    session = session if session is not None else Session()
    session.contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

    result = run_tool_loop(
        session.contents,
        [run_query, write_report],
        terminal_tools={"write_report"},
        system_instruction=BOUNDED_INSTRUCTION,
        max_steps=10,
        console=console,
        observations=session.observations,
    )

    if result.terminal_call is None:
        text = result.final_text or "(ran out of steps before reaching a conclusion)"
        console.print(Panel(text, title="[green]Answer[/green]", border_style="green"))
        return text, session

    report_args = result.terminal_call["args"]
    passed, reason = fact_check_report(
        report_args["findings"], report_args["recommendation"], session.observations
    )

    if not passed:
        console.print(
            f"[red]Report is not accurate[/red] - it makes a claim the data doesn't "
            f"support:\n  {reason}\n[red]Holding it back instead of sending it.[/red]"
        )
        outcome = {"status": "held_back", "reason": reason}
        answer = f"(report held back - inaccurate: {reason})"
    elif report_args["recommendation"].strip():
        console.print("[cyan]Report checked - every claim matches the data.[/cyan]")
        console.print(
            "[bold red]Report includes a recommendation, which is a judgment call, "
            "not a plain fact -> pausing for human review.[/bold red]"
        )
        decision = input("Approve and send? [y/N]: ").strip().lower()
        if decision == "y":
            write_report(**report_args)
            outcome = {"status": "sent"}
            answer = f"Report sent: {report_args['title']}"
        else:
            console.print("[dim]Declined - report held back.[/dim]")
            outcome = {"status": "declined_by_reviewer"}
            answer = "(report declined by reviewer)"
    else:
        console.print("[cyan]Report checked - every claim matches the data.[/cyan]")
        write_report(**report_args)
        outcome = {"status": "sent"}
        answer = f"Report sent: {report_args['title']}"

    # The write_report call in `contents` still needs a matching function
    # response before this history is valid to continue in a follow-up call.
    session.contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_function_response(name="write_report", response={"result": outcome})],
        )
    )
    return answer, session


if __name__ == "__main__":
    # Fixed comparison showing why the bounded instruction matters (see
    # README) - kept commented out on purpose, run it yourself when you
    # want to show it rather than it running automatically every time:
    # demo_question = "How did Q2 2026 go? Anything I should be worried about?"
    # run_unbounded(demo_question)
    # data_analyst_agent(demo_question)

    console.rule("Data Analyst Agent")
    console.print("Ask a question. Blank line to quit. Follow-ups work - it "
                   "remembers the conversation.\n")
    session = None
    while True:
        try:
            question = console.input("[bold cyan]You:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        console.print()
        _, session = data_analyst_agent(question, session=session)
        console.print()
