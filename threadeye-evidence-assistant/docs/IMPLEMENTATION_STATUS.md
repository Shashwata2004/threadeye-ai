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

## Not implemented

- Keyword/BM25 retrieval, hybrid retrieval, reciprocal-rank fusion, or filtering.
- Reranking or retrieval evaluation baseline.
- RAG answer generation or LLM-generated citations.
- MCP server/client, local LLM generation, agent orchestration, companion UI, public deployment.
- ThreadEye production database/API integration or real-document embedding.

Vector indexing alone is not a full RAG system. No Naive RAG, hybrid search, reranking, MCP, or Local LLM claim should
be made from Prompt 04.
