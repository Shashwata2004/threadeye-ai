import { useQuery } from "@tanstack/react-query";
import type { components } from "./schema";
import { ApiError } from "./client";
import { errorDetail } from "./hooks";

export type Profile = components["schemas"]["ProfileOut"];
export type Rules = components["schemas"]["RuleProfile"];
export type MachineDetail = components["schemas"]["MachineDetail"];
export type User = components["schemas"]["UserOut"];
export interface RollEvaluation {
  dataset_id: string; simulated_video: boolean; simulated_detections: boolean; provider: string;
  evaluation: {tp: number; fp: number; fn: number; precision: number; recall: number; missed: string[];
    recall_per_class: Record<string, number>; fp_by_type: Record<string, number>};
  passed: boolean; reasons: string[]; points: number; per_100: number; verdict: string;
  truth_points: number; truth_per_100: number; truth_verdict: string; score_delta: number;
  coverage_pct: number; seconds: number; funnel: Record<string, number>;
}
export type Run = Omit<components["schemas"]["RunOut"], "result"> & {
  result: {passed?: boolean; rolls?: RollEvaluation[]; storage_key?: string} | null;
};
export interface Cutting {
  inspection_id: string; source_hash: string; simulated: boolean;
  policy_selection?: "buyer" | "all" | "two_plus" | "three_plus" | "four_plus";
  policy_locked?: boolean;
  fabric?: {image_url: string; length_yd: number; width_cm: number} | null;
  defects?: {id: string; number: number; cls: string; start_yd: number; end_yd: number;
    across_start_cm: number; across_end_cm: number}[];
  status: "draft" | "approved" | "acknowledged"; approved_at: string | null; acknowledged_at: string | null;
  plan: {length_yd: number; usable_yd: number; skipped_yd: number;
    segments: {start_yd: number; end_yd: number; action: "keep" | "skip"}[];
    policy: {margin_in: number; min_piece_yd: number; min_points_to_cut: number}};
}
export interface CuttingWork {
  inspection_id: string; roll_code: string; challan: string;
  status: "approved" | "acknowledged"; approved_at: string; acknowledged_at: string | null;
  usable_yd: number; skipped_yd: number;
}
export interface Dashboard {
  date: string; scope: string; rolls: number; verdicts: Record<string, number>; avg_per_100: number | null;
  false_alarm_share: number | null; reviewed_detections: number; simulated_rolls: number;
  defect_mix: Record<string, number>;
  coverage_pct: number | null; by_machine: Record<string, number>; by_supplier: Record<string, number>;
  verification: Record<string, {run_id: string; status: string; passed: boolean | null; at: string}>;
  active: {id: string; roll_id: string; status: string}[];
}

export async function request<T>(url: string, body?: unknown, method = "POST"): Promise<T> {
  const response = await fetch(url, {credentials: "same-origin", method: body === undefined ? "GET" : method,
    headers: body === undefined ? undefined : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, errorDetail(data, response.status));
  return data as T;
}

export function useRuns(kind: "verification" | "benchmark", machineId?: string) {
  return useQuery({queryKey: [kind, "runs", machineId],
    queryFn: () => request<Run[]>(`/api/v1/${kind}/runs${machineId ? `?machine_id=${machineId}` : ""}`),
    refetchInterval: (query) => query.state.data?.some((r) => r.status === "queued" || r.status === "running") ? 1500 : 15000});
}
