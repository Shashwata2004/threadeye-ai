"use client";

import { useTranslations } from "next-intl";
import { Card, CardTitle, KpiCard, PageHeader, pct, screenRoot, useBi } from "@/components/screenKit";
import { useModelEvaluation } from "@/lib/api/hooks";
import { EvaluationWorkbench } from "@/components/EvaluationWorkbench";

// The trained detector scored on the held-out test split (ml/kaggle/train.py → test_report.json; the
// matching rule and the per-class thresholds are in ml/fabricdata/operating.py). Every figure is measured:
// with no evaluated model the screen shows "—".

/** Where the test tiles come from (ml/DATASETS.md). */
const SOURCES: Record<string, { en: string; bn: string }> = {
  aitex: { en: "AITEX (Spain, loom camera)", bn: "AITEX (স্পেন, তাঁতের ক্যামেরা)" },
  tianchi: { en: "Tianchi (China, cloth flaws)", bn: "Tianchi (চীন, কাপড়ের ত্রুটি)" },
  zju_leaper: { en: "ZJU-Leaper (patterned fabric)", bn: "ZJU-Leaper (নকশাদার কাপড়)" },
  raw_fabrid: { en: "RAW-FABRID (line-scan)", bn: "RAW-FABRID (লাইন-স্ক্যান)" },
  wfdd: { en: "WFDD (woven fabric)", bn: "WFDD (বোনা কাপড়)" },
  fabricspotdefect: { en: "FabricSpotDefect (stains, Bangladesh)", bn: "FabricSpotDefect (দাগ, বাংলাদেশ)" },
  fabric_stain: { en: "Fabric Stain (Sri Lanka)", bn: "Fabric Stain (শ্রীলঙ্কা)" },
  moratuwa: { en: "Moratuwa (holes, lines)", bn: "Moratuwa (ফুটো, রেখা)" },
  fd_figshare: { en: "FD Dataset (coloured fabric)", bn: "FD Dataset (রঙিন কাপড়)" },
  garment_defects: { en: "Garment fabric", bn: "গার্মেন্টের কাপড়" },
  synth_nuisance: { en: "Stickers, threads, wrinkles, hands", bn: "স্টিকার, সুতা, ভাঁজ, হাত" },
};

const NONE = "—";
const share = (x: number | null | undefined, digits = 1) => (x === null || x === undefined ? NONE : pct(x, digits));
const toneFor = (x: number | null | undefined) => (x === null || x === undefined ? "" : x < 0.7 ? "text-brand-amber" : "text-emerald-700");

export default function BenchmarkPage() {
  const t = useTranslations();
  const bi = useBi();
  const { data: ev, isLoading, isError } = useModelEvaluation();

  const defects = ev?.per_class.filter((c) => !c.nondefect) ?? [];
  const nondefects = ev?.per_class.filter((c) => c.nondefect) ?? [];
  const sources = [...(ev?.per_source ?? [])].sort((a, b) => b.tiles - a.tiles);

  return (
    <div className={`${screenRoot} space-y-5`}>
      <EvaluationWorkbench kind="benchmark" />
      {!ev && (
        <p role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm font-semibold text-brand-amber">
          {isLoading
            ? bi("Loading the model's evaluation…", "মডেলের মূল্যায়ন আসছে…")
            : isError
              ? bi("The evaluation could not be loaded.", "মূল্যায়ন আনা যায়নি।")
              : bi(
                  "No evaluation yet: results appear here once the detector has been trained and scored on the held-out test split.",
                  "এখনো কোনো মূল্যায়ন হয়নি: ডিটেক্টর ট্রেন করে আলাদা রাখা test ভাগে মাপার পর ফলাফল এখানে দেখাবে।",
                )}
        </p>
      )}

      <PageHeader title={t("nav.benchmark")} subtitle={t("placeholder.benchmark")} sample={false} />

      <Card>
        <CardTitle
          hint={bi(
            "Measured on test tiles the model never saw in training; per-class thresholds were chosen on the separate val split.",
            "ট্রেনিংয়ে কখনো না দেখা test টুকরোয় মাপা; প্রতিটি শ্রেণির সীমা আলাদা val ভাগ থেকে বাছা।",
          )}
        >
          {bi("Model under test", "পরীক্ষিত মডেল")}
        </CardTitle>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-slate-500">{bi("Detector", "ডিটেক্টর")}</dt>
            <dd className="font-semibold text-slate-800">{ev ? ev.model : NONE}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">{bi("Training", "ট্রেনিং")}</dt>
            <dd className="font-mono text-slate-800">
              {ev ? `${ev.epochs} ${bi("epochs", "epoch")}${ev.train_minutes ? ` · ${(ev.train_minutes / 60).toFixed(1)} h` : ""}` : NONE}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">{bi("Test split", "test ভাগ")}</dt>
            <dd className="font-mono text-slate-800">
              {ev ? `${ev.tiles.toLocaleString()} ${bi("tiles", "টুকরো")} · ${ev.defects.toLocaleString()} ${bi("defects", "ত্রুটি")}` : NONE}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">{bi("Classes", "শ্রেণি")}</dt>
            <dd className="font-mono text-slate-800">{ev ? `${defects.length} + ${nondefects.length} ${bi("non-defect", "অ-ত্রুটি")}` : NONE}</dd>
          </div>
        </dl>
        {ev && (
          <p className="mt-3 text-xs text-slate-500" title={ev.matching}>
            {bi(
              "A defect counts as found when a box of the same class overlaps it (IoU ≥ 0.3) or has its centre inside it; repeat boxes on a found defect are not counted.",
              "একই শ্রেণির বাক্স ত্রুটির সাথে মিললে (IoU ≥ ০.৩) বা বাক্সের কেন্দ্র ত্রুটির ভেতরে পড়লে ত্রুটিটা ধরা পড়েছে ধরা হয়; একই ত্রুটিতে বাড়তি বাক্স গোনা হয় না।",
            )}
          </p>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard label={bi("Defects found", "ত্রুটি ধরা পড়েছে")} value={share(ev?.found_any_class)} sub={bi("Real defects flagged", "আসল ত্রুটির কত ভাগ")} tone="teal" />
        <KpiCard label={bi("Right class", "সঠিক শ্রেণি")} value={share(ev?.found_right_class)} sub={bi("Found and named correctly", "ধরা ও ঠিক নাম")} tone="teal" />
        <KpiCard
          label={bi("Precision", "প্রিসিশন")}
          value={share(ev?.precision)}
          sub={bi("Flags that were real", "সতর্কবার্তার কত ভাগ সত্যি")}
        />
        <KpiCard
          label={bi("False alarms", "ভুল সতর্কবার্তা")}
          value={<span className="font-mono">{ev ? ev.false_alarms_per_100_tiles.toFixed(1) : NONE}</span>}
          sub={bi("Per 100 tiles", "প্রতি ১০০ টুকরোয়")}
          tone="amber"
        />
        <KpiCard
          label={bi("Non-defects flagged", "অ-ত্রুটিকে ত্রুটি বলা")}
          value={share(ev?.nondefects_called_defect)}
          sub={bi("Stickers, threads, hands…", "স্টিকার, সুতা, হাত…")}
          tone={ev && (ev.nondefects_called_defect ?? 0) > 0.2 ? "red" : "amber"}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardTitle hint={bi("How the model does on each kind of fabric and camera.", "প্রতিটি ধরনের কাপড় ও ক্যামেরায় মডেল কেমন করে।")}>
            {bi("By source", "উৎস অনুযায়ী")}
          </CardTitle>
          <ul className="space-y-2.5">
            {!sources.length && <li className="text-sm text-slate-500">{NONE}</li>}
            {sources.map((s) => {
              const found = s.found_any_class;
              return (
                <li key={s.source}>
                  <div className="mb-0.5 flex items-baseline justify-between gap-2 text-sm">
                    <span className="truncate text-slate-700">{SOURCES[s.source] ? bi(SOURCES[s.source].en, SOURCES[s.source].bn) : s.source}</span>
                    <span className="shrink-0 font-mono text-xs text-slate-600">
                      <span className={`font-semibold ${toneFor(found)}`}>{share(found, 0)}</span>
                      {" · "}
                      {s.false_alarms_per_100_tiles.toFixed(1)} {bi("FA/100", "ভুল/১০০")}
                    </span>
                  </div>
                  <div className="h-2.5 rounded bg-slate-100">
                    {found !== null && found !== undefined && (
                      <div className="h-2.5 rounded bg-brand-teal transition-all duration-500" style={{ width: `${Math.max(2, found * 100)}%` }} />
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            {bi("Bar: share of real defects found. FA/100: false alarms per 100 tiles.", "দাগ: আসল ত্রুটির কত ভাগ ধরা পড়েছে। ভুল/১০০: প্রতি ১০০ টুকরোয় ভুল সতর্কবার্তা।")}
          </p>
        </Card>

        <Card>
          <CardTitle hint={bi("Things that are not defects: the app shows them grey and never scores them.", "যা ত্রুটি নয়: অ্যাপ এগুলো ধূসর দেখায়, কখনো নম্বর কাটে না।")}>
            {bi("Non-defects recognised", "অ-ত্রুটি চেনা")}
          </CardTitle>
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-1">{bi("Kind", "ধরন")}</th>
                <th className="py-1 text-right">{bi("In test", "test-এ")}</th>
                <th className="py-1 text-right">{bi("Recognised", "চিনেছে")}</th>
                <th className="py-1 text-right">{bi("Precision", "প্রিসিশন")}</th>
              </tr>
            </thead>
            <tbody>
              {(nondefects.length ? nondefects : (["sticker", "loose_thread", "wrinkle", "hand"] as const).map((cls) => ({ cls, truth: null, recall: null, precision: null }))).map((c) => (
                <tr key={c.cls} className="border-t border-slate-100">
                  <td className="py-1.5 text-slate-700">{t(`cls.${c.cls}`)}</td>
                  <td className="py-1.5 text-right font-mono">{c.truth ?? NONE}</td>
                  <td className={`py-1.5 text-right font-mono ${toneFor(c.recall)}`}>{share(c.recall)}</td>
                  <td className="py-1.5 text-right font-mono">{share(c.precision)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card>
        <CardTitle hint={ev ? bi("Each class's threshold was chosen on the val split (best F1).", "প্রতিটি শ্রেণির সীমা val ভাগ থেকে বাছা (সেরা F1)।") : undefined}>{bi("Per-class breakdown", "শ্রেণি অনুযায়ী বিশ্লেষণ")}</CardTitle>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-left text-slate-700">
              <tr>
                <th className="px-3 py-2">{bi("Defect class", "ত্রুটির শ্রেণি")}</th>
                <th className="px-3 py-2 text-right">{bi("In test", "test-এ")}</th>
                <th className="px-3 py-2 text-right">{bi("Threshold", "সীমা")}</th>
                <th className="px-3 py-2 text-right">{bi("Precision", "প্রিসিশন")}</th>
                <th className="px-3 py-2 text-right">{bi("Recall", "রিকল")}</th>
              </tr>
            </thead>
            <tbody>
              {!defects.length && (
                <tr>
                  <td colSpan={5} className="px-3 py-3 text-center text-slate-500">
                    {NONE}
                  </td>
                </tr>
              )}
              {[...defects].sort((a, b) => b.truth - a.truth).map((c) => (
                <tr key={c.cls} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-medium text-slate-800">{t(`cls.${c.cls}`)}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.truth.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right font-mono">{c.threshold.toFixed(2)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${toneFor(c.precision)}`}>{share(c.precision)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${toneFor(c.recall)}`}>{share(c.recall)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {bi(
            "Selvage defects are placed by position (a yarn fault in the selvage band), and oil stains are learned as stains: neither has a row of its own.",
            "কিনারার ত্রুটি অবস্থান দিয়ে ঠিক হয় (কিনারার ব্যান্ডে সুতার ত্রুটি), আর তেলের দাগ শেখানো হয়েছে দাগ হিসেবে: এদের আলাদা সারি নেই।",
          )}
        </p>
      </Card>
    </div>
  );
}
