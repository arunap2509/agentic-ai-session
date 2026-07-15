"""
MCP Servers - wired into an LLM
================================

Demo goals:
  - Same DeepWiki MCP server as mcp_client_demo.py, but now the model
    itself decides when to call it. We hand the live ClientSession to
    Gemini as a "tool" and the SDK handles discovery + calling for us.
  - Zero tool-specific code was written here. The server showed up, told
    the model what it could do, and the model used it.

Run:
    python mcp_agent_demo.py
"""

import asyncio
import sys
from pathlib import Path

from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

DEEPWIKI_URL = "https://mcp.deepwiki.com/mcp"

# A few ready-to-run questions. PROMPT_1 is developer-facing; the rest are
# plain-language so a non-technical audience can follow along too. Swap
# which one PROMPT points to (or read one out and let the room pick).
PROMPT_1 = (
    "Using the modelcontextprotocol/servers GitHub repo, tell me: what "
    "reference MCP servers ship in that repo? Give a short bulleted list."
)
PROMPT_2 = (
    "In plain, non-technical language, explain what the facebook/react "
    "project is and why so many websites use it."
)
PROMPT_3 = (
    "Explain what the torvalds/linux repository is, as if you're "
    "explaining it to someone who has never written code."
)
PROMPT_4 = (
    "What is ollama/ollama used for? Explain the problem it solves for "
    "someone who wants to run AI models on their own computer, in "
    "everyday language."
)
PROMPT_5 = (
    "Is the microsoft/vscode project still actively maintained? Explain "
    "how you can tell, in simple terms."
)

PROMPT = PROMPT_5


async def main() -> None:
    client = get_client()

    console.rule("MCP tools handed straight to the model")
    console.print(f"[bold cyan]User:[/bold cyan] {PROMPT}\n")

    async with streamable_http_client(DEEPWIKI_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            contents = [types.Content(role="user", parts=[types.Part(text=PROMPT)])]

            for _ in range(5):
                response = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=contents,
                    # tools=[session] still gets the MCP tool schemas translated
                    # for free. automatic_function_calling is disabled so WE run
                    # the loop below instead of the SDK - that's what lets each
                    # Action / Tool Response print live, round by round, instead
                    # of only appearing after every call has already finished.
                    config={
                        "tools": [session],
                        "automatic_function_calling": {"disable": True},
                    },
                )
                candidate = response.candidates[0].content
                contents.append(candidate)

                calls = [p.function_call for p in candidate.parts if p.function_call]
                if not calls:
                    console.print(f"[bold green]Model's answer:[/bold green]\n{response.text}")
                    return

                response_parts = []
                for call in calls:
                    console.print(f"[yellow]Action:[/yellow] {call.name}({dict(call.args)})")
                    result = await session.call_tool(call.name, dict(call.args))
                    text = "".join(item.text for item in result.content if hasattr(item, "text"))
                    console.print(
                        Panel(
                            text,
                            title=f"[magenta]Tool Response: {call.name}[/magenta]",
                            border_style="magenta",
                        )
                    )
                    response_parts.append(
                        types.Part.from_function_response(name=call.name, response={"result": text})
                    )
                contents.append(types.Content(role="user", parts=response_parts))


if __name__ == "__main__":
    asyncio.run(main())
