"""Shared retrieval primitives for both RAG demos: corpus loading, Gemini
embeddings, cosine similarity, a hand-rolled BM25, and Reciprocal Rank
Fusion. No vector DB, no Docker -- the corpus is 8 markdown files and every
index here is just an in-memory Python object, consistent with the rest of
this course's "no extra infra to fail live" approach.
"""

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.llm import get_client

KB_DIR = Path(__file__).resolve().parent / "knowledge_base"
EMBED_MODEL = "gemini-embedding-001"


@dataclass
class Doc:
    id: str
    text: str
    metadata: dict[str, str]
    embedding: np.ndarray | None = None


def load_corpus() -> list[Doc]:
    docs = []
    for path in sorted(KB_DIR.glob("*.md")):
        metadata, body = _parse_frontmatter(path.read_text())
        docs.append(Doc(id=path.stem, text=body.strip(), metadata=metadata))
    return docs


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        return {}, raw
    _, frontmatter, body = raw.split("---", 2)
    metadata = {}
    for line in frontmatter.strip().splitlines():
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()
    return metadata, body


# --- Embeddings --------------------------------------------------------

def embed(texts: list[str], task_type: str) -> np.ndarray:
    """task_type is RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY. Gemini's
    embedding model is trained asymmetrically for retrieval -- queries and
    documents get different projections -- so using the right one on each
    side measurably improves ranking over embedding both the same way.
    """
    client = get_client()
    response = client.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config={"task_type": task_type},
    )
    return np.array([e.values for e in response.embeddings])


def embed_documents(docs: list[Doc]) -> None:
    vectors = embed([d.text for d in docs], task_type="RETRIEVAL_DOCUMENT")
    for doc, vec in zip(docs, vectors):
        doc.embedding = vec


def embed_query(query: str) -> np.ndarray:
    return embed([query], task_type="RETRIEVAL_QUERY")[0]


def cosine_rank(query_vec: np.ndarray, docs: list[Doc]) -> list[tuple[Doc, float]]:
    scored = []
    for doc in docs:
        sim = float(
            np.dot(query_vec, doc.embedding)
            / (np.linalg.norm(query_vec) * np.linalg.norm(doc.embedding))
        )
        scored.append((doc, sim))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


# --- BM25 (hand-rolled -- no extra dependency for one well-known formula) --

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "to", "for", "of", "in", "on", "and", "or",
    "this", "that", "it", "its", "be", "by", "with", "from", "at", "as", "if",
    "not", "we", "our", "us", "them", "just", "re", "first", "keep", "sure",
    "without", "them", "any", "so", "than", "then", "into", "out", "over",
    "up", "will", "was", "were", "been", "has", "have", "had", "do", "does",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class BM25:
    """Okapi BM25 with the usual defaults (k1=1.5, b=0.75)."""

    def __init__(self, docs: list[Doc], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.doc_tokens = [_tokenize(d.text) for d in docs]
        self.doc_len = [len(toks) for toks in self.doc_tokens]
        self.avg_len = sum(self.doc_len) / len(self.doc_len)

        doc_freq: dict[str, int] = {}
        for toks in self.doc_tokens:
            for term in set(toks):
                doc_freq[term] = doc_freq.get(term, 0) + 1
        n = len(docs)
        self.idf = {
            term: math.log((n - freq + 0.5) / (freq + 0.5) + 1)
            for term, freq in doc_freq.items()
        }

    def rank(self, query: str) -> list[tuple[Doc, float]]:
        query_terms = _tokenize(query)
        scored = []
        for doc, toks, dl in zip(self.docs, self.doc_tokens, self.doc_len):
            term_freq: dict[str, int] = {}
            for term in toks:
                term_freq[term] = term_freq.get(term, 0) + 1
            score = 0.0
            for term in query_terms:
                freq = term_freq.get(term)
                if not freq:
                    continue
                idf = self.idf.get(term, 0.0)
                denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avg_len)
                score += idf * (freq * (self.k1 + 1)) / denom
            scored.append((doc, score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored


def reciprocal_rank_fusion(
    rankings: list[list[Doc]], k: int = 60
) -> list[tuple[Doc, float]]:
    """Merge ranked lists by rank position, not raw score -- BM25 scores and
    cosine similarities live on incomparable scales, so RRF deliberately
    throws the scores away and only uses each list's ordering:
    score(d) = sum over rankers of 1 / (k + rank_in_that_ranker).
    """
    scores: dict[str, float] = {}
    doc_by_id: dict[str, Doc] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            doc_by_id[doc.id] = doc
            scores[doc.id] = scores.get(doc.id, 0.0) + 1.0 / (k + rank)
    merged = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(doc_by_id[doc_id], score) for doc_id, score in merged]
