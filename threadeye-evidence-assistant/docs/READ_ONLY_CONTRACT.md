# Read-only Evidence Contract

## Guarantees implemented in Prompt 02

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

Future work must separately authorize documents, sanitize content, enforce document-level access, resist
prompt injection, and prove that every service remains read-only. None of those future controls or services
is claimed as implemented by Prompt 02.
