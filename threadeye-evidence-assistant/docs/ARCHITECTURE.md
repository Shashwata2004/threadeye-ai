# Architecture

## Current Prompt 02 boundary

```text
Approved ThreadEye Documents
          |
          v
Read-only Path Validation
          |
          v
Metadata + SHA-256 Inventory
          |
          v
JSON on standard output
```

The companion project is independently configured and has no runtime dependency on ThreadEye application
packages. Its only integration surface is an operator-selected ThreadEye source root plus the exact relative
Markdown paths approved in `knowledge/manifest.json`.

Inventory processing is deterministic with respect to file bytes: SHA-256 is calculated by streaming each
approved regular file in binary mode. The output includes relative path, byte size, content hash, modification
timestamp, classification, approval flags, caveats, and a validation error when a document is missing or unsafe.
It never includes document contents.

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
Future Sanitized Ingestion       [NOT IMPLEMENTED]
          |
          v
Future RAG / MCP / LLM Services  [NOT IMPLEMENTED]
```

Any future stage must add a separate authorization review before content leaves the source checkout. Local
inventory approval alone never authorizes ingestion, embedding, redistribution, training, or publication.
