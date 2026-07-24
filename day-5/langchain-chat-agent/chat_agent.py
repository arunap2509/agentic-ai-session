"""
Chat Agent (LangChain) - chat_agent.py

A minimal, multi-turn conversational agent - built to watch the tool-calling
loop happen, not to prove anything the way agent-evals/langchain-agent-evals
does. Three small tools, three things worth watching for as you chat with it:

  1. Tool calls are visible - every time the model decides to call a tool,
     you see the exact call (name + args), then its result, before the
     final reply. That's the loop: model decides -> tool runs -> result
     goes back to the model -> model replies (or calls another tool).
  2. It remembers earlier turns - ask a follow-up like "add 10 to that" and
     it resolves "that" from conversation history, via LangGraph's
     MemorySaver checkpointer (not by us manually maintaining a messages
     list, the way main.py/agent.py does in ../self-evolving-agent/).
  3. Every turn is traced to Langfuse, same as ../langchain-agent-evals/ -
     open your Langfuse project after chatting to see the full trajectory
     for each message, not just what scrolled past in the terminal.

Try asking, in order:
    "What time is it right now?"                  -> get_current_time
    "What's 47 * (12 + 3)?"                        -> calculate
    "What's the weather in Chennai?"               -> get_weather
    "Add 100 to that temperature."                 -> memory + calculate
    "What's 2 to the power of 10, divided by 4?"   -> calculate (order of ops)

Run:
    python chat_agent.py
"""

import ast
import operator
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.panel import Panel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "gemini-flash-latest"
MAX_STEPS = 10  # safety net, not central to the demo - these tools can't loop

SYSTEM_PROMPT = (
    "You are a friendly, concise assistant with three tools: get_current_time, "
    "calculate, and get_weather. Use a tool whenever the question genuinely needs "
    "one - don't guess a time, do arithmetic in your head, or make up weather."
)

console = Console()


@tool
def get_current_time() -> str:
    """Get the current date and time. Use this whenever the user asks about
    "now", today's date, or the current time - you have no other way to know this."""
    return datetime.now().strftime("%A, %Y-%m-%d %H:%M:%S")


_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression syntax: {ast.dump(node)}")


@tool
def calculate(expression: str) -> float:
    """Evaluate a basic arithmetic expression: +, -, *, /, **, parentheses.
    Use this for any calculation instead of doing the math yourself - you're
    prone to arithmetic mistakes, this tool isn't.

    Args:
        expression: A plain arithmetic expression, e.g. "47 * (12 + 3)".
    """
    # A real eval() would execute arbitrary code from model output - parsing
    # to an AST and only walking a fixed whitelist of safe node types (no
    # function calls, names, or attribute access reach this) avoids that.
    return _eval_node(ast.parse(expression, mode="eval").body)


@tool
def get_weather(city: str) -> dict:
    """Get the current weather for a city. Synthetic/mocked data for this
    demo, not a real weather service - but consistent per city, so asking
    about the same city twice gives the same answer.

    Args:
        city: City name, e.g. "Chennai".
    """
    import random

    rng = random.Random(city.strip().lower())
    condition = rng.choice(["Sunny", "Cloudy", "Rainy", "Partly Cloudy", "Clear"])
    return {
        "city": city,
        "condition": condition,
        "temp_celsius": rng.randint(18, 38),
        "humidity_pct": rng.randint(30, 90),
    }


def _extract_text(message) -> str:
    """An AIMessage's .content is either a plain string or (with this
    Gemini integration) a list of content blocks - handle both."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text")


def stream_turn(agent, user_input: str, config: dict) -> None:
    """Streams one turn step by step, printing each new message as it
    arrives - this is what makes the loop visible instead of just showing
    the final answer."""
    for step in agent.stream({"messages": [{"role": "user", "content": user_input}]}, config=config, stream_mode="values"):
        message = step["messages"][-1]
        kind = type(message).__name__

        if kind == "HumanMessage":
            continue  # already shown via console.input's own prompt

        if kind == "AIMessage" and message.tool_calls:
            for call in message.tool_calls:
                console.print(Panel(f"{call['name']}({call['args']})", title="🔧 Tool Call", border_style="blue"))

        elif kind == "ToolMessage":
            console.print(Panel(str(message.content), title=f"Result - {message.name}", border_style="magenta"))

        elif kind == "AIMessage" and not message.tool_calls:
            console.print(f"\n[bold green]Assistant:[/bold green] {_extract_text(message)}")


def main() -> None:
    console.rule("[bold]Chat Agent (LangChain)[/bold]")
    console.print(
        "A conversational agent with 3 tools - watch each tool call and its result "
        "as they happen, then the final reply. It remembers earlier turns.\n"
        "[dim]Traced to Langfuse - open your project after chatting to see the full "
        "trajectory.[/dim]"
    )

    model = ChatGoogleGenerativeAI(model=MODEL)
    agent = create_agent(
        model=model,
        tools=[get_current_time, calculate, get_weather],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},  # one conversation per process run
        "callbacks": [CallbackHandler()],
        "recursion_limit": MAX_STEPS * 2 + 2,
    }

    while True:
        user_input = console.input("\n[bold cyan]You (blank to quit):[/bold cyan] ").strip()
        if not user_input:
            break
        stream_turn(agent, user_input, config)

    get_client().flush()
    console.print("\n[dim]Traces flushed to Langfuse.[/dim]")


if __name__ == "__main__":
    main()
