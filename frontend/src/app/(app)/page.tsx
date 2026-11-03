"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useMe, useSystemStatus, useProviders } from "@/lib/api/hooks";
import { hasPerm } from "@/lib/api/client";
import { request, type Dashboard } from "@/lib/api/operations";
import { Card, CardTitle, KpiCard, PageHeader, screenRoot, useBi } from "@/components/screenKit";
import { ProviderBadge, SampleBadge } from "@/components/badges";

export default function DashboardPage() {
  const bi = useBi();
  const {data: me} = useMe();
  const {data: status} = useSystemStatus();
  const {data: providers} = useProviders();
  const enabled = hasPerm(me, "dashboard.read") || hasPerm(me, "dashboard.own_shift");
  const query = useQuery({queryKey: ["dashboard"], enabled,
    queryFn: () => request<Dashboard>("/api/v1/dashboard"), refetchInterval: 15000});
  const data = query.data;
  const verification = Object.values(data?.verification ?? {});
  const failed = verification.some((v) => v.passed === false || v.status === "failed");
  const running = verification.some((v) => v.status === "running" || v.status === "queued");
  const checked = verification.length && !failed && !running;
  return <div className={`${screenRoot} space-y-5`}>
    <PageHeader title={bi("Dashboard", "ড্যাশবোর্ড")} sample={false}
      subtitle={`${bi("Today in Dhaka", "ঢাকার আজকের হিসাব")} · ${data?.date ?? "—"} · ${me?.display_name ?? ""}`}/>
    {enabled && <>
      {query.isError && <p role="alert" className="text-red-600">{bi("Dashboard could not be loaded.", "হিসাব আনা যায়নি।")}</p>}
      <p className="text-sm text-slate-500">{bi("Latest finalized inspection per roll today. Inspector accounts see their own work.",
        "আজ প্রতি রোলের সর্বশেষ চূড়ান্ত পরীক্ষার হিসাব। ইন্সপেক্টর শুধু নিজের কাজ দেখেন।")}</p>
      {!!data?.simulated_rolls && <p className="flex items-center gap-2 text-sm"><SampleBadge/>{bi(
        `${data.simulated_rolls} rolls used simulated video; these are not factory impact measurements.`,
        `${data.simulated_rolls}টি রোলে ভিডিও সিমুলেটেড; এগুলো কারখানার impact-এর মাপ নয়।`)}</p>}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="kpi-tiles">
        <KpiCard label={bi("Rolls inspected", "পরীক্ষিত রোল")} value={data?.rolls ?? "—"}/>
        <KpiCard label="PASS / BORDERLINE / FAIL" value={data ?
          `${data.verdicts.PASS ?? 0} / ${data.verdicts.BORDERLINE ?? 0} / ${data.verdicts.FAIL ?? 0}` : "—"}/>
        <KpiCard label={bi("Average points / 100 sq yd", "প্রতি ১০০ বর্গগজে গড় পয়েন্ট")} value={data?.avg_per_100?.toFixed(2) ?? "—"}/>
        <KpiCard label={bi("Average coverage", "গড় কভারেজ")} value={data?.coverage_pct == null ? "—" : `${data.coverage_pct}%`}/>
        <KpiCard label={bi("Rejected share of reviewed AI flags", "পর্যালোচিত AI সতর্কতার বাতিল অংশ")}
          value={data?.false_alarm_share == null ? "—" : `${(data.false_alarm_share * 100).toFixed(1)}%`}
          sub={bi(`${data?.reviewed_detections ?? 0} reviewed flags; not test-set false-positive rate`,
            `${data?.reviewed_detections ?? 0}টি পর্যালোচিত সতর্কতা; test-set false-positive rate নয়`)}/>
      </section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardTitle>{bi("Today's verification", "আজকের যাচাই")}</CardTitle>
          <p data-testid="verification-status" className={failed ? "text-red-600" : checked ? "text-emerald-600" : "text-brand-amber"}>
            {failed ? bi("RED: check failed", "লাল: যাচাইয়ে সমস্যা") : checked ? bi("GREEN: checked machines passed", "সবুজ: যাচাই করা মেশিন উত্তীর্ণ") :
              running ? bi("Checks are running", "যাচাই চলছে") : bi("AMBER: no check today", "হলুদ: আজ যাচাই হয়নি")}</p>
          <Link href="/verification" className="text-brand-teal underline">{bi("Open verification", "যাচাই খুলুন")}</Link>
        </Card>
        <Card><CardTitle>{bi("Confirmed defects", "নিশ্চিত ত্রুটি")}</CardTitle>
          {Object.entries(data?.defect_mix ?? {}).map(([name, n]) => <p key={name}>{name}: {n}</p>)}
          {!Object.keys(data?.defect_mix ?? {}).length && <p>{bi("No confirmed defects today.", "আজ নিশ্চিত ত্রুটি নেই।")}</p>}
        </Card>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{[
        [bi("By machine", "মেশিন অনুযায়ী"), data?.by_machine],
        [bi("By mill", "মিল অনুযায়ী"), data?.by_supplier],
      ].map(([label, counts], index) => <Card key={index}><CardTitle>{String(label)}</CardTitle>
        {Object.entries((counts ?? {}) as Record<string, number>).map(([name, n]) => <p key={name}>{name}: {n}</p>)}
      </Card>)}</div>
      <Card><CardTitle>{bi("Open inspections", "অসমাপ্ত পরীক্ষা")}</CardTitle>
        {data?.active.map((row) => <p key={row.id}><Link className="text-brand-teal underline" href={`/inspect/${row.id}`}>
          {row.id.slice(0, 8)} · {row.status}</Link></p>)}
        {data && !data.active.length && <p>{bi("No open inspections.", "অসমাপ্ত পরীক্ষা নেই।")}</p>}
      </Card>
    </>}
    <Card><CardTitle>{bi("System", "সিস্টেম")}</CardTitle>
      <div data-testid="system-status">{bi("Database", "ডাটাবেজ")}: {status?.db ?? "—"} · {bi("Worker", "ওয়ার্কার")}: {status?.worker.alive ? bi("Online", "চালু") : bi("Not connected", "সংযুক্ত নেই")}</div>
      {providers?.filter((p) => p.active).map((p) => <ProviderBadge key={p.provider_id} name={p.display_name} simulated={p.is_simulated}/>)}
    </Card>
  </div>;
}
