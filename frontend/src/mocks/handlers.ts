// MSW handlers: let the frontend run against the OpenAPI contract with no backend
// (`NEXT_PUBLIC_API_MOCKING=enabled pnpm dev`). Types come from the generated schema, so mocks
// break at compile time when the contract changes.
import { http, HttpResponse } from "msw";
import type { Health, Me, ProviderAvailability, SystemStatus } from "@/lib/api/client";

const me: Me = {
  id: "0192f0c0-0000-7000-8000-000000000001",
  username: "inspector",
  display_name: "Mock Inspector",
  role: "inspector",
  locale: "bn",
  digit_style: "latin",
  permissions: ["dashboard.own_shift", "inspections.read", "inspections.run", "defects.confirm", "lots.read"],
};

const simulated: ProviderAvailability = {
  provider_id: "simulated",
  display_name: "Simulated detector (answer key, not AI)",
  kind: "simulated",
  is_simulated: true,
  availability: "planned",
  milestone: "M1",
  note: "MOCK",
  active: true,
};

const health: Health = { status: "ok", db: "ok", profile: "edge", version: "mock", simulated_mode: true };

const status: SystemStatus = {
  profile: "edge",
  version: "mock",
  db: "ok",
  worker: { alive: true, last_seen_at: new Date().toISOString() },
  active_provider: simulated,
  simulated_mode: true,
  sample_data_present: false,
};

export const handlers = [
  http.get("/health", () => HttpResponse.json(health)),
  http.post("/api/v1/auth/login", () =>
    HttpResponse.json(me, { headers: { "Set-Cookie": "te_session=mock; Path=/" } }),
  ),
  http.post("/api/v1/auth/logout", () => new HttpResponse(null, { status: 204 })),
  http.get("/api/v1/auth/me", () => HttpResponse.json(me)),
  http.patch("/api/v1/auth/me", () => HttpResponse.json(me)),
  http.get("/api/v1/system/status", () => HttpResponse.json(status)),
  http.get("/api/v1/providers", () => HttpResponse.json([simulated])),
];
