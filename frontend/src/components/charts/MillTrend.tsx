"use client";

import { useEffect, useRef, useState } from "react";
import type { Chart } from "chart.js";
import { useBi } from "@/components/screenKit";
import { ChartMessage, ChartValues, useChartColors } from "./shared";

export default function MillTrend({ months, values, limit }: { months: string[]; values: (number | null)[]; limit: number }) {
  const bi = useBi();
  const c = useChartColors();
  const ref = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState(false);
  const hasData = values.some(v => v !== null);
  const label = bi("Points / 100 sq yd", "পয়েন্ট / ১০০ বর্গগজ");
  const reference = bi(`Reference: ${limit} pts`, `তুলনার সীমা: ${limit} পয়েন্ট`);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !hasData) return;
    let disposed = false;
    let chart: Chart<"line"> | undefined;
    import("chart.js").then(({ Chart, LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend }) => {
      if (disposed) return;
      Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend);
      chart = new Chart(canvas, {
        type: "line",
        data: { labels: months, datasets: [
          { label, data: values, borderColor: c.teal, backgroundColor: c.teal, pointRadius: 4, spanGaps: false },
          { label: reference, data: months.map(() => limit), borderColor: c.red, borderDash: [6, 5], pointRadius: 0 },
        ] },
        options: { responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { labels: { color: c.text } }, tooltip: { backgroundColor: c.background, titleColor: c.text, bodyColor: c.text, borderWidth: 1, borderColor: c.grid } },
          scales: { x: { ticks: { color: c.muted }, grid: { color: c.grid } }, y: { beginAtZero: true, suggestedMax: limit * 1.25, ticks: { color: c.muted }, grid: { color: c.grid } } },
        },
      });
      canvas.dataset.chartReady = "true";
      setError(false);
    }).catch(() => { if (!disposed) setError(true); });
    return () => { disposed = true; chart?.destroy(); delete canvas.dataset.chartReady; };
  }, [months, values, limit, hasData, label, reference, c.teal, c.red, c.text, c.muted, c.background, c.grid]);
  return <div data-testid="mill-trend">
    {!hasData ? <ChartMessage/> : <div className="relative h-64" hidden={error}><canvas ref={ref} role="img" aria-label={bi("Monthly mill quality trend", "মিলের মাসভিত্তিক মানের প্রবণতা")}/></div>}
    {error && <ChartMessage error/>}
    <p className="mt-2 text-xs text-slate-500">{bi("Gaps mean no inspected rolls. The 40-point line is the scorecard reference; actual buyer rules may differ.", "ফাঁকা অংশে পরীক্ষিত রোল নেই। ৪০ পয়েন্ট এই স্কোরকার্ডের তুলনার সীমা; বায়ারের আসল নিয়ম ভিন্ন হতে পারে।")}</p>
    <ChartValues headers={[bi("Month", "মাস"), label]} rows={months.map((m, i) => [m, values[i] ?? "—"])}/>
  </div>;
}
