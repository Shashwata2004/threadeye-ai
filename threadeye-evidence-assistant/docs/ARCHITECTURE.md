# Architecture

## Prompt 09 boundary

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
  → fixed MCP tool/resource registry
  → official MCP v2 protocol over stdio
  → or explicit authenticated SDK Streamable HTTP on loopback
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
- The MCP server is independent of the ThreadEye application server and has no HTTP listener or deployment.
- Its runtime identity is a separate `threadeye_evidence_mcp` role with only connect, schema usage and evidence-table
  SELECT; read-only transactions and database timeouts are also enforced at connection startup.

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

## MCP serving boundary

The MCP server is a thin adapter: it reuses `HybridRetriever`, `EvidenceAnswerEngine`, citation validation and
abstention rather than reimplementing them. Trusted startup configuration fixes the corpus, serving policy,
authorization reference, document classification, source and embedding profile. Tool arguments can choose only a
bounded query/question, retrieval mode and top-k; they cannot select or widen authorization.

`MCPServer` owns the four fixed tools and three sanitized resources. Strict middleware rejects unknown tool fields
before SDK parsing. A four-operation capacity limiter and 10-second deadline wrap worker-thread calls, while the
database uses an 8-second statement timeout. Stdout is reserved for MCP protocol frames; sanitized diagnostics use
stderr. The official SDK client starts the server as a child process, negotiates the protocol, invokes tools/resources,
tests rejection and terminates it when the client context exits.

The Prompt 09 HTTP adapter constructs the same registry with SDK token verification and one additional request-local
scope middleware. An outer admission layer validates exact loopback Host/Origin, duplicate/oversized headers, methods
and body size before evidence work. SDK authentication validates every stateless request; a post-auth layer applies
bounded per-principal/IP limits and immediate concurrency admission. Token-derived identity lives only in the SDK auth
context for that request. No corpus filter or service state comes from token claims.

Protected Resource Metadata is generated with the SDK's RFC 9728 model and handler at the resource-specific well-known
path. The configured issuer is a fictional offline-test identifier, not an authorization server. HTTP and stdio both
connect with `threadeye_evidence_mcp`; neither transport can index or mutate evidence.
