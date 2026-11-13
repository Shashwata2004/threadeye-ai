# ThreadEye Evidence Assistant

This isolated companion inventories explicitly approved ThreadEye documentation and, for fictional fixtures only,
runs approval-gated sanitization, real local embeddings, PostgreSQL full-text search, pgvector cosine search, and
weighted reciprocal-rank fusion. Prompt 06 adds conservative extractive evidence answers, exact provenance citations,
and explicit abstention. Prompt 07 adds adversarial fixtures, citation mutation defenses, Unicode/input controls,
failure isolation, and a reproducible 60-case security evaluation. Prompt 08 adds one official-SDK MCP v2 server over
stdio, a fixed trusted synthetic-corpus scope, four read-only tools, three sanitized resources, and a dedicated
least-privilege database identity. Prompt 09 adds an explicitly launched, authenticated localhost Streamable HTTP
transport with EdDSA access tokens, per-operation scopes, protected-resource metadata, rate limiting and audit events.
Prompt 10 adds a separate localhost-only judge UI, an operator-controlled browser session, genuine server-side MCP
calls, safe evidence rendering, responsive layouts, and reproducible search/answer/abstention workflows.
Prompt 11 adds a release QA package, an independently pre-labeled ten-case synthetic holdout, a reproducible real
browser regression, clean-install verification, original-product regression evidence, and companion-only fixes found
during testing. The first holdout run was 5/10 and the examined post-fix rerun was 8/10; both are preserved honestly.
It does not modify or import the ThreadEye application. All six real ThreadEye documents remain blocked from
content ingestion and embedding.

LLM-generated RAG answers, reranking, public/remote MCP deployment, local LLM generation, and deployment are not
implemented.

## Environments

The inventory and Prompt 03 ingestion commands remain pure Python and work with Python 3.9+. Prompt 04 vector
features use an isolated Python 3.11 environment:

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-vector.lock
.venv/bin/python -m pip install --no-deps -e .
```

The lock records the exact verified macOS ARM64 environment. The model cache, virtual environment, local database
credentials, and generated outputs are ignored by Git.

## Existing inventory and ingestion

```bash
PYTHONPATH=src python3 -m threadeye_evidence inventory \
  --source-root .. --manifest knowledge/manifest.json

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m threadeye_evidence ingest
```

Inventory is metadata-only. Ingestion requires independent inventory approval, ingestion approval, a documented
authorization reference, an exact intended-use match, and source hash verification before sanitization.

## Start the isolated vector database

```bash
cp .env.db.example .env.db
# Replace the local-only password in .env.db.
docker compose --env-file .env.db up -d --wait
```

The pinned `pgvector/pgvector:0.8.7-pg17-bookworm` service uses a dedicated database, user, volume, network,
1 GB memory limit, one CPU, health check, and only `127.0.0.1:55432`. It never connects to ThreadEye or Supabase.

Export the CLI connection without printing the password:

```bash
set -a; source .env.db; set +a
export THREADEYE_EVIDENCE_DATABASE_URL="postgresql://${EVIDENCE_DB_USER}:${EVIDENCE_DB_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
```

## Index and retrieval CLI

```bash
# Metadata plus genuine CPU inference verification
PYTHONPATH=src .venv/bin/python -m threadeye_evidence model-info --verify

# Approval → sanitization → chunk validation → real embedding → transactional upsert
PYTHONPATH=src .venv/bin/python -m threadeye_evidence index

# Migration, pgvector, profile, source, and chunk status
PYTHONPATH=src .venv/bin/python -m threadeye_evidence index-status

# Backward-compatible authorized vector query
PYTHONPATH=src .venv/bin/python -m threadeye_evidence query \
  "Who reviews flagged defect classifications and records a reason?" --top-k 3

# Independent PostgreSQL keyword, genuine BGE vector, or two-branch hybrid retrieval
PYTHONPATH=src .venv/bin/python -m threadeye_evidence search \
  --mode keyword --query 'ROLL-NST-204' --top-k 3 --offline-model
PYTHONPATH=src .venv/bin/python -m threadeye_evidence search \
  --mode vector --query 'Who decides whether a proposed flaw label should stand?' --top-k 3 --offline-model
PYTHONPATH=src .venv/bin/python -m threadeye_evidence search \
  --mode hybrid --query 'content hash sanitized observation' --top-k 3 --candidate-k 6 \
  --rrf-k 60 --keyword-weight 1 --vector-weight 1 --format summary --offline-model

# Fixed 35-query benchmark; runs keyword, vector, and hybrid separately
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-retrieval --offline-model --format summary

# Deterministic extraction with validated citations, or a structured abstention
PYTHONPATH=src .venv/bin/python -m threadeye_evidence answer-evidence \
  --question 'Which supplier lot is recorded for ROLL-NST-204?' --offline-model --format summary

# Calibrate only on development, then evaluate the frozen configuration on held-out cases
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-answers \
  --split development --offline-model --format summary
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-answers \
  --split held_out --offline-model --format summary

# Index only exact separately approved fictional security fixtures
PYTHONPATH=src .venv/bin/python -m threadeye_evidence index-security-fixtures --offline-model

# Development first; final holdout remains frozen
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-security \
  --split development --offline-model --format summary
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-security \
  --split final_holdout --offline-model --format summary
```

After the first verified download, add `--offline-model` to vector commands. Stop without deleting data using
`docker compose --env-file .env.db down`; remove only the isolated companion volume with
`docker compose --env-file .env.db down -v` when its test data is no longer needed.

## Tests

```bash
# Unit and Prompt 02/03 regressions; integration tests skip unless explicitly enabled
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v

# Genuine model and real pgvector integration
THREADEYE_RUN_MODEL_TESTS=1 THREADEYE_RUN_DB_TESTS=1 \
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v

# After exporting the trusted MCP config/cache and read-only MCP database URL above
THREADEYE_RUN_MODEL_TESTS=1 THREADEYE_RUN_DB_TESTS=1 THREADEYE_RUN_MCP_TESTS=1 \
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v

# Full Prompt 09 run, including two real authenticated localhost HTTP clients
THREADEYE_RUN_MODEL_TESTS=1 THREADEYE_RUN_DB_TESTS=1 THREADEYE_RUN_MCP_TESTS=1 \
  THREADEYE_RUN_HTTP_TESTS=1 THREADEYE_RUN_UI_TESTS=1 \
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v

# Independent QA holdout (do not tune thresholds against this examined dataset)
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-qa-holdout --offline-model --format summary
```

## Read-only MCP server

The MCP process is independently launchable and uses the official `mcp==2.3.0` Python SDK. It exposes only the fixed
fictional corpus in `config/mcp-synthetic.json`. The client cannot select a corpus, source, policy, authorization
reference, embedding profile, file, SQL statement, shell command, or network destination.

After the main schema is migrated and the synthetic corpus is indexed, configure a separate local password for the
MCP role. Pass credentials through environment variables, never command-line arguments:

```bash
set -a; source .env.db; set +a
export THREADEYE_EVIDENCE_ADMIN_DATABASE_URL="postgresql://${EVIDENCE_DB_ADMIN_USER}:${EVIDENCE_DB_ADMIN_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
export THREADEYE_EVIDENCE_MCP_DATABASE_URL="postgresql://${EVIDENCE_MCP_DB_USER}:${EVIDENCE_MCP_DB_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
export THREADEYE_EVIDENCE_MCP_CONFIG="$PWD/config/mcp-synthetic.json"
export THREADEYE_EVIDENCE_MODEL_CACHE="$PWD/build/model-cache"
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.database
```

Run the stdio server for an MCP launcher, or execute the official-client verification that starts and terminates a
real subprocess:

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.server
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.verify_client
```

The server writes MCP frames only to stdout and diagnostics only to stderr. Stdio is a local transport, not caller
authentication: anyone able to launch the process with the trusted configuration and read-only database credential
can exercise that deliberately limited synthetic scope. See [MCP server operations and evidence](docs/MCP_SERVER.md).

## Authenticated localhost MCP HTTP

Prompt 09 preserves stdio and adds a separate explicit launcher at `http://127.0.0.1:8765/mcp`. It requires the same
read-only service configuration plus `config/mcp-http.json` and an operator-owned Ed25519 public key:

```bash
export THREADEYE_EVIDENCE_HTTP_CONFIG="$PWD/config/mcp-http.json"
export THREADEYE_EVIDENCE_HTTP_PUBLIC_KEY="/absolute/path/to/ed25519-public-key.pem"
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.http_server
```

The server never receives a private signing key and does not issue tokens. For the reproducible test-only flow, this
command generates an ephemeral signing key and short-lived synthetic tokens, starts the real HTTP subprocess, invokes
two official SDK clients with different scopes, runs negative tests, and shuts it down:

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.verify_http
```

This is a local OAuth resource-server demonstration, not a complete authorization server or interactive OAuth login.
See [authenticated Streamable HTTP architecture and evidence](docs/MCP_HTTP.md).

## Local judge UI

The independent UI is served only at `http://127.0.0.1:8770`. Its Python backend holds an ephemeral development-only
signing key, starts the existing authenticated MCP HTTP process, and makes official SDK calls for an authenticated
local browser session. The browser never receives an MCP bearer token, signing key or database URL.

After preparing the database and exporting the trusted MCP variables above, set a local access code without printing
it and launch both isolated services:

```bash
read -s THREADEYE_EVIDENCE_UI_ACCESS_CODE
export THREADEYE_EVIDENCE_UI_ACCESS_CODE
export THREADEYE_EVIDENCE_UI_PORT=8770 # optional; loopback-only
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m threadeye_evidence.ui.launcher
```

Open `http://127.0.0.1:8770`, enter the operator-provided code, and use the three judge-demonstration cards. Press
Ctrl-C to stop both the UI and its owned MCP subprocess. The access code is a localhost demonstration boundary, not
production identity management. Plain localhost HTTP prevents a `Secure` cookie; the cookie is still HttpOnly,
SameSite=Strict, host-only, short-lived and paired with CSRF, Host and Origin validation. See
[the complete judge demonstration guide](docs/JUDGE_DEMO.md).

Read [the grounded-answering and abstention design](docs/ANSWERING.md),
[the hybrid retrieval design and benchmark](docs/HYBRID_RETRIEVAL.md),
[the vector implementation](docs/VECTOR_INDEXING.md), [ingestion controls](docs/INGESTION.md),
[architecture](docs/ARCHITECTURE.md), [MCP server](docs/MCP_SERVER.md),
[authenticated MCP HTTP](docs/MCP_HTTP.md),
[judge UI demonstration](docs/JUDGE_DEMO.md),
[security evaluation](docs/SECURITY_EVALUATION.md), and
[final release QA](docs/FINAL_QA.md), and [threat model](docs/THREAT_MODEL.md). Inventory approval is not
permission to embed, redistribute, train on, publish, or expose a real document.
