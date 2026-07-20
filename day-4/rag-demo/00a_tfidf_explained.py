"""TF-IDF, worked by hand -- every intermediate number printed, nothing
hidden inside a library call. Same corpus and query as
00b_cosine_similarity_explained.py, so the two can be run back to back and
compared directly: this script ranks by sparse keyword weights, the other
ranks by dense semantic vectors.

The four steps, in order:
  1. Tokenize every doc + the query (lowercase, split on non-letters).
  2. TF (term frequency): how often a term shows up in a doc, normalized by
     that doc's length so long docs don't win just by being long.
  3. IDF (inverse document frequency): how rare a term is *across the whole
     corpus* -- log(N / how many docs contain it). A term in every doc gets
     IDF 0 and can never contribute to a score, no matter how often it
     repeats. This corpus deliberately doesn't filter stopwords, so "the"
     (in all 5 docs) demonstrates that IDF does the suppressing on its own
     -- no hand-picked stopword list required.
  4. TF-IDF = TF x IDF, and a doc's score for a query is just the sum of
     TF-IDF over the query's own terms.

Part 2 runs the exact same pipeline on a different 5-doc corpus, built to
show a complete miss: two documents are genuinely about a dog in a park
but use zero words in common with the query ("canine", "green space",
"meadow" instead of "dog"/"park"), one document is completely irrelevant
but happens to literally contain the word "park", and two are unrelated
cat documents. TF-IDF only ever matches literal tokens, so it can't just
under-rank the relevant paraphrased docs -- it ties them with the
irrelevant ones at a score of exactly 0, while the coincidentally-worded
irrelevant doc wins outright.

Run:
    python 00a_tfidf_explained.py
"""

import math
import re
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

console = Console()

DOCS = {
    "doc1": "The cat sat on the mat.",
    "doc2": "The dog played in the park.",
    "doc3": "The cat played with a toy.",
    "doc4": "The dog loves the park.",
    "doc5": "The park was quiet today.",
}
FAILURE_DOCS = {
    "doc1": "The canine enjoys playing in the green space.",  # relevant: a dog, in a park -- zero literal overlap with "dog"/"park"
    "doc2": "The puppy loves the meadow near downtown.",       # relevant: a dog, in a park-like space -- zero literal overlap
    "doc3": "The park bench was recently repainted.",          # irrelevant to dogs, but literally contains "park"
    "doc4": "The kitten sat on the mat.",                      # irrelevant -- a cat
    "doc5": "The kitten played with a toy.",                   # irrelevant -- a cat
}
QUERY = "dog park"

_TOKEN_RE = re.compile(r"[a-z]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Doc:
    id: str
    text: str
    tokens: list[str]


def term_frequency(term: str, tokens: list[str]) -> float:
    return tokens.count(term) / len(tokens)


def inverse_document_frequency(term: str, docs: list[Doc], n: int) -> float:
    df = sum(1 for d in docs if term in d.tokens)
    return math.log(n / df) if df else 0.0


def run_tfidf(docs_dict: dict[str, str], query: str) -> list[tuple[Doc, float]]:
    docs = [Doc(doc_id, text, tokenize(text)) for doc_id, text in docs_dict.items()]
    query_terms = tokenize(query)
    n = len(docs)

    console.rule("[bold]Step 1: tokenize[/bold]")
    console.print(f'Query: "{query}" -> {query_terms}\n')
    tok_table = Table()
    tok_table.add_column("doc")
    tok_table.add_column("text")
    tok_table.add_column("tokens", overflow="fold")
    for d in docs:
        tok_table.add_row(d.id, d.text, str(d.tokens))
    console.print(tok_table)

    vocabulary = sorted({t for d in docs for t in d.tokens})
    console.print(f"\nVocabulary ({len(vocabulary)} unique terms): {vocabulary}\n")

    console.rule("[bold]Step 2: term frequency -- TF(t, d) = count(t, d) / len(d)[/bold]")
    tf_table = Table(title="TF (only terms that appear at least once anywhere)")
    tf_table.add_column("term")
    for d in docs:
        tf_table.add_column(d.id, justify="right")
    tf = {}
    for term in vocabulary:
        row = []
        for d in docs:
            val = term_frequency(term, d.tokens)
            tf[(term, d.id)] = val
            row.append(f"{val:.3f}" if val else "-")
        tf_table.add_row(term, *row)
    console.print(tf_table)

    console.rule("[bold]Step 3: inverse document frequency -- IDF(t) = log(N / df(t))[/bold]")
    console.print(f"N = {n} documents in the corpus\n")
    idf_table = Table(title="IDF, sorted low -> high (low = appears in nearly every doc, contributes little)")
    idf_table.add_column("term")
    idf_table.add_column("df(t)", justify="right")
    idf_table.add_column("idf(t) = log(N/df)", justify="right")
    idf = {term: inverse_document_frequency(term, docs, n) for term in vocabulary}
    for term, val in sorted(idf.items(), key=lambda kv: kv[1]):
        df = sum(1 for d in docs if term in d.tokens)
        note = "  <- in every doc, can never score" if df == n else ""
        idf_table.add_row(term, str(df), f"{val:.4f}{note}")
    console.print(idf_table)

    console.rule("[bold]Step 4: TF-IDF = TF x IDF, scored against the query[/bold]")
    console.print(
        f"score(d, q) = sum over query terms t of TF-IDF(t, d)  -- query terms: {query_terms}\n"
    )
    score_table = Table(title=f'Score breakdown for query "{query}"', show_lines=True)
    score_table.add_column("doc")
    score_table.add_column("text")
    for t in query_terms:
        score_table.add_column(f"tfidf({t})", justify="right")
    score_table.add_column("score", justify="right")

    scores = []
    for d in docs:
        contributions = []
        total = 0.0
        for t in query_terms:
            tfidf = tf.get((t, d.id), 0.0) * idf.get(t, 0.0)
            total += tfidf
            contributions.append(f"{tfidf:.4f}" if tfidf else "0 (term absent)")
        scores.append((d, total))
        score_table.add_row(d.id, d.text, *contributions, f"[bold]{total:.4f}[/bold]")
    console.print(score_table)

    console.rule("[bold]Ranking[/bold]")
    scores.sort(key=lambda t: t[1], reverse=True)
    rank_table = Table()
    rank_table.add_column("#", width=3, justify="right")
    rank_table.add_column("doc")
    rank_table.add_column("text")
    rank_table.add_column("score", justify="right")
    for i, (d, s) in enumerate(scores, 1):
        rank_table.add_row(str(i), d.id, d.text, f"{s:.4f}")
    console.print(rank_table)
    return scores


if __name__ == "__main__":
    console.rule("[bold blue]PART 1 -- how TF-IDF works[/bold blue]")
    run_tfidf(DOCS, QUERY)

    console.rule("[bold]Why this ranking[/bold]")
    console.print(
        "doc2 and doc4 rank highest because they're the only two docs "
        "containing BOTH query terms ('dog' and 'park') -- everything else "
        "gets at most partial credit. doc5 has 'park' but not 'dog', so it "
        "scores lower but not zero. doc1 and doc3 contain neither term, so "
        "they score exactly 0, tied last, regardless of anything else in "
        "their text.\n\n"
        "Notice 'the' appears in every single document (more than any other "
        "word) but contributed nothing to any score -- its IDF is "
        "log(5/5) = log(1) = 0. That's TF-IDF's whole mechanism for "
        "ignoring uninformative words: not a stopword list, just the math "
        "naturally zeroing out anything too common to discriminate between "
        "documents.\n"
    )

    console.rule("[bold red]PART 2 -- where TF-IDF completely misses[/bold red]")
    console.print(
        "A different 5-doc corpus:\n"
        f'  doc1 (relevant, paraphrased): "{FAILURE_DOCS["doc1"]}"\n'
        f'  doc2 (relevant, paraphrased): "{FAILURE_DOCS["doc2"]}"\n'
        f'  doc3 (irrelevant, coincidental match): "{FAILURE_DOCS["doc3"]}"\n'
        f'  doc4 (irrelevant): "{FAILURE_DOCS["doc4"]}"\n'
        f'  doc5 (irrelevant): "{FAILURE_DOCS["doc5"]}"\n'
    )
    failure_scores = run_tfidf(FAILURE_DOCS, QUERY)

    top_doc, top_score = failure_scores[0]
    doc1_score = next(s for d, s in failure_scores if d.id == "doc1")
    doc2_score = next(s for d, s in failure_scores if d.id == "doc2")
    doc4_score = next(s for d, s in failure_scores if d.id == "doc4")

    console.rule("[bold]Why this fails[/bold]")
    console.print(
        f"\"{top_doc.text}\" ({top_doc.id}) wins outright with a score of "
        f"{top_score:.4f} -- and it has nothing to do with dogs. It only "
        "wins because it happens to contain the literal word 'park'.\n\n"
        f"Meanwhile doc1 ({doc1_score:.4f}) and doc2 ({doc2_score:.4f}) -- "
        "the two documents that are actually about a dog in a park, just "
        "worded with synonyms -- score *exactly* 0.0000, tied precisely "
        f"with doc4 ({doc4_score:.4f}), a document about a kitten that has "
        "nothing to do with the query at all. TF-IDF has no way to express "
        "'probably relevant, worded differently' -- a term either appears "
        "verbatim or it contributes nothing, so genuinely relevant "
        "documents with no literal keyword overlap are completely "
        "indistinguishable from irrelevant ones, while an irrelevant "
        "document with one lucky keyword match outranks both of them. "
        "This is exactly the gap 00b_cosine_similarity_explained.py's "
        "embeddings close -- run it and compare where doc1/doc2 land there."
    )
