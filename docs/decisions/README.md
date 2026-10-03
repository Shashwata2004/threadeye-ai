# Architecture decision records

Short records of decisions that are expensive to reverse. Details: `docs/PLAN.md`.

| # | Decision | Why | Date |
|---|---|---|---|
| 0001 | Two deployment profiles from one codebase: `edge` (Docker Compose, offline) and `cloud_demo` (Vercel Hobby ×2 + Supabase free) | Edge-first product; zero-cost judges' link | 2026-10-03 |
| 0002 | Browser-clocked live inspection for video-file sources (`POST /advance`); server-clocked for headless runs and future webcams; one `Runner.advance()` | Works on serverless; same code gives idempotent power-loss resume | 2026-10-03 |
| 0003 | PDFs with fpdf2 + HarfBuzz; always Latin font primary with Noto Sans Bengali fallback | Pure wheels (Vercel + Docker); the M0 spike showed Bengali-primary breaks mixed lines | 2026-10-03 |
| 0004 | Own auth (argon2id + server-side sessions, httpOnly cookie), not Supabase Auth | Identical on edge and cloud; revocable | 2026-10-03 |
| 0005 | All tables in Postgres schema `threadeye` (not exposed via Supabase Data API); migrations pin `search_path=public` | Security on Supabase; correct autogenerate when the DB user is also named `threadeye` | 2026-10-03 |
| 0006 | Next.js (team choice) with client components + TanStack Query; `proxy.ts` only for the UX redirect | Team familiarity; all auth is server-side in FastAPI | 2026-10-03 |
| 0007 | Answer key reachable only by the simulated provider and the evaluation services (import-linter) | Nothing may silently depend on ground truth | 2026-10-03 |
| 0008 | Bundled fonts (Noto Sans, Noto Sans Bengali, Noto Sans Mono) | Offline; system mono fonts drew ASCII digits as Bengali in `lang=bn` (found in M0) | 2026-10-03 |
