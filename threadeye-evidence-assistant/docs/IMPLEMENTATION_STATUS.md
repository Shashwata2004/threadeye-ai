# Implementation Status

## Implemented

Prompt 02 provides the exact allowlist, read-only inventory, SHA-256 hashing, path/symlink/size controls, and
protected-core baseline. Prompt 03 adds independent content authorization, expected-hash verification, sensitive-value
redaction, Markdown normalization, deterministic heading-aware chunks, stable IDs, source spans, provenance, and
synthetic sanitized snapshots.

Prompt 04 adds:

- Versioned embedding-provider interface and deterministic test double.
- Genuine FastEmbed 0.9.1 CPU inference with `BAAI/bge-small-en-v1.5`, 384 dimensions, cosine distance, and exact
  model-source revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55`.
- Finite-value, count, dimension, UTF-8, empty-input, length, and batch validation.
- Pinned PostgreSQL 17/pgvector 0.8.7 Compose service isolated on loopback.
- Idempotent, checksum-recorded schema migration and real `vector(384)` storage.
- Transactional provenance-preserving upsert, duplicate prevention, stale-chunk removal, and model-profile isolation.
- Exact cosine top-k search with sanitized text, distance/similarity, and source/chunk provenance.
- Synthetic five-topic corpus and unit, security, regression, genuine-model, and real-database tests.
- CLI commands: `model-info`, `index`, `index-status`, and `query`.

Prompt 05 adds and verifies:

- Stored English `tsvector` generated only from sanitized text, a GIN index, `websearch_to_tsquery`, and
  `ts_rank_cd` keyword ranking.
- Strict test-only serving authorization, independent of ingestion approval, applied within both SQL branches.
- Three modes: PostgreSQL keyword, pinned-BGE pgvector, and genuine two-branch hybrid retrieval.
- Configurable weighted reciprocal-rank fusion with `k=60`, stable chunk deduplication, native scores/ranks, and
  deterministic ties.
- Fixed 35-query fictional evaluation dataset with Hit Rate@1/3/5, Recall@5, MRR, no-result accuracy, latency, and
  explicit per-query failures.
- `search` and `evaluate-retrieval` CLI commands with structured JSON and summaries.
- 100 passing tests with all real-model and isolated-database integration flags enabled.

Prompt 06 adds and verifies:

- Authorized hybrid-retrieval-to-answer orchestration with typed answered/abstention responses.
- Deterministic extractive answers whose complete text is restricted to validated supporting excerpts.
- Source, source-hash, chunk, chunk-hash, heading, normalized-span, processing, authorization, corpus and excerpt
  citation verification.
- Versioned multi-signal sufficiency using identifiers, lexical support, keyword evidence, cosine similarity and
  ambiguity margin; RRF is never treated as a probability.
- Explicit request/evidence safeguards for secrets, prompt injection, production access, contradictory evidence and
  fabric-verdict/scoring overrides.
- A fixed 44-case answer dataset with independent development and held-out splits, 22 answerable and 22 negative cases.
- Genuine database answer, abstention, unauthorized-scope and adversarial-document demonstrations.
- CLI commands: `answer-evidence` and `evaluate-answers`.

Prompt 07 adds and verifies:

- Five separately approved fictional adversarial documents and an isolated security-fixture retrieval policy.
- NFKC input handling, hidden-control/mixed-script rejection, safe question echo, identifier/domain consistency and
  conservative keyword-stuffing detection without changing Prompt 06 numeric thresholds.
- Stronger citation integrity through stored-content hash recomputation, span consistency, complete optional-filter
  validation and bounded citation counts.
- Structured fail-closed behavior for database/model/profile/keyword/vector/citation failures; hybrid failures are
  never silently treated as degraded success.
- A fixed independent 60-case dataset with separate 30-case development and final-holdout splits plus security,
  leakage, failure and latency metrics.
- `index-security-fixtures` and `evaluate-security` CLI commands.
- 139 passing tests with genuine BGE and PostgreSQL/pgvector enabled and no skips.

Prompt 08 adds and verifies:

- Official `mcp==2.3.0` v2 `MCPServer` and `Client` APIs on Python 3.11, with stdio as the only transport.
- Four fixed, annotated read-only tools for search, extractive answers, source metadata and capability metadata.
- Three sanitized resources for capabilities, corpus manifest and security policy.
- Operator-controlled trusted startup authorization fixing one fictional corpus, source, policy, authorization
  reference, classification and exact embedding profile; client arguments cannot widen this scope.
- A dedicated `threadeye_evidence_mcp` PostgreSQL role with only the required SELECT access, default read-only
  transactions and runtime identity/transaction checks.
- Bounded queries, top-k, response size, concurrency, tool execution, database statements and connection attempts.
- Strict unknown-argument rejection, safe protocol errors, stderr-only diagnostics and a fixed negative tool surface.
- A genuine official-client subprocess lifecycle covering initialize/version negotiation, discovery, resource read,
  successful search/answer, abstention, unauthorized scope rejection, forbidden tool rejection and clean shutdown.
- 151 passing tests with genuine BGE, PostgreSQL/pgvector and MCP stdio integration enabled, with zero skips; unchanged
  retrieval/answer datasets remain fully passing and security evaluation remains 30/30 development, 29/30 holdout.

## Not implemented

- LLM-generated answer generation or LLM-generated citations.
- Reranking, contextual RAG, graph RAG, Self-RAG, corrective RAG, or agentic RAG.
- Remote authenticated/HTTP MCP, local LLM generation, agent orchestration, companion UI, public deployment.
- ThreadEye production database/API integration or real-document embedding.

Prompt 08 is a hardened extractive evidence-answering pipeline exposed by one real local stdio MCP server, but it is
not an LLM-powered RAG generator. No hosted/local LLM, reranking, remote MCP, agent, frontend, reuse or public-deployment
claim should be made.
