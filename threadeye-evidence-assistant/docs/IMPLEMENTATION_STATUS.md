# Implementation Status

## Implemented in Prompt 02

- Independent companion Python project foundation
- Explicit documentation allowlist manifest
- Read-only document inventory
- Streaming SHA-256 content hashing
- File size and modification-time metadata
- Canonical path and file safety validation
- Missing/invalid-document error reporting without content copying
- Synthetic-fixture unit and security tests
- Protected ThreadEye file-hash baseline metadata

## Implemented in Prompt 03

- Independent inventory and content-ingestion approval gates
- Document-specific team authorization and intended-use matching
- Pre/post-read and manifest SHA-256 verification
- Conservative sensitive-pattern redaction with private-key fail-closed behavior
- Deterministic Markdown line-ending, whitespace, paragraph, list and code-fence normalization
- Heading-hierarchy-aware variable chunking
- Bounded oversized-section splitting at paragraph, sentence or line boundaries
- Stable chunk identifiers and content hashes
- Contiguous normalized source spans with zero overlap and verified complete coverage
- Provenance metadata for source, authorization, processing version and sanitization state
- Synthetic CLI dry-run and explicitly requested ignored sanitized snapshots
- Approval, sanitization, normalization, chunking, provenance and regression tests

## Not implemented yet

- Embeddings or embedding-model selection
- PostgreSQL or pgvector
- Vector retrieval or hybrid search
- RAG query or answer generation
- Citation generation or retrieval evaluation
- MCP server or MCP client integration
- Ollama or any local LLM
- Agentic orchestration
- Companion frontend/UI
- Public deployment
- ThreadEye database or production API integration

No RAG, MCP, or Local LLM CloudCamp points should be claimed from this foundation alone.
