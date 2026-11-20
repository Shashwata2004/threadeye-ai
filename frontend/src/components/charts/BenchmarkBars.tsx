"use client";

import { useEffect, useRef, useState } from "react";
import type * as Plotly from "plotly.js";
import { useBi } from "@/components/screenKit";
import { ChartMessage, ChartValues, useChartColors } from "./shared";

export type BenchmarkRow = { label: string; first: number | null; second: number | null };

export default function BenchmarkBars({ rows, firstLabel, secondLabel }: { rows: BenchmarkRow[]; firstLabel: string; secondLabel: string }) {
  const bi = useBi();
  const c = useChartColors();
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const hasData = rows.some(r => r.first !== null || r.second !== null);
  useEffect(() => {
    const element = ref.current;
    if (!element || !hasData) return;
    // Each effect owns its plot node, so a late cleanup cannot purge a newer plot.
    const target = document.createElement("div");
    target.style.width = "100%";
    target.style.height = "100%";
    element.replaceChildren(target);
    let disposed = false;
    let plot: typeof Plotly | undefined;
    let ready = false;
    const observer = new ResizeObserver(() => { if (ready) plot?.Plots.resize(target); });
    observer.observe(element);
    import("plotly.js-basic-dist-min").then(async module => {
      if (disposed) return;
      plot = module.default;
      const traces: Plotly.Data[] = [
        { type: "bar", orientation: "h", name: firstLabel, y: rows.map(r => r.label), x: rows.map(r => r.first === null ? null : r.first * 100), marker: { color: c.teal } },
        { type: "bar", orientation: "h", name: secondLabel, y: rows.map(r => r.label), x: rows.map(r => r.second === null ? null : r.second * 100), marker: { color: c.blue } },
      ];
      await plot.newPlot(target, traces, {
        autosize: true, barmode: "group", paper_bgcolor: "transparent", plot_bgcolor: "transparent",
        font: { color: c.text }, margin: { l: 130, r: 12, t: 55, b: 45 },
        legend: { orientation: "h", x: 0, y: 1.16 },
        xaxis: { range: [0, 100], tickmode: "array", tickvals: [0, 50, 100], ticksuffix: "%", gridcolor: c.grid, fixedrange: false, automargin: true },
        yaxis: { autorange: "reversed", automargin: true, fixedrange: true,
          tickmode: "array", tickvals: rows.map(r => r.label), ticktext: rows.map(r => r.label.length > 20 ? `${r.label.slice(0, 18)}…` : r.label) },
        hoverlabel: { bgcolor: c.background, font: { color: c.text } },
      }, { responsive: true, displaylogo: false, displayModeBar: false });
      if (disposed) { plot.purge(target); return; }
      ready = true;
      element.dataset.chartReady = "true";
      setError(false);
    }).catch(() => { if (!disposed) setError(true); });
    return () => { disposed = true; ready = false; observer.disconnect(); plot?.purge(target); target.remove(); delete element.dataset.chartReady; };
  }, [rows, firstLabel, secondLabel, hasData, c.teal, c.blue, c.text, c.grid, c.background]);
  return <div data-testid="benchmark-bars">
    {!hasData ? <ChartMessage/> : <div ref={ref} hidden={error} style={{ height: Math.max(280, rows.length * 48 + 100) }} role="img" aria-label={bi("Model evaluation comparison", "মডেলের মূল্যায়নের তুলনা")}/>}
    {error && <ChartMessage error/>}
    <ChartValues headers={[bi("Source / class", "উৎস / শ্রেণি"), firstLabel, secondLabel]} rows={rows.map(r => [r.label, r.first === null ? "—" : `${(r.first * 100).toFixed(1)}%`, r.second === null ? "—" : `${(r.second * 100).toFixed(1)}%`])}/>
  </div>;
}
