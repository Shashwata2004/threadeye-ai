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

## Follow-up: permission notices and hydration

`ViewOnlyNote` now uses a div wrapper so its paragraph content produces valid HTML. This fixes the
audit permission notice's nested-paragraph hydration error. The supplier scorecard page distinguishes
restricted access, loading and request failure from genuinely empty data, and gives restricted users
a link to receiving. Store permissions remain enforced by the API.

Four browser checks passed (Bangla/English, store/QC access), with no hydration or page errors.
Restricted pages did not request audit/scorecard data; authorized scorecards still rendered deliveries.
Read-only checks against the running API returned 403 for store and 200 for supervisor, with two
inspected rolls represented. Frontend lint/typecheck and 337-key translation parity passed.

## Follow-up: permission notices for every role

The app shell now checks page capabilities before mounting restricted content, including direct
URLs for audit, suppliers, benchmark, administration and cutting details. A shared Bangla/English
notice distinguishes missing access from missing records and links to a permitted landing page.
Read-only evaluation users retain history with an explicit explanation of unavailable run actions.
QC administration starts at buyer rules; restricted tabs show the same notice. API permissions
remain unchanged.

Nine mocked browser tests passed across all seven roles, plus Bangla wording and QC tab navigation.
Denied pages requested no page data, offered permitted destinations and produced no hydration errors.
Frontend lint/typecheck, translation parity and whitespace checks passed. All browser API traffic
was mocked; no shared records were created or changed.

## Follow-up: defect photo coordinates and retained resolution

Smaller browser captures overwrote the same blob key used by larger server images, even when
the conditional frame-row update retained the larger dimensions. Evidence crops then applied
the wrong scale and could show unrelated fabric with the detection box outside the crop.
Frame blob keys now include dimensions. Both UI and PDF evidence derive scale from actual JPEG
width and calibrated view width, handling existing mismatched captures without relying on stale
metadata. Crop responses revalidate instead of retaining stale images.

Four mismatched captures in inspection `01a1a233-bf87-785f-861c-9d7f064e2e52` were restored
from the original linescan video; their prior metadata was backed up under ignored build output.
No defect classification, points or supervisor decision changed. Fourteen unit/integration tests
passed against the isolated local test database, including retained blob dimensions/hash and
legacy-scale crop coverage. Ruff and whitespace checks passed.

## Follow-up: discoverable cutting work

Added a permission-checked `/api/v1/cutting` list and `/cutting` screen for current approved plans.
Pending receipt is the default; filters retain acknowledged history. Drafts, archived deliveries
and approvals with an outdated source fingerprint are excluded. The cutting role lands directly
on this page, with navigation to each instruction sheet and back. Approval/acknowledgment refresh
the cached list, which also polls every 15 seconds. Receipt is explicitly distinguished from
physical cutting completion.

Two backend integration tests and fourteen browser tests passed, covering approved work discovery,
receipt state, denied roles, invalid approvals, Bangla/English navigation and existing decision
locking. Lint, typecheck, translation parity (338 keys) and whitespace checks passed. Read-only
verification against shared data found the two pending plans for TE-000001 and TE-000004.

## Follow-up: inspection list workflow status

Recent completed inspections now show the saved QC decision, cutting instruction approval and
cutting master's receipt independently from the system verdict. Pending decisions, drafts,
unissued instructions and inspections awaiting finalization have explicit labels. The list API
outer-joins cutting plans in its existing query, and the UI refreshes every 15 seconds. Updated
the OpenAPI contract and generated frontend types.

Backend integration coverage passed through not-issued, draft, approved and acknowledged states.
Bangla/English browser checks passed for independent system/QC decisions and cutting receipt;
four existing abort browser cases also passed. Frontend checks and Ruff passed. Read-only API
verification found TE-000001 accepted/approved/awaiting receipt and TE-000004 accepted/acknowledged.

## Follow-up: cutting PDF sign-off identity

Cutting PDFs now include the stored approver and receiving user's display name, username and
event time in Asia/Dhaka with an explicit UTC offset. Missing sign-off states are explicit;
invalidated approvals do not print stale identities. Both English and Bangla PDFs were rendered
and checked with pdftotext in two passing cutting integration tests, including pending receipt.
Ruff and whitespace checks passed.

## Follow-up: delivery decisions and truthful claim downloads

Claim packs now require a delivery decision of ACCEPT_WITH_REJECTS or REJECT plus at least one
latest finalized roll signed REJECT or ACCEPT_WITH_CLAIM. Automatic FAIL, yardage shortage alone,
pending/inspect-all decisions and unconditional acceptance cannot authorize a pack. A shared
eligibility rule drives the API, lot verdict response and supplier scorecards. The delivery decision
panel explains the separate roll/delivery decisions; scorecards link straight to that panel.

Both claim buttons now fetch and validate the ZIP response, show failures and only report download
started after the complete ZIP arrives. Four backend integration tests and four Bangla/English
browser cases passed, covering blocked pending claims, signed dispositions, checksum-valid ZIPs,
decision navigation and failed/successful downloads. Frontend checks, Ruff and contract generation
passed. Tests used isolated local Postgres and mocked browser APIs; no shared decisions changed.
