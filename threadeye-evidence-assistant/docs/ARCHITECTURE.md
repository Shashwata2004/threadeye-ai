# Architecture

## Prompt 05 boundary

```text
Exact manifest entry
  → inventory approval + ingestion approval + intended-use authorization
  → source hash verification
  → in-memory redaction and Markdown normalization
  → deterministic heading-aware chunks
  → sealed provenance validation (no arbitrary source-path input)
  → pinned BGE CPU embeddings
  → dimension/finite-value validation
  → isolated PostgreSQL transaction and pgvector upsert
  → separate serving authorization (test-only synthetic corpus)
  → PostgreSQL FTS and/or exact cosine retrieval with provenance
  → weighted reciprocal-rank fusion for hybrid mode
  → Prompt 06 request policy and authorization-scope check
  → multi-signal evidence sufficiency and abstention
  → deterministic sentence extraction
  → exact citation/provenance/claim validation
  → typed answered or abstained response
```

The companion has no runtime dependency on ThreadEye application packages. Inventory remains metadata-only.
Vector indexing accepts only an `IngestionResult` produced by the Prompt 03 pipeline, rechecks its hashes,
authorization, chunk coverage, spans, sanitization state, and a second sanitization pass, then embeds only the
verified sanitized chunk text.

## Isolation

- Pure inventory/ingestion still works with Python 3.9 and no third-party packages.
- Vector functionality uses an ignored Python 3.11 virtual environment and pinned dependency lock.
- The only model is a pinned 384-dimensional BGE Small ONNX revision, executed on CPU.
- The Compose project, PostgreSQL database/user, network, volume, and host port are companion-specific.
- The database URL parser rejects remote hosts, wrong database/user identities, URL parameters, and missing passwords.
- Migration SQL also refuses any database name except `threadeye_evidence`.
- No ThreadEye/Supabase configuration, credentials, schemas, networks, or data are used.

## Model and corpus versioning

An embedding profile key hashes provider, model, exact revision, dimension, metric, and encoding. Rows are keyed by
profile plus stable chunk ID, and every query filters one exact profile. A new revision therefore creates a separate
representation and cannot silently mix with old vectors. A deterministic corpus version covers source and normalized
hashes, authorization, processing version, profile, and ordered chunk IDs.

Repeated indexing atomically upserts identical chunks. Changed source content produces new chunk IDs and removes stale
chunks for that source/profile inside the same short transaction. External model inference happens before the database
transaction.

## Search strategy

Vector mode uses exact `<=>` cosine distance. Keyword mode uses a stored English `tsvector`,
`websearch_to_tsquery`, and `ts_rank_cd`. Hybrid mode executes both branches over the same SQL authorization scope,
then calculates `sum(weight/(k+rank))`; it never adds incomparable native scores. Results deduplicate by stable chunk
ID, preserve provenance/native scores, break ties by chunk ID, and enforce a hard top-20 limit.

The synthetic corpus is too small to justify HNSW. A GIN full-text index exists for growth, but the verified
representative `EXPLAIN (ANALYZE, BUFFERS)` selected a sequential scan over six authorized chunks. No GIN scan or
vector-index scan is falsely claimed.

## Answering boundary

The answer engine never changes retrieval authorization and never reads source files. It receives only database rows
already filtered by corpus, policy, authorization reference and model profile. The response is `answered` only when
evidence passes the frozen sufficiency configuration and every output sentence is an exact cited excerpt. Otherwise it
returns a distinct unauthorized, unsupported, insufficient, retrieval-error or citation-failure status.

Retrieved Markdown remains untrusted data. Prompt-like instructions are excluded from evidence selection. This layer
does not call an LLM, ThreadEye backend, Supabase, scoring engine, review workflow or approval system.
