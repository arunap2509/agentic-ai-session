"""HyDE (Hypothetical Document Embeddings) vs. direct query embedding, on
the same knowledge base as the other rag-demo scripts.

The problem HyDE targets: a short, vague, colloquial query doesn't *read*
like the documents it should match. "Money service keeps randomly dying
... feels like it just falls over" shares almost no vocabulary or register
with a runbook written as Symptoms/Root cause/Fix with kubectl commands.
Embedding the query directly and comparing it to document embeddings is a
query-to-document match across two very different writing styles, and nets
out to a near coin flip between the right service and the wrong one.

HyDE's move: ask an LLM to write a *hypothetical* runbook paragraph that
would plausibly answer the vague question -- invented specifics are fine,
it's never shown to the user. That hypothetical document is written in the
same register as the real corpus, so embedding it and comparing
document-to-document (not query-to-document) lands much closer to the
actually-relevant doc.

Run:
    python 04_hyde.py
"""

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval import Doc, cosine_rank, embed, embed_documents, embed_query, load_corpus

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import MODEL, get_client

console = Console()

VAGUE_QUERY = (
    "Money service keeps randomly dying whenever there's a big rush of "
    "orders. No idea why, feels like it just falls over."
)

HYDE_INSTRUCTION = (
    "You are drafting a hypothetical internal SRE runbook excerpt that "
    "would plausibly answer an on-call engineer's vague question. Write in "
    "the same style as a real runbook: Symptoms / Root cause / Fix "
    "sections, specific-sounding technical details (kubectl commands, "
    "config keys, error codes). It's fine if details are invented -- this "
    "document is only used to improve retrieval, it is never shown to the "
    "engineer. 120 words max."
)

ANSWER_INSTRUCTION = (
    "You are an on-call assistant. Answer the engineer's question using "
    "ONLY the provided runbook excerpt. Be concise -- 3 sentences max."
)

TOP_K = 1


def generate_hyde_doc(query: str) -> str:
    response = get_client().models.generate_content(
        model=MODEL,
        contents=f"Engineer's question: {query}",
        config={"system_instruction": HYDE_INSTRUCTION},
    )
    return response.text.strip()


def generate_answer(query: str, chunks: list[Doc]) -> str:
    context = "\n\n".join(f"[{d.id}]\n{d.text}" for d in chunks)
    prompt = f"Context:\n{context}\n\nQuestion: {query}"
    response = get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"system_instruction": ANSWER_INSTRUCTION},
    )
    return response.text.strip()


def print_ranking(title: str, ranked: list[tuple[Doc, float]]) -> None:
    table = Table(title=title, expand=True)
    table.add_column("#", width=3, justify="right", no_wrap=True)
    table.add_column("doc", overflow="fold", ratio=2)
    table.add_column("service", overflow="fold", ratio=1)
    table.add_column("sim", width=7, justify="right", no_wrap=True)
    for i, (doc, score) in enumerate(ranked[:4], 1):
        table.add_row(
            str(i),
            f"[bold yellow]{doc.id}[/bold yellow]" if doc.id == "payment-service-oom" else doc.id,
            doc.metadata.get("service", ""),
            f"{score:.4f}",
        )
    console.print(table)


if __name__ == "__main__":
    console.rule("[bold]Loading corpus + embedding[/bold]")
    docs = load_corpus()
    embed_documents(docs)
    console.print(f"{len(docs)} docs loaded from knowledge_base/\n")

    console.rule("[bold]Vague query[/bold]")
    console.print(VAGUE_QUERY + "\n")

    # --- Direct: embed the vague query itself, compare to document embeddings ---
    direct_ranked = cosine_rank(embed_query(VAGUE_QUERY), docs)
    print_ranking("Direct query embedding (query -> documents)", direct_ranked)
    direct_chunks = [doc for doc, _ in direct_ranked[:TOP_K]]
    direct_answer = generate_answer(VAGUE_QUERY, direct_chunks)

    console.print()

    # --- HyDE: generate a hypothetical document, embed it, compare doc-to-doc ---
    console.rule("[bold]Generating hypothetical document (HyDE)[/bold]")
    hyde_doc = generate_hyde_doc(VAGUE_QUERY)
    console.print(hyde_doc + "\n")

    hyde_vec = embed([hyde_doc], task_type="RETRIEVAL_DOCUMENT")[0]
    hyde_ranked = cosine_rank(hyde_vec, docs)
    print_ranking("HyDE: hypothetical doc embedding (document -> documents)", hyde_ranked)
    hyde_chunks = [doc for doc, _ in hyde_ranked[:TOP_K]]
    hyde_answer = generate_answer(VAGUE_QUERY, hyde_chunks)

    console.rule("[bold]Answers[/bold]")
    direct_correct = direct_chunks[0].id == "payment-service-oom"
    hyde_correct = hyde_chunks[0].id == "payment-service-oom"

    console.print(
        "[bold]Direct RAG answer[/bold] "
        + ("[green](retrieved payment-service-oom)[/green]" if direct_correct
           else f"[bold red](retrieved {direct_chunks[0].id} instead)[/bold red]")
    )
    console.print(direct_answer + "\n")

    console.print(
        "[bold]HyDE RAG answer[/bold] "
        + ("[green](retrieved payment-service-oom)[/green]" if hyde_correct
           else f"[bold red](retrieved {hyde_chunks[0].id} instead)[/bold red]")
    )
    console.print(hyde_answer + "\n")

    if not direct_correct and hyde_correct:
        direct_margin = direct_ranked[1][1] - direct_ranked[0][1]  # runner-up beat the right doc
        hyde_margin = hyde_ranked[0][1] - hyde_ranked[1][1]  # right doc beat the runner-up
        console.rule("[bold red]Result[/bold red]")
        console.print(
            "Direct embedding put a different service's runbook 1st, ahead "
            "of the right one, because a vague colloquial query and a "
            "structured runbook just don't look alike in embedding space -- "
            f"it's close to a coin flip (the wrong doc won by {direct_margin:.4f} "
            "cosine similarity). Rewriting the query into a hypothetical "
            "answer in the corpus's own register turns the search into a "
            "document-to-document match, and the right doc now wins by "
            f"{hyde_margin:.4f} instead -- a decisive gap, not a coin flip. "
            "(Exact margins vary run to run since the hypothetical doc is "
            "freshly generated each time -- rerun to see it move.)"
        )
