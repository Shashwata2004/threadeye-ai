import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

// Same-origin: Caddy (edge) or Next.js rewrites (dev/cloud) route /api to FastAPI. Types come from
// docs/api/openapi.json via `pnpm gen:api`, so the contract is shared with the backend.
export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });

export type Me = components["schemas"]["MeOut"];
export type SystemStatus = components["schemas"]["SystemStatusOut"];
export type Health = components["schemas"]["HealthOut"];
export type ProviderAvailability = components["schemas"]["ProviderAvailabilityOut"];
export type AuditEntry = components["schemas"]["AuditEntryOut"];
export type AuditVerify = components["schemas"]["AuditVerifyOut"];
export type Role = Me["role"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function hasPerm(me: Me | null | undefined, perm: string): boolean {
  return !!me && me.permissions.includes(perm);
}
export type Lot = components["schemas"]["LotOut"];
export type Roll = components["schemas"]["RollOut"];
export type RollCreate = components["schemas"]["RollCreate"];
