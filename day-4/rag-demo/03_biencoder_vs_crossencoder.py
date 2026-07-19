"""Bi-encoder (semantic search) vs. cross-encoder (reranking), on a lexical
ambiguity case: the query "apple computer" against docs that are a mix of
Apple-the-tech-company, Apple-the-fruit, and one deliberate trap doc that
contains both keywords by coincidence.

A bi-encoder embeds the query and each document *independently*, then
compares vectors -- it never sees query and document together. That's what
makes it fast enough to search a whole corpus (embed once, compare with
cheap cosine similarity), but it also means it can only compare
bag-of-meaning summaries, not reason about how specific words interact.

A cross-encoder feeds the (query, document) pair through the model
*together*, so attention can run between every query token and every
document token. That's why it can tell "computer" doesn't relate to
"snack" in the trap doc even though "computer" and "apple" both appear
literally -- but it has to run a full forward pass per document, so it
doesn't scale to searching a whole corpus by itself. In production this is
why it's a second-stage *reranker*: bi-encoder retrieves a candidate set
fast, cross-encoder reorders that small set precisely.

Uses local sentence-transformers models (~90MB total, first run downloads
them): `all-MiniLM-L6-v2` (bi-encoder) and
`cross-encoder/ms-marco-MiniLM-L-6-v2` (cross-encoder). This is the one
script in rag-demo/ that isn't Gemini-API-only -- cross-encoders don't have
a hosted Gemini equivalent.

Run:
    pip install sentence-transformers
    python 03_biencoder_vs_crossencoder.py
"""

from rich.console import Console
from rich.table import Table
from sentence_transformers import CrossEncoder, SentenceTransformer
from sentence_transformers.util import cos_sim

console = Console()

QUERY = "apple computer"

DOCS = [
    {
        "text": "The new MacBook Pro is a powerful Apple computer built for creative professionals.",
        "relevant": True,
    },
    {
        "text": "An apple a day keeps the doctor away, especially a crisp Granny Smith.",
        "relevant": False,
    },
    {
        "text": "Apple Inc. unveiled new hardware at its product keynote this week.",
        "relevant": True,
    },
    {
        "text": "I sliced a fresh apple and mixed it into my morning oatmeal.",
        "relevant": False,
    },
    {
        "text": (
            "Computers are complex machines; some engineers keep a bowl of "
            "apples at their desk for a snack."
        ),
        "relevant": False,
    },
    {
        "text": (
            "Apple's stock rallied this week after the company unveiled a new "
            "lineup of high-performance computers for professional users."
        ),
        "relevant": True,
    },
]


def label(text: str, relevant: bool) -> str:
    color = "green" if relevant else "red"
    return f"[{color}]{text}[/{color}]"


def precision_at_k(ranked: list[dict], k: int) -> float:
    return sum(1 for d in ranked[:k] if d["relevant"]) / k


if __name__ == "__main__":
    console.rule("[bold]Query[/bold]")
    console.print(f'"{QUERY}"\n')
    console.print(
        "One doc below is a trap: it contains both 'computer' and 'apple' "
        "but is about neither Apple-the-company nor a computer -- it's "
        "engineers snacking on fruit near their computers.\n"
    )

    console.rule("[bold]Loading models (first run downloads ~90MB each)[/bold]")
    bi_encoder = SentenceTransformer("all-MiniLM-L6-v2")
    cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    query_vec = bi_encoder.encode(QUERY)
    doc_vecs = bi_encoder.encode([d["text"] for d in DOCS])
    bi_scores = cos_sim(query_vec, doc_vecs)[0].tolist()

    ce_scores = cross_encoder.predict([(QUERY, d["text"]) for d in DOCS]).tolist()

    bi_ranked = sorted(
        ({**d, "score": s} for d, s in zip(DOCS, bi_scores)),
        key=lambda d: -d["score"],
    )
    ce_ranked = sorted(
        ({**d, "score": s} for d, s in zip(DOCS, ce_scores)),
        key=lambda d: -d["score"],
    )

    table = Table(title="Bi-encoder vs. cross-encoder ranking", expand=True)
    table.add_column("rank", width=4, no_wrap=True)
    table.add_column("Bi-encoder (cosine similarity)", ratio=1)
    table.add_column("Cross-encoder (relevance score)", ratio=1)
    for i in range(len(DOCS)):
        bi_d, ce_d = bi_ranked[i], ce_ranked[i]
        table.add_row(
            str(i + 1),
            f"{label(bi_d['text'], bi_d['relevant'])}\n[dim]score: {bi_d['score']:.4f}[/dim]",
            f"{label(ce_d['text'], ce_d['relevant'])}\n[dim]score: {ce_d['score']:.4f}[/dim]",
        )
    console.print(table)

    k = 3
    bi_p = precision_at_k(bi_ranked, k)
    ce_p = precision_at_k(ce_ranked, k)

    console.rule("[bold]Precision@3[/bold]")
    console.print(f"Bi-encoder:    {bi_p:.0%} of the top {k} are actually relevant")
    console.print(f"Cross-encoder: {ce_p:.0%} of the top {k} are actually relevant\n")

    trap = next(d for d in DOCS if not d["relevant"] and "snack" in d["text"])
    bi_trap_rank = next(i for i, d in enumerate(bi_ranked, 1) if d["text"] == trap["text"])
    ce_trap_rank = next(i for i, d in enumerate(ce_ranked, 1) if d["text"] == trap["text"])

    console.rule("[bold]Takeaway[/bold]")
    console.print(
        f"The trap doc (irrelevant, contains both keywords by coincidence) "
        f"ranks #{bi_trap_rank} under the bi-encoder -- ahead of genuinely "
        f"relevant docs -- because embedding the query and document "
        f"separately just measures overall vector closeness, and shared "
        f"keywords pull vectors together regardless of how those words "
        f"relate to each other. The cross-encoder, which attends across "
        f"query and document tokens jointly, ranks the same trap doc "
        f"#{ce_trap_rank} and gives it a negative score -- it can tell "
        f"'computer' in the query doesn't relate to 'snack' in the "
        f"document, which a bi-encoder's independent embeddings can't see."
    )
