"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import {
  Card,
  CardTitle,
  Field,
  KpiCard,
  PageHeader,
  inputCls,
  pct,
  primaryBtn,
  screenRoot,
  useBi,
} from "@/components/screenKit";

// An evaluation run: the detector scored on a held-out split (the ThreadEye test split, see
// ml/DATASETS.md). Nothing is measured yet: results come from the trained model's test evaluation.
export type EvaluationResult = {
  dataset: string;
  split: "test" | "val";
  provider: string;
  at: string;
  precision: number;
  recall: number;
  faPerYard: number;
  iou: number;
  /** Raw detections → after de-duplication → after the non-defect filter → confirmed by the inspector. */
  funnel: [number, number, number, number];
  classes: { id: string; support: number; p: number; r: number; confusion: string | null }[];
  nuisance: { id: string; n: number }[];
};

const DATASETS: { id: string; en: string; bn: string }[] = [];

const PROVIDERS = [
  { id: "sim", en: "Simulated detector", bn: "সিমুলেটেড ডিটেক্টর", ready: true },
  { id: "onnx", en: "ThreadEye Local ONNX (not configured)", bn: "ThreadEye লোকাল ONNX (কনফিগার হয়নি)", ready: false },
  { id: "ext", en: "External API (not configured)", bn: "এক্সটার্নাল API (কনফিগার হয়নি)", ready: false },
] as const;

/** The detector's classes (backend/threadeye/data/taxonomy.yaml) and the non-defect categories. */
const DEFECT_CLASSES = [
  "hole", "stain", "oil_stain", "slub", "broken_yarn", "missing_yarn",
  "knot", "crease_mark", "contamination", "shade_bar", "selvage_defect", "other_defect",
] as const;
const NUISANCE = [
  { id: "loose_thread", color: "bg-brand-navy" },
  { id: "sticker", color: "bg-brand-teal" },
  { id: "wrinkle", color: "bg-amber-500" },
  { id: "pin_hole", color: "bg-red-500" },
  { id: "hand", color: "bg-violet-500" },
  { id: "board", color: "bg-slate-400" },
] as const;

const NONE = "—";

export default function BenchmarkPage() {
  const t = useTranslations();
  const bi = useBi();

  const [dataset, setDataset] = useState<string>(DATASETS[0]?.id ?? "");
  const [split, setSplit] = useState<"test" | "val">("test");
  const [provider, setProvider] = useState<string>("sim");
  const [seed, setSeed] = useState(0);

  // No run yet: every figure shows "—" until an evaluation result is loaded here.
  const result = null as EvaluationResult | null;
  const f1 = result && result.precision + result.recall > 0
    ? (2 * result.precision * result.recall) / (result.precision + result.recall)
    : null;
  const funnel = result?.funnel ?? null;
  const funnelMax = funnel?.[0] || 1;
  const nuisanceCount = (id: string) => result?.nuisance.find((x) => x.id === id)?.n ?? null;
  const nuisanceTotal = result?.nuisance.reduce((s, x) => s + x.n, 0) ?? 0;
  const classRow = (id: string) => result?.classes.find((c) => c.id === id) ?? null;

  const funnelSteps = [
    bi("Raw detections", "কাঁচা শনাক্তকরণ"),
    bi("After deduplication", "ডুপ্লিকেট বাদের পর"),
    bi("After non-defect filtering", "অ-ত্রুটি ফিল্টারের পর"),
    bi("Confirmed by inspector", "ইন্সপেক্টর নিশ্চিত করেছেন"),
  ];
  const funnelColors = ["bg-slate-400", "bg-brand-navy", "bg-brand-teal", "bg-emerald-500"];

  return (
    <div className={`${screenRoot} space-y-5`}>
      <p role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm font-semibold text-brand-amber">
        {bi(
          "No evaluation yet: results appear here once the detector has been trained and scored on the held-out test split.",
          "এখনো কোনো মূল্যায়ন হয়নি: ডিটেক্টর ট্রেন করে আলাদা রাখা test ভাগে মাপার পর ফলাফল এখানে দেখাবে।",
        )}
      </p>

      <PageHeader title={t("nav.benchmark")} subtitle={t("placeholder.benchmark")} sample={false} />

      <Card>
        <CardTitle hint={bi("Choose what to score against the answer key.", "কোন ডেটা উত্তর-চাবির সাথে মেলানো হবে তা বাছুন।")}>
          {bi("Benchmark run", "বেঞ্চমার্ক রান")}
        </CardTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_2fr_1fr_auto] lg:items-end">
          <Field label={bi("Dataset", "ডেটাসেট")}>
            <select className={inputCls} value={dataset} onChange={(e) => setDataset(e.target.value)} disabled={!DATASETS.length}>
              {!DATASETS.length && <option value="">{bi("No evaluated dataset yet", "এখনো কোনো মূল্যায়িত ডেটাসেট নেই")}</option>}
              {DATASETS.map((d) => (
                <option key={d.id} value={d.id}>
                  {bi(d.en, d.bn)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={bi("Split", "বিভাজন")}>
            <select className={inputCls} value={split} onChange={(e) => setSplit(e.target.value as "test" | "val")}>
              <option value="test">test</option>
              <option value="val">val</option>
            </select>
          </Field>
          <Field label={bi("Provider", "প্রোভাইডার")}>
            <select className={inputCls} value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.ready}>
                  {bi(p.en, p.bn)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={bi("Seed", "সিড")}>
            <input
              type="number"
              className={`${inputCls} font-mono`}
              value={seed}
              min={0}
              onChange={(e) => setSeed(Math.max(0, Math.floor(Number(e.target.value) || 0)))}
            />
          </Field>
          <button
            type="button"
            className={primaryBtn}
            disabled
            title={bi("Runs arrive with the trained model's test evaluation.", "ট্রেন করা মডেলের test মূল্যায়নের সাথে রান আসবে।")}
          >
            {bi("Run evaluation", "মূল্যায়ন চালান")}
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {result
            ? `${bi("Showing", "দেখানো হচ্ছে")}: ${result.dataset} · ${result.split} · ${result.provider} · ${result.at}`
            : bi("No run to show yet.", "দেখানোর মতো কোনো রান এখনো নেই।")}
        </p>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard label={bi("Precision", "প্রিসিশন")} value={result ? pct(result.precision) : NONE} sub={bi("Flags that were real", "সত্যি ত্রুটি ছিল")} tone="teal" />
        <KpiCard label={bi("Recall", "রিকল")} value={result ? pct(result.recall) : NONE} sub={bi("Real defects found", "পাওয়া আসল ত্রুটি")} tone="teal" />
        <KpiCard label={bi("F1-score", "F1-স্কোর")} value={f1 !== null ? pct(f1) : NONE} sub={bi("Balance of both", "দুটির ভারসাম্য")} />
        <KpiCard
          label={bi("False-alarm rate", "ভুল সতর্কতার হার")}
          value={<span className="font-mono">{result ? result.faPerYard.toFixed(2) : NONE}</span>}
          sub={bi("False positives / yard", "প্রতি গজে ভুল সতর্কতা")}
          tone={result && result.faPerYard > 0.2 ? "red" : "amber"}
        />
        <KpiCard
          label={bi("Mean box IoU", "গড় বক্স IoU")}
          value={<span className="font-mono">{result ? result.iou.toFixed(2) : NONE}</span>}
          sub={bi("Box overlap with truth", "আসল বক্সের সাথে মিল")}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardTitle hint={bi("How raw detector output narrows to confirmed defects.", "কাঁচা শনাক্তকরণ থেকে নিশ্চিত ত্রুটি পর্যন্ত।")}>
            {bi("False-alarm funnel", "ভুল সতর্কতার ফানেল")}
          </CardTitle>
          <ol className="space-y-2">
            {funnelSteps.map((step, i) => {
              const n = funnel?.[i] ?? null;
              const dropped = funnel && i > 0 ? funnel[i - 1] - funnel[i] : 0;
              return (
                <li key={i}>
                  <div className="mb-0.5 flex items-baseline justify-between text-sm">
                    <span className="text-slate-700">
                      {i + 1}. {step}
                    </span>
                    <span className="font-mono font-semibold text-brand-navy">
                      {n ?? NONE}
                      {n !== null && i > 0 && <span className="ml-2 text-xs font-normal text-red-600">−{dropped}</span>}
                    </span>
                  </div>
                  <div className="h-6 rounded bg-slate-100">
                    {n !== null && (
                      <div
                        className={`mx-auto h-6 rounded transition-all duration-500 ${funnelColors[i]}`}
                        style={{ width: `${Math.max(4, (n / funnelMax) * 100)}%` }}
                      />
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>

        <Card>
          <CardTitle hint={bi("False positives by non-defect category.", "অ-ত্রুটি ধরন অনুযায়ী ভুল সতর্কতা।")}>
            {bi("Nuisance breakdown", "অপ্রাসঙ্গিক সতর্কতার ভাগ")}
          </CardTitle>
          <div className="flex h-7 overflow-hidden rounded bg-slate-100" role="img" aria-label={bi("Nuisance share", "অপ্রাসঙ্গিক সতর্কতার অংশ")}>
            {nuisanceTotal > 0 &&
              NUISANCE.map((x) => {
                const n = nuisanceCount(x.id) ?? 0;
                return (
                  <div
                    key={x.id}
                    className={`${x.color} transition-all duration-500`}
                    style={{ width: `${(n / nuisanceTotal) * 100}%` }}
                    title={`${t(`cls.${x.id}`)}: ${n}`}
                  />
                );
              })}
          </div>
          <ul className="mt-4 space-y-2">
            {NUISANCE.map((x) => {
              const n = nuisanceCount(x.id);
              return (
                <li key={x.id} className="flex items-center gap-2 text-sm">
                  <span className={`h-3 w-3 shrink-0 rounded-sm ${x.color}`} />
                  <span className="flex-1 text-slate-700">{t(`cls.${x.id}`)}</span>
                  <span className="font-mono font-semibold text-brand-navy">{n ?? NONE}</span>
                  <span className="w-12 text-right text-xs text-slate-500">
                    {n !== null && nuisanceTotal > 0 ? pct(n / nuisanceTotal, 0) : NONE}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      <Card>
        <CardTitle>{bi("Per-class breakdown", "শ্রেণি অনুযায়ী বিশ্লেষণ")}</CardTitle>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-left text-slate-700">
              <tr>
                <th className="px-3 py-2">{bi("Defect class", "ত্রুটির শ্রেণি")}</th>
                <th className="px-3 py-2 text-right">{bi("Support", "নমুনা")}</th>
                <th className="px-3 py-2 text-right">{bi("Precision", "প্রিসিশন")}</th>
                <th className="px-3 py-2 text-right">{bi("Recall", "রিকল")}</th>
                <th className="px-3 py-2">{bi("Common confusion", "সাধারণ বিভ্রান্তি")}</th>
              </tr>
            </thead>
            <tbody>
              {DEFECT_CLASSES.map((id) => {
                const c = classRow(id);
                return (
                  <tr key={id} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-medium text-slate-800">{t(`cls.${id}`)}</td>
                    <td className="px-3 py-2 text-right font-mono">{c ? c.support : NONE}</td>
                    <td className={`px-3 py-2 text-right font-mono ${c ? (c.p < 0.85 ? "text-brand-amber" : "text-emerald-700") : ""}`}>
                      {c ? pct(c.p) : NONE}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${c ? (c.r < 0.85 ? "text-brand-amber" : "text-emerald-700") : ""}`}>
                      {c ? pct(c.r) : NONE}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{c?.confusion ? t(`cls.${c.confusion}`) : NONE}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
