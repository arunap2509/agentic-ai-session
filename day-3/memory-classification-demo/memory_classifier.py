"""
Memory Classification Demo - memory_classifier.py

A standalone day-3 project, not tied to any of the other three (Data
Analyst Agent, Ticker Triaging Agent, Coding Agent). Given a conversation
transcript, one model call extracts every distinct piece of information
in it and classifies each into one of five memory types - in-context,
key-value, vector, episodic, procedural - with a one-line rationale.

This is a classification demo only: nothing here writes to a database,
a vector store, or a file. The output is a table, not a stored memory.

Structured output (response_mime_type + a Pydantic response_schema) is
the same pattern taught in day-2/04-structured-output - guarantees the
model returns a list of {extracted_info, memory_type, rationale} objects
instead of free text you'd have to parse yourself.

Multiple conversations live in conversations/ so you can switch which one
you're demoing without touching code:

Run:
    python memory_classifier.py                                  # pick interactively
    python memory_classifier.py conversation_2_customer_support.md # run a specific one directly
"""

import sys
from pathlib import Path

from google.genai import types
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

CONVERSATIONS_DIR = Path(__file__).resolve().parent / "conversations"

CLASSIFY_INSTRUCTION = (
    "You are analyzing a conversation transcript between a user and an assistant "
    "to decide, for each distinct piece of information in it, which of five memory "
    "systems it belongs in. Read the whole transcript before deciding - some "
    "categories (episodic, procedural) can only be recognized by looking at more "
    "than one turn at once, not a single line in isolation.\n\n"
    "The five categories:\n"
    "- in_context: only matters for finishing the current exchange - not worth "
    "remembering once the conversation ends.\n"
    "- key_value: a small, stable, durable fact about the user (name, role, a "
    "stated preference, a config-like value) - cheap to store as a single fact "
    "and look up later by key.\n"
    "- vector: part of a larger, growing body of content, better retrieved later "
    "by meaning/similarity than by exact key - a note, an explanation, something "
    "searchable by paraphrase rather than exact wording.\n"
    "- episodic: a specific past event, decision, or interaction referenced in "
    "time (\"last time\", \"we decided\", \"I told you before\") - tied to a "
    "moment, not a standalone fact.\n"
    "- procedural: a repeated pattern of behavior or a preferred way of doing a "
    "recurring task, inferred from the user doing or asking for the same shape "
    "of thing more than once in the transcript - it should take a real repeat "
    "to earn this label, not a single request.\n\n"
    "Extract every distinct piece of information worth a classification decision "
    "- don't skip the mundane ones, the in_context items are part of the point. "
    "For each, give a short extracted snippet or paraphrase, the single "
    "best-fitting category, and a one-sentence rationale that ties back to the "
    "category definition above, not just a restatement of the snippet."
)

LABELS = {
    "in_context": "In-Context Memory",
    "key_value": "Key-Value Store",
    "vector": "Vector Memory",
    "episodic": "Episodic Memory",
    "procedural": "Procedural Memory",
}


class ClassifiedItem(BaseModel):
    extracted_info: str
    memory_type: str
    rationale: str


class ClassificationResult(BaseModel):
    items: list[ClassifiedItem]


def classify_conversation(transcript: str) -> list[ClassifiedItem]:
    response = get_client().models.generate_content(
        model=MODEL,
        contents=f"Transcript:\n\n{transcript}",
        config=types.GenerateContentConfig(
            system_instruction=CLASSIFY_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ClassificationResult,
        ),
    )
    return ClassificationResult.model_validate_json(response.text).items


def print_classification(items: list[ClassifiedItem]) -> None:
    table = Table(title="Memory Classification")
    table.add_column("Extracted Info", overflow="fold", ratio=2)
    table.add_column("Memory Type", overflow="fold")
    table.add_column("Rationale", overflow="fold", ratio=2)
    for item in items:
        table.add_row(item.extracted_info, LABELS.get(item.memory_type, item.memory_type), item.rationale)
    console.print(table)


def list_conversations() -> list[Path]:
    return sorted(CONVERSATIONS_DIR.glob("*.md"))


def pick_conversation() -> Path:
    files = list_conversations()
    if not files:
        raise RuntimeError(f"No conversation files found in {CONVERSATIONS_DIR}")

    if len(sys.argv) > 1:
        chosen = CONVERSATIONS_DIR / sys.argv[1]
        if chosen.exists():
            return chosen
        console.print(f"[red]{sys.argv[1]} not found in conversations/ - showing the list instead.[/red]\n")

    console.print("[bold cyan]Available demo conversations:[/bold cyan]")
    for i, f in enumerate(files, start=1):
        console.print(f"  {i}. {f.name}")
    choice = console.input("\nPick a number (blank = 1): ").strip()
    index = int(choice) - 1 if choice else 0
    return files[index]


def run(path: Path) -> None:
    console.rule(f"Memory Classification Demo - {path.name}")
    transcript = path.read_text()
    console.print(transcript)
    items = classify_conversation(transcript)
    console.print()
    print_classification(items)


if __name__ == "__main__":
    run(pick_conversation())
