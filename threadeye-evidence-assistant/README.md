# ThreadEye Evidence Assistant

This isolated companion inventories explicitly approved ThreadEye documentation and, for fictional fixtures only,
runs approval-gated sanitization, real local embeddings, PostgreSQL full-text search, pgvector cosine search, and
weighted reciprocal-rank fusion. Prompt 06 adds conservative extractive evidence answers, exact provenance citations,
and explicit abstention. Prompt 07 adds adversarial fixtures, citation mutation defenses, Unicode/input controls,
failure isolation, and a reproducible 60-case security evaluation.
It does not modify or import the ThreadEye application. All six real ThreadEye documents remain blocked from
content ingestion and embedding.

LLM-generated RAG answers, reranking, MCP, local LLM generation, a UI, and deployment are not implemented.

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
```

Read [the grounded-answering and abstention design](docs/ANSWERING.md),
[the hybrid retrieval design and benchmark](docs/HYBRID_RETRIEVAL.md),
[the vector implementation](docs/VECTOR_INDEXING.md), [ingestion controls](docs/INGESTION.md),
[architecture](docs/ARCHITECTURE.md), [security evaluation](docs/SECURITY_EVALUATION.md), and
[threat model](docs/THREAT_MODEL.md). Inventory approval is not
permission to embed, redistribute, train on, publish, or expose a real document.
