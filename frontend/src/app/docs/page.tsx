"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Document, type DocumentData } from "@/components/docs/Document";
import { LanguageToggle } from "@/components/LanguageToggle";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";
import "@/styles/fabric.css";
export default function DocsPage() {
  const theme = useTheme();
  const q = useQuery({
    queryKey: ["public-docs"],
    queryFn: async () => {
      const r = await fetch("/api/v1/documentation", { cache: "no-store" });
      if (!r.ok) throw new Error("unavailable");
      return r.json() as Promise<DocumentData>;
    },
    refetchInterval: 15000,
    retry: false,
  });
  // Never retain content after an expired schedule or an unpublished response.
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const end = q.data?.content.ends_at;
    let timer: ReturnType<typeof setTimeout>;
    const check = () => {
      const remaining = end ? Date.parse(end) - Date.now() : Infinity;
      setExpired(remaining <= 0);
      if (end && remaining > 0) timer = setTimeout(check, Math.min(2147483647, remaining));
    };
    timer = setTimeout(check, 0);
    return () => clearTimeout(timer);
  }, [q.data?.content.ends_at]);
  return (
    <main className="te-linen min-h-screen" data-theme={theme}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-300 p-4">
        <Link href="/login" className="font-semibold">
          ThreadEye AI
        </Link>
        <div className="flex gap-3">
          <LanguageToggle loggedIn={false} />
          <ThemeToggle />
        </div>
      </div>
      {q.isError || expired ? (
        <div className="mx-auto max-w-xl p-10">
          <h1 className="text-2xl font-semibold">Documentation unavailable</h1>
          <p className="mt-3">
            This page is not currently published or could not be loaded.
          </p>
          <Link href="/login" className="mt-4 inline-block underline">
            Sign in
          </Link>
        </div>
      ) : q.data ? (
        <Document data={q.data} />
      ) : (
        <p role="status" className="p-10">
          Loading documentation…
        </p>
      )}
    </main>
  );
}
