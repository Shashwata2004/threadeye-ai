# Validation record — operational features, 3 November 2026

These checks cover the local working implementation. They do not claim that the unchanged remote HEAD
or hosted Vercel application contains these changes. Repository/release publication was excluded.

## Final checks

- `make lint`: Ruff, formatting, strict mypy, both import-boundary contracts and frontend checks passed.
- `make test`: **280 backend tests passed**, using the throwaway local PostgreSQL database; frontend
  lint, TypeScript and parity of **330 Bangla/English keys** also passed.
- Recovery tests: real child-process SIGKILL before/after committing inspection transactions at five
  reproducible frame positions (10 cases), preserving final score/verdict and unique contiguous events.
- Actual MP4 encoding/serving, cutting approval/acknowledgment/PDF, reviewed-label image scaling,
  immutable rule versions, measurement re-scoring/locking, benchmark split guard, machine/user
  permissions, revoked recurring permissions, scheduling and sample archive are covered by tests.
- Clean source snapshot: **344 source files**, no private environment, local dependencies or model
  weights; only the generated synthetic CI roll was injected. Build, internal-network/offline check
  and five browser flows passed in **69.88 seconds**, with already cached build dependencies/images.
  This is not a cold-download timing claim. Snapshot hashes/logs are in `build/fresh-source-check.json`,
  `build/fresh-source-check.log` and the referenced `SOURCE_SNAPSHOT.json`.
- The fresh-snapshot browser flows cover Bangla/English live inspection to verdict/PDF, both-language
  verification/history plus real admin persistence and cutting decisions, and benchmark run comparison.
- Eight separate browser cases verified simulated/real mode banners in both languages and both themes.
- Opt-in real-model browser test passed: actual ONNX inference on the line-scan video, explicit known
  reviewer additions, final verdict and Bangla PDF. This is workflow conformance, not blind accuracy or
  measured human/business improvement. The default CI run skips this case without local model assets.
- Bangla dark-mode cutting screen was visually inspected; the handout renders as one A4 page.
- Later launcher cleanup and recurring-permission checks were verified separately: stopping the
  launcher closes its process groups, and a demoted account cannot keep scheduling verification.

A fresh-source attempt exposed concurrent API/worker builds racing to write the same image tag.
`make build`, `make up`, CI and the source-check script now build the shared backend once (`api web`),
then start without rebuilding it. The successful source check includes that fix. An initial benchmark
browser test used an overly strict label selector; it now selects the combobox by its accessible role
and the comparison flow passed.

## Local demo compatibility

- Shared Supabase schema verified at **0008_operations**, with both new operational tables present.
  The migration adds nullable measurement columns/tables; no inspection or audit data was deleted.
- Local `make demo` restarted with the real model and the durable jobs worker. `/health` reports
  database OK and `simulated_mode=false`. The new protected verification route returns 401 without
  authentication, confirming it is registered rather than the old 404.
- Local launcher now manages separate process groups so shutting it down also stops Next.js children.
- Temporary Docker test stacks/volumes were removed. The local demo is left running for the owner.

## Limits

Factory pilot measurements, camera calibration validation, industrial rule sign-off, source-licence
confirmation, team registration details and physical rehearsals require team/owner evidence. No such
measurements or approvals were fabricated. M7 model improvement and M8 final submission are outside
this request. The model and the line-scan source video were not retrained or regenerated.

## Follow-up: abort unfinished inspections from the list

The open/recent inspection rows now offer a permission-checked abort action beside Continue.
Successful aborts refresh both lists, preserve the old record and prefill/focus the roll code for
another inspection. Four browser cases passed (Bangla/dark, English/light, read-only permission and
server-error handling), including dismissing confirmation and loading the same roll again. A targeted
PostgreSQL integration test also passed, verifying that abort preserves saved defects and releases
that roll for a distinct new inspection. Frontend lint/typecheck and parity of 335 translation keys passed.

## Follow-up: fabric cutting map with transparent overlays

The cutting page now stitches an unannotated fabric strip from the local source video using
frames.csv positions, compensating for lateral drift and cropping the board and label bar. It never
uses the simulator's annotated roll_preview or answer key. Repeated frames retain the first usable
observation; hand-obscured/unobserved areas remain grey. The image is bounded to 8192 by 1024 pixels
and cached in process. Protected image requests require cutting.read. Servers without the local
video/vision dependency retain a labelled cutting diagram.

Transparent red zones show the existing cutting plan, including margins; yellow boxes use only
confirmed, non-excluded inspection defects. Yard coordinates remain aligned to the source even
when the measured cutting length differs. Opacity and zoom are adjustable. Approval and PDF logic
remain unchanged.

Validation: two image-service unit tests passed (drift, hand exclusion, duplicate frames, board/label
cropping, yard orientation, caching and missing-media behavior). The cutting approval/PDF/labels
PostgreSQL integration case passed with added image permission/content and confirmed-defect checks.
Two mocked browser cases passed in English and Bangla, covering texture loading, overlay coordinates,
opacity, zoom and the unavailable-image fallback. The actual line-scan mosaic was generated and
visually inspected; browser checks also used that image without creating any shared-database records.
Ruff, mypy, import contracts and frontend lint/typecheck passed; OpenAPI/types were regenerated.
Playwright output directories are now excluded from ESLint so generated trace bundles are not linted.

## Follow-up: automatic cutting-policy selection and signed decisions

The cutting page defaults to the inspection's pinned buyer policy. A supervisor may select
all confirmed defects or a 2/3/4-point threshold before cutting approval. Selection saves immediately,
persists per inspection, recalculates skip zones and participates in the plan fingerprint; buyer
scoring, margins and minimum-piece settings stay unchanged. Approved policies are locked on the
server and in the dropdown. Existing default-policy hashes/approvals remain valid. No migration
or changes to existing buyer profiles were required.

Saved supervisor decisions now remain visible as disabled radios and the original reason. The API
locks the first decision, rejects attempts to change either verdict or reason, and accepts an exact
same-actor retry without adding events/audit entries or changing its timestamp. Unsaved drafts
survive navigation/reload within the same browser tab; failed requests retain the draft for retry.

Validation: all 28 operations/live-inspection integration cases passed on disposable PostgreSQL,
including policy persistence/permissions/approval locking, unchanged scoring and signed-decision
retry/change rejection. Three mocked browser cases passed (English/light, Bangla/dark and network
failure), covering automatic policy selection, auto-save, recalculated overlays, approval locking,
returning from cutting, reload persistence and disabled signed decisions. Ruff, mypy, import
contracts, frontend lint/typecheck and translation parity (337 keys) passed. OpenAPI/types regenerated.
Shared business records were not modified by these tests.

## Follow-up: disable verification actions throughout an active check

The evaluation form now keeps run/schedule actions disabled while a saved run is queued or running,
including after refresh. Submission immediately inserts the returned run into the query cache;
existing history polling releases the controls when processing completes or fails. A visible status
explains the wait. Loading/error states also prevent submitting without knowing the current run state.
This changes the form controls, not server-side concurrency across separate clients.

Three mocked browser cases passed: Bangla/English queued-to-running-to-completed transitions and
refreshing an active run followed by failure. All three verification buttons stay disabled during
processing and become usable afterward. Frontend lint/typecheck and translation parity passed.
