# ThreadEye Evidence Assistant — Judge Demonstration

## Demonstration boundary

This is an independently operated localhost companion over fictional synthetic evidence. It does not modify the
original ThreadEye fabric-inspection application, inspect fabric, issue a roll verdict, change four-point scores,
access production/Supabase data or generate answers with an LLM.

The actual query path is:

```text
Browser session
  → localhost Starlette backend-for-frontend
  → official MCP SDK Client
  → authenticated Streamable HTTP at 127.0.0.1
  → fixed read-only MCP tools
  → hybrid retrieval / extractive answer / citation validation
  → authorized synthetic PostgreSQL/pgvector rows
```

## Secure local launch

1. Create `.env.db` from `.env.db.example`, set local-only passwords and start the isolated database:

   ```bash
   docker compose --env-file .env.db up -d --wait
   ```

2. Export the main/admin/read-only database URLs, `THREADEYE_EVIDENCE_MCP_CONFIG=$PWD/config/mcp-synthetic.json`
   and `THREADEYE_EVIDENCE_MODEL_CACHE=$PWD/build/model-cache` as described in the README. Run the database setup
   command to ensure `threadeye_evidence_mcp` is SELECT-only.
3. Enter a 12–128 character local access code without echoing it and launch:

   ```bash
   read -s THREADEYE_EVIDENCE_UI_ACCESS_CODE
   export THREADEYE_EVIDENCE_UI_ACCESS_CODE
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
     .venv/bin/python -m threadeye_evidence.ui.launcher
   ```

4. Open `http://127.0.0.1:8770`, enter the same code, and wait for the real `MCP connected` indicator.
5. Press Ctrl-C to stop the UI and its owned MCP subprocess cleanly. Stop the database without deleting it using
   `docker compose --env-file .env.db down`.

The launcher creates temporary mode-0600 MCP configuration/public-key files and an in-memory private signing key.
Nothing is written to browser storage. The browser gets a host-only HttpOnly SameSite=Strict session cookie plus a
CSRF token. Plain HTTP localhost prevents a `Secure` cookie; this is one reason the interface is not production-ready.

## Guided workflow 1 — supported hybrid search

- Fixed evaluation query: `content hash sanitized observation`
- Mode: `hybrid`
- Top-k: `3`
- Actual result: three authorized results from `technical-evidence.md`
- Actual top chunk: `e1569f1c868b8657f838f33e`
- Top-branch ranks: keyword 1 and vector 1
- Actual top RRF score: `0.03278688524590164`

RRF is displayed as ranking information, not a probability or confidence. The result came through the genuine MCP
`search_evidence` tool and the top passage was independently retrieved by both branches.

## Guided workflow 2 — grounded extractive answer

- Question: `Which supplier lot is recorded for ROLL-NST-204?`
- Actual state: `ANSWERED`
- Actual answer: `In the fictional receiving workflow, an operator records roll identifier ROLL-NST-204, declared length, fabric construction, supplier lot LOT-FX-17, and arrival timestamp.`
- Source identifier: `technical-evidence.md`
- Chunk: `f53285a64a29b46ed7e52aad`
- Heading: `Fictional Mill Evidence Packet › Fabric Receiving`
- Normalized span: `242–413`
- Citation validation: true

The displayed answer exactly equals its cited excerpt. Citation inspection exposes only sanitized identifiers,
provenance and normalized locations; it cannot read an arbitrary file.

## Guided workflow 3 — safe abstention

- Question: `What is tomorrow's weather in Dhaka?`
- Actual state: `ABSTAINED`
- Service status: `insufficient_evidence`
- Reason: `insufficient_relevance`
- Answer: null
- Citations: zero

No fallback or invented answer is displayed.

## Browser evidence

The existing Playwright 1.63 runtime drove installed Google Chrome headlessly against the real local services.
Desktop was 1440×1000; mobile was 390×844. Both connected to MCP and had no horizontal overflow. The run observed no
console errors, no local-storage keys, one HttpOnly Strict session cookie, three search result cards, one validated
citation, `ANSWERED` and `ABSTAINED` states.

- `docs/evidence/screenshots/prompt10-overview-desktop.png`
- `docs/evidence/screenshots/prompt10-search-desktop.png`
- `docs/evidence/screenshots/prompt10-citation-desktop.png`
- `docs/evidence/screenshots/prompt10-abstention-desktop.png`
- `docs/evidence/screenshots/prompt10-overview-mobile.png`

## Tests

Run the full genuine integration suite after exporting the trusted values:

```bash
THREADEYE_RUN_MODEL_TESTS=1 \
THREADEYE_RUN_DB_TESTS=1 \
THREADEYE_RUN_MCP_TESTS=1 \
THREADEYE_RUN_HTTP_TESTS=1 \
THREADEYE_RUN_UI_TESTS=1 \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
.venv/bin/python -m unittest discover -s tests -v
```

The verified final run is 175 passed, zero failed and zero skipped. It preserves real BGE, PostgreSQL/pgvector,
stdio MCP, authenticated HTTP MCP, dedicated read-only database-role and previous evaluation coverage.

## Troubleshooting

- `configured localhost port is unavailable`: stop the old local process or set distinct
  `THREADEYE_EVIDENCE_MCP_HTTP_PORT` and `THREADEYE_EVIDENCE_UI_PORT` values.
- `startup failed safely`: confirm all three trusted MCP environment values and the operator access code exist.
- `MCP unavailable`: do not treat the UI as connected; inspect sanitized local audit output and database health.
- Login rejected: use the exact `127.0.0.1` URL and the operator-provided code; `localhost` is intentionally rejected.

## Known limitations

This is local single-process session control, not production identity, TLS, OAuth onboarding, token revocation,
distributed rate limiting or public deployment. It uses synthetic evidence only. Retrieval and deterministic
extraction do not prove factory outcomes or ROI. Human verification remains recommended.
