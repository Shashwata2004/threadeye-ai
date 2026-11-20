"use client";

import { useTheme } from "@/components/ThemeToggle";
import { useBi } from "@/components/screenKit";

export function useChartColors() {
  const dark = useTheme() === "dark";
  return {
    text: dark ? "#efe6d6" : "#1f2a37",
    muted: dark ? "#bcae98" : "#5b5446",
    grid: dark ? "#4e4436" : "#d6c8ad",
    background: dark ? "#27221c" : "#f5f0e6",
    teal: dark ? "#2dd4bf" : "#0f766e",
    amber: dark ? "#fbbf24" : "#b45309",
    red: dark ? "#f87171" : "#b91c1c",
    blue: dark ? "#93c5fd" : "#1d4ed8",
  };
}

export function ChartMessage({ error = false }: { error?: boolean }) {
  const bi = useBi();
  return <p role="status" className="py-8 text-sm text-slate-500">{error
    ? bi("The chart could not be drawn. Exact values are available below.", "চার্ট আঁকা যায়নি। নিচে সঠিক মান দেখুন।")
    : bi("No data to plot yet.", "এখনো চার্ট দেখানোর তথ্য নেই।")}</p>;
}

export function ChartValues({ headers, rows }: { headers: string[]; rows: (string | number)[][] }) {
  const bi = useBi();
  return <details className="mt-3 text-sm">
    <summary className="cursor-pointer text-brand-teal underline">{bi("View chart data", "চার্টের তথ্য দেখুন")}</summary>
    <div className="mt-2 max-h-72 overflow-auto"><table className="min-w-full text-left text-xs">
      <thead><tr>{headers.map((h, i) => <th key={i} className="p-2">{h}</th>)}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={i} className="border-t border-slate-200">
        {row.map((v, j) => <td key={j} className="p-2">{v}</td>)}
      </tr>)}</tbody>
    </table></div>
  </details>;
}
