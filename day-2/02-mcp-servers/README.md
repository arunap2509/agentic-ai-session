# MCP Servers

Both scripts connect to **DeepWiki** (`https://mcp.deepwiki.com/mcp`), a
real public MCP server with no auth required — it exposes tools to answer
questions about any public GitHub repo's documentation.

## `mcp_client_demo.py` — the raw protocol

No LLM involved at all. This script IS the host, it creates an MCP client,
and connects to a server running somewhere else entirely. Demonstrates:

- Host / Client / Server as three distinct roles
- Discovery — lists the server's tools and their schemas before calling
  anything
- Calls `ask_question` directly and prints the raw server response

```bash
python mcp_client_demo.py
```

## `mcp_agent_demo.py` — wired into the model

Same server, but now Gemini decides when to call it. The live MCP
`ClientSession` is handed straight to the model as a tool — no manual
schema translation, no glue code. Zero tool-specific code was written for
this server.

This uses automatic function calling, so the tool-call loop runs entirely
inside one `generate_content()` call and by default you'd only see the
final text. The script pulls `response.automatic_function_calling_history`
back out afterwards and prints each Action/Observation, so you can still
see exactly which tool the model picked and what it got back.

```bash
python mcp_agent_demo.py
```

The file defines five ready-to-run questions, `PROMPT_1` through
`PROMPT_5` — `PROMPT` picks which one actually runs. `PROMPT_1` is
developer-facing (about the MCP servers repo itself); `PROMPT_2`–`PROMPT_5`
ask about well-known repos (React, Linux, Ollama, VS Code) in plain
language, so non-technical people in the room can follow the question and
judge the answer without needing to know what a repo even is. Edit the
`PROMPT = PROMPT_1` line to switch which one runs.

Note: `config={"tools": [session]}` is passed as a plain dict rather than
`types.GenerateContentConfig(...)` — the SDK deep-copies a
`GenerateContentConfig` object internally, which fails on a live MCP
session (it isn't deep-copyable). Passing a dict skips that copy.

## `mcp_multi_server_demo.py` — two servers, one agent

DeepWiki only exposes tools. To see the other two MCP primitives, this
script also connects to the official **Everything** reference server
(`@modelcontextprotocol/server-everything`) — a server built specifically
to exercise every part of the protocol (tools, resources, prompts,
sampling). It runs locally over stdio as a subprocess (`npx -y
@modelcontextprotocol/server-everything`), unlike DeepWiki which is a
remote HTTP endpoint.

Requires Node.js (`npx` on your PATH) — first run downloads the package.

```bash
python mcp_multi_server_demo.py
```

What it shows:

1. **Discovery, side by side** — lists tools/resources/prompts for both
   servers. DeepWiki: tools only, resources/prompts empty or unsupported.
   Everything: all three populated (19 tools, 4 resource types, 4 prompts).
2. **One merged tool set, two servers behind it** — both servers' tools
   are handed to the model together; the model just sees one list and
   doesn't know two different servers answer for it.
3. **Routing by name** — the prompt asks for a repo summary (only
   DeepWiki can answer that), a sum, and an echo (only Everything has
   those tools), so the calls the model makes have to be dispatched to
   the right session. `tool_server` maps each tool name to whichever
   server declared it; every printed tool call and result names which
   server handled it.
4. Same content/tool_calls printing as the other scripts, so you see
   exactly which server's tools got called and in what order, whether
   the model batches them into one turn or spreads them across several.
