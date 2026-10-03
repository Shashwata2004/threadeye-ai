# CLAUDE.md: project memory for AI assistants

> Disclosed in TOOLING.md (competition rule). Keep it short and current.

## What this is
ThreadEye AI is a retrofit camera assistant for fabric inspection machines at Bangladeshi garment
factories (receiving inspection). The chain: frames → detector provider → roll coordinates → de-dup →
non-defect filter → inspector confirm → 4-point verdict → report, claim pack, cutting plan, supplier
score. Competition: International AI Builders Congress 2026, Idea to Unicorn, IndustrySphere AI →
Quality Vision. Full plan: `docs/PLAN.md`. Current milestone: **M0 done; do not start M1 without an
explicit instruction.**

## Non-negotiable rules
- **Honesty:** anything simulated says SIMULATED (UI, PDFs, exports, videos). Sample/fictional data is
  flagged `is_sample_data` and shows "SAMPLE DATA". Never invent metrics or confidences
  (`confidence=None` unless the provider is calibrated). Never call a report "ASTM/AQL compliant";
  use "4-point inspection report".
- **No ground truth outside the simulator provider:** only `threadeye.providers.simulated` and
  `threadeye.services.{verification,benchmark}` may import `threadeye.datasets.answer_key`
  (enforced by import-linter). The pipeline uses positions + detections only.
- **Never silently fall back to the simulator** when a real detector fails.
- **Append-only:** `inspection_events` and `audit_log` are never updated or deleted (DB triggers).
  Every user command writes an audit row in the same transaction.
- **Secrets only in env vars.** `.env` is never committed; `.env.example` lists every variable.

## Conventions
- Units are in field names: `_yd` along the roll, `_cm` across, `_in` defect size, `_px` pixels.
- Simulator conventions (verified): `view_region` = 0,0,1920,1008. GT boxes are roll coordinates
  (x from the fabric's left edge, y absolute roll px). Frame position = `(x + fabric_x0_px[f], y − roll_y_top_px[f])`.
  `length_in = max(w_cm, h_cm) / 2.54`.
- `threadeye.core` is pure Python (no I/O, no numpy at import time) so it runs on Vercel too.
- DB tables live in Postgres schema `threadeye`; UUIDv7 primary keys; timestamps in UTC.
- The API returns codes (`FAIL`, `hole`); the UI translates them. No literal UI strings: use
  `frontend/messages/{en,bn}.json`, and both files must have identical keys.
- Role checks are server-side via `Depends(require(Perm.X))`.

## Commands
- `make env && make up` starts the edge stack (http://localhost:8080). `make down` stops it.
- `make test` runs backend tests (starts a throwaway Postgres on :55432) + frontend checks.
- `make check` runs everything CI runs. `make openapi` regenerates `docs/api/openapi.json` + TS types.
- `make verify-offline` proves the app containers have no internet access.
