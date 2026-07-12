# Day 2 — Tools, MCP, and Agent Design Patterns

Demo code for the Day 2 session. One shared virtualenv, one `.env`, three
folders:

```
01-tools/                    Tools & Agent SDK
02-mcp-servers/               MCP Servers (live public server)
03-agent-design-patterns/     Agent Design Patterns (9 patterns)
common/                       Shared Gemini client helper used by every script
```

## Setup (do this once)

```bash
cd day-2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set GEMINI_API_KEY (get one free at https://aistudio.google.com/apikey)
```

That's it — every script below assumes this same activated venv and `.env`.

## Why Gemini

We're using the Gemini API directly (not OpenRouter): the free tier is
genuinely free (no card, ~1,500 requests/day, more than enough for live
demos) and the `google-genai` SDK has first-class MCP support, which the
MCP servers folder leans on directly.

## Running things

Activate the venv once per terminal session, then run any script from the
`day-2` directory:

```bash
source .venv/bin/activate
python 01-tools/tool_calling_demo.py
python 02-mcp-servers/mcp_client_demo.py
python 03-agent-design-patterns/01_react.py
# ...etc
```

See each folder's own README for what each script demonstrates.

## Notes for the live session

- All Gemini calls go through `common/llm.py`, which reads `GEMINI_MODEL`
  from `.env` (defaults to `gemini-flash-latest` — an alias, so it won't
  break if a specific dated model gets deprecated before the session).
  `gemini-flash-lite-latest` is a genuinely weaker/cheaper alternative,
  documented in `.env.example` — useful when you want a demo to actually
  show a model struggling (e.g. the FAIL branch in
  `03-agent-design-patterns/02_reflection.py`).
- `02-mcp-servers/` needs internet access to reach `mcp.deepwiki.com`
  (a public, no-auth MCP server) — worth a quick connectivity check
  wherever you're presenting.
- `03-agent-design-patterns/04_human_in_the_loop.py` pauses on a real
  terminal prompt — good for a "watch it stop and wait for me" moment.
