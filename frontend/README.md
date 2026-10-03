# ThreadEye AI frontend

Next.js 16 (App Router) + TypeScript, Tailwind 4, next-intl (bn/en, cookie-based locale), TanStack Query,
openapi-fetch with types generated from `../docs/api/openapi.json`.

```bash
pnpm install
API_ORIGIN=http://localhost:8000 pnpm dev          # against a local FastAPI (uv run uvicorn ...)
NEXT_PUBLIC_API_MOCKING=enabled pnpm dev           # no backend: MSW mocks from src/mocks/
pnpm check                                         # i18n parity + eslint + tsc
pnpm gen:api                                       # regenerate src/lib/api/schema.d.ts
```

Rules:
- **No literal UI strings.** Add keys to both `messages/en.json` and `messages/bn.json`
  (`pnpm i18n:check` enforces parity).
- The **SIMULATION MODE banner** (`components/badges.tsx`) must stay on every screen while the detector
  is simulated.
- `src/proxy.ts` only redirects to `/login` as UX. FastAPI enforces every permission.
- Next.js 16 differs from older versions: read `node_modules/next/dist/docs/` (see `AGENTS.md`).
