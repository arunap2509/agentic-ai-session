"""
MCP Servers - two servers, one agent
========================================

DeepWiki (remote, streamable HTTP, tools only) plus the official
"Everything" reference server (local, over stdio - launched as a
subprocess via `npx -y @modelcontextprotocol/server-everything`), which
deliberately implements every MCP primitive: tools, resources, and
prompts. Connecting to both side by side answers, live, whether a given
server exposes more than tools - discovery below prints DeepWiki's empty
resource/prompt lists next to Everything's populated ones.

The prompt then asks for things that live on different servers, so the
tool-use loop has to route each call to the right session by name - the
model just sees one merged set of tools and doesn't know or care that
two different servers are behind them.

Requires Node.js/npx installed locally (`npx` pulls the Everything server
package on first run - no separate install step).

Run:
    python mcp_multi_server_demo.py
"""

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

DEEPWIKI_URL = "https://mcp.deepwiki.com/mcp"
EVERYTHING_SERVER = StdioServerParameters(
    command="npx", args=["-y", "@modelcontextprotocol/server-everything"]
)

PROMPT = (
    "Using the modelcontextprotocol/servers GitHub repo, tell me in one "
    "sentence what the Everything reference server is for. Separately, "
    "add 47 and 89, and echo back the exact phrase 'demo complete'."
)


async def discover(label: str, session: ClientSession) -> list[types.Tool]:
    console.print(f"\n[bold]{label}[/bold]")
    tools = (await session.list_tools()).tools
    console.print(f"  tools: {[t.name for t in tools]}")

    try:
        resources = (await session.list_resources()).resources
        console.print(f"  resources: {[r.uri for r in resources] or 'none'}")
    except Exception as exc:
        console.print(f"  resources: not supported ({exc.__class__.__name__})")

    try:
        prompts = (await session.list_prompts()).prompts
        console.print(f"  prompts: {[p.name for p in prompts] or 'none'}")
    except Exception as exc:
        console.print(f"  prompts: not supported ({exc.__class__.__name__})")

    return tools


async def main() -> None:
    async with AsyncExitStack() as stack:
        deepwiki_read, deepwiki_write, _ = await stack.enter_async_context(
            streamable_http_client(DEEPWIKI_URL)
        )
        deepwiki = await stack.enter_async_context(
            ClientSession(deepwiki_read, deepwiki_write)
        )
        await deepwiki.initialize()

        everything_read, everything_write = await stack.enter_async_context(
            stdio_client(EVERYTHING_SERVER)
        )
        everything = await stack.enter_async_context(
            ClientSession(everything_read, everything_write)
        )
        await everything.initialize()

        console.rule("Discovery: what does each server expose?")
        deepwiki_tools = await discover("deepwiki (remote, streamable HTTP)", deepwiki)
        everything_tools = await discover("everything (local, stdio)", everything)

        sessions = {"deepwiki": deepwiki, "everything": everything}
        tool_server = {t.name: "deepwiki" for t in deepwiki_tools}
        tool_server.update({t.name: "everything" for t in everything_tools})

        console.rule("Tool-use loop across two servers")
        console.print(f"user: {PROMPT}")

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part(text=PROMPT)])
        ]
        client = get_client()

        for step in range(1, 7):
            response = await client.aio.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[*deepwiki_tools, *everything_tools]
                ),
            )
            candidate_content = response.candidates[0].content
            contents.append(candidate_content)

            function_calls = response.function_calls

            console.print(f"\nmodel response, step {step}:")
            console.print(f"  content: {response.text!r}")
            if function_calls:
                console.print(
                    "  tool_calls: "
                    + str(
                        [
                            {
                                "name": c.name,
                                "args": dict(c.args),
                                "server": tool_server[c.name],
                            }
                            for c in function_calls
                        ]
                    )
                )
            else:
                console.print("  tool_calls: None")

            if not function_calls:
                return

            response_parts = []
            for call in function_calls:
                session = sessions[tool_server[call.name]]
                result = await session.call_tool(call.name, dict(call.args))
                text = "".join(
                    item.text for item in result.content if hasattr(item, "text")
                )
                console.print(
                    f"  tool result for {call.name} ({tool_server[call.name]}): {text}"
                )
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response={"result": text}
                        )
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))

        raise RuntimeError("did not finish within max steps")


if __name__ == "__main__":
    asyncio.run(main())
