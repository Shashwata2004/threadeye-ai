# Tasks: Reviewed Defect Preparation Manifest

**Input**: [spec.md](spec.md), [plan.md](plan.md)

**Status**: Planned. Progress is tracked in the checklist below.

## Phase 1 — Design and Contracts

- [ ] T001 Record decoder strategy, resource limits, overwrite rules, canonical output and exit codes in `specs/001-reviewed-defect-manifest/research.md`.
- [ ] T002 Define entities and unknown-value semantics in `specs/001-reviewed-defect-manifest/data-model.md`.
- [ ] T003 Define the versioned output schema and optional lineage contract in `specs/001-reviewed-defect-manifest/contracts/manifest.schema.json` and accompanying documentation.
- [ ] T004 Revisit constitution gates against the concrete contract in `specs/001-reviewed-defect-manifest/plan.md`.

## Phase 2 — Inventory (US1, Priority P1)

- [ ] T005 [US1] Implement bounded archive inventory, input hashing and separate output handling in `scripts/prepare_reviewed_defects.py`.
- [ ] T006 [US1] Implement reference, category, image-integrity and COCO geometry checks in `scripts/prepare_reviewed_defects.py`.
- [ ] T007 [US1] Preserve decisions, source provenance and unknown metadata; distinguish positive and review counts in `scripts/prepare_reviewed_defects.py`.
- [ ] T008 [US1] Add empty/mixed-decision, malformed-geometry, missing/corrupt-image and unsafe-ZIP cases in `backend/tests/unit/test_reviewed_defect_manifest.py`.

## Phase 3 — Source Groups (US2, Priority P2)

- [ ] T009 [US2] Implement explicit lineage ingestion, evidence hashes, shared-donor/background grouping and unassigned ambiguous splits in `scripts/prepare_reviewed_defects.py`.
- [ ] T010 [US2] Add shared-donor-across-datasets, different-seed, missing-lineage and answer-key cases in `backend/tests/unit/test_reviewed_defect_manifest.py`.

## Phase 4 — Handoff (US3, Priority P3)

- [ ] T011 [US3] Implement stable ordering, issue codes, report rendering and exit behavior in `scripts/prepare_reviewed_defects.py`.
- [ ] T012 [US3] Add determinism, unchanged-source and overwrite cases in `backend/tests/unit/test_reviewed_defect_manifest.py`.
- [ ] T013 [US3] Write actual invocation examples in `specs/001-reviewed-defect-manifest/quickstart.md` and align the Claude skill with the implemented CLI.

## Phase 5 — Validation Evidence

- [ ] T014 Run focused tests on disposable fixtures and record commands/results in `specs/001-reviewed-defect-manifest/quickstart.md`.
- [ ] T015 Exercise the Claude skill on an authorized export and record the actual invocation and unresolved issues in `TOOLING.md`.
- [ ] T016 Review acceptance criteria and update `spec.md` and `TOOLING.md` with delivered scope, leaving unmet items open.

## Dependencies

T001–T004 establish the contract. US1 supplies the inventory used by US2 and US3.
Complete T008, T010 and T012 before acceptance validation. Framework installation
does not complete these feature tasks or authorize training, uploads or deployment.
