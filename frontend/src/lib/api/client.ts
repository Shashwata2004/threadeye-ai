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
export type Inspection = components["schemas"]["InspectionSnapshot"];
export type InspectionListItem = components["schemas"]["InspectionListItem"];
export type Defect = components["schemas"]["DefectOut"];
// view_region is a 4-tuple in the schema; the generated response type widens it to number[].
export type Track = Omit<components["schemas"]["TrackOut"], "view_region"> & { view_region: number[] };
export type SamplingPlan = components["schemas"]["SamplingPlanOut"];
export type ScoreSummary = components["schemas"]["ScoreSummary"];
export type EventEnvelope = components["schemas"]["EventEnvelope"];
export type Dataset = components["schemas"]["DatasetOut"];
export type Machine = components["schemas"]["MachineOut"];

/** Defect classes the inspector can choose (taxonomy.yaml, kind "defect"). */
export const DEFECT_CLASSES = [
  "hole",
  "stain",
  "oil_stain",
  "slub",
  "broken_yarn",
  "missing_yarn",
  "knot",
  "crease_mark",
  "contamination",
  "shade_bar",
  "selvage_defect",
  "other_defect",
] as const;

export const REJECT_REASONS = [
  "sticker",
  "loose_thread",
  "wrinkle",
  "pin_hole",
  "hand",
  "board",
  "not_visible",
  "other",
] as const;

/** A fresh key per user action: a retried request with the same key is applied once. */
export function idempotencyKey(): string {
  return crypto.randomUUID();
}
