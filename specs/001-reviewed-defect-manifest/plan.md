# Implementation Plan: Reviewed Defect Preparation Manifest

**Branch**: `001-reviewed-defect-manifest` (proposed) | **Date**: 2026-11-20

**Spec**: [spec.md](spec.md)

**Status**: Draft, manually authored during setup; not output from an executed
`/speckit-plan` workflow. Feature code and tests remain pending.

## Summary

Add an offline Python utility around existing reviewed labels ZIPs. Inventory
decisions, identify invalid data, preserve evidence and produce a versioned
manifest/report. Keep the export API and database unchanged.

## Technical Context

**Language/Version**: Python 3.12, matching the backend.

**Primary Dependencies**: Standard-library ZIP, JSON, hashing and filesystem
utilities. Image-integrity decoder strategy remains a design decision; prefer
an existing dependency rather than adding one without need.

**Storage**: Local inputs and separate output files, no database.

**Testing**: Focused tests using small synthetic archives, not run during setup.

**Target Platform**: Developer Linux, offline.

**Project Type**: Developer CLI utility, outside business API handlers.

**Performance Goals**: Process entries sequentially without loading the entire
archive into memory. Numeric resource limits must be decided before coding;
no measured throughput is claimed.

**Constraints**: Immutable inputs; no network, inference, training, production
changes or inferred reviewer/donor identity.

**Scale/Scope**: One labels ZIP with optional lineage input per invocation.
Cross-export split decisions require an explicit comparison source.

## Constitution Check

| Principle | Proposed treatment | Implementation evidence |
| --- | --- | --- |
| Traceable behavior | Preserve provider/source fields and input hashes | Pending |
| Human authority | Do not invent reviewer identity | Pending |
| Provenance | Explicit lineage; ambiguous splits unassigned | Pending |
| Compatibility | Offline utility, unchanged business API | Pending |
| Evidence | Versioned output, explicit unknowns and failures | Pending |

Revisit these gates after concrete contract design and after implementation.

## Project Structure

Existing exporter: `backend/threadeye/api/routers/operations.py`.
Existing assisted workflow: `.claude/skills/prepare-defect-review-data/SKILL.md`.

Proposed files, not created during setup:

```text
scripts/prepare_reviewed_defects.py
backend/tests/unit/test_reviewed_defect_manifest.py
specs/001-reviewed-defect-manifest/research.md
specs/001-reviewed-defect-manifest/data-model.md
specs/001-reviewed-defect-manifest/contracts/manifest.schema.json
specs/001-reviewed-defect-manifest/quickstart.md
```

Match existing test conventions before implementation. Separate archive inventory
from CLI output. Do not create a service, migration or training pipeline.

## Phase 0 — Resolve Design Decisions

Record decoder choice, ZIP byte/entry/expansion limits, overwrite behavior,
canonical ordering, exit codes and optional lineage format. Identify evidence
the current export cannot supply. Do not guess missing model hashes or actors.

## Phase 1 — Contracts

Define the manifest schema, good/bad examples, issue severity and unknown-value
semantics. Specify exported-image coordinates and source grouping rules. Draft
an offline quickstart and revisit constitution gates against these contracts.

## Phase 2 — Implementation and Validation

Implement the utility and focused archive-safety, geometry, provenance and
determinism cases from tasks.md. Use disposable fixtures, followed by an authorized
local export. Record actual commands and results. Training and deployment stay
outside this feature.

## Complexity Tracking

No constitutional exception proposed. Decoder, exact CLI arguments and numeric
resource limits are pending decisions, not an accepted implementation.
