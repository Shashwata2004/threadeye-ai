# Operational milestone completion record

Scope requested on 3 November 2026: remaining work outside M7 and M8. The owner explicitly excluded
repository publication and release publishing. This record describes local implementation; it does
not claim that the preliminary submission, factory pilot, public deployment or Congress presentation
has been performed.

## M3 — source and preliminary preparation

- Preliminary eight-section draft: `docs/submission/preliminary.md`.
- Private judge-access instructions: `docs/submission/judge-access-note.md`.
- Current provenance/tooling/prompt records updated; unresolved source licences remain explicit.
- Clean-source verification script: `scripts/verify_source_checkout.py --browser`. It copies tracked
  and unignored working files, excluding local environments/dependencies/credentials, injects only
  the generated synthetic CI roll, and builds/tests a separate offline Docker project/database.
  Because the implementation is uncommitted, this is a working-source snapshot test, not a claim
  about the unchanged remote HEAD. Inspect its result in `build/fresh-source-check.json`.
- Repository publication, release tags and release publication: excluded by owner.

## M4 — trustworthy operations

- Daily verification: machine/reference dataset selection, simulated or real local provider, seed,
  recorded recall/FP/score tolerances, queued/completed/failed states and saved per-machine history.
- GREEN/RED results and an AMBER no-run-today state on the dashboard. A failed check warns on the
  live screen for that machine. This is software verification with known video, not camera certification.
- Optional daily edge-worker checks, configured explicitly per machine. No run configuration is invented.
- Real machine CRUD/calibration records and user-management UI backed by permission-checked APIs.
- Immutable buyer-profile versions; existing lots keep their pinned profile. What-if preview uses
  the actual backend scoring engine, including per-yard caps and configured verdict bands.
- Recorded, idempotent length/width measurements; finalized/aborted inspections lock measurement edits.
  Width follows the buyer's declared/measured/cuttable basis. A measured-width profile requires that
  measurement before finalization. Simulator geometry remains the reference for simulated video.
- Recovery tests SIGKILL a child process before/after database commit at five reproducible frame cuts;
  resume must reproduce points/verdict and contiguous, unique events. This is not a physical power-cut
  or PostgreSQL WAL-crash experiment on a factory laptop.

## M5 — cutting and evidence

- Pure cutting algorithm: confirmed eligible defects, full-width margins, zone merging, minimum usable
  pieces, clipped roll boundaries and usable/skipped length.
- Cutting page with strip/segment table, supervisor approval, cutting-master acknowledgment and PDF in
  Bangla/English. Approvals bind a source hash; repeated actions are idempotent.
- Edge MP4 export jobs and source-video playback. Completed clips are included in claim packs alongside
  reports/photos and covered by the existing ZIP checksums. Serverless cloud uses source playback.
- Postgres-backed jobs with row-lock claims, status/history, failure records and abandoned-lease retry.
  The worker processes verification, benchmarks and clips; lightweight PDFs remain inline.

## M6 — measurement, configuration and access

- Real dashboard KPIs from finalized inspections, own-inspector scope, Dhaka day boundaries, coverage,
  defect mix, machine/mill counts, active inspections and explicit simulated-source counts.
- Multi-roll benchmark runs, selected provider/seed, held-out-test manifest guard, model/input hashes,
  per-class recall, false-alarm categories, pipeline funnel and side-by-side run comparison.
- Real provider selection for new inspections, persisted separately for edge and serverless. Existing
  inspections retain their provider/model snapshots. The external-API provider remains a stub by design.
- Reviewed-label ZIP export: images, COCO annotations, decisions, image scale and source groups. Splits
  remain unassigned and labels require review; there is no automatic retraining.
- Optional sample-delivery archive for demo reset, off by default. It aborts sample open inspections,
  hides archived samples from current lists/KPIs/scorecards and preserves reports/events/audit records.
  Unmarked real deliveries are excluded. Nightly edge scheduling starts the next Dhaka day after 03:00.
- About/provenance page; KPI definitions in `docs/KPIS.md`; keepalive and manual deploy-smoke workflows.
- Docker backend includes ONNX/vision runtime and ffmpeg. Local-model browser conformance test is opt-in
  (`E2E_REAL_MODEL=1`) because model/video assets are not redistributed in a clean checkout.

## M9 — team presentation preparation

- Three-minute pitch and ten-attempt rehearsal log: `docs/congress/pitch-and-rehearsal.md`.
- Printable one-page handout: `docs/congress/one-pager.pdf`, regenerated with
  `backend/.venv/bin/python scripts/build_onepager.py`.
- Rehearsing with people, physical setup and presenting at Congress remain team actions.

## Validation and running

Run `make lint`, `make test`, frontend Playwright against a local/offline stack, and
`backend/.venv/bin/python scripts/verify_source_checkout.py --browser`. The real-model browser test
checks real inference followed by explicit known reviewer corrections; it is a workflow test, not
an independent accuracy or savings measurement. Full test results for this work are in `docs/VALIDATION.md`.

Migration `0008_operations` adds two tables and nullable measurement columns. Docker applies it on
startup. For the shared Supabase laptop profile use `make cloud-migrate` before restarting `make demo`.
This migration is backward-compatible with the earlier application; no evidence or audit rows are deleted.

M7 model improvement/target-laptop polish and M8 final submission/video production are excluded.
Factory savings, industry-default sign-off, team roster and source-licence confirmations require real
observations or owner/domain input; the software does not manufacture these facts.

Final verification summary: `make lint` and `make test` passed (280 backend tests, frontend checks,
330 translation keys). Clean-source Docker/offline + five browser flows passed in 69.88 s with cached
build dependencies. Mode-banner cases and real-model browser conformance also passed in dedicated
runs. Supabase schema 0008_operations is applied; the updated local app and worker are running.
The local launcher now cleans up its process groups, including the Next.js child processes.
