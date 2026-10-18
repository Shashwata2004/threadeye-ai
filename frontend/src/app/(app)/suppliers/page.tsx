"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { hasPerm } from "@/lib/api/client";
import { useMe } from "@/lib/api/hooks";
import {
  Card,
  CardTitle,
  KpiCard,
  PageHeader,
  Pill,
  ViewOnlyNote,
  ghostBtn,
  inputCls,
  pct,
  screenRoot,
  useBi,
} from "@/components/screenKit";

// Sample scorecards (fictional mills) until the M5 scorecard endpoint exists.
const FAIL_LIMIT = 40;
const MONTHS = [
  { en: "May", bn: "মে" },
  { en: "Jun", bn: "জুন" },
  { en: "Jul", bn: "জুলাই" },
  { en: "Aug", bn: "আগস্ট" },
  { en: "Sep", bn: "সেপ্টে" },
  { en: "Oct", bn: "অক্টো" },
];

type Status = "accepted" | "review" | "rejected";
interface Delivery {
  challan: string;
  received: string;
  fabric: string;
  pass: number;
  review: number;
  fail: number;
  avgPts: number;
  shortageYd: number;
  status: Status;
  claimUsd?: number;
}
interface Mill {
  id: string;
  name: string;
  acceptance: number;
  avgPts: number;
  claims: number;
  claimUsd: number;
  shortage: number;
  trend: number[];
  mix: { en: string; bn: string; share: number }[];
  deliveries: Delivery[];
}

const MILLS: Mill[] = [
  {
    id: "mill-a",
    name: "Sample Mill A (Shaoxing)",
    acceptance: 0.789,
    avgPts: 26.8,
    claims: 3,
    claimUsd: 10200,
    shortage: 0.016,
    trend: [22.4, 25.1, 31.6, 43.2, 28.9, 26.8],
    mix: [
      { en: "Shade variation", bn: "রঙের তারতম্য", share: 45 },
      { en: "Oil stains", bn: "তেলের দাগ", share: 25 },
      { en: "Broken yarn", bn: "ছেঁড়া সুতা", share: 20 },
      { en: "Holes", bn: "ছিদ্র", share: 10 },
    ],
    deliveries: [
      { challan: "CH-2026-1004", received: "2026-10-12", fabric: "Cotton twill 3/1", pass: 7, review: 2, fail: 1, avgPts: 24.6, shortageYd: 14.5, status: "review" },
      { challan: "CH-2026-0988", received: "2026-09-28", fabric: "Poplin 40s", pass: 9, review: 1, fail: 0, avgPts: 18.2, shortageYd: 12.0, status: "accepted", claimUsd: 1200 },
      { challan: "CH-2026-0941", received: "2026-08-19", fabric: "Cotton twill 3/1", pass: 4, review: 2, fail: 4, avgPts: 43.2, shortageYd: 22.8, status: "rejected", claimUsd: 6400 },
      { challan: "CH-2026-0903", received: "2026-07-30", fabric: "Canvas 10 oz", pass: 6, review: 2, fail: 2, avgPts: 31.6, shortageYd: 9.4, status: "rejected", claimUsd: 2600 },
    ],
  },
  {
    id: "pacific",
    name: "Pacific Denim Mills",
    acceptance: 0.861,
    avgPts: 19.7,
    claims: 2,
    claimUsd: 6100,
    shortage: 0.011,
    trend: [18.1, 20.4, 22.9, 19.5, 17.8, 19.7],
    mix: [
      { en: "Shade variation", bn: "রঙের তারতম্য", share: 38 },
      { en: "Slubs", bn: "স্লাব", share: 27 },
      { en: "Broken yarn", bn: "ছেঁড়া সুতা", share: 21 },
      { en: "Oil stains", bn: "তেলের দাগ", share: 14 },
    ],
    deliveries: [
      { challan: "CH-2026-1011", received: "2026-10-14", fabric: "Denim 12 oz", pass: 11, review: 1, fail: 0, avgPts: 16.9, shortageYd: 2.1, status: "accepted" },
      { challan: "CH-2026-0972", received: "2026-09-21", fabric: "Stretch denim 10 oz", pass: 8, review: 2, fail: 2, avgPts: 27.3, shortageYd: 11.0, status: "rejected", claimUsd: 4200 },
      { challan: "CH-2026-0930", received: "2026-08-09", fabric: "Denim 12 oz", pass: 10, review: 1, fail: 1, avgPts: 22.9, shortageYd: 8.2, status: "rejected", claimUsd: 1900 },
    ],
  },
  {
    id: "bengal",
    name: "Bengal Knit Fabrics",
    acceptance: 0.912,
    avgPts: 15.9,
    claims: 1,
    claimUsd: 2100,
    shortage: 0.008,
    trend: [17.2, 16.4, 14.8, 15.1, 16.6, 15.9],
    mix: [
      { en: "Holes", bn: "ছিদ্র", share: 41 },
      { en: "Needle lines", bn: "সুইয়ের দাগ", share: 29 },
      { en: "Oil stains", bn: "তেলের দাগ", share: 18 },
      { en: "Shade variation", bn: "রঙের তারতম্য", share: 12 },
    ],
    deliveries: [
      { challan: "CH-2026-1009", received: "2026-10-10", fabric: "Single jersey 160 gsm", pass: 14, review: 1, fail: 0, avgPts: 14.2, shortageYd: 0.0, status: "accepted" },
      { challan: "CH-2026-0961", received: "2026-09-15", fabric: "Pique 220 gsm", pass: 12, review: 2, fail: 1, avgPts: 19.8, shortageYd: 6.5, status: "rejected", claimUsd: 2100 },
      { challan: "CH-2026-0919", received: "2026-08-02", fabric: "Rib 1x1", pass: 13, review: 1, fail: 0, avgPts: 15.1, shortageYd: 1.2, status: "accepted" },
    ],
  },
];

const MIX_COLORS = ["bg-brand-navy", "bg-brand-teal", "bg-amber-500", "bg-red-500"];

export default function SuppliersPage() {
  const t = useTranslations();
  const bi = useBi();
  const { data: me } = useMe();
  const canClaim = hasPerm(me, "claims.write");

  const [millId, setMillId] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [drafted, setDrafted] = useState<Set<string>>(new Set());

  const selected = MILLS.find((m) => m.id === millId);
  const view = useMemo(() => {
    if (selected) return selected;
    // All mills: roll-weighted where it matters, plain average for the trend.
    const rolls = (m: Mill) => m.deliveries.reduce((s, d) => s + d.pass + d.review + d.fail, 0);
    const total = MILLS.reduce((s, m) => s + rolls(m), 0);
    return {
      acceptance: 0.846,
      avgPts: 21.4,
      claims: MILLS.reduce((s, m) => s + m.claims, 0),
      claimUsd: MILLS.reduce((s, m) => s + m.claimUsd, 0),
      shortage: 0.012,
      trend: MONTHS.map((_, i) => MILLS.reduce((s, m) => s + m.trend[i] * rolls(m), 0) / total),
      mix: null,
    };
  }, [selected]);

  const rows = MILLS.filter((m) => !selected || m.id === selected.id)
    .flatMap((m) => m.deliveries.map((d) => ({ ...d, mill: m.name })))
    .filter((d) => {
      const q = query.trim().toLowerCase();
      return !q || d.challan.toLowerCase().includes(q) || d.fabric.toLowerCase().includes(q) || d.mill.toLowerCase().includes(q);
    })
    .sort((a, b) => b.received.localeCompare(a.received));

  const chartMax = 50;
  const statusPill = (s: Status) =>
    s === "accepted" ? (
      <Pill tone="emerald">{bi("Accepted", "গৃহীত")}</Pill>
    ) : s === "review" ? (
      <Pill tone="amber">{bi("Under review", "পর্যালোচনায়")}</Pill>
    ) : (
      <Pill tone="red">{bi("Rejected", "প্রত্যাখ্যাত")}</Pill>
    );

  return (
    <div className={`${screenRoot} space-y-5`}>
      <PageHeader title={t("nav.suppliers")} subtitle={t("placeholder.suppliers")} />

      <Card className="flex flex-wrap items-end gap-3">
        <label className="min-w-56 flex-1 text-sm">
          <span className="mb-1 block font-medium text-slate-700">{bi("Mill", "মিল")}</span>
          <select className={inputCls} value={millId} onChange={(e) => setMillId(e.target.value)}>
            <option value="all">{bi("All mills", "সব মিল")}</option>
            {MILLS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-56 flex-1 text-sm">
          <span className="mb-1 block font-medium text-slate-700">{bi("Search deliveries", "চালান খুঁজুন")}</span>
          <input
            type="search"
            className={inputCls}
            placeholder={bi("Challan no., fabric or mill", "চালান নং, ফেব্রিক বা মিল")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label={bi("Mill acceptance rate", "মিলের গ্রহণযোগ্যতার হার")}
          value={pct(view.acceptance)}
          sub={bi("Rolls accepted", "গৃহীত রোল")}
          tone={view.acceptance >= 0.85 ? "emerald" : "amber"}
        />
        <KpiCard
          label={bi("Avg points / 100 sq yd", "গড় পয়েন্ট / ১০০ বর্গগজ")}
          value={<span className="font-mono">{view.avgPts.toFixed(1)}</span>}
          sub={bi(`Fail limit ${FAIL_LIMIT} pts`, `ফেল সীমা ${FAIL_LIMIT} পয়েন্ট`)}
          tone={view.avgPts >= FAIL_LIMIT ? "red" : "navy"}
        />
        <KpiCard
          label={bi("Defect claims raised", "উত্থাপিত ক্লেইম")}
          value={`$${view.claimUsd.toLocaleString("en-US")}`}
          sub={bi(`Across ${view.claims} claims`, `${view.claims}টি ক্লেইমে`)}
          tone="red"
        />
        <KpiCard
          label={bi("Avg yardage shortage", "গড় গজ ঘাটতি")}
          value={pct(view.shortage)}
          sub={bi("Declared vs measured", "ঘোষিত বনাম মাপা")}
          tone="amber"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardTitle hint={bi("Average defect points per 100 sq yd, by month.", "মাসভিত্তিক গড় ত্রুটি পয়েন্ট (প্রতি ১০০ বর্গগজ)।")}>
            {bi("Quality trend", "মানের প্রবণতা")}
          </CardTitle>
          <div className="relative h-48 border-b border-l border-slate-200 pl-1">
            <div
              className="absolute inset-x-0 border-t-2 border-dashed border-red-500"
              style={{ bottom: `${(FAIL_LIMIT / chartMax) * 100}%` }}
            >
              <span className="absolute -top-5 right-0 text-xs font-semibold text-red-600">
                {bi(`Fail ${FAIL_LIMIT} pts`, `ফেল ${FAIL_LIMIT} পয়েন্ট`)}
              </span>
            </div>
            <div className="flex h-full items-end justify-around gap-2">
              {view.trend.map((v, i) => (
                <div key={MONTHS[i].en} className="flex h-full w-full max-w-12 flex-col items-center justify-end">
                  <span className="mb-1 font-mono text-xs text-slate-600">{v.toFixed(1)}</span>
                  <div
                    className={`w-full rounded-t transition-all duration-500 ${
                      v >= FAIL_LIMIT ? "bg-red-500" : v >= 28 ? "bg-amber-500" : "bg-emerald-500"
                    }`}
                    style={{ height: `${(Math.min(v, chartMax) / chartMax) * 100}%` }}
                    title={`${bi(MONTHS[i].en, MONTHS[i].bn)}: ${v.toFixed(1)}`}
                  />
                </div>
              ))}
            </div>
          </div>
          <div className="mt-1 flex justify-around pl-1 text-xs text-slate-500">
            {MONTHS.map((m) => (
              <span key={m.en} className="w-full max-w-12 text-center">
                {bi(m.en, m.bn)}
              </span>
            ))}
          </div>
        </Card>

        <Card>
          <CardTitle hint={bi("Where this mill's defect points come from.", "এই মিলের ত্রুটি কোথা থেকে আসে।")}>
            {bi("Defect mix", "ত্রুটির ধরন")}
          </CardTitle>
          {view.mix ? (
            <>
              <div className="flex h-7 overflow-hidden rounded">
                {view.mix.map((x, i) => (
                  <div key={x.en} className={MIX_COLORS[i % MIX_COLORS.length]} style={{ width: `${x.share}%` }} title={`${bi(x.en, x.bn)} ${x.share}%`} />
                ))}
              </div>
              <ul className="mt-4 flex flex-wrap gap-2">
                {view.mix.map((x, i) => (
                  <li key={x.en} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-sm">
                    <span className={`h-2.5 w-2.5 rounded-full ${MIX_COLORS[i % MIX_COLORS.length]}`} />
                    <span className="font-mono font-semibold text-brand-navy">{x.share}%</span>
                    <span className="text-slate-700">{bi(x.en, x.bn)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <ul className="space-y-3">
              {MILLS.map((m) => (
                <li key={m.id}>
                  <button type="button" onClick={() => setMillId(m.id)} className="w-full text-left">
                    <span className="mb-1 block text-sm font-medium text-brand-navy hover:underline">{m.name}</span>
                    <span className="flex h-3 overflow-hidden rounded">
                      {m.mix.map((x, i) => (
                        <span key={x.en} className={MIX_COLORS[i % MIX_COLORS.length]} style={{ width: `${x.share}%` }} />
                      ))}
                    </span>
                  </button>
                </li>
              ))}
              <li className="text-xs text-slate-500">{bi("Pick a mill to see its full mix.", "পূর্ণ বিবরণ দেখতে একটি মিল বাছুন।")}</li>
            </ul>
          )}
        </Card>
      </div>

      <Card>
        <CardTitle>{bi("Recent deliveries & roll history", "সাম্প্রতিক চালান ও রোলের ইতিহাস")}</CardTitle>
        {!canClaim && (
          <div className="mb-3">
            <ViewOnlyNote>
              {bi("View only: claims are raised by a merchandiser or admin.", "শুধু দেখার জন্য: ক্লেইম তোলেন মার্চেন্ডাইজার বা অ্যাডমিন।")}
            </ViewOnlyNote>
          </div>
        )}
        {rows.length === 0 ? (
          <p className="text-sm text-slate-500">{bi("No deliveries match your search.", "আপনার খোঁজের সাথে কোনো চালান মেলেনি।")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-100 text-left text-slate-700">
                <tr>
                  <th className="px-3 py-2 whitespace-nowrap">
                    {bi("Challan no.", "চালান নং")}
                    {!selected && ` · ${bi("Mill", "মিল")}`}
                  </th>
                  <th className="px-3 py-2">{bi("Received", "গ্রহণের তারিখ")}</th>
                  <th className="px-3 py-2">{bi("Fabric", "ফেব্রিক")}</th>
                  <th className="px-3 py-2 text-right">{bi("Rolls", "রোল")}</th>
                  <th className="px-3 py-2">{bi("Pass / Review / Fail", "পাস / পর্যালোচনা / ফেল")}</th>
                  <th className="px-3 py-2 text-right">{bi("Avg pts/100 yd²", "গড় পয়েন্ট")}</th>
                  <th className="px-3 py-2 text-right">{bi("Shortage (yd)", "ঘাটতি (গজ)")}</th>
                  <th className="px-3 py-2">{bi("Status & claim", "অবস্থা ও ক্লেইম")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => {
                  const rolls = d.pass + d.review + d.fail;
                  const claimable = !d.claimUsd && (d.status !== "accepted" || d.shortageYd > 10);
                  return (
                    <tr key={d.challan} className="border-t border-slate-100 align-middle">
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="font-mono text-xs">{d.challan}</span>
                        {!selected && <span className="block text-xs text-slate-500">{d.mill}</span>}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap font-mono text-xs text-slate-600">{d.received}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{d.fabric}</td>
                      <td className="px-3 py-2 text-right font-mono">{rolls}</td>
                      <td className="px-3 py-2">
                        <div className="flex h-2 w-24 overflow-hidden rounded bg-slate-100">
                          <span className="bg-emerald-500" style={{ width: `${(d.pass / rolls) * 100}%` }} />
                          <span className="bg-amber-500" style={{ width: `${(d.review / rolls) * 100}%` }} />
                          <span className="bg-red-500" style={{ width: `${(d.fail / rolls) * 100}%` }} />
                        </div>
                        <span className="font-mono text-xs">
                          <span className="text-emerald-700">{d.pass}</span> / <span className="text-brand-amber">{d.review}</span> /{" "}
                          <span className="text-red-600">{d.fail}</span>
                        </span>
                      </td>
                      <td className={`px-3 py-2 text-right font-mono ${d.avgPts >= FAIL_LIMIT ? "font-semibold text-red-600" : ""}`}>
                        {d.avgPts.toFixed(1)}
                      </td>
                      <td className={`px-3 py-2 text-right font-mono ${d.shortageYd > 10 ? "text-brand-amber" : ""}`}>{d.shortageYd.toFixed(1)}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col items-start gap-1">
                          {statusPill(d.status)}
                          {d.claimUsd ? (
                            <Pill tone="navy">
                              {bi("Claim", "ক্লেইম")} ${d.claimUsd.toLocaleString("en-US")}
                            </Pill>
                          ) : drafted.has(d.challan) ? (
                            <Pill tone="teal">✓ {bi("Claim drafted", "ক্লেইম খসড়া হয়েছে")}</Pill>
                          ) : claimable ? (
                            <button
                              type="button"
                              className={`${ghostBtn} px-2 py-0.5 text-xs`}
                              disabled={!canClaim}
                              title={canClaim ? undefined : bi("Merchandiser or admin only", "শুধু মার্চেন্ডাইজার বা অ্যাডমিন")}
                              onClick={() => setDrafted((s) => new Set(s).add(d.challan))}
                            >
                              {bi("Raise claim", "ক্লেইম তুলুন")}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
