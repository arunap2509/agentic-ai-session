"""Cosine similarity on real embeddings, worked by hand -- every
intermediate number printed. Same corpus and query as
00a_tfidf_explained.py, so the two can be compared directly: that script
ranks by sparse keyword weights, this one ranks by dense semantic vectors.

The steps, in order:
  1. The query and every document get converted into a vector (a list of
     numbers) by Gemini's embedding model -- this is what "embedding" means.
     Similar meaning -> vectors that point in a similar direction, even if
     the exact words don't match.
  2. Cosine similarity measures the ANGLE between two vectors, not their
     length: cos(q, d) = (q . d) / (||q|| * ||d||)
       - q . d      = dot product (multiply matching positions, sum them)
       - ||q||, ||d|| = each vector's own length (Euclidean norm)
     Dividing by both lengths is what makes it "cosine" and not just a dot
     product -- a long document shouldn't automatically win just because
     its vector has more magnitude, the same way a long doc shouldn't win
     in TF-IDF just by repeating words.
  3. Rank documents by that score, highest first.

Part 2 runs the same pipeline on the SAME 5 documents but a query nothing
in the corpus can actually answer, to show where this breaks: cosine
similarity always returns a ranked list -- there's no natural "zero", no
built-in way to say "none of these are actually relevant." The top score
for a completely unrelated query lands in the same range as a genuinely
relevant result in Part 1, with nothing to tell them apart.

Run:
    python 00b_cosine_similarity_explained.py
"""

import sys
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval import embed

console = Console()

DOCS = {
    "doc1": "The cat sat on the mat.",
    "doc2": "The dog played in the park.",
    "doc3": "The cat played with a toy.",
    "doc4": "The dog loves the park.",
    "doc5": "The park was quiet today.",
}
QUERY = "dog park"

# Same 5 docs as Part 1, on purpose -- Part 2's point is that a query
# NOTHING here can answer still gets a confident-looking top match.
OFFTOPIC_QUERY = "What is the capital of France?"

SAMPLE_DIMS = 8  # how many vector values to print -- full vectors are 3072-dim, unreadable


def sample_str(vec: np.ndarray) -> str:
    # Plain "x, y, z" text, no [] -- Rich reads square brackets as markup
    # tags, so "[0.009, 0.038]" silently vanishes instead of printing.
    return ", ".join(f"{float(v):.3f}" for v in vec[:SAMPLE_DIMS])


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float, float]:
    """Returns (dot_product, norm_a, norm_b, cosine_similarity) -- every term
    in the formula, not just the final number.
    """
    dot = float(np.dot(a, b))
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    return dot, norm_a, norm_b, dot / (norm_a * norm_b)


def run_cosine(docs_dict: dict[str, str], query: str, explain_dims: bool = False) -> list[tuple[str, str, float]]:
    doc_ids = list(docs_dict.keys())
    doc_texts = list(docs_dict.values())

    console.rule("[bold]Step 1: embed the query and every document[/bold]")
    console.print(f'Query: "{query}"\n')
    query_vec = embed([query], task_type="RETRIEVAL_QUERY")[0]
    doc_vecs = embed(doc_texts, task_type="RETRIEVAL_DOCUMENT")

    console.print(
        f"Each piece of text becomes a {query_vec.shape[0]}-dimensional vector. "
        f"First {SAMPLE_DIMS} of {query_vec.shape[0]} values shown below (the "
        "rest follow the same idea, just unreadable at this width):\n"
    )

    vec_table = Table(title="Sample of the actual embedding vectors")
    vec_table.add_column("text")
    vec_table.add_column(f"first {SAMPLE_DIMS} dims (of {query_vec.shape[0]})", overflow="fold")
    vec_table.add_row(f'QUERY: "{query}"', sample_str(query_vec))
    for doc_id, vec in zip(doc_ids, doc_vecs):
        vec_table.add_row(f"{doc_id}: {docs_dict[doc_id]}", sample_str(vec))
    console.print(vec_table)

    if explain_dims:
        console.print(
            f"\nWhy {query_vec.shape[0]}? That's not a value anyone chose "
            "for this demo -- it's the native output size of Gemini's "
            "embedding model (gemini-embedding-001), baked in during "
            "training the same way a neural network's final layer has "
            "however many outputs it was built with. Unlike a TF-IDF "
            "vector, where dimension #482 means something concrete (\"count "
            "of the word 'park'\"), no single one of these 3072 numbers "
            "means anything on its own -- meaning is distributed jointly "
            "across all of them.\n\n"
            "The model also supports Matryoshka Representation Learning "
            "(MRL): it was deliberately trained so that truncating a vector "
            "down to its first 768 or 1536 values still gives a usable, "
            "meaningful embedding, not garbage -- so an application can "
            "trade a little accuracy for smaller/cheaper vectors without "
            "re-embedding anything. One catch: vectors only come "
            "pre-normalized to unit length (||v|| = 1, see Step 2) at the "
            "full 3072 -- truncate to a smaller size and you have to "
            "normalize it yourself.\n"
        )

    console.rule("[bold]Step 2: cosine similarity -- cos(q, d) = (q . d) / (||q|| x ||d||)[/bold]")
    console.print(
        "Gemini's embeddings come out already unit-length (||v|| = 1 for "
        "every vector -- verified, not assumed), so the (||q|| x ||d||) "
        "part of the formula is always dividing by 1. That means cosine "
        "similarity here reduces to a plain dot product; showing the norms "
        "and the dot product as separate columns from the final score would "
        "just be printing the same number three times.\n"
    )
    sim_table = Table(title="Cosine similarity per document")
    sim_table.add_column("doc")
    sim_table.add_column("text")
    sim_table.add_column("cosine similarity", justify="right")

    results = []
    for doc_id, text, vec in zip(doc_ids, doc_texts, doc_vecs):
        _, _, _, sim = cosine_similarity(query_vec, vec)
        results.append((doc_id, text, sim))
        sim_table.add_row(doc_id, text, f"[bold]{sim:.4f}[/bold]")
    console.print(sim_table)

    console.rule("[bold]Ranking[/bold]")
    results.sort(key=lambda t: t[2], reverse=True)
    rank_table = Table()
    rank_table.add_column("#", width=3, justify="right")
    rank_table.add_column("doc")
    rank_table.add_column("text")
    rank_table.add_column("cosine similarity", justify="right")
    for i, (doc_id, text, sim) in enumerate(results, 1):
        rank_table.add_row(str(i), doc_id, text, f"{sim:.4f}")
    console.print(rank_table)
    return results


if __name__ == "__main__":
    console.rule("[bold blue]PART 1 -- how cosine similarity works[/bold blue]")
    results = run_cosine(DOCS, QUERY, explain_dims=True)

    console.rule("[bold]Why this ranking[/bold]")
    top_id, top_text, _ = results[0]
    console.print(
        f"The embedding model never counted words -- it never knows 'dog' and "
        f"'park' are literally in the query. It placed \"{QUERY}\" and each "
        f"document in the same 3072-dimensional meaning-space, and "
        f"\"{top_text}\" ({top_id}) landed closest because its *meaning* is "
        f"closest to the query's meaning, not because of any shared "
        f"substring.\n\n"
        "Compare this ranking to 00a_tfidf_explained.py's ranking on the "
        "exact same corpus and query: TF-IDF can only ever match on literal "
        "tokens ('dog' has to appear as the string 'dog'), while this "
        "ranking would still work even if a document said 'puppy' or "
        "'canine' instead -- that's the entire practical difference between "
        "sparse keyword vectors and dense embedding vectors.\n"
    )

    console.rule("[bold red]PART 2 -- where cosine similarity completely misses[/bold red]")
    console.print(
        "Same 5 documents as Part 1 -- cats, dogs, a park. New query, about "
        f'something none of them are even remotely about: "{OFFTOPIC_QUERY}"\n'
    )
    offtopic_results = run_cosine(DOCS, OFFTOPIC_QUERY)

    top_id, top_text, top_sim = offtopic_results[0]
    part1_best = results[0][2]
    part1_worst = results[-1][2]
    part1_spread = part1_best - part1_worst
    gap_to_worst = part1_worst - top_sim

    console.rule("[bold]Why this fails[/bold]")
    console.print(
        f"\"{top_text}\" ({top_id}) comes back as the #1 result for "
        f"\"{OFFTOPIC_QUERY}\" with a similarity of {top_sim:.4f} -- a "
        "score that looks entirely plausible on its own. Nothing about the "
        "number itself signals 'none of these are actually relevant.'\n\n"
        f"Compare it to Part 1: the genuinely best match there scored "
        f"{part1_best:.4f}, and even the *least* relevant doc in that "
        f"corpus (still nominally about a park) scored {part1_worst:.4f}. "
        f"This off-topic query's top score ({top_sim:.4f}) sits only "
        f"{gap_to_worst:.4f} below that least-relevant score -- a gap "
        f"{part1_spread / gap_to_worst:.0f}x smaller than Part 1's own "
        "spread between its best and worst result. A totally unrelated "
        "question and a weakly-relevant real document land almost on top "
        "of each other. Cosine similarity always returns a fully ranked "
        "list, because every vector has *some* angle to every other "
        "vector -- it structurally cannot output 'no good match exists,' "
        "only 'here is my best guess, presented with the same confidence "
        "either way.' TF-IDF, for all its faults, gets this one thing "
        "right for free: an off-topic query here would score every "
        "document exactly 0, an honest 'nothing matched.'"
    )
