# Day 4 — Multi-Agent Systems

Two multi-agent projects (`incident-commander/`, `research-pipeline/`) and
a RAG retrieval-quality demo (`rag-demo/`).

## How to run

```
cd day-4
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste in your GEMINI_API_KEY
```

Then see each project's own README for how to run it and example inputs:
`incident-commander/README.md`, `research-pipeline/README.md`,
`rag-demo/README.md`.

## What each component does

### `incident-commander/`
Investigates a monitoring alert and either fixes it automatically or
escalates to a human. See `incident-commander/README.md` for details.

### `research-pipeline/`
Researches any question from multiple angles and produces a reconciled,
fact-checked report. See `research-pipeline/README.md` for details.

### `rag-demo/`
Two fundamentals scripts (TF-IDF and cosine similarity, worked by hand on
a tiny hand-verifiable corpus) plus four retrieval-quality comparisons:
naive vs. metadata-filtered search, keyword (BM25) vs. semantic search
merged with Reciprocal Rank Fusion, bi-encoder vs. cross-encoder
reranking, and direct search vs. HyDE on a deliberately vague query. See
`rag-demo/README.md` for details.

### `common/` (shared by both projects)
- `llm.py` — Gemini client setup.
- `agent_loop.py` — the tool-calling loop every agent runs on.
- `web_search.py` — live web search tool used by research-pipeline's agents.
- `audit_log.py` — records every agent action (`{agent_id, action, input, output, timestamp}`).
- `state_store.py` — saves a run's state to disk.
- `json_utils.py` — parses an agent's JSON response.
