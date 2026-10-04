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

/** FastAPI error bodies: {"detail": "..."} or a validation list. */
export function errorDetail(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const d = (error as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0] && typeof d[0] === "object" && "msg" in d[0]) return String(d[0].msg);
  }
  return "unknown error";
}
