"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { init, use, type ECharts } from "echarts/core";
import { HeatmapChart } from "echarts/charts";
import { GridComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import type { Defect } from "@/lib/api/client";
import { useBi } from "@/components/screenKit";
import { ChartMessage, ChartValues, useChartColors } from "./shared";

export default function DefectHeatmap({ defects, lengthYd }: { defects: Defect[]; lengthYd: number }) {
  const bi = useBi();
  const t = useTranslations();
  const c = useChartColors();
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const confirmed = useMemo(() => defects.filter(d => d.kind === "defect" && d.status === "confirmed"), [defects]);
  const step = Math.max(1, Math.ceil(lengthYd / 60));
  const bins = Number.isFinite(lengthYd) && lengthYd > 0 ? Math.ceil(lengthYd / step) : 0;
  const valid = useMemo(() => confirmed.filter(d => Number.isFinite(d.center_yd) && d.center_yd >= 0 && d.center_yd <= lengthYd), [confirmed, lengthYd]);
  const classes = useMemo(() => [...new Set(valid.map(d => d.current_cls))].sort(), [valid]);
  const names = useMemo(() => classes.map(cls => t.has(`cls.${cls}`) ? t(`cls.${cls}`) : cls), [classes, t]);
  const ranges = useMemo(() => Array.from({ length: bins }, (_, i) => `${i * step}–${Math.min((i + 1) * step, lengthYd).toFixed(2)}`), [bins, step, lengthYd]);
  const cells = useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of valid) {
      const x = Math.min(bins - 1, Math.floor(d.center_yd / step));
      const y = classes.indexOf(d.current_cls);
      const key = `${x}:${y}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return classes.flatMap((_, y) => ranges.map((__, x) => [x, y, counts.get(`${x}:${y}`) ?? 0]));
  }, [valid, bins, step, classes, ranges]);
  const hasData = bins > 0 && valid.length > 0;
  const unit = bi("yd", "গজ");
  useEffect(() => {
    const element = ref.current;
    if (!element || !hasData) return;
    let disposed = false;
    let chart: ECharts | undefined;
    const observer = new ResizeObserver(() => chart?.resize());
    observer.observe(element);
    Promise.resolve().then(() => {
      if (disposed) return;
      use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, SVGRenderer]);
      chart = init(element, undefined, { renderer: "svg" });
      chart.setOption({
        animation: false, textStyle: { color: c.text },
        tooltip: { position: "top", renderMode: "richText", backgroundColor: c.background, textStyle: { color: c.text },
          formatter: (params: unknown) => {
            const [x, y, n] = (params as { value: number[] }).value;
            return `${names[y]}\n${ranges[x]} ${unit}: ${n}`;
          } },
        grid: { top: 10, bottom: 90, left: 8, right: 15, containLabel: true },
        xAxis: { type: "category", data: ranges, name: unit, nameLocation: "middle", nameGap: 45,
          axisLabel: { color: c.muted, rotate: 40 }, splitArea: { show: true } },
        yAxis: { type: "category", data: names, axisLabel: { color: c.muted, width: 115, overflow: "truncate" } },
        visualMap: { min: 0, max: Math.max(1, ...cells.map(v => v[2])), calculable: false, orient: "horizontal", bottom: 0,
          left: "center", precision: 0, textStyle: { color: c.text }, inRange: { color: [c.background, c.teal] } },
        series: [{ type: "heatmap", data: cells, itemStyle: { borderColor: c.grid, borderWidth: 1 }, emphasis: { itemStyle: { borderColor: c.amber, borderWidth: 2 } } }],
      });
      element.dataset.chartReady = "true";
      setError(false);
    }).catch(() => { if (!disposed) setError(true); });
    return () => { disposed = true; observer.disconnect(); chart?.dispose(); delete element.dataset.chartReady; };
  }, [hasData, names, ranges, cells, unit, c.text, c.muted, c.background, c.grid, c.teal, c.amber]);
  return <div data-testid="defect-heatmap">
    {!hasData ? <ChartMessage/> : <div ref={ref} hidden={error} style={{ height: Math.max(270, classes.length * 40 + 150) }} role="img" aria-label={bi("Confirmed defects by class and roll position", "শ্রেণি ও রোলের অবস্থান অনুযায়ী নিশ্চিত ত্রুটি")}/>}
    {error && <ChartMessage error/>}
    <p className="mt-2 text-xs text-slate-500">{bi(
      `Confirmed defects only; each counted once at its centre. Bin width: ${step} yd. This is a defect count, not cutting instructions or points.`,
      `শুধু নিশ্চিত ত্রুটি; প্রতিটি কেন্দ্রের অবস্থানে একবার গোনা। প্রতি ঘর: ${step} গজ। এটি ত্রুটির সংখ্যা, কাটিং নির্দেশনা বা পয়েন্ট নয়।`)}</p>
    {confirmed.length > valid.length && <p className="text-sm text-brand-amber">{bi("Some defects have unavailable or out-of-range positions and are not plotted.", "কিছু ত্রুটির অবস্থান অনুপস্থিত বা সীমার বাইরে, তাই চার্টে নেই।")}</p>}
    <ChartValues headers={[bi("Class", "শ্রেণি"), bi("Position (yd)", "অবস্থান (গজ)"), bi("Count", "সংখ্যা")]}
      rows={cells.filter(v => v[2] > 0).map(([x, y, n]) => [names[y], ranges[x], n])}/>
  </div>;
}
