# Feature Specification: Reviewed Defect Preparation Manifest

**Feature Branch**: `001-reviewed-defect-manifest` (proposed; not created)

**Created**: 2026-11-20

**Status**: Draft — documentation only; implementation and acceptance pending

**Input**: Prepare existing reviewed-defect exports for a future training-data
review, with explicit provenance and source isolation. No automatic training.

## Existing Behavior and Proposed Delta

The app already exports a labels ZIP containing images, COCO annotations,
confirmed/rejected decisions, dataset-level groups and detector-provider info.
It marks the export as not training-ready. This proposal adds an offline
preparation manifest and an issue report alongside that unchanged ZIP.

## User Scenarios & Testing

### User Story 1 — Inventory an export (Priority: P1)

As a model maintainer, I need to identify incomplete labels before using GPU time.

**Independent Test**: Inventory a small archive with confirmed/rejected decisions
and compare counts, sources and geometry issues against its known contents.

**Acceptance Scenarios**:

1. **Given** an export, **when** prepared, **then** record its hash, class counts,
   review counts and source types separately.
2. **Given** rejected flags, **when** inventoried, **then** retain them as decisions,
   without creating positive annotations or asserting the whole image is clean.
3. **Given** missing reviewer, donor or model evidence, **when** reported, **then**
   leave it unknown and identify the missing evidence.

### User Story 2 — Prevent source leakage (Priority: P2)

As a model maintainer, I need verified lineage distinguished from dataset IDs.

**Independent Test**: Provide different rendered datasets sharing a known donor
and require a single shared group.

**Acceptance Scenarios**:

1. **Given** shared donors/backgrounds, **when** grouped, **then** derived frames
   remain together regardless of seed or dataset ID.
2. **Given** missing lineage, **when** proposing a split, **then** retain unassigned
   status and do not claim source independence.
3. **Given** answer-key-derived entries, **when** preparing data, **then** preserve
   that provenance for explicit review.

### User Story 3 — Reproduce the handoff (Priority: P3)

As a reviewer, I need an issue report tied to immutable inputs, without accessing
the live database.

**Independent Test**: Repeat preparation and compare canonical manifest content.

**Acceptance Scenarios**:

1. **Given** identical inputs, **when** prepared twice, **then** stable IDs, counts,
   hashes, groups and issues match.
2. **Given** invalid geometry or missing images, **when** prepared, **then** report
   affected entries and block any training-ready conclusion.

### Edge Cases

Empty exports, several decisions per image, unknown categories, duplicate IDs,
missing/corrupt images, missing hashes, nonfinite/zero/out-of-bounds boxes,
unavailable lineage, malformed JSON, ZIP traversal, duplicate archive paths and
excessive decompression. Do not silently repair or discard problematic records.

## Requirements

### Functional Requirements

- **FR-001**: Read existing authorized labels ZIPs without changing input bytes.
- **FR-002**: Write versioned JSON and a readable report separately from inputs.
- **FR-003**: Retain input hashes, tool version, image references, annotations,
  decisions, source evidence and issues; distinguish unknown fields explicitly.
- **FR-004**: Check referential integrity, image dimensions and finite COCO
  `[x, y, width, height]` geometry in exported-image coordinates.
- **FR-005**: Preserve simulated-video and answer-key provenance independently.
- **FR-006**: Accept optional explicit donor/background lineage and hash it;
  dataset ID alone must not establish independence.
- **FR-007**: Leave ambiguous splits unassigned and label proposals as proposals.
- **FR-008**: Document stable issue codes and nonzero exit behavior for blocking
  inputs; prevent source-file overwrite.
- **FR-009**: Work offline without database credentials, inference, training,
  data uploads or model activation.
- **FR-010**: Bound archive size/expansion and reject unsafe or duplicate paths.

### Key Entities

**PreparationManifest**: versioned inventory, hashes, counts, groups and issues.
**SourceLineage**: supplied original-donor/background evidence, distinct from
dataset IDs. **ReviewIssue**: code, severity, affected entry and remediation.

## Success Criteria

- **SC-001**: Every decision is counted once; positives remain separate from
  rejected flags, with no automatic promotion to labels.
- **SC-002**: Representative malformed references, geometry, images and unsafe
  archives produce the documented issues and exit behavior.
- **SC-003**: Identical inputs produce matching canonical manifests.
- **SC-004**: Shared lineage stays grouped; ambiguous sources remain unassigned.
- **SC-005**: Preparation requires no network or running app and cannot activate
  a model.

No success criterion was executed or passed during setup.
