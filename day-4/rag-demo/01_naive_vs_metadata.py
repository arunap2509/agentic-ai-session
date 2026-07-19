"""Naive RAG vs. metadata-filtered RAG, on the same query.

Metadata-filtered RAG here is two LLM-adjacent steps, not one manual
constant: (1) an LLM call extracts a structured filter from the query --
same response_schema pattern as day-2/04-structured-output -- THEN (2) that
filter is applied to the corpus before embedding search runs. Nothing about
which service this query is about is hardcoded; it's derived from the query
text at run time, same as a real "understand the query, then retrieve"
pipeline would do it.

The corpus mirrors incident-commander's runbook world, extended so every
service has an OOMKilled runbook and payment-service specifically has an
extra wrinkle: a PCI compliance policy that overrides the "no approval
needed" default that applies to every other service. That policy is worded
very differently from an operational runbook (compliance/audit language,
not kubectl commands) - similar service, dissimilar wording. Pure top-k
cosine search over the whole corpus reliably ranks it below the cutoff.
Filtering to the extracted service first cannot miss it: there are only
three payment-service docs, and it's one of them.

incident-commander/tools/runbook_retrieval.py already does keyword-overlap
retrieval with no reasoning loop - this demo is that same idea taken one
step further into embeddings, and then shows why "search everything, keep
the top matches" still isn't enough without metadata.

Run:
    python 01_naive_vs_metadata.py
"""

import sys
from pathlib import Path

from google.genai import types
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval import Doc, cosine_rank, embed_documents, embed_query, load_corpus

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

QUERY = (
    "Pods for payment-service are getting OOMKilled during checkout traffic "
    "spikes. What's the fix, and do I need any approval before restarting?"
)

ANSWER_INSTRUCTION = (
    "You are an on-call assistant. Answer the engineer's question using ONLY "
    "the provided runbook/policy excerpts. If the excerpts don't mention an "
    "approval requirement, do not invent one. Be concise - 3 sentences max."
)

POLICY_DOC_ID = "pci-escalation-policy"


class ServiceFilter(BaseModel):
    service: str | None


def extract_service_filter(query: str, known_services: list[str]) -> str | None:
    """Same structured-output pattern as day-2/04-structured-output --
    response_mime_type + a Pydantic response_schema, so the model is
    constrained to return exactly {"service": ...} instead of free text we'd
    have to parse. This is the "get the filter" step: an LLM call over the
    query text, run before any retrieval happens, not a hardcoded constant.
    """
    instruction = (
        "Extract a metadata filter from an on-call engineer's question: "
        "which service (if any) is this about? Only choose from this exact "
        f"list: {known_services}. If the question doesn't clearly name or "
        "imply exactly one of these services, return null for service."
    )
    response = get_client().models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=instruction,
            response_mime_type="application/json",
            response_schema=ServiceFilter,
        ),
    )
    return ServiceFilter.model_validate_json(response.text).service


def generate_answer(query: str, chunks: list[Doc]) -> str:
    context = "\n\n".join(f"[{d.id}]\n{d.text}" for d in chunks)
    prompt = f"Context:\n{context}\n\nQuestion: {query}"
    response = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"system_instruction": ANSWER_INSTRUCTION},
    )
    return response.text.strip()


def print_retrieval_table(title: str, ranked: list[tuple[Doc, float]], top_k: int) -> None:
    table = Table(title=title, show_lines=True, expand=True)
    table.add_column("#", width=3, justify="right", no_wrap=True)
    table.add_column("doc", overflow="fold", ratio=2)
    table.add_column("service / type", overflow="fold", ratio=1)
    table.add_column("sim", width=7, justify="right", no_wrap=True)
    for i, (doc, score) in enumerate(ranked, 1):
        retrieved = i <= top_k
        rank_label = f"{i} ✓" if retrieved else str(i)
        table.add_row(
            rank_label,
            doc.id,
            f"{doc.metadata.get('service', '')} / {doc.metadata.get('doc_type', '')}",
            f"{score:.4f}",
            style="bold green" if retrieved else "dim",
        )
    console.print(table)


def saw_policy_doc(chunks: list[Doc]) -> bool:
    """Whether the PCI policy doc actually made it into the context handed
    to the LLM -- deterministic, unlike grepping the generated answer text
    for words like "approval" (which shows up either way: the wrong answer
    says approval is *not* needed).
    """
    return any(d.id == POLICY_DOC_ID for d in chunks)


if __name__ == "__main__":
    console.rule("[bold]Loading corpus + embedding[/bold]")
    docs = load_corpus()
    embed_documents(docs)
    console.print(f"{len(docs)} docs loaded from knowledge_base/\n")

    console.rule("[bold]Query[/bold]")
    console.print(QUERY + "\n")

    query_vec = embed_query(QUERY)
    top_k = 2

    # --- Naive: cosine search over the entire corpus ---
    naive_ranked = cosine_rank(query_vec, docs)
    print_retrieval_table(f"Naive RAG - cosine over all {len(docs)} docs (top {top_k} kept)", naive_ranked, top_k)
    naive_chunks = [doc for doc, _ in naive_ranked[:top_k]]
    naive_answer = generate_answer(QUERY, naive_chunks)

    console.print()

    # --- Metadata-filtered: ask the LLM which service this is about, THEN retrieve ---
    console.rule("[bold]Step 1: extract the filter (LLM call, no retrieval yet)[/bold]")
    known_services = sorted(
        {d.metadata.get("service") for d in docs if d.metadata.get("service", "none") != "none"}
    )
    service_filter = extract_service_filter(QUERY, known_services)
    console.print(f"Known services in the corpus: {known_services}")
    console.print(f'Extracted filter: [bold]service = "{service_filter}"[/bold]\n')

    console.rule("[bold]Step 2: apply the filter, then retrieve[/bold]")
    filtered_docs = [d for d in docs if d.metadata.get("service") == service_filter] if service_filter else docs
    filtered_ranked = cosine_rank(query_vec, filtered_docs)
    print_retrieval_table(
        f"Metadata-filtered RAG - service={service_filter} only, "
        f"{len(filtered_docs)} candidates (top {top_k} kept)",
        filtered_ranked,
        top_k,
    )
    filtered_chunks = [doc for doc, _ in filtered_ranked[:top_k]]
    filtered_answer = generate_answer(QUERY, filtered_chunks)

    console.rule("[bold]Answers[/bold]")
    naive_saw_policy = saw_policy_doc(naive_chunks)
    filtered_saw_policy = saw_policy_doc(filtered_chunks)

    console.print(
        "[bold]Naive RAG answer[/bold] "
        + ("[green](PCI policy was in context)[/green]" if naive_saw_policy
           else "[bold red](PCI policy doc never retrieved!)[/bold red]")
    )
    console.print(naive_answer + "\n")

    console.print(
        "[bold]Metadata-filtered RAG answer[/bold] "
        + ("[green](PCI policy was in context)[/green]" if filtered_saw_policy
           else "[bold red](PCI policy doc never retrieved!)[/bold red]")
    )
    console.print(filtered_answer + "\n")

    if not naive_saw_policy and filtered_saw_policy:
        console.rule("[bold red]Result[/bold red]")
        console.print(
            "Naive top-k retrieval never surfaced pci-escalation-policy.md - it "
            "ranks below the cutoff because compliance-worded text sits farther "
            "from the operational query in embedding space than an unrelated "
            "service's runbook does. The naive answer would let an on-call "
            "engineer restart a PCI-scoped service with no approval, which is "
            "itself a compliance finding. Filtering to service=payment-service "
            "first can't miss that doc - it's one of only three candidates."
        )
