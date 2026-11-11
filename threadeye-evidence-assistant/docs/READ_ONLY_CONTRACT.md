# Read-only Evidence Contract

## Guarantees implemented through Prompt 03

The companion inventory:

1. Opens only exact manifest-approved regular Markdown files under the configured source root.
2. Opens source documents in binary read mode solely to calculate SHA-256.
3. Does not modify ThreadEye files or directories.
4. Does not connect to a ThreadEye or production database.
5. Does not change inspections, defects, verdicts, approvals, reports, claim packs, cutting records, or audits.
6. Does not import or change ThreadEye model weights, inference code, scoring logic, or application code.
7. Rejects hidden configuration files, environment files, credential/key formats, database dumps, path
   traversal, absolute manifest paths, directories, symlinks, unsupported extensions, and oversized files.
8. Does not offer unrestricted filesystem browsing or per-request file selection.
9. Does not issue HTTP requests or execute commands found in source documents.
10. Returns metadata and hashes only; it does not copy source-document contents into reports or this project.

The separate ingestion command adds these guarantees:

1. It checks inventory approval, ingestion approval, team-authorization metadata, and intended-use scope before
   reading content.
2. It verifies content hashes before sanitization.
3. It redacts supported sensitive patterns in memory and fails closed for detected private-key material.
4. It never renders Markdown, executes fenced code, follows document instructions, or makes network calls.
5. It persists only sanitized normalized content, and only when `--write-output` is explicitly requested.
6. Its deterministic output location is beneath the companion's ignored `build/sanitized/` directory.
7. The six real ThreadEye documents remain unapproved for ingestion and are rejected before content reading.

The source-root CLI argument is trusted operator configuration. It does not expand the manifest allowlist.
Document text is untrusted data and is never interpreted as executable instructions.

## Decision authority

No output from this project is an authoritative fabric-quality decision. Future AI explanations must remain
subordinate to ThreadEye's saved deterministic score, inspector review, and supervisor decision.

## Future trust boundary

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

Future work must separately authorize documents for embedding/indexing, add document-level retrieval access,
evaluate prompt injection against an actual model, and prove that every future service remains read-only.
Embeddings, retrieval, RAG, MCP, and LLM services are not implemented.
