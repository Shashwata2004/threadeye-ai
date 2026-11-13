# ThreadEye Evidence Assistant — Final QA

Recorded: 2026-11-12
Scope: Prompt 11 release-candidate verification over fictional synthetic evidence only
Decision: **verified for the bounded localhost judge demonstration, with explicit semantic-relevance limitations**

## Executive summary

The Prompt 02–10 implementation is genuine rather than README-only. The final all-flags suite passed **180/180**
tests with no failures or skips. It exercised the pinned BGE model on CPU, PostgreSQL 17.11 with pgvector 0.8.7,
keyword/vector/hybrid retrieval, extractive answers, citations, security evaluation, the restricted database role,
official-SDK stdio MCP, two authenticated Streamable HTTP clients, and the UI-to-MCP path.

Prompt 11 found and fixed three companion-only release defects:

1. Valid same-origin UI POST requests bypassed the 8 KiB `Content-Length` check because of middleware control flow.
2. Three general unsafe-request wording families were not recognized before retrieval.
3. The runtime package version lagged behind `pyproject.toml`.

The new, pre-labeled QA holdout produced only 5/10 exact outcomes on its untouched first execution. Three general
policy fixes improved the now-examined regression rerun to 8/10 without changing thresholds or historical datasets.
One false answer and one false abstention remain. This is a material limitation: verified citations ensure provenance
and extractive support, but do not alone prove that the passage semantically answers the question.

## Git state and boundaries

- Required branch: `feature/threadeye-evidence-assistant`
- Verified starting HEAD: `cd3cde7f475772df451bd31ed3dfe93215c45c01`
- Correct Prompt 02 ancestry baseline: `a0c7141`
- Starting tree: clean
- Prompt 03–11 diff command: `git diff --name-only a0c7141 --`
- Result: every changed path begins with `threadeye-evidence-assistant/`; no original application path changed.
- No push, merge, rebase, reset, pull request, deployment, production Supabase connection, or Prompt 12 work occurred.

The frozen 144-path list is in `docs/evidence/prompt11-full-diff-paths.txt` and is reproducible with the command above.
It covers only the companion's configuration, documentation, synthetic fixtures, evaluation sets, migrations, Python
package, and tests. The review also ran
`git diff --name-only a0c7141 -- | awk '$0 !~ /^threadeye-evidence-assistant\//'`; it returned no paths.

## Prompt 02–10 implementation inventory

| Capability | Implementation | Actual verification | Dependencies | Status / limitation |
|---|---|---|---|---|
| Secure source inventory | `corpus/allowlist.py`, `inventory.py`, `hashing.py`, `knowledge/manifest.json` | allowlist, traversal, symlink, size, read-only and hashing tests | Python stdlib | Implemented; six real files are metadata-inventory only |
| Approval-gated ingestion | `corpus/ingestion.py`, `sanitization.py`, `normalization.py`, `chunking.py` | ingestion, authorization, sanitization, normalization and chunking tests | Python stdlib | Implemented; synthetic fixtures only |
| Embeddings | `vector/embeddings.py` | genuine BGE CPU repeatability and 384-dimensional integration tests | FastEmbed 0.9.1, ONNX Runtime 1.31.1 | Implemented; pinned cache required offline |
| Isolated vector DB | `compose.yaml`, migrations, `vector/database.py`, `indexing.py` | PostgreSQL/pgvector migration, idempotency, rollback, profile and provenance tests | PostgreSQL 17.11, pgvector 0.8.7 | Implemented on loopback-only companion DB |
| Keyword retrieval | `retrieval/store.py`, migration 002 | real generated `tsvector`, GIN and SQL ranking tests | PostgreSQL full-text search | Implemented; English stemming and small synthetic corpus |
| Vector retrieval | `retrieval/store.py`, `vector/indexing.py` | genuine model insert/query and profile-isolation tests | BGE + pgvector | Implemented; exact scan, not ANN |
| Hybrid/RRF | `retrieval/engine.py`, `fusion.py` | both branches, weighted one-based RRF, deterministic tie and 35-query benchmark | keyword + vector backends | Implemented; ranking scores are not probabilities |
| Extractive answering | `answering/engine.py`, `extractive.py`, `abstention.py` | 44-case benchmark plus real DB integration | retrieval layer | Implemented; no generative LLM |
| Citation validation | `answering/citations.py` | hash, span, scope, profile, tamper and exact-extract tests | stored sanitized chunks | Implemented; semantic relevance still needs review |
| Abstention | `answering/abstention.py`, `policy.py` | unsupported, ambiguous, unsafe and contradictory cases | fixed policy/thresholds | Implemented but not perfect on new phrasing |
| Adversarial guards | `security/`, `evaluation/security-v1.json` | 60-case evaluation and injected failure tests | synthetic fixtures only | Implemented defense-in-depth, not comprehensive resistance |
| MCP stdio | `mcp/server.py`, `service.py`, `verify_client.py` | genuine official-SDK subprocess lifecycle | MCP 2.3.0 | Implemented; launcher authority is process-local |
| MCP HTTP | `mcp/http_server.py`, `http_authorization.py`, `http_security.py`, `verify_http.py` | two official clients, JWT and HTTP negatives, restart | MCP, PyJWT, Ed25519 | Implemented on localhost; no external OAuth interoperability |
| Authorization scopes | retrieval policies plus MCP request context | cross-corpus, unknown argument, restricted-principal tests | server-owned configuration | Implemented and fail closed |
| Read-only database role | `mcp/database.py`, `docker/init/001-companion-role.sh` | real SQL identity/grant denial tests | `threadeye_evidence_mcp` | Implemented; DB administrator compromise is out of scope |
| Judge UI / browser | `ui/`, `tests/browser_prompt11.cjs` | real Chrome desktop/mobile workflow through MCP HTTP | Starlette, Uvicorn, Playwright/Chrome | Implemented for localhost demonstration only |

No capability in this table is marked verified solely because it is documented.

## Test environment

| Component | Measured version |
|---|---|
| macOS | 27.2.1 (26B131) |
| Python | 3.11.17 |
| FastEmbed / ONNX Runtime | 0.9.1 / 1.31.1 |
| PostgreSQL / pgvector server | 17.11 / 0.8.7 |
| psycopg / pgvector client | 3.3.8 / 0.5.1 |
| MCP SDK | 2.3.0 |
| Starlette / Uvicorn | 1.10.0 / 0.54.0 |
| PyJWT / cryptography | 2.15.1 / 50.0.2 |
| Node / Playwright / Chrome | 26.10.0 / 1.63.0 / 157.0.8103.39 |
| Docker | 29.9.2 |

The working virtualenv's installed distribution metadata was stale before QA (`0.8.0`) while source execution used
the checkout. A clean install reported `0.9.0`; Prompt 11 aligned package `__version__` with that project version.
MCP server `0.8.0` and UI `0.9.0` remain intentionally separately versioned components.

## Full regression

The start-of-task unmodified Prompt 10 baseline ran 175 tests in 9.152 seconds (9.95 seconds wall), with zero
failures and zero skips. The final command was:

```bash
THREADEYE_RUN_MODEL_TESTS=1 \
THREADEYE_RUN_DB_TESTS=1 \
THREADEYE_RUN_MCP_TESTS=1 \
THREADEYE_RUN_HTTP_TESTS=1 \
THREADEYE_RUN_UI_TESTS=1 \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
.venv/bin/python -m unittest discover -s tests
```

Final result: **180 passed, 0 failed, 0 skipped**, 9.999 test seconds and 10.92 wall seconds. The five additional
tests cover the fixed QA holdout schema/integration, request-policy wording, request-size enforcement, and release
version metadata. No passing result was inferred from prior reports.

## Genuine pipeline and evaluation

The all-flags suite and explicit CLI runs exercised:

```text
approved technical-evidence.md
  → hash/authorization/sanitization/chunking
  → pinned BGE-small-en-v1.5 CPU embedding
  → isolated pgvector rows
  → PostgreSQL keyword + vector branches
  → weighted RRF
  → deterministic exact extraction
  → citation revalidation
  → fixed MCP tool
  → authenticated Streamable HTTP
  → Starlette backend-for-frontend
  → real Chrome display
```

The serving corpus and every displayed passage were synthetic. There is no alternate UI retrieval implementation.

Measured historical regressions:

- Retrieval v1, 35 queries: hybrid Hit@1 0.906, Hit@3 1.000, Recall@5 1.000, MRR 0.948; average hybrid query
  latency 36.701 ms.
- Answer v1 held-out, 24 cases: answerability, correct abstention, citation validity/precision/source correctness and
  structured validity all 1.000; average 54.591 ms; false-answer and false-abstention rates 0.
- Security v1: development 30/30 exact, 0/2 attack success, 7/7 injected failures correct; historical final holdout
  29/30, 0/2 attack success, 7/7 injected failures correct.

The security holdout is not represented as untouched: its first Prompt 07 run was 27/30 and later general fixes made
it 29/30. The known false abstention remains documented and the 60-case file was not edited in Prompt 11.

## New Prompt 11 holdout

`evaluation/qa-holdout-v1.json` contains ten independently worded synthetic cases: five positive and five negative.
Labels were written before first execution; every case carries a human semantic-review marker; threshold tuning is
forbidden; an automated loader rejects exact reuse of historical benchmark questions.

| Run | Exact | False answers | False abstentions | Valid citations | Runtime failures |
|---|---:|---:|---:|---:|---:|
| First independent execution | 5/10 | 3/5 | 1/5 | 7/7 returned answers | 0 |
| Examined regression after general policy fixes | 8/10 | 1/5 | 1/5 | 5/5 returned answers | 0 |

The fixes recognize credential-disclosure verbs, noun-form shipment approval requests, and attempts to elevate
embedded Markdown as authority. They do not change retrieval thresholds. The two remaining misses are:

- `QA11-P03`: a valid scoring-normalization question falsely abstains (`insufficient_relevance`).
- `QA11-N01`: an unsupported spindle-speed question receives a valid exact extract from an irrelevant section.

The second run is explicitly an examined regression, not a new independent score. Manual factual review remains
required and no factory-accuracy claim follows from this dataset.

## MCP and database verification

The official SDK stdio client negotiated protocol `2025-11-25`, completed search, a cited answer and abstention, denied
an unauthorized scope argument and nonexistent `delete_roll`, and terminated its subprocess.

The registry was exactly:

- Tools: `search_evidence`, `answer_evidence_question`, `list_evidence_sources`, `get_evidence_capabilities`
- Resources: `threadeye://evidence/capabilities`, `threadeye://evidence/corpus-manifest`,
  `threadeye://evidence/security-policy`

Two official HTTP clients independently authenticated. The full-scope client searched and answered; the metadata-only
client could read metadata but was denied search and answer without evidence leakage. Missing, malformed, unsigned,
expired, wrong-key, wrong-algorithm, wrong-issuer, wrong-audience, wrong-token-type, wrong-principal and wrong-scope
tokens all returned 401. Host, Origin, duplicate Authorization, body size, token size and method controls returned the
expected 421/403/400/413/431/405 responses. Rate limiting returned 429 then recovered to 200. A clean shutdown/restart
accepted protected metadata. Sanitized logs excluded raw tokens, private keys, DB passwords and raw questions.

The real runtime identity was `threadeye_evidence_mcp`; `transaction_read_only` was `on`. SELECT succeeded. INSERT,
UPDATE, DELETE, TRUNCATE, schema DDL, temporary-table DDL, CREATE ROLE and CREATE DATABASE failed. The role was not a
superuser and had no create-database, create-role or inheritance permission. Both MCP transports use this restricted
DSN. No write tool exists.

## Failure isolation and recovery

| Failure | Evidence | Safe result / recovery |
|---|---|---|
| DB unavailable / service stopped | `test_security_hardening` | structured retrieval error; no answer or degraded fallback |
| DB timeout | same | bounded injected timeout; no answer |
| Embedding unavailable | same | retrieval error, no fallback |
| Keyword, vector, or invalid profile | same plus hybrid tests | either branch failure fails the hybrid request closed |
| Both retrieval paths unavailable | DB/service fault | no partial claim |
| Citation tamper | security and citation suites | `citation_validation_failed`, no answer/citations |
| MCP stdio disconnect/shutdown | real verifier | client context terminated child cleanly |
| HTTP unavailable / restart | HTTP verifier, UI gateway tests | explicit backend-unavailable state; restart verified |
| Invalid/expired/wrong-scope bearer | HTTP negative matrix | 401 or tool denial, no evidence leakage |
| UI session expiry / CSRF | UI security tests and browser | 401/403; no request execution |
| Excessive body | browser plus regression test | 413 after Prompt 11 middleware fix |
| Rate exhaustion | real HTTP verifier | 429 then 200 after bounded window |
| Excess concurrency / cancellation | HTTP security tests | immediate 429; capacity released after cancellation |
| Browser disconnect / logout | browser context close and logout | session revoked; API returns 401 |
| Shutdown/restart | launcher and real HTTP verifier | owned child terminated; restarted endpoint becomes ready |

The known stuck-native-worker limitation remains: cancelling or timing out an async wrapper cannot forcibly stop a
native thread that ignores cancellation. DB statements and transport operations have lower-level timeouts, but there
is no process-isolated worker kill boundary. No indefinitely blocking process was created during QA.

## Browser E2E

The browser skill's preferred in-app `node_repl` runtime was not available in this session. The committed QA script
therefore used existing Playwright 1.63 with installed Chrome, against the actual launcher-owned MCP HTTP process.

It passed at 1440×1000 and 390×844. Covered behavior included invalid and valid login, MCP connection, HttpOnly Strict
session cookie, empty local/session storage, skip-link keyboard focus, live status regions, unauthorized API access,
real hybrid search, source metadata, supported extractive answer, focused citation dialog, exact supporting excerpt,
safe abstention, unexpected-field/CSRF/oversize rejection, logout invalidation, and desktop/mobile overflow checks.
Successful flows produced no console errors. Three intentional negative HTTP requests produced the expected browser
network-console entries for 400, 403 and 413.

Measured single-run timings (not production benchmarks): login plus overview 376 ms; search interaction 1,699 ms;
answer interaction 1,605 ms; browser-script workflow 8,197 ms. These include local browser/UI/MCP overhead and are not
statistically representative.

Screenshots:

- `docs/evidence/screenshots/prompt11-invalid-login.png`
- `docs/evidence/screenshots/prompt11-overview-desktop.png`
- `docs/evidence/screenshots/prompt11-search-desktop.png`
- `docs/evidence/screenshots/prompt11-citation-desktop.png`
- `docs/evidence/screenshots/prompt11-abstention-desktop.png`
- `docs/evidence/screenshots/prompt11-overview-mobile.png`

## Clean-environment reproducibility

A disposable Python 3.11.17 virtualenv installed `requirements-vector.lock`, installed the package without dependency
resolution, imported the CLI and ran 23 focused inventory/QA/UI tests: all passed. The temporary directory was removed.
This proves a clean Python install, not a completely cold machine: the real integration verification used the existing
isolated PostgreSQL container and pre-existing pinned offline model cache. A full cold model download and new Docker
volume were deliberately not performed, so those remain qualified rather than claimed.

Required runtime inputs remain explicit and secret-free in documentation:
`THREADEYE_EVIDENCE_DATABASE_URL`, `THREADEYE_EVIDENCE_ADMIN_DATABASE_URL`,
`THREADEYE_EVIDENCE_MCP_DATABASE_URL`, `THREADEYE_EVIDENCE_MCP_CONFIG`,
`THREADEYE_EVIDENCE_MODEL_CACHE`, and an operator-entered `THREADEYE_EVIDENCE_UI_ACCESS_CODE`.

## Original ThreadEye regression and integrity

No production service or real operational data was used. An isolated temporary PostgreSQL 16.4 container on a distinct
port ran original backend integration tests and was removed afterward.

- Backend unit: 213 passed, 0 failed, 0 skipped, 29.04 seconds.
- Backend integration: 77 passed, 0 failed, 1 skipped, 45.38 seconds. The skipped edge clip-export test requires
  `ffmpeg`, which was not installed.
- Frontend `pnpm check`: i18n parity passed with 338 keys in each locale; ESLint and TypeScript passed, 17.37 seconds.
- Deterministic four-point scoring/verdict, RBAC, audit-chain/append-only behavior, reports and operational workflows
  were covered by those existing tests.
- Local-model tests used a fake forward pass and verified model contract/tiling/stitching. **Real YOLOX ONNX inference
  was not rerun**, so Prompt 11 makes no such claim.

All seven protected hashes exactly match the required baseline:

| Path | SHA-256 |
|---|---|
| `backend/threadeye/core/scoring/four_point.py` | `c4ed4d7e633c961707816d2377440cdcdbc39bd0c80bab0be9f183970756c284` |
| `backend/threadeye/core/providers.py` | `293c3509fcfff31726bf4c392e022ad328d95b79381fc78ca4be6d92d1f4ac9a` |
| `backend/threadeye/providers/local_model.py` | `f11d1e5bd44f60022e032e506c48c340e1e98741c424d122d340c4ff69b63878` |
| `backend/threadeye/db/audit.py` | `afe8080aeb2d44b45394090ceab2a9ec9cefa3b7c6b4463111801b37a7befd7e` |
| `backend/threadeye/security/rbac.py` | `02c00191c6f9b363cf51eb212cef1fcda00a024b7a2a352c93c05fc697abaf9f` |
| `backend/pyproject.toml` | `176a3601e820a8b719923617c7e3d0681eab63a452034885220cab6bba2b167c` |
| `frontend/package.json` | `405f04a8c9d59db1285c056188b369fd990275153f6fd63ae1351ec1fd11840a` |

## Privacy and real-document approval

All six real document entries (`README.md`, `PROVENANCE.md`, `docs/PLAN.md`, `docs/MILESTONES.md`,
`docs/VALIDATION.md`, `ml/DATASETS.md`) still have `future_ingestion_approved=false`. They were not read through the
ingestion path, embedded, indexed, exposed by MCP or displayed in the UI. Inventory approval and content-ingestion
approval remain separate, and serving authorization is a third independent control.

The companion scan found no absolute user paths, credential-shaped tokens, tracked model/cache artifacts or real
secrets. Two private-key markers are intentional fictional unit-test inputs. DSN matches are environment placeholders
or fictional test values. `.env.db` and the model cache remain ignored. Screenshot hashes are recorded in the JSON
artifact. No MCP/UI listeners remained after the run.

## CloudCamp evidence readiness

Truthfully supported: real BGE embeddings, semantic chunking, isolated pgvector, PostgreSQL keyword search, hybrid RRF,
citation-grounded extraction, abstention, one read-only MCP server over two transports, authenticated localhost HTTP,
actual MCP use by the UI, real browser evidence, and reproducible security/QA tests.

Unsupported and prohibited claims: generative LLM-RAG, a local generative LLM, multiple custom MCP servers,
independent cross-project MCP reuse, Graph/agentic RAG, public production deployment, comprehensive injection
resistance, production factory accuracy, and verified factory ROI.

Remaining non-code submission blockers are a public/unlisted YouTube demonstration, a clickable original ThreadEye
Figma prototype, judge-accessible repository strategy, final official submission fields, team-leader review and final
GitHub CI after a team-approved PR. Prompt 11 does not predict CloudCamp points.

## Release-candidate checklist

- [x] Correct start branch/HEAD and clean baseline
- [x] Prompt 02 ancestry confirmed
- [x] Complete all-flags regression passed
- [x] Genuine BGE/PostgreSQL/pgvector passed
- [x] Official stdio and HTTP MCP clients passed
- [x] Exact read-only MCP registry confirmed
- [x] Restricted DB write operations denied
- [x] Real MCP-backed browser desktop/mobile flow passed
- [x] Historical security results preserved
- [x] New holdout first result and post-fix rerun reported separately
- [x] Controlled failures fail closed; stuck-worker limit retained
- [x] Original backend/frontend isolated regressions run
- [x] Seven protected hashes match
- [x] Full Prompt 03–11 diff is companion-only
- [x] Six real ingestion flags remain false
- [x] Clean Python install tested with explicit qualification
- [x] Secret/privacy scan completed
- [x] No production access, push, merge, PR or deployment

## Residual risks and Prompt 12 readiness

The bounded synthetic judge demonstration passes Prompt 11 acceptance with the limitations above. It is not a
production release. The new holdout's remaining semantic false answer is the most important technical risk; a future
stage should investigate relevance calibration using a separate development set, never tune against this examined
holdout, and preserve false-answer reporting.

Prompt 12 may be planned only after team review of this report, the remaining relevance risk and the local commit. No
Prompt 12 implementation was started.

Machine-readable details: `docs/evidence/prompt11-qa-verification.json`.
