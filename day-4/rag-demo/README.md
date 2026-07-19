# RAG Demo — Retrieval Quality

Four short scripts. The first three share one knowledge base; each makes
the same point from a different angle: "search and grab the top matches"
quietly throws away information a real RAG system needs to get right.

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
- **Query B** paraphrases everything ("billing service" instead of
  payment-service, "dying from running out of memory" instead of
  OOMKilled, "bounce" instead of restart). BM25 has almost no literal
  token overlap with the right doc and ranks a different service's
  runbook first; semantic search reads through the paraphrase and gets it
  in one.

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
