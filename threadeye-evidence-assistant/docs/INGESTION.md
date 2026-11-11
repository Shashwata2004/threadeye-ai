# Approval-gated Ingestion and Chunking

## Authorization gates

Content is read only after all conditions pass:

1. The exact relative path is present in the manifest.
2. `inventory_approved` is true.
3. `future_ingestion_approved` is true.
4. A `team_authorization` object records reference, intended use, approver label, and scope.
5. The requested intended use exactly matches the authorization.
6. The file passes the Prompt 02 path, symlink, type, and size controls.

The six real ThreadEye documents fail condition 3. The separate synthetic manifest authorizes only the fictional
Prompt 03 fixture. Manifest authorization is reviewable evidence, not a cryptographic signature; team review of
any real authorization change remains required.

## Hash verification

The pipeline streams SHA-256 before reading, hashes the bytes actually read, and streams SHA-256 again. All
three values must match. When the manifest pins `expected_sha256`, it must also match. A mismatch fails without
including document content in the error.

## Supported sanitization patterns

Current conservative regex rules redact:

- PostgreSQL, MySQL/MariaDB, MongoDB, and Redis connection URLs.
- Bearer tokens and selected common token/key prefixes.
- API-key, token, password, and secret assignments.
- Email addresses.
- localhost, loopback, RFC1918-style private IPv4, and `.internal` HTTP(S) URLs.
- Labeled customer, factory, buyer, mill, and inspection identifiers.

Detected private-key headers fail closed and require manual review. Findings record only type and action, never
the matched value. Regexes cannot detect every secret, personal identifier, encoded value, or domain-specific
factory/customer reference. Real-document ingestion therefore still requires manual review and additional
detectors before publication.

## Normalization

Normalization converts CRLF/CR to LF, removes trailing whitespace outside code fences, collapses repeated blank
lines outside fences, preserves Markdown headings/lists/paragraphs, and preserves fenced code as inert text. It
does not render HTML, execute commands, or reinterpret factual content.

## Variable chunking

Defaults are target 800 characters, maximum 1200 characters, and zero overlap. ATX headings define sections and
carry a parent heading path. Headings inside fenced code are ignored. A coherent section at or below the maximum
stays intact; oversized sections split near the target at paragraph boundaries, then sentence boundaries, then
line boundaries, with a hard maximum fallback.

Zero overlap prevents accidental duplication. A coverage assertion verifies that concatenating chunks exactly
reconstructs the sanitized normalized document.

Every chunk records source relative path and SHA-256, stable ID, heading path, sanitization state, chunk SHA-256,
order, normalized start/end offsets, span basis, processing version, authorization reference, size, and overlap.
IDs derive deterministically from source identity, source span, content hash, and processing version.

## Output

The default CLI is a dry run and emits statistics plus metadata without chunk content. `--write-output` writes a
deterministically named JSON snapshot containing sanitized normalized text and chunks beneath the ignored
`build/sanitized/` directory. Raw input is never written by the pipeline.

## Limitations

- No real ThreadEye document is approved for ingestion.
- No embedding, vector index, retrieval, RAG answer, MCP server, or LLM exists.
- Offset spans refer to sanitized normalized text, not byte positions in the original raw file.
- Regex sanitization requires later defense in depth and human review.
- Authorization records are policy metadata, not cryptographic signatures.
