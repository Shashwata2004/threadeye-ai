# CloudCamp Evidence Pack

Recorded: 2026-11-13

Purpose: provide a truthful, reproducible submission and team-review package for the original ThreadEye product and
its isolated Evidence Assistant. This directory does not submit a form, publish a branch, create a pull request, or
claim that missing external proof exists.

## Authority and scoring boundary

The current public organizer sources checked on 2026-11-13 were:

- CloudCamp submission rules v1.1, published 2026-05-12:
  `https://cloudcampbd.com/events/ai-builders-congress/policies/submission`
- CloudCamp AI usage and provenance policy v1.1, published 2026-05-12:
  `https://cloudcampbd.com/events/ai-builders-congress/policies/ai-usage`

Both URLs returned HTTP 200. The submission rules require a one-page structured summary and a three-minute concept or
prototype video covering the problem/users, AI solution, demo or workflow, AI approach/tools/RAG/data, impact/KPIs
and next steps. They also require an AI-native approach, system flow, prototype/demo, Bangla or localization
consideration, potential impact, originality and transparent tooling/data/contribution disclosure.

The private scoring implementation and exact 425-point pre-judgment / 215-point submission formulas were not publicly
verifiable. `251/425` and `133/215` are retained only as historical screenshot values. The separate offline form
replica is not an official scoring engine.

## Evidence index

| Document | Purpose |
|---|---|
| `CLAIM_MATRIX.md` | Official-rule and historical-field claim audit with safe wording |
| `TECHNICAL_EVIDENCE.md` | Prompt 01–11R capability inventory, RAG, MCP and tooling evidence |
| `JUDGE_DEMO.md` | Reproducible two-system judge demonstration |
| `VIDEO_SCRIPT.md` | Three-minute narration, shot list and upload checklist |
| `FIGMA_CHECKLIST.md` | Required clickable original-product prototype coverage |
| `SUBMISSION_LINK_AUDIT.md` | Known, missing and blocked external proof links |
| `SUBMISSION_CHECKLIST.md` | Field-by-field form readiness and suggested wording |
| `PR_READINESS.md` | Base-branch analysis, copy-ready PR body and publishing plan |
| `RESIDUAL_RISKS.md` | Security, evidence limitations and separate readiness decisions |
| `VERIFICATION.json` | Sanitized machine-readable Prompt 12 verification snapshot |
| `BRANCH_DIFF_PATHS.txt` | Final path inventory relative to the proposed `main` base |

Existing primary evidence remains authoritative and is referenced rather than copied:

- `../FINAL_QA.md`
- `../ANSWER_RELIABILITY_REVIEW.md`
- `../HYBRID_RETRIEVAL.md`
- `../ANSWERING.md`
- `../SECURITY_EVALUATION.md`
- `../MCP_SERVER.md`
- `../MCP_HTTP.md`
- `../JUDGE_DEMO.md`
- `../evidence/prompt09-http-verification.json`
- `../evidence/prompt10-ui-verification.json`
- `../evidence/prompt11-qa-verification.json`
- `../evidence/prompt11r-answer-reliability-results.json`

## Verification snapshot

- Companion suite: 190 passed, 0 failed, 0 skipped with all genuine integration flags (final run: 10.919 seconds).
- Real Chrome through Playwright 1.63: passed at 1440×1000 and 390×844.
- Public frontend and API health URLs: HTTP 200; deployed revision and authenticated workflow not verified here.
- Public GitHub URL: HTTP 404 for an unauthenticated viewer.
- YouTube URL: missing.
- Figma URL and verified interactions: missing.
- Evidence Assistant: localhost only; no public URL.
- Protected original-core hashes: 7/7 match.
- Real-document ingestion approvals: 0/6; all six remain false.

## Truthful one-line architecture

ThreadEye is an original fabric-inspection workflow with a locally executable YOLOX-S ONNX detector, inspector
correction, deterministic four-point scoring and human approvals; its hosted demo is explicitly simulated. The
separate Evidence Assistant uses pinned BGE embeddings, PostgreSQL keyword/pgvector retrieval, weighted RRF,
deterministic extractive answers, validated citations and one read-only MCP server over stdio or authenticated local
HTTP against fictional evidence.
