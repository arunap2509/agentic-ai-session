# Chat Agent (LangChain)

A minimal, multi-turn conversational agent built to make the tool-calling
loop *visible*, not to prove anything the way `../agent-evals/` or
`../langchain-agent-evals/` do. Three small tools
(`get_current_time`, `calculate`, `get_weather`), one REPL, streamed output
so you see every tool call and its result before the final reply - not
just the finished answer.

## What to watch for

1. **The loop, step by step.** Each turn streams via `agent.stream(...,
   stream_mode="values")` instead of a single `.invoke()` - you see
   `🔧 Tool Call` → `Result` → `Assistant:` in order, exactly as they
   happen. That sequence *is* the loop: model decides it needs a tool →
   tool runs → result goes back into the conversation → model replies (or
   decides it needs another tool and repeats).
2. **Real conversation memory.** Ask a follow-up like "add 100 to that
   temperature" after asking about the weather, and it resolves "that" from
   earlier in the conversation - via LangGraph's `MemorySaver` checkpointer
   (`checkpointer=MemorySaver()` + a fixed `thread_id`), not by us manually
   appending to a messages list the way `../self-evolving-agent/`'s
   `agent.py` does.
3. **Traced to Langfuse**, same setup as `../langchain-agent-evals/` - open
   your Langfuse project after chatting to see the full trajectory behind
   any reply, not just what scrolled past in the terminal.

## Try

```
What time is it right now?                    -> get_current_time
What's 47 * (12 + 3)?                          -> calculate
What's the weather in Chennai?                 -> get_weather
Add 100 to that temperature.                   -> memory + calculate
```

## Run it

```
cd day-5
python3 -m venv .venv && source .venv/bin/activate   # if not already set up
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY + LANGFUSE_SECRET_KEY/PUBLIC_KEY/BASE_URL

cd langchain-chat-agent
python chat_agent.py
```
