"use client";

import { useEffect, useState, type ReactNode } from "react";
import { worker } from "./browser";

/** Starts the MSW service worker, then renders the app (only when NEXT_PUBLIC_API_MOCKING=enabled). */
export default function MockGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    worker.start().then(() => setReady(true));
  }, []);
  return ready ? children : null;
}
