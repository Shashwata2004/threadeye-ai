"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useBi } from "@/components/screenKit";
import { ChartMessage, ChartValues, useChartColors } from "./shared";

export default function VerdictDonut({ verdicts }: { verdicts: Record<string, number> }) {
  const bi = useBi();
  const c = useChartColors();
  const values = [
    { name: bi("PASS", "পাস"), value: verdicts.PASS ?? 0, color: c.teal },
    { name: bi("BORDERLINE", "সীমার কাছাকাছি"), value: verdicts.BORDERLINE ?? 0, color: c.amber },
    { name: bi("FAIL", "ফেল"), value: verdicts.FAIL ?? 0, color: c.red },
  ];
  const total = values.reduce((sum, row) => sum + row.value, 0);
  return <div data-testid="verdict-donut">
    {!total ? <ChartMessage/> : <>
      <div className="relative mx-auto h-64 w-full max-w-lg" role="img" aria-label={bi("Today's roll verdict distribution", "আজকের রোলের ফলাফলের অনুপাত")}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart><Pie data={values.filter(v => v.value > 0)} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="88%" stroke={c.background} isAnimationActive={false}>
            {values.filter(v => v.value > 0).map(v => <Cell key={v.name} fill={v.color}/>) }
          </Pie><Tooltip contentStyle={{ background: c.background, color: c.text, borderColor: c.grid }} itemStyle={{ color: c.text }}/></PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <strong className="text-3xl font-bold">{total}</strong><span className="text-sm text-slate-500">{bi("rolls", "রোল")}</span>
        </div>
      </div>
      <ul className="flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm">{values.map(v => <li key={v.name} className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-full" style={{ background: v.color }}/>{v.name}: <strong>{v.value}</strong>
      </li>)}</ul>
    </>}
    <ChartValues headers={[bi("Verdict", "ফলাফল"), bi("Rolls", "রোল")]} rows={values.map(v => [v.name, v.value])}/>
  </div>;
}
