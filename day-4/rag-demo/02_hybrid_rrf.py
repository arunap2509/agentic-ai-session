"""Keyword search (BM25) vs. semantic search (embeddings) vs. the two
merged with Reciprocal Rank Fusion, on the same 8-doc corpus as
01_naive_vs_metadata.py.

Two queries, chosen to each favor a different retriever:

  Query A names an exact config key (`SESSION_TTL_SECONDS`) that appears
  verbatim in exactly one doc -- BM25's home turf, exact-token overlap.

  Query B paraphrases the identifying details ("billing service" for
  payment-service, "bounce" for restart) but still shares generic ops
  vocabulary with every OOM runbook ("pods", "memory", "service") -- that
  vocabulary is too generic to discriminate between the 5 candidate docs,
  so BM25 ranks them within a tight band and which one lands on top comes
  down to length-normalization noise, not relevance. It happens to rank
  the wrong service first. Semantic search reads through the paraphrase
  and separates the 5 candidates on meaning instead.

RRF doesn't know in advance which kind of query it's getting. The point of
this demo is that it doesn't have to: merging by rank position lets
whichever retriever is confident this time pull the right doc up, without
having to pick BM25 or embeddings ahead of time.

Run:
    python 02_hybrid_rrf.py
"""

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval import BM25, Doc, cosine_rank, embed_documents, embed_query, load_corpus, reciprocal_rank_fusion

console = Console()

QUERIES = [
    {
        "label": "Query A -- exact config key",
        "text": (
            "What's the exact fix for the checkout-service OOM issue -- I see "
            "SESSION_TTL_SECONDS in the config, what should I set it to?"
        ),
        "highlight": "checkout-service-oom",
    },
    {
        "label": "Query B -- identifying terms paraphrased away",
        "text": (
            "Our billing service pods keep dying from running out of memory, "
            "and we're not sure if we're allowed to just bounce them without "
            "checking with anyone first."
        ),
        "highlight": "payment-service-oom",
    },
]

TOP_N = 5


def rank_position(doc_id: str, ranking: list[Doc]) -> int:
    for i, doc in enumerate(ranking, 1):
        if doc.id == doc_id:
            return i
    return len(ranking)


def print_comparison(
    bm25_ranked: list[tuple[Doc, float]],
    sem_ranked: list[tuple[Doc, float]],
    rrf_ranked: list[tuple[Doc, float]],
    highlight: str,
) -> None:
    table = Table(title=f"Top {TOP_N} by retriever (score shown under each doc)", expand=True, show_lines=True)
    table.add_column("#", width=3, justify="right", no_wrap=True)
    table.add_column("BM25 (keyword)", overflow="fold", ratio=1)
    table.add_column("Semantic (embeddings)", overflow="fold", ratio=1)
    table.add_column("RRF (merged)", overflow="fold", ratio=1)

    def cell(doc: Doc, score: float, precision: int) -> str:
        line = f"{doc.id}\n[dim]score: {score:.{precision}f}[/dim]"
        return f"[bold yellow]{line}[/bold yellow]" if doc.id == highlight else line

    for i in range(TOP_N):
        bm25_doc, bm25_score = bm25_ranked[i]
        sem_doc, sem_score = sem_ranked[i]
        rrf_doc, rrf_score = rrf_ranked[i]
        table.add_row(
            str(i + 1),
            cell(bm25_doc, bm25_score, 3),
            cell(sem_doc, sem_score, 4),
            cell(rrf_doc, rrf_score, 5),
        )
    console.print(table)


if __name__ == "__main__":
    console.rule("[bold]Loading corpus + building indexes[/bold]")
    docs = load_corpus()
    embed_documents(docs)
    bm25 = BM25(docs)
    console.print(f"{len(docs)} docs indexed for both BM25 and semantic search.\n")

    for q in QUERIES:
        console.rule(f"[bold]{q['label']}[/bold]")
        console.print(q["text"] + "\n")

        bm25_scored = bm25.rank(q["text"])
        sem_scored = cosine_rank(embed_query(q["text"]), docs)
        bm25_ranking = [doc for doc, _ in bm25_scored]
        sem_ranking = [doc for doc, _ in sem_scored]
        rrf_ranked = reciprocal_rank_fusion([bm25_ranking, sem_ranking])

        print_comparison(bm25_scored, sem_scored, rrf_ranked, q["highlight"])

        bm25_pos = rank_position(q["highlight"], bm25_ranking)
        sem_pos = rank_position(q["highlight"], sem_ranking)
        rrf_pos = rank_position(q["highlight"], [d for d, _ in rrf_ranked])

        console.print(
            f"\n[bold]{q['highlight']}[/bold] ranked #{bm25_pos} in BM25, "
            f"#{sem_pos} in semantic, #{rrf_pos} in the RRF merge.\n"
        )

    console.rule("[bold]Takeaway[/bold]")
    console.print(
        "Query A: BM25 and semantic already agree (#1 in both) because the "
        "exact config key is both a strong keyword match and semantically "
        "central to the doc -- RRF just confirms it.\n\n"
        "Query B: BM25 ranks the correct doc second, behind a wrong service's "
        "runbook -- not because there's no lexical overlap, but because the "
        "only overlap is generic ops vocabulary ('pods', 'memory', 'service') "
        "that all 5 OOM runbooks share almost identically. That's too "
        "generic to discriminate between them, so BM25 scores all 5 within "
        "a tight band (1.41-1.69) and which one lands on top is mostly "
        "length-normalization noise, not relevance. Semantic search "
        "separates them on meaning instead -- it reads 'billing service' "
        "and 'dying from running out of memory' as payment-service + "
        "OOMKilled specifically, not just 'some service, some memory "
        "issue'. RRF, which only sees rank positions and never knows which "
        "retriever is right in advance, still lands the correct doc at the "
        "top -- because it only needed one of the two signals to be "
        "confident."
    )
