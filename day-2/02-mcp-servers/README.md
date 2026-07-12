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
