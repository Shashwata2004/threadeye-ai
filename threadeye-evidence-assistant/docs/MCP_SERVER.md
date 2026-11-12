# Read-only Evidence MCP Server

## Verified implementation

Prompt 08 added one independently launchable MCP server using the
[official Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk), pinned to
`mcp==2.3.0` on Python 3.11.17. It uses the v2 `MCPServer` and `Client` APIs. Prompt 09 preserves this stdio launcher
and adds a separately launched authenticated localhost Streamable HTTP adapter described in [MCP_HTTP.md](MCP_HTTP.md).
Neither launcher provides public deployment, production integration or LLM generation.

```text
Authorized local MCP launcher
  -> official MCP protocol over stdin/stdout
  -> fixed tool/resource registry and strict argument validation
  -> operator-owned trusted authorization configuration
  -> existing retrieval and extractive-answer engines
  -> dedicated read-only PostgreSQL identity
  -> one authorized fictional synthetic source
```

Stdio is transport isolation, not cryptographic authentication. Anyone who can launch this process with its trusted
configuration, model cache, and database credential can exercise the limited permissions they confer. The HTTP
launcher authenticates every request, but remains loopback-only and is not a public remote service.

## Fixed registry

All tools carry read-only, non-destructive, idempotent, closed-world annotations.

| Tool | Inputs | Result | Enforcement |
|---|---|---|---|
| `search_evidence` | `query`, `mode` (`keyword`, `vector`, `hybrid`), `top_k` | Matches, sanitized evidence, scores, headings, hashes, spans and citation-ready provenance | 1,000-character query, top-k 1–5, fixed source filters, Prompt 07 input/injection policy |
| `answer_evidence_question` | `question`, optional bounded `mode` | Existing typed extractive answer or abstention, validated citations, supporting chunks and limitations | Same fixed authorization, citation validation, no LLM generation |
| `list_evidence_sources` | none | Non-sensitive source metadata and corpus version | Only the authorized synthetic source; no repository enumeration |
| `get_evidence_capabilities` | none | Genuine modes, model metadata, limits and explicit exclusions | Sanitized metadata only |

Unknown arguments are rejected before SDK model parsing so a caller cannot smuggle `corpus_id`, source, policy,
authorization reference or profile overrides. Forbidden tools such as `delete_roll`, `execute_sql`, `read_file`,
`run_shell`, `approve_verdict` and `modify_audit` are absent from discovery and fail as unknown tools.

The fixed resources are:

- `threadeye://evidence/capabilities`
- `threadeye://evidence/corpus-manifest`
- `threadeye://evidence/security-policy`

They expose sanitized JSON metadata only. They do not expose repository directories, source documents, credentials,
model weights, production records, inspection images, buyer information, users or operational reports.

## Trusted authorization

`THREADEYE_EVIDENCE_MCP_CONFIG` must identify an operator-controlled regular file owned by the current user. A symlink,
missing file, different owner, group/world-writable file, unknown field, invalid bound or profile mismatch fails closed.
The checked-in Prompt 08 configuration fixes:

- corpus `threadeye-synthetic-evidence-v1`;
- policy `prompt05-test-only`;
- authorization reference `PROMPT-04-SYNTHETIC-VECTOR-FIXTURE`;
- classification `synthetic_test_fixture`;
- the exact pinned BGE embedding profile; and
- source `technical-evidence.md` only.

Tool inputs cannot expand that scope. The six real documents remain ingestion-unapproved and are not read, indexed or
served. The server also requires `THREADEYE_EVIDENCE_MCP_DATABASE_URL` to use the exact local database and exact
`threadeye_evidence_mcp` role. Credentials are neither accepted as tool arguments nor logged.

## Database least privilege

The operator-only `threadeye-evidence-mcp-db-setup` command creates or rotates the companion-local MCP identity using
environment-only credentials. It revokes database/schema/table privileges, then grants only database connect, schema
usage and `SELECT` on `evidence_assistant.chunk_embeddings`. The role is non-superuser, cannot create databases or
roles, does not inherit privileges, and defaults to read-only transactions. The server never runs this setup path.

Runtime connections independently require:

- exact database `threadeye_evidence` and user `threadeye_evidence_mcp` on loopback;
- `default_transaction_read_only=on` and a verified read-only transaction;
- 5-second connect timeout, 8-second statement timeout and 2-second lock timeout.

Integration tests execute a real `SELECT`, confirm the role is neither superuser nor database/role creator and does
not inherit privileges, then prove `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, schema DDL, temporary-table DDL and role
creation are denied. No production or Supabase credential is used.

## Installation and local startup

Install only in the ignored companion Python 3.11 environment:

```bash
.venv/bin/python -m pip install -r requirements-vector.lock
.venv/bin/python -m pip install --no-deps -e .
```

Create `.env.db` from `.env.db.example`, choose separate local admin and MCP passwords, and start the isolated
database. Migrate/index with the existing admin identity before granting the read-only role:

```bash
docker compose --env-file .env.db up -d --wait
set -a; source .env.db; set +a
export THREADEYE_EVIDENCE_DATABASE_URL="postgresql://${EVIDENCE_DB_USER}:${EVIDENCE_DB_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
export THREADEYE_EVIDENCE_MODEL_CACHE="$PWD/build/model-cache"
PYTHONPATH=src .venv/bin/python -m threadeye_evidence index

export THREADEYE_EVIDENCE_ADMIN_DATABASE_URL="$THREADEYE_EVIDENCE_DATABASE_URL"
export THREADEYE_EVIDENCE_MCP_DATABASE_URL="postgresql://${EVIDENCE_MCP_DB_USER}:${EVIDENCE_MCP_DB_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
export THREADEYE_EVIDENCE_MCP_CONFIG="$PWD/config/mcp-synthetic.json"
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.database
```

An MCP launcher should execute this command with only the three runtime variables above:

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.server
```

Stdout is exclusively the protocol stream. Startup denial and sanitized diagnostics go to stderr. No banner or debug
text is emitted to stdout.

## Genuine protocol verification

The reproducible verifier uses the official SDK `Client` and `StdioServerParameters` to spawn the real server:

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.verify_client
```

The verified lifecycle negotiates protocol version `2025-11-25`, identifies server `threadeye-evidence` version
`0.7.0`, discovers exactly four tools and three resources, reads the capabilities resource, performs hybrid search,
returns an extractive answer with a validated citation, safely abstains for an unsupported weather question, rejects
an injected corpus argument, rejects `delete_roll`, exits the client context and terminates the subprocess.

During implementation the first genuine client call showed that the SDK's default input model ignored an unexpected
argument. A server middleware now rejects every argument outside each fixed schema; the genuine unauthorized call and
unit regression prove the correction.

The final Prompt 08 run passed 151 tests with all genuine model, database and MCP flags enabled: zero failures and zero
skips. The unchanged 35-query retrieval benchmark completed without runtime failures; hybrid Hit@1 was 0.906, Hit@3/5
and Recall@5 were 1.000, and hybrid MRR was 0.948. Both unchanged answer splits were perfect across answerability,
correct abstention, citation validity/precision, source correctness and structured response metrics (20 development
and 24 held-out cases). The unchanged security evaluation remained 30/30 development and 29/30 final holdout, with
zero attack successes in the measured cases and all 7/7 failure cases handled correctly in each split.

## Resource and reliability limits

- Maximum normalized query/question: 1,000 characters.
- Maximum top-k: 5.
- Maximum serialized payload: 65,536 bytes.
- Maximum concurrent tools/resources: 4.
- Per-tool/resource deadline: 10 seconds.
- Database statement timeout: 8 seconds; connect timeout: 5 seconds.
- Each query owns a context-managed database connection; client context exit terminates the stdio child process.
- Unexpected implementation failures return sanitized tool/resource errors and log only the exception type to stderr.

These limits reduce local resource exhaustion but are not public rate limiting or multi-tenant isolation. Abandoned
worker threads rely on the shorter database statement timeout to finish after an MCP deadline.

## Supported claims and limitations

The project truthfully demonstrates one custom MCP server **built** with an official SDK and **used** by a genuine
client over stdio. It demonstrates authorized keyword/vector/hybrid retrieval, deterministic extractive answering,
citation validation, abstention and read-only database enforcement on fictional evidence.

The combined project now demonstrates the same server through stdio and authenticated local Streamable HTTP. It does
not demonstrate a second independently built server, cross-project reuse, public remote users, agents, generative RAG,
production ThreadEye data, operational decisions, deployment or reuse bonus eligibility.
