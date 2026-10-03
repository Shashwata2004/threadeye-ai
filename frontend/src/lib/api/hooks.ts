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
