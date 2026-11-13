# Final Pull Request Readiness Package

## Base-branch analysis

Read-only analysis on 2026-11-13 found:

- Feature: `feature/threadeye-evidence-assistant`, originally based on `a0c71415d3daa172b44aef643031def2d16844df`.
- `mohammad` and `origin/mohammad`: `a0c71415d3daa172b44aef643031def2d16844df`.
- `main` and `origin/main`: `ca6faac0736d71c20143eb389dc255a60ce98077`.
- Merge base with `mohammad`: its tip, `a0c7141`.
- Merge base with `main`: its tip, `ca6faac`.
- Before Prompt 12, `mohammad..feature` contained 10 commits / 151 paths; `main..feature` contained 11 commits /
  160 paths.
- The extra commit relative to `main` is Prompt 02 foundation commit `a0c7141`. Inspection found its `main` diff
  confined to `threadeye-evidence-assistant/`; no unrelated Mohammad-branch application change was detected.

Technical recommendation: use **`main`** if the team wants one complete PR containing Prompt 02 foundation through
Prompt 12. Using `mohammad` omits Prompt 02 from the PR diff because the foundation is already in that base. This is
not authorization: the team leader must confirm the actual target and whether `a0c7141` is intended for `main`.

Questions for the team leader:

1. Is `main` the authorized base, and should Prompt 02 commit `a0c7141` be included?
2. May the local feature branch be published to `origin`?
3. Will judges receive repository access, or must the repository become public after a secret/license review?
4. Who owns final YouTube, Figma, deployment and form verification?
5. Which remote CI checks and reviewers are required before merge?

No merge, rebase, reset, cherry-pick, push, PR or deployment was performed.

## Copy-ready pull request

**Title**

`feat: add isolated ThreadEye Evidence Assistant with verified retrieval, MCP, and judge UI`

**Body**

### Summary

Adds an isolated, synthetic-evidence companion that inventories approved documentation, performs real local BGE and
PostgreSQL/pgvector hybrid retrieval, returns conservative extractive answers with exact citations, exposes one
read-only MCP server over stdio/authenticated localhost HTTP, and supplies a localhost judge UI. It also adds the
CloudCamp evidence and release-review package.

### Motivation

Judges and reviewers need reproducible technical evidence without granting a new system access to ThreadEye
production data or changing the operational fabric-inspection product.

### Original ThreadEye core protection

- All tracked changes are inside `threadeye-evidence-assistant/`.
- Seven protected original-core hashes match their approved baseline.
- No original backend/frontend, model weights, scoring, RBAC, audit, schema, deployment or CI file changes.
- All six real-document ingestion approvals remain false.

### Companion architecture

- Explicit six-document metadata inventory and fixed synthetic allowlists.
- Path traversal/symlink protection, hashing, approval checks, sanitization and provenance.
- Isolated PostgreSQL/pgvector database; no Supabase or production connection.

### Evidence ingestion policy

Content ingestion requires independent inventory and ingestion approval, documented authorization, exact intended-use
match and source-hash verification. Only approved fictional evidence is indexed in demonstrations/tests.

### Embedding/vector stack

Pinned BGE CPU embeddings with recorded profile/model cache and genuine inference tests; PostgreSQL 17 plus pgvector
0.8.7 in an isolated local service.

### Hybrid retrieval

Independent PostgreSQL full-text and cosine-vector branches combined with weighted reciprocal-rank fusion. RRF is a
ranking score, not probability or confidence.

### Extractive answering and citations

Deterministic passage extraction, statement sufficiency checks, exact normalized spans, validated citations and
explicit abstention. No generative LLM, advanced RAG variant or neural reranker is included.

### MCP stdio and HTTP

One official-Python-SDK server exposes four fixed read-only tools and three sanitized resources. Genuine official
clients exercise both stdio and authenticated Streamable HTTP; they are two transports of the same server.

### Authentication and read-only database

Local HTTP verifies EdDSA tokens and operation scopes, rate limits requests and records sanitized events. The service
database identity has SELECT-only privileges and read-only transactions. This is not complete OAuth onboarding or a
public service.

### Judge UI

Loopback-only UI with operator-controlled access, server-side MCP calls, HttpOnly SameSite=Strict session cookie,
CSRF/Host/Origin/body-size controls, safe rendering and responsive search/answer/abstention workflows.

### Real regression tests

Current all-flags local run: 190 tests passed, zero failed and zero skipped with genuine BGE, PostgreSQL/pgvector,
MCP stdio, authenticated HTTP, read-only database and UI integrations. Current real Chrome/Playwright run passed
desktop and mobile workflows plus negative security paths.

### Security evaluation

Development set: 30/30 exact. Examined final holdout: 29/30; 0/2 attack successes and 7/7 injected failures handled.
These are fictional automated fixtures, not a comprehensive security certification.

### Reliability limitations

Prompt 11 first holdout was 5/10 and examined post-fix was 8/10. Prompt 11R known QA is 9/10 with one conservative
false abstention; fresh first run was 10/12 and examined post-fix is 12/12. Small synthetic datasets have no
independent human label review and cannot establish general/factory accuracy.

### Reproduction commands

See `threadeye-evidence-assistant/README.md`, `docs/cloudcamp/JUDGE_DEMO.md` and
`docs/cloudcamp/TECHNICAL_EVIDENCE.md`. Local secrets must remain in ignored environment files.

### Reviewer checklist

- [ ] Confirm every changed path is inside the companion directory.
- [ ] Confirm the intended PR base includes Prompt 02 exactly once.
- [ ] Recompute seven protected hashes and six ingestion flags.
- [ ] Run 190-test all-flags suite with genuine local integrations.
- [ ] Inspect current evaluation JSON/history; distinguish first runs from examined reruns.
- [ ] Run browser search, citation and abstention workflows.
- [ ] Verify database role is read-only and negative authorization cases fail closed.
- [ ] Scan tracked changes and screenshots for secrets/private data.
- [ ] Review licenses, especially the recorded AITEX redistribution question.

### Known limitations

Localhost demonstration only; no public deployment, TLS, production identity, complete OAuth, cross-project MCP reuse,
generative LLM, factory data, factory pilot or measured ROI. Retrieval/citations and rule-based entailment still need
human review for consequential use.

### Deployment status

The companion is not deployed. The existing original hosted workflow uses a simulated detector. The trained YOLOX-S
path is local and was not rerun in Prompt 12.

### Required follow-up actions

Confirm base and publishing approval; push the feature branch; inspect remote CI; complete/license-review Figma and
YouTube proof; verify judge repository/hosted access; request team review; merge only after authorization.

## Publishing plan — do not run until approved

### GitHub Desktop

1. Fetch and confirm the current branch is `feature/threadeye-evidence-assistant`; do not switch to or commit on
   `main`.
2. Inspect the History and Changes tabs; confirm the Prompt 12 commit and a clean tree.
3. Ask the team leader to confirm the target branch (`main` is the technical recommendation).
4. Perform the documented secret/license review.
5. After explicit approval, select **Publish branch**. Do not force-push.
6. Confirm the remote branch appears, then open one **Draft Pull Request** with the title/body above and confirmed
   base.
7. Inspect all CI checks and request team-leader review. Merge only after required approval.

### Equivalent safe commands

```bash
git status --short --branch
git log -1 --oneline
git diff --name-status main...HEAD
git push -u origin feature/threadeye-evidence-assistant   # only after explicit approval
git ls-remote --heads origin feature/threadeye-evidence-assistant
```

Create the Draft PR through the approved GitHub UI after confirming the base. Never force-push or rewrite shared
history as part of this plan. A private repository requires explicit judge access; a 404 can be normal for a signed-out
reviewer but is not acceptable proof without access instructions.
