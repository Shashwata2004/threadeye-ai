# Architecture

## Current Prompt 03 boundary

```text
Approved ThreadEye Documents
          |
          v
Read-only Path Validation
          |
          v
Inventory Approval
          |
          v
Independent Ingestion Approval + Team Authorization
          |
          v
Hash Verification → Sanitization → Normalization → Heading-aware Chunking
          |
          v
Safe Statistics or Ignored Sanitized Snapshot
```

The companion project has no runtime dependency on ThreadEye application packages. Its only integration
surface is an operator-selected source root plus exact relative Markdown paths approved in a manifest.

Inventory remains metadata-only. Content ingestion is a separate gate: the entry must also set
`future_ingestion_approved`, contain a document-specific team authorization, and match the requested intended
use. Authorization is checked before source content is read. The six real-document entries remain blocked.

Authorized synthetic input is hash-verified before and after reading, sanitized in memory, normalized without
rendering, and partitioned into deterministic heading-aware chunks. Only sanitized content can reach the
optional ignored snapshot. Dry-run output contains statistics and provenance metadata, not chunk contents.

## Dependency and deployment isolation

- Runtime code uses only the Python standard library.
- No ThreadEye module is imported.
- No environment file is parsed.
- No database driver or HTTP client is used.
- No Docker service or deployment configuration is created.
- The original ThreadEye repository remains independently runnable.

## Future boundary — NOT IMPLEMENTED

```text
Approved ThreadEye Documents
          |
          v
Read-only Inventory & Validation
          |
          v
Approval-gated Sanitized Ingestion
          |
          v
Deterministic Heading-aware Chunks
          |
          v
Future Embeddings / RAG / MCP / LLM Services  [NOT IMPLEMENTED]
```

Manifest authorization is an auditable policy record, not cryptographic proof of a person's identity. Team
review of authorization changes remains mandatory. Ingestion authorization never authorizes embedding,
redistribution, training, or publication.
