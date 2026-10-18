"use client";

import { useLocale } from "next-intl";
import type { ReactNode } from "react";
import { SampleBadge } from "@/components/badges";
import "@/styles/screens.css";

/**
 * Small building blocks shared by the Benchmark, Mill scorecards, Change ledger and Admin screens.
 * Labels that have no key in messages/*.json yet are given inline in both languages through `useBi`,
 * so these screens do not touch the shared message files.
 */
export function useBi() {
  const bn = useLocale() === "bn";
  return (en: string, bnText: string) => (bn ? bnText : en);
}

export function PageHeader({
  title,
  subtitle,
  sample = true,
  actions,
}: {
  title: string;
  subtitle: string;
  sample?: boolean;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="te-serif text-2xl font-bold text-(--te-ink)">{title}</h1>
          {sample && <SampleBadge />}
        </div>
        <p className="te-serif text-sm text-(--te-ink-soft)">{subtitle}</p>
      </div>
      {actions}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`te-stitched rounded-lg p-5 ${className}`}>{children}</section>;
}

export function CardTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3">
      <h2 className="te-serif text-base font-semibold text-(--te-ink)">{children}</h2>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function KpiCard({
  label,
  value,
  sub,
  tone = "navy",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "navy" | "teal" | "amber" | "red" | "emerald";
}) {
  const tones = {
    navy: "text-(--te-ink)",
    teal: "text-brand-teal",
    amber: "text-brand-amber",
    red: "text-red-600",
    emerald: "text-emerald-600",
  } as const;
  return (
    <div className="te-stitched rounded-lg p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${tones[tone]}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

/** Shown to roles that may look at a screen but not change it (the API refuses their writes anyway). */
export function ViewOnlyNote({ children }: { children: ReactNode }) {
  return (
    <p role="note" className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-brand-amber">
      {children}
    </p>
  );
}

export const inputCls =
  "w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 focus:border-brand-teal focus:outline-none focus:ring-1 focus:ring-brand-teal disabled:bg-slate-100 disabled:text-slate-400";

export const primaryBtn =
  "inline-flex items-center justify-center gap-2 rounded-md bg-brand-teal px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50";

export const ghostBtn =
  "inline-flex items-center justify-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

export function Pill({ tone, children }: { tone: "emerald" | "amber" | "red" | "slate" | "teal" | "navy"; children: ReactNode }) {
  const tones = {
    emerald: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/30",
    amber: "bg-amber-500/10 text-brand-amber ring-amber-500/30",
    red: "bg-red-500/10 text-red-600 ring-red-500/30",
    slate: "bg-slate-100 text-slate-600 ring-slate-300",
    teal: "bg-teal-500/10 text-brand-teal ring-teal-500/30",
    navy: "bg-brand-navy/10 text-brand-navy ring-brand-navy/20",
  } as const;
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** Root class for these screens: turns on the fabric skin in styles/screens.css. */
export const screenRoot = "te-screen";

/** Fixed-point percentage, e.g. pct(0.914) → "91.4%". */
export function pct(x: number, digits = 1): string {
  return `${(x * 100).toFixed(digits)}%`;
}
