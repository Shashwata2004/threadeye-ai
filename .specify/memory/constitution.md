# ThreadEye Constitution

## Core Principles

### I. Traceable AI behavior

Disclose the actual detector provider separately from simulated camera footage.
Preserve inspection model/rule snapshots and historical decisions after upgrades.
Describe vision detectors, embeddings and generative LLMs according to the actual
runtime path; do not substitute one claim for another.

### II. Human authority and accountable operations

Inspection review, supervisor decisions, challan decisions, cutting approval and
cutting acknowledgement have distinct permissions and meanings. Enforce them at
the API boundary, communicate denied access clearly, and retain actor identity
and audit evidence. A UI selection is not proof of a persisted decision.

### III. Provenance before learning

Inspector corrections are review data, not automatic training. Preserve images,
source labels, decisions and hashes. Split data by original donor/background,
not rendered frame. Unknown lineage remains unknown. Answer-key detections must
not become independent human ground truth through confirmation alone. Require
relevant line-scan evaluation and rollback before activating a model.

### IV. Deployment and contract compatibility

Keep edge/offline and cloud paths explicit. Respect serverless execution limits.
Version artifact contracts and regenerate API types when backend contracts change.
Support Bangla and English in user-facing changes and label units explicitly.

### V. Evidence proportional to claims

Trace requested behavior through specs, implementation tasks and suitable checks.
Keep unfinished tasks and skipped checks visible. Distinguish measured outcomes,
demo scenarios and proposed factory benefits. Framework setup today is not proof
of its use in earlier work. Prefer focused implementation to redundant tooling.

## Development Workflow

Maintain spec.md, plan.md and tasks.md in numbered feature directories. Resolve
consequential design questions before implementation and review plans against
these principles. Test risky behavior and changed contracts with representative
failures and disposable data. Respect explicit user limits on validation; record
skipped checks without declaring acceptance criteria passed.

Specs and skill invocations do not imply training, publishing, data upload or
model activation. Follow the user's authorized scope and keep credentials out
of committed files.

## Governance

Use this constitution alongside root AGENTS.md and applicable directory guidance.
Explicit user instructions take precedence. Amendments must explain their reason
and affected features. Use semantic versioning for material changes. Do not
backdate adoption or rewrite historical tooling evidence retrospectively.

**Version**: 1.0.0 | **Ratified**: 2026-11-20 | **Last Amended**: 2026-11-20

Initial setup only; application compliance and feature acceptance were not tested.
