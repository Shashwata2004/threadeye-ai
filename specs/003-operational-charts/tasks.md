# Tasks

- [x] Add four plotting dependencies and client-only chart components.
- [x] Integrate with the four existing pages and monthly weighting.
- [x] Verify data fidelity, empty states, locales, themes and narrow layouts.
- [x] Record usage and validation in TOOLING.md.

Validation: `pnpm check` and `pnpm build` passed. The production build served on
an isolated loopback port passed 18 Playwright tests across visualizations,
cutting maps, cutting policy/decision persistence and permission notices.
API responses were isolated fixtures; no shared database changes were made.
