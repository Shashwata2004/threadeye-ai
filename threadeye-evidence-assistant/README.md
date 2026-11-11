# ThreadEye Evidence Assistant

This companion project inventories a small, explicitly approved set of ThreadEye documentation without
changing the ThreadEye application. Prompt 03 adds approval-gated Markdown sanitization, deterministic
normalization, and heading-aware variable chunking using synthetic fixtures only. The six real ThreadEye
documents remain blocked from content ingestion.

RAG answers, embeddings, vector search, MCP, local LLM inference, a UI, and deployment are not implemented.

## Requirements

- Python 3.9 or newer
- A local ThreadEye checkout available as a read-only source
- No database, network service, Docker container, or third-party Python package

## Run the inventory

From this directory:

```bash
PYTHONPATH=src python3 -m threadeye_evidence inventory \
  --source-root .. \
  --manifest knowledge/manifest.json
```

The command writes JSON metadata to standard output. It does not write an inventory report, copy document
contents, connect to a database, or make network requests. `--source-root` is operator configuration; callers
cannot request individual filesystem paths. Only the exact paths approved in the manifest are considered.

## Run the synthetic ingestion demonstration

The default command uses only `examples/synthetic/demo.md` and its separate synthetic authorization manifest:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m threadeye_evidence ingest
```

It prints safe statistics and chunk metadata without chunk content. To write the deterministic sanitized
snapshot beneath the ignored `build/sanitized/` directory:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m threadeye_evidence ingest --write-output
```

The ingestion command accepts only an exact manifest entry. It requires inventory approval, future-ingestion
approval, a documented authorization reference, and an exact intended-use match before reading file contents.
The real manifest intentionally has no such approvals.

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Tests use synthetic files in operating-system temporary directories. They do not modify or inventory the real
ThreadEye checkout.

## Security boundary

Read [the read-only contract](docs/READ_ONLY_CONTRACT.md), [architecture](docs/ARCHITECTURE.md), and
[threat model](docs/THREAT_MODEL.md) before extending this project. The detailed ingestion, sanitization,
chunking, provenance, and limitations are in [INGESTION.md](docs/INGESTION.md). Inventory approval is not
permission to embed, redistribute, train on, publish, or expose a document to an AI system.
