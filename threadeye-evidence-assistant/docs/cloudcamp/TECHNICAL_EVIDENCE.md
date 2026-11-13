# Technical Evidence and Capability Inventory

## Prompt 01–11R inventory

| Stage | Capability and status | Code location | Tests / command | Evidence | Limit and eligible claim |
|---|---|---|---|---|---|
| 01 | Original-core audit and gap analysis — historically documented | `knowledge/protected-core-baseline.json`, root plans | Protected-hash command in `VERIFICATION.json` | Prompt history and baseline | Claim audit/protection, not a runtime feature |
| 02 | Six-document allowlist and read-only inventory — implemented and verified | `corpus/allowlist.py`, `inventory.py`, `hashing.py` | `tests/test_allowlist.py`, `test_inventory.py`, `test_read_only.py` | `READ_ONLY_CONTRACT.md` | Inventory approval is not ingestion approval |
| 03 | Approval-gated sanitization, normalization and heading-aware variable chunking — implemented and verified | `corpus/ingestion.py`, `sanitization.py`, `normalization.py`, `chunking.py` | ingestion/sanitization/chunking tests | `INGESTION.md` | Synthetic approved content only |
| 04 | Real pinned BGE CPU embeddings and isolated PostgreSQL/pgvector — executed | `vector/embeddings.py`, `database.py`, `indexing.py`, migrations | all-flags suite; real embedding/pgvector tests | `VECTOR_INDEXING.md` | Exact small-corpus search; no ANN claim |
| 05 | PostgreSQL keyword, vector and weighted RRF hybrid retrieval — executed | `retrieval/store.py`, `engine.py`, `fusion.py` | 35-query evaluation | `HYBRID_RETRIEVAL.md` | RRF is ranking, not probability/confidence |
| 06 | Deterministic grounded extraction, citation validation and abstention — executed | `answering/engine.py`, `extractive.py`, `citations.py`, `abstention.py` | 44-case answer evaluation | `ANSWERING.md` | No generative LLM |
| 07 | Adversarial security evaluation and failure isolation — executed | `security/evaluation.py`, `faults.py`, answer policy | 30/30 development, 29/30 examined holdout | `SECURITY_EVALUATION.md` | Synthetic attacks; not comprehensive immunity |
| 08 | One official-SDK read-only MCP server over stdio — executed | `mcp/server.py`, `service.py`, `verify_client.py` | official-client integration | `MCP_SERVER.md` | One server, fixed scope |
| 09 | Authenticated Streamable HTTP transport — executed | `mcp/http_server.py`, authorization/security modules, `verify_http.py` | two official clients and negative matrix | `MCP_HTTP.md`, Prompt 09 JSON | Local resource-server demo, not complete OAuth/public service |
| 10 | Secure localhost judge UI — executed, including current Chrome run | `ui/` and `tests/browser_prompt11.cjs` | UI integration plus Playwright/Chrome | screenshots and Prompt 10 JSON | Local session boundary only |
| 11 | End-to-end QA, original-core regression evidence and reproducibility — historically and currently verified where rerun | QA module and release tests | current 190-test suite; historical original-app checks | `FINAL_QA.md`, Prompt 11 JSON | Original application tests were not rerun in Prompt 12 |
| 11R | Statement-level reliability remediation and fresh evaluation — implemented and verified | answer policy/sufficiency/citations, `reliability/evaluation.py` | known QA 9/10; examined reliability 12/12 | `ANSWER_RELIABILITY_REVIEW.md`, Prompt 11R JSON | First fresh result remains 10/12; no general 100% claim |

## Current reproducible results

| Evaluation | Prompt 12 result |
|---|---|
| Companion all-flags suite | 190 passed, 0 failed, 0 skipped; final run 10.919 test seconds |
| Retrieval v1 | 35 queries; hybrid Hit@1 0.906, Hit@3/5 and Recall@5 1.000, MRR 0.948; 0 failures |
| Answer v1 development | 20/20 answerability; 0 false answers/abstentions; citation validity 1.000 |
| Answer v1 held-out | 24/24 answerability; 0 false answers/abstentions; citation validity 1.000 |
| Security development | 30/30 exact; 0/2 attack success; 7/7 injected failures correct |
| Security examined holdout | 29/30 exact; 0/2 attack success; 7/7 injected failures correct |
| Known QA | 9/10; 0/5 false answers; 1/5 false abstentions; 4/4 citation validity |
| Reliability development regression | 12/12 examined rerun |
| Reliability fresh history | First run 10/12; post-fix examined reruns 12/12 |
| Real browser | Passed Chrome/Playwright search, answer, citation, abstention, auth/CSRF/size checks and shutdown |

## Safe RAG wording

Use:

> ThreadEye Evidence Assistant implements a retrieval-and-extraction pipeline: deterministic heading-aware chunks,
> pinned BGE embeddings, PostgreSQL full-text and pgvector retrieval, weighted reciprocal-rank fusion, safe
> abstention, and exact citation-validated extractive answers over authorized fictional evidence.

Do not claim generative Naive RAG, a local generative LLM, contextual/Graph/Self/Corrective/agentic RAG, neural
reranking, autonomous agents or production knowledge integration. Embeddings are not proof that a local generative LLM
ran.

## MCP built/used summary

- Built: **one** custom `threadeye-evidence` MCP server using the official Python SDK.
- Fixed tools: `search_evidence`, `answer_evidence_question`, `list_evidence_sources`,
  `get_evidence_capabilities`.
- Sanitized resources: capabilities, corpus manifest and security policy.
- Used: genuine official client calls through stdio and authenticated Streamable HTTP.
- Auth: two independent local client contexts, request scopes, negative authorization tests.
- Data boundary: dedicated `threadeye_evidence_mcp` identity with SELECT-only access and read-only transactions.
- Stdio and HTTP are transports of the same server, not two custom servers.
- No public deployment, complete external OAuth onboarding, production integration or cross-project reuse is proven.

## AI-native development and provenance

| Tool / evidence | Verified statement | Excluded inference |
|---|---|---|
| Claude Code and prompt library | Root `TOOLING.md` and `PROMPTS.md` document planning and early implementation | Not Claude Artifacts |
| Codex | Root tooling/prompt history and companion commit history document implementation/review assistance | Not a runtime product agent or formal agent framework |
| GitHub Actions | CI, keepalive and manual smoke workflow files exist | Current feature branch has not passed remote CI |
| GNU Make | Root Makefile provides build/test/demo tasks | Not Make.com |
| Kaggle | Private/public notebook references and work logs document training orchestration | A URL or submission state alone is not model-quality proof |
| Vercel CLI | Deployment script and responding public frontend/API URLs exist | Deployed revision and authenticated workflow were not verified here |
| Playwright/Chrome | Current real browser verification executed | Not production monitoring |
| MCP tooling | Original Claude built-ins are disclosed; one product MCP server is now built and used | No multiple-server or reuse bonus claim |

## Core commands

```bash
# All companion integrations after trusted local environment is exported
THREADEYE_RUN_MODEL_TESTS=1 \
THREADEYE_RUN_DB_TESTS=1 \
THREADEYE_RUN_MCP_TESTS=1 \
THREADEYE_RUN_HTTP_TESTS=1 \
THREADEYE_RUN_UI_TESTS=1 \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v

PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-retrieval --offline-model --format summary
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-answers --split held_out --offline-model --format summary
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-security --split final_holdout --offline-model --format summary
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-qa-holdout --offline-model --format summary
```
