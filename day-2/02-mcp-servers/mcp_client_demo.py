"""
MCP Servers - raw protocol demo
================================

Demo goals:
  - Host / Client / Server: this script IS the host, it creates an MCP
    client, and connects to a server running somewhere else entirely
    (mcp.deepwiki.com - a public, remote, no-auth-required MCP server).
  - What a server exposes: tools (functions), and here we call one
    directly, with no LLM involved at all - just the protocol.

DeepWiki lets you ask questions about any public GitHub repo's
auto-generated documentation. No API key needed for this script.

Run:
    python mcp_client_demo.py
"""

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from rich.console import Console
from rich.panel import Panel

console = Console()

DEEPWIKI_URL = "https://mcp.deepwiki.com/mcp"
REPO = "modelcontextprotocol/servers"


async def main() -> None:
    console.rule("Host / Client / Server")
    console.print(f"[bold]Host:[/bold] this script")
    console.print(f"[bold]Client:[/bold] mcp ClientSession (this process)")
    console.print(f"[bold]Server:[/bold] {DEEPWIKI_URL} (runs remotely, over HTTP)\n")

    async with streamablehttp_client(DEEPWIKI_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            console.rule("Discovery: what does this server expose?")
            tools = await session.list_tools()
            for tool in tools.tools:
                console.print(f"[cyan]tool:[/cyan] {tool.name}")
                console.print(f"  {tool.description.strip().splitlines()[0]}")
                console.print(f"  schema: {tool.inputSchema}\n")

            console.rule(f"Calling a tool directly: ask_question({REPO!r}, ...)")
            result = await session.call_tool(
                "ask_question",
                {
                    "repoName": REPO,
                    "question": "What transport protocols does this repo's MCP servers support?",
                },
            )
            answer = "\n".join(
                part.text for part in result.content if hasattr(part, "text")
            )
            console.print(Panel(answer, title="Server response", border_style="cyan"))


if __name__ == "__main__":
    asyncio.run(main())
