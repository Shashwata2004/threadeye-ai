"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
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

// Sample evaluation shown until the M6 benchmark endpoint exists. Runs happen in the browser only.
const DATASETS = [
  { id: "aitex", en: "AITEX Fabric Dataset (10 rolls)", bn: "AITEX ফেব্রিক ডেটাসেট (১০ রোল)" },
  { id: "twill", en: "Synthetic Twill Set (20 rolls)", bn: "সিন্থেটিক টুইল সেট (২০ রোল)" },
] as const;

const PROVIDERS = [
  { id: "sim", en: "Simulated rad-02", bn: "সিমুলেটেড rad-02", ready: true },
  { id: "onnx", en: "ThreadEye Local ONNX (not configured)", bn: "ThreadEye লোকাল ONNX (কনফিগার হয়নি)", ready: false },
  { id: "ext", en: "External API (not configured)", bn: "এক্সটার্নাল API (কনফিগার হয়নি)", ready: false },
] as const;

const BASE = {
  precision: 0.914,
  recall: 0.882,
  faPerYard: 0.12,
  iou: 0.76,
  funnel: [142, 38, 19, 15],
  classes: [
    { en: "Hole", bn: "ছিদ্র", support: 24, p: 0.958, r: 0.917, confEn: "Pin hole (nuisance)", confBn: "পিন ছিদ্র (অপ্রাসঙ্গিক)" },
    { en: "Oil Stain", bn: "তেলের দাগ", support: 31, p: 0.903, r: 0.871, confEn: "Stain", confBn: "দাগ" },
    { en: "Slub / Thick Yarn", bn: "স্লাব / মোটা সুতা", support: 46, p: 0.889, r: 0.87, confEn: "Knot", confBn: "গিঁট" },
    { en: "Crease Mark", bn: "ভাঁজের দাগ", support: 18, p: 0.857, r: 0.833, confEn: "Handling wrinkle", confBn: "হাতের ভাঁজ" },
    { en: "Broken Yarn", bn: "ছেঁড়া সুতা", support: 27, p: 0.92, r: 0.852, confEn: "Missing yarn", confBn: "অনুপস্থিত সুতা" },
  ],
  nuisance: [
    { en: "Loose thread", bn: "আলগা সুতা", n: 9, color: "bg-brand-navy" },
    { en: "Fabric sticker", bn: "ফেব্রিক স্টিকার", n: 6, color: "bg-brand-teal" },
    { en: "Handling wrinkle", bn: "হাতের ভাঁজ", n: 5, color: "bg-amber-500" },
    { en: "Selvage pinhole", bn: "সেলভেজ পিন ছিদ্র", n: 3, color: "bg-red-500" },
    { en: "Board reflection", bn: "বোর্ডের প্রতিফলন", n: 2, color: "bg-slate-400" },
  ],
};

/** Deterministic jitter so a different dataset/split/seed gives a different, repeatable run. */
function jitter(key: string) {
  let h = 2166136261;
  for (const c of key) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return (n: number) => {
    h = Math.imul(h ^ (h >>> 15), 2246822507) ^ n;
    return ((h >>> 0) % 1000) / 1000 - 0.5; // -0.5 … 0.5
  };
}

function evaluate(dataset: string, split: string, seed: number) {
  if (dataset === "aitex" && split === "test" && seed === 42) return BASE;
  const j = jitter(`${dataset}|${split}|${seed}`);
  const clamp = (x: number) => Math.min(0.995, Math.max(0.5, x));
  const scale = dataset === "twill" ? 2 : 1;
  const funnel = BASE.funnel.map((v, i) => Math.round(v * scale * (1 + j(i) * 0.25)));
  for (let i = 1; i < funnel.length; i++) funnel[i] = Math.min(funnel[i], funnel[i - 1]);
  return {
    precision: clamp(BASE.precision + j(10) * 0.06),
    recall: clamp(BASE.recall + j(11) * 0.06),
    faPerYard: Math.max(0.02, BASE.faPerYard + j(12) * 0.08),
    iou: clamp(BASE.iou + j(13) * 0.08),
    funnel,
    classes: BASE.classes.map((c, i) => ({
      ...c,
      support: Math.round(c.support * scale * (1 + j(20 + i) * 0.3)),
      p: clamp(c.p + j(30 + i) * 0.08),
      r: clamp(c.r + j(40 + i) * 0.08),
    })),
    nuisance: BASE.nuisance.map((x, i) => ({ ...x, n: Math.max(1, Math.round(x.n * scale * (1 + j(50 + i) * 0.5))) })),
  };
}

export default function BenchmarkPage() {
  const t = useTranslations();
  const bi = useBi();

  const [dataset, setDataset] = useState<string>("aitex");
  const [split, setSplit] = useState<"test" | "val">("test");
  const [provider, setProvider] = useState<string>("sim");
  const [seed, setSeed] = useState(42);
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState({ dataset: "aitex", split: "test", seed: 42, at: new Date() });

  const result = useMemo(() => evaluate(run.dataset, run.split, run.seed), [run]);
  const f1 = (2 * result.precision * result.recall) / (result.precision + result.recall);
  const funnelMax = result.funnel[0] || 1;
  const nuisanceTotal = result.nuisance.reduce((s, x) => s + x.n, 0);
  const datasetLabel = DATASETS.find((d) => d.id === run.dataset);

  function runEvaluation() {
    setRunning(true);
    window.setTimeout(() => {
      setRun({ dataset, split, seed, at: new Date() });
      setRunning(false);
    }, 1200);
  }

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
          "SIMULATION BENCHMARK: Measures pipeline quality with simulated detectors — not real-world AI accuracy.",
          "সিমুলেশন বেঞ্চমার্ক: সিমুলেটেড ডিটেক্টর দিয়ে পাইপলাইনের মান মাপা হয় — এটি বাস্তব AI-এর নির্ভুলতা নয়।",
        )}
      </p>

      <PageHeader title={t("nav.benchmark")} subtitle={t("placeholder.benchmark")} />

      <Card>
        <CardTitle hint={bi("Choose what to score against the answer key.", "কোন ডেটা উত্তর-চাবির সাথে মেলানো হবে তা বাছুন।")}>
          {bi("Benchmark run", "বেঞ্চমার্ক রান")}
        </CardTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_2fr_1fr_auto] lg:items-end">
          <Field label={bi("Dataset", "ডেটাসেট")}>
            <select className={inputCls} value={dataset} onChange={(e) => setDataset(e.target.value)}>
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
          <button type="button" className={primaryBtn} onClick={runEvaluation} disabled={running}>
            {running && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
            {running ? bi("Running…", "চলছে…") : bi("Run evaluation", "মূল্যায়ন চালান")}
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {bi("Showing", "দেখানো হচ্ছে")}: {datasetLabel ? bi(datasetLabel.en, datasetLabel.bn) : ""} ·{" "}
          <span className="font-mono">{run.split}</span> · {bi("seed", "সিড")} <span className="font-mono">{run.seed}</span> ·{" "}
          {run.at.toLocaleTimeString()}
        </p>
      </Card>

      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-5 ${running ? "opacity-50" : ""}`}>
        <KpiCard label={bi("Precision", "প্রিসিশন")} value={pct(result.precision)} sub={bi("Flags that were real", "সত্যি ত্রুটি ছিল")} tone="teal" />
        <KpiCard label={bi("Recall", "রিকল")} value={pct(result.recall)} sub={bi("Real defects found", "পাওয়া আসল ত্রুটি")} tone="teal" />
        <KpiCard label={bi("F1-score", "F1-স্কোর")} value={pct(f1)} sub={bi("Balance of both", "দুটির ভারসাম্য")} />
        <KpiCard
          label={bi("False-alarm rate", "ভুল সতর্কতার হার")}
          value={<span className="font-mono">{result.faPerYard.toFixed(2)}</span>}
          sub={bi("False positives / yard", "প্রতি গজে ভুল সতর্কতা")}
          tone={result.faPerYard > 0.2 ? "red" : "amber"}
        />
        <KpiCard label={bi("Mean box IoU", "গড় বক্স IoU")} value={<span className="font-mono">{result.iou.toFixed(2)}</span>} sub={bi("Box overlap with truth", "আসল বক্সের সাথে মিল")} />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardTitle hint={bi("How raw detector output narrows to confirmed defects.", "কাঁচা শনাক্তকরণ থেকে নিশ্চিত ত্রুটি পর্যন্ত।")}>
            {bi("False-alarm funnel", "ভুল সতর্কতার ফানেল")}
          </CardTitle>
          <ol className="space-y-2">
            {result.funnel.map((n, i) => {
              const dropped = i > 0 ? result.funnel[i - 1] - n : 0;
              return (
                <li key={i}>
                  <div className="mb-0.5 flex items-baseline justify-between text-sm">
                    <span className="text-slate-700">
                      {i + 1}. {funnelSteps[i]}
                    </span>
                    <span className="font-mono font-semibold text-brand-navy">
                      {n}
                      {i > 0 && <span className="ml-2 text-xs font-normal text-red-600">−{dropped}</span>}
                    </span>
                  </div>
                  <div className="h-6 rounded bg-slate-100">
                    <div
                      className={`mx-auto h-6 rounded transition-all duration-500 ${funnelColors[i]}`}
                      style={{ width: `${Math.max(4, (n / funnelMax) * 100)}%` }}
                    />
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
          <div className="flex h-7 overflow-hidden rounded" role="img" aria-label={bi("Nuisance share", "অপ্রাসঙ্গিক সতর্কতার অংশ")}>
            {result.nuisance.map((x) => (
              <div
                key={x.en}
                className={`${x.color} transition-all duration-500`}
                style={{ width: `${(x.n / nuisanceTotal) * 100}%` }}
                title={`${bi(x.en, x.bn)}: ${x.n}`}
              />
            ))}
          </div>
          <ul className="mt-4 space-y-2">
            {result.nuisance.map((x) => (
              <li key={x.en} className="flex items-center gap-2 text-sm">
                <span className={`h-3 w-3 shrink-0 rounded-sm ${x.color}`} />
                <span className="flex-1 text-slate-700">{bi(x.en, x.bn)}</span>
                <span className="font-mono font-semibold text-brand-navy">{x.n}</span>
                <span className="w-12 text-right text-xs text-slate-500">{pct(x.n / nuisanceTotal, 0)}</span>
              </li>
            ))}
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
              {result.classes.map((c) => (
                <tr key={c.en} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-medium text-slate-800">{bi(c.en, c.bn)}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.support}</td>
                  <td className={`px-3 py-2 text-right font-mono ${c.p < 0.85 ? "text-brand-amber" : "text-emerald-700"}`}>{pct(c.p)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${c.r < 0.85 ? "text-brand-amber" : "text-emerald-700"}`}>{pct(c.r)}</td>
                  <td className="px-3 py-2 text-slate-600">{bi(c.confEn, c.confBn)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
