# Architecture

## Prompt 04 boundary

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
  → exact cosine query with provenance
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

Prompt 04 uses exact `<=>` cosine distance with deterministic chunk-ID tie-breaking and a hard top-20 limit. The
synthetic corpus is too small to justify HNSW; only B-tree metadata indexes are created. No vector-index scan is
claimed. Prompt 05 will add separate keyword/vector retrieval, fusion, filters, and evaluation.
