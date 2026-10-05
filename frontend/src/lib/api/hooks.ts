"use client";

import { useQuery } from "@tanstack/react-query";
import { ApiError, api, type Me } from "./client";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Me | null> => {
      const { data, response } = await api.GET("/api/v1/auth/me");
      if (response.status === 401) return null;
      if (!data) throw new ApiError(response.status, "failed to load session");
      return data;
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data, response } = await api.GET("/health");
      if (!data) throw new ApiError(response.status, "health check failed");
      return data;
    },
    staleTime: 30_000,
  });
}

export function useSystemStatus(enabled = true) {
  return useQuery({
    queryKey: ["system-status"],
    enabled,
    refetchInterval: 10_000,
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/system/status");
      if (!data) throw new ApiError(response.status, "status unavailable");
      return data;
    },
  });
}

export function useProviders(enabled = true) {
  return useQuery({
    queryKey: ["providers"],
    enabled,
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/providers");
      if (!data) throw new ApiError(response.status, "providers unavailable");
      return data;
    },
  });
}

export function useAudit(enabled = true) {
  return useQuery({
    queryKey: ["audit"],
    enabled,
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/audit", { params: { query: { limit: 100 } } });
      if (!data) throw new ApiError(response.status, "audit unavailable");
      return data;
    },
  });
}

// ------------------------------------------------------------------------------------ receiving (M1)
async function must<T>(p: Promise<{ data?: T; response: Response }>, what: string): Promise<T> {
  const { data, response } = await p;
  if (data === undefined) throw new ApiError(response.status, `${what} unavailable`);
  return data;
}

export function useLots() {
  return useQuery({ queryKey: ["lots"], queryFn: () => must(api.GET("/api/v1/lots"), "lots") });
}

export function useLot(id: string) {
  return useQuery({
    queryKey: ["lot", id],
    queryFn: () => must(api.GET("/api/v1/lots/{lot_id}", { params: { path: { lot_id: id } } }), "lot"),
  });
}

export function useLotRolls(id: string) {
  return useQuery({
    queryKey: ["lot-rolls", id],
    queryFn: () => must(api.GET("/api/v1/rolls", { params: { query: { lot_id: id } } }), "rolls"),
  });
}

export function useSampling(id: string) {
  return useQuery({
    queryKey: ["lot-sampling", id],
    queryFn: () =>
      must(api.GET("/api/v1/lots/{lot_id}/sampling-suggestion", { params: { path: { lot_id: id } } }), "sampling"),
  });
}

export function useMasterData(enabled = true) {
  const suppliers = useQuery({
    queryKey: ["suppliers"],
    enabled,
    queryFn: () => must(api.GET("/api/v1/suppliers"), "suppliers"),
  });
  const buyers = useQuery({ queryKey: ["buyers"], enabled, queryFn: () => must(api.GET("/api/v1/buyers"), "buyers") });
  const profiles = useQuery({
    queryKey: ["rule-profiles"],
    enabled,
    queryFn: () => must(api.GET("/api/v1/rule-profiles"), "profiles"),
  });
  return { suppliers, buyers, profiles };
}

/** FastAPI error bodies: {"detail": "..."}, {"detail": {"message": ...}} or a validation list.
 *  Without a readable body (e.g. a server error), the HTTP status is shown instead. */
export function errorDetail(error: unknown, status?: number): string {
  if (error && typeof error === "object" && "detail" in error) {
    const d = (error as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "message" in d) return String((d as { message: unknown }).message);
    if (Array.isArray(d) && d[0] && typeof d[0] === "object" && "msg" in d[0]) return String(d[0].msg);
  }
  if (status && status >= 500) return `server error (HTTP ${status}); check the API log`;
  return status ? `HTTP ${status}` : "unknown error";
}

// ------------------------------------------------------------------------------------ inspection (M2)
export function useDatasets(enabled = true) {
  return useQuery({ queryKey: ["datasets"], enabled, queryFn: () => must(api.GET("/api/v1/datasets"), "datasets") });
}

export function useMachines(enabled = true) {
  return useQuery({ queryKey: ["machines"], enabled, queryFn: () => must(api.GET("/api/v1/machines"), "machines") });
}

export function useInspections(params: { open_only?: boolean; roll_id?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ["inspections", params],
    queryFn: () => must(api.GET("/api/v1/inspections", { params: { query: params } }), "inspections"),
  });
}

export function useInspection(id: string) {
  return useQuery({
    queryKey: ["inspection", id],
    queryFn: () =>
      must(api.GET("/api/v1/inspections/{inspection_id}", { params: { path: { inspection_id: id } } }), "inspection"),
  });
}

export function useTrack(id: string, enabled = true) {
  return useQuery({
    queryKey: ["track", id],
    enabled,
    staleTime: Infinity,
    retry: false,
    queryFn: () =>
      must(api.GET("/api/v1/inspections/{inspection_id}/track", { params: { path: { inspection_id: id } } }), "track"),
  });
}

export function usePlan(id: string, enabled = true) {
  return useQuery({
    queryKey: ["plan", id],
    enabled,
    staleTime: Infinity,
    queryFn: () =>
      must(api.GET("/api/v1/inspections/{inspection_id}/plan", { params: { path: { inspection_id: id } } }), "plan"),
  });
}

export function useDefects(id: string) {
  return useQuery({
    queryKey: ["defects", id],
    queryFn: () =>
      must(api.GET("/api/v1/inspections/{inspection_id}/defects", { params: { path: { inspection_id: id } } }), "defects"),
  });
}
