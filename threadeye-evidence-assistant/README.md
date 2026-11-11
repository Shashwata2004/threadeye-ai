# ThreadEye Evidence Assistant — Foundation

This companion project inventories a small, explicitly approved set of ThreadEye documentation without
copying document contents or changing the ThreadEye application. Prompt 02 implements only the read-only
foundation. RAG, embeddings, vector search, MCP, local LLM inference, a UI, and deployment are not implemented.

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

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Tests use synthetic files in operating-system temporary directories. They do not modify or inventory the real
ThreadEye checkout.

## Security boundary

Read [the read-only contract](docs/READ_ONLY_CONTRACT.md), [architecture](docs/ARCHITECTURE.md), and
[threat model](docs/THREAT_MODEL.md) before extending this project. Inventory approval is not permission to
embed, redistribute, train on, publish, or expose a document to an AI system.
