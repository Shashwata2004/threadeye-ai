# Real Embeddings and Isolated pgvector

## Verified embedding profile

| Field | Value |
|---|---|
| Library | FastEmbed 0.9.1 / ONNX Runtime 1.31.1 |
| Public model ID | `BAAI/bge-small-en-v1.5` |
| ONNX source | `Qdrant/bge-small-en-v1.5-onnx-Q` |
| Exact revision | `aa8f8b060edb00e03bfdd08813a2949946c8ba55` |
| License | MIT |
| Download size | Approximately 0.067 GB |
| Dimension | 384 |
| Metric | Cosine distance |
| Encoding | UTF-8 |
| Runtime | Python 3.11.17, macOS ARM64, CPUExecutionProvider |

The revision is passed to FastEmbed's Hugging Face download path and cached below ignored `build/model-cache/`.
Model weights are never committed. Document and query embeddings use the same exact profile. Inputs must be non-empty,
valid UTF-8, at most 20,000 characters, and batches must contain 1–256 items. Every output count, dimension, type, NaN,
and infinity is checked.

## Database

Compose pins `pgvector/pgvector:0.8.7-pg17-bookworm`; the verified container reports PostgreSQL 17.11 and pgvector
0.8.7. The database is `threadeye_evidence`, the user is `threadeye_evidence`, and the only host binding is
`127.0.0.1:55432`. A named companion volume and network avoid ThreadEye resources. Health checks, 1 GB memory, and one
CPU keep resource use modest.

The container bootstrap installs `vector` as its internal admin, creates the non-superuser application login, and
revokes public database/schema creation. Migration `001_evidence_vectors.sql` refuses another database name, verifies
that pgvector is present, and creates:

- `schema_migrations`: migration filename/checksum/time.
- `index_runs`: corpus/profile/model metadata and completed-run audit.
- `chunk_embeddings`: sanitized text, full Prompt 03 provenance, `vector(384)`, corpus/profile, run, and timestamps.

Schema constraints enforce hashes, chunk IDs, dimensions, cosine metric, spans, status, and non-empty sanitized text.
All application values use bound parameters. There is no arbitrary-SQL CLI.

## Index lifecycle

1. Prompt 03 authorizes, hash-checks, sanitizes, normalizes, and chunks an exact synthetic manifest entry.
2. Prompt 04 revalidates the sealed result and rejects changed hashes, duplicate IDs, broken spans/coverage,
   authorization mismatches, private-key material, or a second sanitization change.
3. The provider embeds sanitized chunk text before opening a write transaction.
4. A short transaction records a run, atomically upserts `(profile_key, chunk_id)`, and removes stale chunks for the
   same source/profile.
5. Repeat indexing updates the same rows without duplication. Changed content yields new hashes and chunk IDs.

A model revision changes the profile and corpus version. Old and new profiles may coexist for controlled re-embedding,
but queries filter one exact profile, so representations never mix. Removing an obsolete profile should be a separate,
reviewed maintenance operation; Prompt 04 provides no destructive CLI.

## Retrieval and performance

The query command embeds one validated string, uses exact pgvector cosine distance, orders ties by chunk ID, and limits
results to 20. It returns sanitized synthetic text plus source path/hash, chunk hash, headings, normalized span,
processing/sanitization/authorization fields, model revision, corpus version, distance, and similarity.

Prompt 05 preserves this exact profile and distance operator behind a stricter shared retrieval scope. Serving now
requires `retrieval_authorized=true` plus exact corpus, access policy, ingestion authorization reference, and model
profile matches. Optional source/hash/corpus/processing/classification filters are also parameterized. An incompatible
authorized corpus/profile combination fails with a controlled re-embedding error instead of mixing vectors.

The corpus is intentionally tiny, so a sequential exact scan is more appropriate than HNSW. Metadata B-tree indexes
support source/profile and run-status operations. No approximate vector-index usage or full RAG is claimed.

## Security boundaries

- Remote database hosts, Supabase hosts, wrong DB/user identities, URL query parameters, and absent passwords fail closed.
- All six real manifest entries keep `future_ingestion_approved: false`.
- Only fictional synthetic fixtures have embedding authorization.
- No production inspection data, ThreadEye credentials, raw unauthorized document, model cache, or local DB password is
  committed.
- The vector database does not call ThreadEye, Supabase, an LLM, or an MCP server.
