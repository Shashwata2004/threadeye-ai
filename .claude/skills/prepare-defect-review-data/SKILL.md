---
name: prepare-defect-review-data
description: Prepare an existing ThreadEye reviewed-defect labels ZIP for a human training-data review, preserving source provenance, coordinate conventions and split isolation. Use for inspector-correction dataset preparation, not for training, deployment or generic model evaluation.
argument-hint: "<path-to-labels.zip>"
---

# Prepare reviewed defect data

Work from the supplied ThreadEye `labels-<inspection-id>.zip` archive. Read root
`AGENTS.md` and the exporter in
`backend/threadeye/api/routers/operations.py` before interpreting unfamiliar
fields. The existing route is `GET /inspections/{inspection_id}/labels.zip`
under the API's configured prefix and requires `Perm.LABEL_DATA_EXPORT`.
Use an existing authorized export when available. Do not invent a CLI command
or bypass the permission check to obtain data.

## Existing export format

The ZIP contains images and `annotations.json` with:

- `images`: image dimensions, filename, `source_group`, `split` and `sha256`.
- `annotations`: confirmed defect boxes in COCO `[x, y, width, height]` pixels,
  class IDs, area, `label_source` and `source`.
- `decisions`: confirmed/rejected status, defect ID, image ID, rejection reason,
  `label_source` and `source`.
- `info`: simulated-video flag, detector provider and a not-training-ready notice.

`source_group` currently uses the inspection dataset ID. It does not establish
that original donors or backgrounds are disjoint across rendered datasets.
The export does not establish reviewer identity, complete correction history,
model hash, or a lineage back to every donor. Mark absent evidence as unknown.
Do not infer manual/reclassified counts from fields that do not distinguish them.

## Preparation workflow

1. Identify the archive and requested output directory. If the archive is not
   supplied, locate an already authorized local export or ask for the missing
   path. Do not change app data or export a shared database without task scope.
2. Inventory entries without executing archive contents. Prevent path traversal
   and bound extraction sizes if unpacking is needed. Preserve the original ZIP
   and record its SHA-256 in the review output.
3. Reconcile image IDs, filenames, dimensions, categories, annotations and
   decisions. Check finite, positive boxes against the exported image dimensions.
   Do not apply the original video scale again to already scaled COCO boxes.
   Record missing images or inconsistent metadata as issues rather than inventing
   labels or silently dropping records.
4. Count images, positive boxes and confirmed/rejected decisions separately.
   List per-class counts, answer-key-derived entries, unknown sources and missing
   review evidence. A rejected AI flag is not proof that the entire image is clean;
   other missed defects may exist in the same frame.
5. Group by known original donor/background lineage where available. Keep
   ambiguous groups unassigned. A frame split or different render seed alone
   cannot establish independence. Compare against the intended replay and
   evaluation sources before suggesting splits.
6. Produce a concise review report and a companion manifest in the requested
   output directory. Record archive hash, source references, counts, issues,
   proposed groups and pending human checks. Use `null`/unknown for unavailable
   evidence. Clearly label any proposed split as a proposal.

## Completion boundaries

The result is a preparation report, not a certified dataset. Confirmed boxes need
visual review, and class mappings and source lineage need review before training.
Do not mark data training-ready when blocking issues remain. Never run training,
activate a checkpoint, change production thresholds, or upload data as a side
effect of this skill. Do not claim that inspectors' edits currently retrain the
live model. Follow the user's requested limits on checks and record skipped work.

The proposed machine-readable manifest feature is documented in
`specs/001-reviewed-defect-manifest/`; its unchecked tasks are not implemented by
the presence of this skill.
