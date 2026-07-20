# RAG Demo — Retrieval Quality

Two fundamentals scripts, then four comparison scripts. The fundamentals
(`00a`, `00b`) show the actual math behind keyword search and semantic
search on a tiny, hand-verifiable example — worth running first if the
audience needs that refresher before the comparisons mean anything. The
four comparisons (`01`-`04`) share one knowledge base; each makes the same
point from a different angle: "search and grab the top matches" quietly
throws away information a real RAG system needs to get right.

`incident-commander/tools/runbook_retrieval.py` already does retrieval —
keyword overlap over 5 static runbooks, no reasoning loop. This demo is
that same idea taken one step further (real embeddings, a real BM25, a
real merge algorithm) over a knowledge base that extends
incident-commander's own service universe
(`payment-service`, `checkout-service`, `auth-service`, `inventory-service`,
`shipping-service`).

## Setup

From `day-4/` (one level up):
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste in your GEMINI_API_KEY
```

## How to run

```
cd rag-demo
python 00a_tfidf_explained.py
python 00b_cosine_similarity_explained.py
python 01_naive_vs_metadata.py
python 02_hybrid_rrf.py
python 04_hyde.py
```

No vector DB, no Docker for those three. `retrieval.py` loads the 8
markdown files in `knowledge_base/` into an in-memory Python list, calls
Gemini's embedding endpoint, and does cosine similarity with plain
`numpy` — the same "no extra infra to fail live" approach as the rest of
this course.

`03_biencoder_vs_crossencoder.py` is the one exception — cross-encoders
don't have a hosted Gemini equivalent, so it needs a local model:
```
pip install -r requirements-crossencoder.txt   # adds sentence-transformers + torch, ~90MB model download on first run
python 03_biencoder_vs_crossencoder.py
```

## `00a_tfidf_explained.py` / `00b_cosine_similarity_explained.py` — the fundamentals

Both scripts run two parts: Part 1 shows how the technique works, Part 2
shows where it completely breaks. Both use the same 5-doc corpus and the
same query (`"dog park"`) for Part 1 — five one-line sentences about
cats, dogs, and a park, deliberately simple enough to check the numbers
by hand. Every failure case below is a real, measured result, not a
staged one — several other failure hypotheses (exact numeric IDs,
negation, coincidental keyword traps, numeric-threshold reasoning) were
tried first and this strong an embedding model held up fine on all of
them; the two failures kept here are the ones that actually reproduce.

**`00a` Part 1 (TF-IDF)** ranks purely on literal token overlap: a doc has
to contain the exact string "dog" to get credit for "dog." It prints
tokens, the full TF table, and the full IDF table sorted low-to-high,
which surfaces something worth calling out live: "the" appears in every
single document (more than any other word) but contributes exactly `0` to
every score, because `idf(the) = log(N/df) = log(5/5) = 0`. No stopword
list was used — the math alone suppresses it, which is the actual point
of IDF.

**`00a` Part 2** — a different 5-doc corpus: two documents are genuinely
about a dog in a park but share *zero* literal tokens with the query
("canine ... green space", "puppy ... meadow" instead of "dog"/"park"),
one document is about a park bench and has nothing to do with dogs but
happens to contain the literal word "park", and two are unrelated cat
documents. Result: the irrelevant park-bench doc wins outright, while
both genuinely relevant documents score *exactly* `0.0000` — tied
precisely with the irrelevant cat documents. TF-IDF can't express
"probably relevant, worded differently"; a term either appears verbatim
or contributes nothing at all.

**`00b` Part 1 (cosine similarity)** embeds the same query and documents
with Gemini and ranks by meaning instead of literal tokens — it would
still work if a document said "puppy" instead of "dog." It also explains
why the vectors are 3072-dimensional (the native output size of
`gemini-embedding-001`, trained with Matryoshka Representation Learning
so it can also be truncated to 768/1536 if you need smaller vectors) and
why the table only prints the final cosine similarity rather than the
dot product and both norms separately — Gemini's embeddings are verified
unit-length, so `||q|| x ||d|| = 1` and cosine similarity *is* the dot
product here; printing all three would just be the same number three
times. Part 1 lands on the same top-2 ranking as `00a`'s Part 1, worth
pointing out: they agree here because the literal words *and* the
meaning point the same way; `02_hybrid_rrf.py` is where you see them
disagree.

**`00b` Part 2** reuses the exact same 5 docs from Part 1, but asks a
question none of them can answer at all ("What is the capital of
France?"). The top "match" still comes back with a similarity score
(`0.5678`) that sits only `0.0163` below Part 1's *least*-relevant
result (`0.5841`) — a totally unrelated question and a weakly-relevant
real document land almost on top of each other, a gap roughly 9x smaller
than Part 1's own best-to-worst spread. Cosine similarity always returns
a fully ranked list — every vector has *some* angle to every other
vector — so it structurally cannot say "no good match exists," only
"here's my best guess," with the same apparent confidence either way.
TF-IDF, for all its faults, gets this one for free: an off-topic query
against that corpus scores every document exactly `0`, an honest
"nothing matched."

## `01_naive_vs_metadata.py` — does metadata filtering improve retrieval?

**The knowledge base**: 5 near-identical OOMKilled runbooks (one per
service — same boilerplate structure, different root cause and fix), plus
two policy docs. One of those policies matters a lot: `payment-service`
sits in PCI scope, and a separate policy doc
(`pci-escalation-policy.md`) overrides the "restart is pre-approved,
low risk" default that applies to every other service — a plain pod
restart on `payment-service` requires Compliance sign-off first.

**The query**: an on-call engineer asks how to fix OOMKilled
`payment-service` pods and whether they need approval to restart.

**Naive RAG** (cosine search over all 8 docs, top 2 kept) correctly finds
the payment-service OOM runbook — but the compliance policy doc is worded
in audit/legal language, not kubectl commands, so it sits farther from the
operational query in embedding space than *a different service's runbook*
does. It ranks 6th out of 8 and never makes the cut. The generated answer
confidently tells the engineer no approval is needed — which is both wrong
and itself a compliance finding.

**Metadata-filtered RAG** is two steps, not a hardcoded filter:
1. An LLM call extracts a structured filter from the query — same
   `response_schema` pattern as `day-2/04-structured-output` — constrained
   to the known services in the corpus. For this query it returns
   `service="payment-service"`.
2. *Then* the corpus is filtered to that service (3 candidates instead of
   8) before ranking runs, so the policy doc can't be missed — it's one of
   the three.

Same generation step, correct answer.

This is measured with real Gemini embeddings and a real extraction call
each run, not staged: both the extracted filter and the naive run's
ranking table print live, so you can see exactly why the policy doc missed
the naive cutoff.

## `02_hybrid_rrf.py` — keyword search + semantic search, merged with RRF

Same 8-doc corpus, two queries chosen to each favor a different retriever:

- **Query A** names an exact config key (`SESSION_TTL_SECONDS`) that
  appears verbatim in exactly one doc. BM25's home turf — both BM25 and
  semantic search agree, #1 in both, RRF just confirms it.
- **Query B** paraphrases the *identifying* terms ("billing service"
  instead of payment-service, "bounce" instead of restart) but still
  shares generic ops vocabulary ("pods", "memory", "service") with every
  OOM runbook in the corpus. That vocabulary is too generic to
  discriminate between the 5 candidate docs, so BM25 scores all 5 within a
  tight band and which one comes out on top is mostly
  length-normalization noise, not relevance — it happens to rank a
  different service's runbook first. Semantic search separates the 5 on
  meaning instead and gets it in one.

RRF merges the two rankings by **rank position**, not raw score — BM25
scores and cosine similarities live on different scales, so
`score(d) = Σ 1 / (k + rank_in_that_list)` is the standard way to combine
them without needing to normalize anything. On Query B, RRF lands the
correct doc at #1 even though BM25 alone put it 2nd — it only needed one
of the two signals to be confident, and didn't need to know in advance
which one that would be.

## `03_biencoder_vs_crossencoder.py` — semantic search vs. reranking

Different corpus (a classic lexical-ambiguity case, not the runbook KB):
the query `"apple computer"` against 6 short docs — some genuinely about
Apple-the-tech-company, some about apples-the-fruit, and one deliberate
trap doc ("computers are complex machines; engineers keep a bowl of apples
at their desk for a snack") that contains both keywords by coincidence and
is about neither.

A **bi-encoder** (`all-MiniLM-L6-v2`) embeds the query and each document
*independently*, then compares vectors — fast enough to search a whole
corpus, but it only ever compares bag-of-meaning summaries. It ranks the
trap doc #2, ahead of two genuinely relevant docs, because shared keywords
pull embeddings together regardless of how those words actually relate.

A **cross-encoder** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) feeds the
(query, document) pair through the model *together*, so attention runs
between every query token and every document token — it can tell
"computer" doesn't relate to "snack" even though both keywords are
present. It ranks the trap doc #4 with a negative score, and gets a clean
100% precision@3 against the bi-encoder's 67%. The cost: one full forward
pass per document, which is why in production a cross-encoder is a
second-stage *reranker* over a bi-encoder's candidate set, not a
replacement for it.

## `04_hyde.py` — HyDE (Hypothetical Document Embeddings)

Same runbook knowledge base as 01/02. The query is deliberately vague and
colloquial: *"Money service keeps randomly dying whenever there's a big
rush of orders. No idea why, feels like it just falls over."* No service
name, no technical vocabulary — nothing that overlaps with how the
runbooks are actually written.

**Direct embedding** (embed the query, compare to document embeddings)
puts a different service's runbook 1st, narrowly ahead of the correct one
— close to a coin flip, because a colloquial complaint and a structured
Symptoms/Root-cause/Fix runbook just don't read alike, even about the same
underlying incident.

**HyDE** asks Gemini to draft a *hypothetical* runbook paragraph that
would plausibly answer the vague question (invented specifics are fine —
it's never shown to the user), embeds that hypothetical document as a
document (not a query), and compares it to the corpus document-to-document
instead of query-to-document. The right runbook jumps to a clear #1. Exact
margins move a bit each run since the hypothetical doc is freshly
generated each time — the script prints the real numbers live rather than
a canned "before/after" pair.

## Files

- `00a_tfidf_explained.py` — standalone, no `retrieval.py` dependency;
  its own tiny 5-sentence corpus, TF-IDF implemented inline for
  readability.
- `00b_cosine_similarity_explained.py` — same tiny corpus, uses
  `retrieval.py`'s `embed()` for real Gemini embeddings.
- `knowledge_base/*.md` — 8 docs, each with a small frontmatter header
  (`service`, `doc_type`, `env`) used as retrieval metadata (used by
  01, 02, 04).
- `retrieval.py` — corpus loader, Gemini embedding helpers, cosine
  ranking, a hand-rolled BM25 (Okapi, k1=1.5/b=0.75), and RRF.
- `01_naive_vs_metadata.py`, `02_hybrid_rrf.py`, `04_hyde.py` — Gemini-only
  demos, no extra install.
- `03_biencoder_vs_crossencoder.py` — needs
  `requirements-crossencoder.txt`; self-contained, doesn't use
  `retrieval.py` or `knowledge_base/`.
