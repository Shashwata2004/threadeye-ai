"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useState, type ReactNode } from "react";

const MOCKING = process.env.NEXT_PUBLIC_API_MOCKING === "enabled";

// MSW is browser-only: load it with ssr:false so it never enters the server bundle.
const MockGate = dynamic(() => import("@/mocks/MockGate"), { ssr: false });

/** React Query + optional MSW (frontend development against the OpenAPI contract, no backend). */
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } }));
  const content = <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return MOCKING ? <MockGate>{content}</MockGate> : content;
}
