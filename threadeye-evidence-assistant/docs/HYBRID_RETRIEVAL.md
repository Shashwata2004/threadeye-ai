# Hybrid Retrieval and Evaluation

## Database design

Migration `002_hybrid_retrieval.sql` appends serving-policy fields and a stored `search_vector` to the existing
`chunk_embeddings` table. The vector is generated with `to_tsvector('english', sanitized_text)`, so neither raw nor
unapproved source content is indexed. A GIN index named `chunk_embeddings_search_vector_idx` supports full-text
growth; a composite B-tree supports the shared retrieval scope.

Keyword queries use bound parameters, `websearch_to_tsquery('english', query)`, `@@`, and
`ts_rank_cd(search_vector, query, 32)`. Vector queries reuse the pinned FastEmbed BGE profile and exact pgvector
cosine operator. Both SQL statements require `retrieval_authorized=true`, corpus ID, access policy, ingestion
authorization reference, and embedding profile before ranking. Optional source path/hash, corpus version, processing
version, and classification filters are exact matches from a fixed column allowlist.

Ingestion approval and retrieval permission are distinct. Existing/new rows default to `unassigned`, `deny`, and
`false`. Only the fictional `technical-evidence.md` fixture is indexed with corpus
`threadeye-synthetic-evidence-v1`, policy `prompt05-test-only`, and classification `synthetic_test_fixture`.

## Fusion contract

Hybrid mode must complete both branches. Failure of either raises a named backend error; degraded output is never
presented as hybrid success. Candidate lists are fused with:

```text
RRF(d) = Σ weight_i / (k + rank_i(d))
```

Defaults are `k=60`, keyword weight `1.0`, and vector weight `1.0`; CLI values are finite and bounded. Ranks are
one-based. Missing branch results contribute nothing for that branch. Stable chunk ID deduplicates candidates;
conflicting provenance fails closed. Native keyword score, cosine distance/similarity, both original ranks, retrieval
methods, and fused score are retained. Final ties use chunk ID and top-k is strictly limited to 20.

## Reproducible evaluation

`evaluation/retrieval-v1.json` contains 35 labels fixed before prediction review: exact terms, quoted phrases, short
keywords, semantic paraphrases, identifiers, long questions, overlapping/ambiguous topics, and three out-of-corpus
queries. Relevance is a fictional source section, not a post-hoc model prediction.

Run after exporting the isolated database URL:

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence index --offline-model
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-retrieval --offline-model --format summary
```

Verified at `2026-11-11T13:10:26.106330+00:00` with the command above, PostgreSQL 17.11, pgvector 0.8.7, corpus
`daf7d3392d0a8a4f80dd24925f58bccbdd6814f5f231a74293d0dd834bbd5efd`, and BGE profile
`dc896e19f1401dd04a95036f020ce3059e9dae728a6f018065707619f681d825`:

| Mode | Hit@1 | Hit@3 | Hit@5 | Recall@5 | MRR | No-result accuracy | Avg latency | Failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Keyword | 0.65625 | 0.65625 | 0.65625 | 0.65625 | 0.65625 | 1.0 | 14.625 ms | 0 |
| Vector | 0.84375 | 1.0 | 1.0 | 1.0 | 0.911458 | 0.0 | 36.232 ms | 0 |
| Hybrid | 0.90625 | 1.0 | 1.0 | 1.0 | 0.947917 | 0.0 | 38.601 ms | 0 |

Hit Rate@k is the fraction of 32 queries with relevance labels that return at least one labeled section by k.
Recall@5 is mean section-label recall over those 32. MRR uses the first labeled result. No-result accuracy is the
fraction of three negative queries returning zero chunks. Latency is in-process wall time over successful queries.

Exact vector search always returns nearest neighbors when an authorized corpus exists, so vector and hybrid currently
have zero negative-query abstention. No similarity threshold was selected after seeing predictions. Prompt 06 must
design calibrated evidence/answer abstention independently.

## Genuine demonstrations

All demonstrations queried the isolated `threadeye_evidence` database with the test-only filters above.

- Keyword `ROLL-NST-204`: chunk `f53285a64a29b46ed7e52aad`, Fabric Receiving, keyword rank 1, score
  `0.09090909`, 14.890 ms.
- Vector `Who decides whether a proposed flaw label should stand and documents why?`: chunk
  `59e04794f6ffa0ba4b96508e`, Supervisor Review, vector rank 1, cosine similarity `0.667214`, 443.765 ms including
  cold process/model initialization.
- Hybrid `content hash sanitized observation`: chunk `e1569f1c868b8657f838f33e`, Quality Inspection Evidence,
  keyword rank 1, vector rank 1, keyword score `0.010989011`, cosine similarity `0.723231`, RRF
  `0.03278688524590164`, 445.928 ms including cold initialization.

Representative `EXPLAIN (ANALYZE, BUFFERS)` for `ROLL-NST-204` reported `Limit → Sort → Seq Scan`, planning
`0.989 ms`, execution `0.236 ms`. PostgreSQL reasonably did not use the GIN index for this tiny corpus.

## Limitations and performance

- The authorized benchmark has only six chunks from one fictional document; results do not predict production scale.
- Exact vector scans and English stemming are deliberate; no HNSW, language detection, BM25 extension, reranker, or
  threshold calibration exists.
- A fresh CLI process includes model startup; benchmark averages reuse one loaded provider.
- This layer retrieves evidence only. It does not generate answers, validate answer citations, call an LLM/MCP, make
  fabric decisions, or replace supervisor approval.

## CloudCamp evidence

Verified claims supported here are Vector Database, heading-aware variable chunking, and Hybrid Search (PostgreSQL
keyword + pgvector semantic retrieval with RRF). This does not support claims for Naive/Contextual/Graph/Self/
Corrective/Agentic RAG, reranking, answer citations, MCP, or a local LLM.
