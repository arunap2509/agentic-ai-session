"""
MCP Servers - prompts and resources (not tools)
================================================

Tools are model-controlled - the model decides on its own when to call
one. Prompts and resources are not:

  - Prompts are user-controlled - meant to be picked explicitly by a
    person (think "slash commands"), not something the model chooses to
    invoke itself.
  - Resources are application-controlled - the spec leaves it up to the
    host app's policy (a person attaching one, the host auto-attaching
    one, or even the host handing resource-reading to the model). Not
    fixed to "user picks it" the way prompts are.

No LLM is involved here - this script is the host, calling prompts/get
and resources/read directly against the Everything server and printing
exactly what comes back.

Run:
    python mcp_prompts_resources_demo.py
"""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console

console = Console()

EVERYTHING_SERVER = StdioServerParameters(
    command="npx", args=["-y", "@modelcontextprotocol/server-everything"]
)


async def main() -> None:
    async with stdio_client(EVERYTHING_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            console.rule("Prompts")
            prompts = (await session.list_prompts()).prompts
            for p in prompts:
                console.print(f"prompt: {p.name}  args={[a.name for a in (p.arguments or [])]}")

            console.print("\ncalling get_prompt('simple-prompt'):")
            result = await session.get_prompt("simple-prompt")
            for m in result.messages:
                console.print(f"  role={m.role}  content={m.content}")

            console.print("\ncalling get_prompt('args-prompt', {'city': 'Athens'}):")
            result = await session.get_prompt("args-prompt", {"city": "Athens"})
            for m in result.messages:
                console.print(f"  role={m.role}  content={m.content}")

            console.rule("Resources")
            templates = (await session.list_resource_templates()).resourceTemplates
            for t in templates:
                console.print(f"resource template: {t.uriTemplate}")

            uri = "demo://resource/dynamic/text/1"
            console.print(f"\ncalling read_resource({uri!r}):")
            result = await session.read_resource(uri)
            for c in result.contents:
                console.print(f"  uri={c.uri}  mimeType={c.mimeType}")
                console.print(f"  content={getattr(c, 'text', None)}")


if __name__ == "__main__":
    asyncio.run(main())
