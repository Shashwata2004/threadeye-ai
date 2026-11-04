"use client";

import { useFormatter, useTranslations } from "next-intl";
import { PermissionNotice } from "@/components/PermissionNotice";
import { ClaimPackButton } from "@/components/ClaimPackButton";
import Link from "next/link";
import { useMemo, useState } from "react";
import { hasPerm, type MillScorecard } from "@/lib/api/client";
import { useMe, useScorecards } from "@/lib/api/hooks";
import {
  Card,
  CardTitle,
  KpiCard,
  PageHeader,
  Pill,
  ViewOnlyNote,
  inputCls,
  pct,
  screenRoot,
  useBi,
} from "@/components/screenKit";

// Supplier scorecards (M5): GET /suppliers/scorecard, from each roll's latest finalized inspection.
const FAIL_LIMIT = 40;

type Status = "accepted" | "review" | "rejected";
interface Delivery {
  lotId: string;
  challan: string;
  received: string;
  fabric: string;
  pass: number;
  review: number;
  fail: number;
  avgPts: number;
  shortageYd: number;
  status: Status;
  claims: number;
  claimEligible: boolean;
  lotDecision: string | null;
}
interface Mill {
  id: string;
  name: string;
  acceptance: number;
  avgPts: number;
  claims: number;
  shortage: number;
  trend: (number | null)[];
  mix: { cls: string; share: number }[];
  deliveries: Delivery[];
}
type Card = MillScorecard;

/** A mill with inspected rolls, as the page draws it (numbers the API leaves empty count as 0). */
function toMill(c: Card): Mill {
  return {
    id: c.id,
    name: c.name,
    acceptance: c.acceptance ?? 0,
    avgPts: c.avg_points_per_100 ?? 0,
    claims: c.claims,
    shortage: c.shortage ?? 0,
    trend: c.trend.map((m) => m.avg_points_per_100 ?? null),
    mix: c.mix,
    deliveries: c.deliveries.map((d) => ({
      lotId: d.lot_id,
      challan: d.challan,
      received: d.received,
      fabric: d.fabric,
      pass: d.passed,
      review: d.review,
      fail: d.failed,
      avgPts: d.avg_points_per_100 ?? 0,
      shortageYd: d.shortage_yd,
      status: d.status,
      claims: d.claims,
      claimEligible: d.claim_eligible,
      lotDecision: d.lot_decision ?? null,
    })),
  };
}
const NONE = "—";

const MIX_COLORS = ["bg-brand-navy", "bg-brand-teal", "bg-amber-500", "bg-red-500"];

export default function SuppliersPage() {
  const t = useTranslations();
  const bi = useBi();
  const { data: me } = useMe();
  const canView = hasPerm(me, "suppliers.scorecard");
  const canClaim = hasPerm(me, "claims.write");
  const format = useFormatter();
  const { data: cards, isPending: loading, isError } = useScorecards(canView);
  const MILLS = useMemo(() => (cards ?? []).filter((c) => c.rolls_inspected > 0).map(toMill), [cards]);
  // The last six months, as the API counts them (oldest first).
  const MONTHS = useMemo(
    () =>
      (cards?.[0]?.trend ?? []).map((m) => {
        const label = format.dateTime(new Date(`${m.month}-01T00:00:00`), { month: "short" });
        return { key: m.month, en: label, bn: label };
      }),
    [cards, format],
  );

  const [millId, setMillId] = useState<string>("all");
  const [query, setQuery] = useState("");

  const selected = MILLS.find((m) => m.id === millId);
  const view = useMemo(() => {
    if (selected) return selected;
    if (!MILLS.length) return null;
    // All mills: weighted by inspected rolls (a month counts the mills with rolls in it).
    const rolls = (m: Mill) => m.deliveries.reduce((s, d) => s + d.pass + d.review + d.fail, 0);
    const total = MILLS.reduce((s, m) => s + rolls(m), 0) || 1;
    const weighted = (f: (m: Mill) => number) => MILLS.reduce((s, m) => s + f(m) * rolls(m), 0) / total;
    const monthly = (i: number) => {
      const withData = MILLS.filter((m) => m.trend[i] !== null);
      const n = withData.reduce((s, m) => s + rolls(m), 0);
      return n ? withData.reduce((s, m) => s + (m.trend[i] ?? 0) * rolls(m), 0) / n : null;
    };
    return {
      acceptance: weighted((m) => m.acceptance),
      avgPts: weighted((m) => m.avgPts),
      claims: MILLS.reduce((s, m) => s + m.claims, 0),
      shortage: weighted((m) => m.shortage),
      trend: MONTHS.map((_, i) => monthly(i)),
      mix: null,
    };
  }, [selected, MILLS, MONTHS]);

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

  if (!me || !canView || loading || isError) return (
    <div className={`${screenRoot} space-y-5`}>
      <PageHeader title={t("nav.suppliers")} subtitle={t("placeholder.suppliers")} sample={false} />
      {!me ? <p className="text-slate-500">{t("common.loading")}</p> : !canView ?
        <PermissionNotice title={bi("This account cannot view mill scorecards.", "এই অ্যাকাউন্টে মিলের স্কোরকার্ড দেখার অনুমতি নেই।")}>
          <p>{bi("This does not mean there are no deliveries or inspections. QC supervisors, merchandisers, management and admins can view this information.",
            "এর অর্থ চালান বা পরিদর্শনের তথ্য নেই—এমন নয়। QC সুপারভাইজার, মার্চেন্ডাইজার, ম্যানেজমেন্ট ও অ্যাডমিন এই তথ্য দেখতে পারেন।")}</p>
        </PermissionNotice>
      : isError ? <p role="alert" className="text-red-700">{bi("Could not load mill scorecards. Please try again.", "মিলের স্কোরকার্ড লোড করা যায়নি। আবার চেষ্টা করুন।")}</p>
        : <p className="text-slate-500">{t("common.loading")}</p>}
    </div>
  );

  return (
    <div className={`${screenRoot} space-y-5`}>
      <PageHeader title={t("nav.suppliers")} subtitle={t("placeholder.suppliers")} sample={false} />

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
          value={view ? pct(view.acceptance) : NONE}
          sub={bi("Rolls accepted", "গৃহীত রোল")}
          tone={view && view.acceptance < 0.85 ? "amber" : "emerald"}
        />
        <KpiCard
          label={bi("Avg points / 100 sq yd", "গড় পয়েন্ট / ১০০ বর্গগজ")}
          value={<span className="font-mono">{view ? view.avgPts.toFixed(1) : NONE}</span>}
          sub={bi(`Fail limit ${FAIL_LIMIT} pts`, `ফেল সীমা ${FAIL_LIMIT} পয়েন্ট`)}
          tone={view && view.avgPts >= FAIL_LIMIT ? "red" : "navy"}
        />
        <KpiCard
          label={bi("Defect claims raised", "উত্থাপিত ক্লেইম")}
          value={view ? String(view.claims) : NONE}
          sub={bi("Rolls accepted with a claim or rejected", "ক্লেইমসহ গৃহীত বা বাতিল রোল")}
          tone="red"
        />
        <KpiCard
          label={bi("Avg yardage shortage", "গড় গজ ঘাটতি")}
          value={view ? pct(view.shortage) : NONE}
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
              {MONTHS.map((month, i) => {
                const v = view ? view.trend[i] : null;
                return (
                  <div key={month.key} className="flex h-full w-full max-w-12 flex-col items-center justify-end">
                    <span className="mb-1 font-mono text-xs text-slate-600">{v !== null ? v.toFixed(1) : NONE}</span>
                    {v !== null && (
                      <div
                        className={`w-full rounded-t transition-all duration-500 ${
                          v >= FAIL_LIMIT ? "bg-red-500" : v >= 28 ? "bg-amber-500" : "bg-emerald-500"
                        }`}
                        style={{ height: `${(Math.min(v, chartMax) / chartMax) * 100}%` }}
                        title={`${bi(month.en, month.bn)}: ${v.toFixed(1)}`}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          <div className="mt-1 flex justify-around pl-1 text-xs text-slate-500">
            {MONTHS.map((m) => (
              <span key={m.key} className="w-full max-w-12 text-center">
                {bi(m.en, m.bn)}
              </span>
            ))}
          </div>
        </Card>

        <Card>
          <CardTitle hint={bi("Where this mill's defect points come from.", "এই মিলের ত্রুটি কোথা থেকে আসে।")}>
            {bi("Defect mix", "ত্রুটির ধরন")}
          </CardTitle>
          {view?.mix ? (
            <>
              <div className="flex h-7 overflow-hidden rounded">
                {view.mix.map((x, i) => (
                  <div key={x.cls} className={MIX_COLORS[i % MIX_COLORS.length]} style={{ width: `${x.share}%` }} title={`${t(`cls.${x.cls}`)} ${x.share}%`} />
                ))}
              </div>
              <ul className="mt-4 flex flex-wrap gap-2">
                {view.mix.map((x, i) => (
                  <li key={x.cls} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-sm">
                    <span className={`h-2.5 w-2.5 rounded-full ${MIX_COLORS[i % MIX_COLORS.length]}`} />
                    <span className="font-mono font-semibold text-brand-navy">{x.share}%</span>
                    <span className="text-slate-700">{t(`cls.${x.cls}`)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : !MILLS.length ? (
            <p className="text-sm text-slate-500">
              {bi("No inspected deliveries yet: the mix appears once rolls from a mill are inspected.", "এখনো কোনো চালান পরিদর্শন হয়নি: কোনো মিলের রোল পরিদর্শন হলে এখানে দেখাবে।")}
            </p>
          ) : (
            <ul className="space-y-3">
              {MILLS.map((m) => (
                <li key={m.id}>
                  <button type="button" onClick={() => setMillId(m.id)} className="w-full text-left">
                    <span className="mb-1 block text-sm font-medium text-brand-navy hover:underline">{m.name}</span>
                    <span className="flex h-3 overflow-hidden rounded">
                      {m.mix.map((x, i) => (
                        <span key={x.cls} className={MIX_COLORS[i % MIX_COLORS.length]} style={{ width: `${x.share}%` }} />
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
          <p className="text-sm text-slate-500">
            {MILLS.length
              ? bi("No deliveries match your search.", "আপনার খোঁজের সাথে কোনো চালান মেলেনি।")
              : bi("No deliveries yet.", "এখনো কোনো চালান নেই।")}
          </p>
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
                  return (
                    <tr key={d.challan} className="border-t border-slate-100 align-middle">
                      <td className="px-3 py-2 whitespace-nowrap">
                        <Link href={`/lots/${d.lotId}#lot-decision`} className="font-mono text-xs text-brand-teal underline">{d.challan}</Link>
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
                          {d.claims > 0 && (
                            <Pill tone="navy">
                              {bi(`${d.claims} roll(s) to claim`, `${d.claims}টি রোলে ক্লেইম`)}
                            </Pill>
                          )}
                          <ClaimPackButton lotId={d.lotId} disabled={!canClaim || !d.claimEligible}/>
                          {!d.claimEligible && <p className="max-w-xs text-xs text-slate-500">{
                            !d.lotDecision || d.lotDecision === "INSPECT_ALL" ? bi("Claim blocked: finalize the delivery decision first.", "ক্লেইম বন্ধ: আগে পুরো চালানের সিদ্ধান্ত দিন।") :
                            d.lotDecision === "ACCEPT" ? bi("Accepted without a claim; claim pack unavailable.", "নিঃশর্তে গৃহীত; ক্লেইম প্যাক প্রযোজ্য নয়।") :
                            bi("No roll has a QC claim/return decision.", "কোনো রোলে QC-এর দাবি/ফেরতের সিদ্ধান্ত নেই।")}</p>}
                          <Link href={`/lots/${d.lotId}#lot-decision`} className="text-xs text-brand-teal underline">{
                            hasPerm(me, "verdict.decide") ? bi("Record delivery decision", "চালানের সিদ্ধান্ত দিন") : bi("View delivery decision", "চালানের সিদ্ধান্ত দেখুন")}</Link>
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
