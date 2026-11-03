"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useDatasets, useMachines, useMe, useProviders } from "@/lib/api/hooks";
import { hasPerm } from "@/lib/api/client";
import { request, useRuns, type Run } from "@/lib/api/operations";
import { Card, CardTitle, Field, inputCls, primaryBtn, useBi, Pill } from "./screenKit";

export function EvaluationWorkbench({kind}: {kind: "verification" | "benchmark"}) {
  const bi = useBi();
  const client = useQueryClient();
  const {data: me} = useMe();
  const {data: datasets} = useDatasets();
  const {data: machines} = useMachines();
  const {data: providers} = useProviders();
  const [datasetIds, setDatasetIds] = useState<string[]>([]);
  const [machine, setMachine] = useState("");
  const [provider, setProvider] = useState("simulated");
  const [preset, setPreset] = useState("realistic");
  const [seed, setSeed] = useState(42);
  const [recall, setRecall] = useState(0.8);
  const [falseAlarms, setFalseAlarms] = useState(0);
  const [delta, setDelta] = useState(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const history = useRuns(kind);
  const activeRun = history.data?.find(r => r.status === "queued" || r.status === "running");
  const actionsBlocked = busy || !!activeRun || history.isPending || history.isError;
  const schedules = useQuery({queryKey: ["verification-schedules"], enabled: kind === "verification",
    queryFn: () => request<{machine_id: string; enabled: boolean}[]>("/api/v1/verification/schedules")});
  const canRun = hasPerm(me, kind === "verification" ? "verification.run" : "benchmark.run");
  async function schedule(enabled: boolean) {
    if (actionsBlocked) return;
    setBusy(true); setError("");
    try {await request("/api/v1/verification/schedules", {dataset_ids: datasetIds, provider_id: provider, preset,
      machine_id: machine || machines?.[0]?.id || null, seed, min_recall: recall, max_false_alarms: falseAlarms,
      max_score_delta: delta, enabled}, "PUT"); await schedules.refetch();}
    catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
  }
  async function run(event: FormEvent) {
    event.preventDefault();
    if (actionsBlocked) return;
    setBusy(true); setError("");
    try {
      const submitted = await request<Run>(`/api/v1/${kind}/runs`, {dataset_ids: datasetIds, provider_id: provider, preset, seed,
        machine_id: machine || machines?.[0]?.id || null, min_recall: recall,
        max_false_alarms: falseAlarms, max_score_delta: delta});
      client.setQueryData<Run[]>([kind, "runs", undefined], previous =>
        [submitted, ...(previous ?? []).filter(r => r.id !== submitted.id)]);
      await client.invalidateQueries({queryKey: [kind, "runs"]});
      await client.invalidateQueries({queryKey: ["dashboard"]});
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const reason = (code: string) => ({recall_below_tolerance: bi("Recall below tolerance", "শনাক্তের হার সীমার নিচে"),
    false_alarms_above_tolerance: bi("Too many false alarms", "ভুল সতর্কতা সীমার বেশি"),
    score_delta_above_tolerance: bi("Score difference above tolerance", "স্কোরের পার্থক্য সীমার বেশি")}[code] ?? code);
  const comparisons = history.data?.filter((r) => selected.includes(r.id)) ?? [];
  return <div className="space-y-4" data-testid={`${kind}-workbench`}>
    <Card>
      <CardTitle>{bi("Run a reference-video check", "রেফারেন্স ভিডিও দিয়ে পরীক্ষা চালান")}</CardTitle>
      <p className="mb-4 text-sm text-slate-500">{bi(
        "Every video is simulated. Select simulated detections or the real local model. This checks the pipeline, not physical camera calibration.",
        "প্রতি পরীক্ষায় ভিডিও সিমুলেটেড। সিমুলেটেড শনাক্তকারী অথবা নিজের মডেল বাছুন। এটি সফটওয়্যারের পরীক্ষা; বাস্তব ক্যামেরার ক্যালিব্রেশন নয়।")}</p>
      {kind === "benchmark" && <p className="mb-4 text-sm text-brand-amber">{bi(
        "Only held-out test datasets with a verified manifest are accepted.", "শুধু test manifest-সহ ডেটা চলবে; train/validation ডেটা চলবে না।")}</p>}
      {canRun && <form onSubmit={run} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={bi("Datasets (up to 5)", "ডেটাসেট (সর্বোচ্চ ৫টি)")}>
          <select required multiple className={inputCls} value={datasetIds} data-testid="evaluation-datasets"
            onChange={(e) => setDatasetIds(Array.from(e.target.selectedOptions, (o) => o.value))}>
            {datasets?.map((d) => <option key={d.id} value={d.id}>{d.id}</option>)}
          </select>
        </Field>
        <Field label={bi("Machine", "মেশিন")}><select className={inputCls} value={machine || machines?.[0]?.id || ""}
          onChange={(e) => setMachine(e.target.value)}>
          {machines?.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
        </select></Field>
        <Field label={bi("Detector", "শনাক্তকারী")}><select className={inputCls} value={provider}
          onChange={(e) => setProvider(e.target.value)}>
          {providers?.filter((p) => p.availability === "available").map((p) => <option key={p.provider_id}
            value={p.provider_id}>{p.display_name}</option>)}
        </select></Field>
        <Field label={bi("Simulation preset", "সিমুলেশনের ধরন")}><select disabled={provider !== "simulated"}
          className={inputCls} value={preset} onChange={(e) => setPreset(e.target.value)}>
          <option value="realistic">{bi("Realistic (with errors)", "বাস্তবসম্মত (ভুলসহ)")}</option>
          <option value="perfect">{bi("Perfect (answer key)", "নিখুঁত (উত্তর অনুযায়ী)")}</option>
        </select></Field>
        <Field label={bi("Minimum recall (0–1)", "সর্বনিম্ন শনাক্তের হার (০–১)")}><input required type="number"
          min={0} max={1} step={0.01} className={inputCls} value={recall} onChange={(e) => setRecall(+e.target.value)}/></Field>
        <Field label={bi("Simulation seed", "সিমুলেশনের seed")}><input type="number" min={0} max={2147483647} className={inputCls}
          value={seed} onChange={(e) => setSeed(+e.target.value)}/></Field>
        <Field label={bi("Maximum false alarms", "সর্বোচ্চ ভুল সতর্কতা")}><input required type="number"
          min={0} className={inputCls} value={falseAlarms} onChange={(e) => setFalseAlarms(+e.target.value)}/></Field>
        <Field label={bi("Maximum score difference / 100 sq yd", "প্রতি ১০০ বর্গগজে স্কোরের সর্বোচ্চ পার্থক্য")}>
          <input required type="number" min={0} step={0.1} className={inputCls} value={delta}
            onChange={(e) => setDelta(+e.target.value)}/></Field>
        <button disabled={actionsBlocked || !datasetIds.length || datasetIds.length > 5} className={`${primaryBtn} self-end`}
          data-testid="evaluation-run">{busy ? bi("Submitting…", "জমা হচ্ছে…") : activeRun
            ? bi("Check in progress…", "পরীক্ষা চলছে…") : bi("Run check", "পরীক্ষা চালান")}</button>
        {activeRun && <p role="status" data-testid="evaluation-active" className="text-sm sm:col-span-2 lg:col-span-3">
          {activeRun.status === "queued"
            ? bi("A check is queued. These actions will be available when it finishes.", "একটি পরীক্ষা অপেক্ষমাণ। পরীক্ষা শেষ হলে বোতামগুলো আবার চালু হবে।")
            : bi("A check is running. These actions will be available when it finishes.", "একটি পরীক্ষা চলছে। পরীক্ষা শেষ হলে বোতামগুলো আবার চালু হবে।")}
        </p>}
        {kind === "verification" && <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-3">
          <button type="button" disabled={actionsBlocked || !datasetIds.length} className={primaryBtn} onClick={() => void schedule(true)}>{bi("Enable daily worker check", "worker দিয়ে দৈনিক যাচাই চালু")}</button>
          <button type="button" disabled={actionsBlocked || !datasetIds.length} className={primaryBtn} onClick={() => void schedule(false)}>{bi("Disable schedule", "দৈনিক যাচাই বন্ধ")}</button>
          <p className="text-sm text-slate-500">{bi("Runs once per Dhaka day while the edge worker is running. Cloud demo uses the run button.", "এজ worker চালু থাকলে ঢাকার প্রতিদিনে একবার চলে। ক্লাউড ডেমোতে পরীক্ষা চালান বোতাম ব্যবহার করুন।")}</p>
          <p className="text-sm">{bi("Configured schedules", "সংরক্ষিত সময়সূচি")}: {schedules.data?.length ?? 0} · {bi("Enabled", "চালু")}: {schedules.data?.filter((s) => s.enabled).length ?? 0}</p>
        </div>}
      </form>}
      {error && <p role="alert" className="mt-3 text-red-600">{error}</p>}
    </Card>
    {history.isError && <p role="alert">{bi("History could not be loaded.", "আগের পরীক্ষাগুলো আনা যায়নি।")}</p>}
    {history.isLoading && <p>{bi("Loading…", "লোড হচ্ছে…")}</p>}
    {!history.isLoading && !history.isError && !history.data?.length && <Card>{bi("No checks yet.", "এখনো পরীক্ষা হয়নি।")}</Card>}
    <Card>
      <CardTitle>{bi("History · select two completed runs to compare", "পরীক্ষার ইতিহাস · তুলনা করতে দুটি সম্পূর্ণ পরীক্ষা বাছুন")}</CardTitle>
      {comparisons.length === 2 && <div className="mb-4 grid gap-2 sm:grid-cols-2" data-testid="run-comparison">
        {comparisons.map((r) => <div key={r.id} className="rounded border border-slate-300 p-3 text-sm">
          <p className="font-mono">{r.id.slice(0, 8)}</p>
          {r.result?.rolls?.map((roll) => <p key={roll.dataset_id}>{roll.dataset_id}: TP {roll.evaluation.tp}, FP {roll.evaluation.fp},
            FN {roll.evaluation.fn} · {roll.per_100.toFixed(2)} /100 · {roll.seconds.toFixed(2)} s</p>)}
        </div>)}
      </div>}
      <div className="space-y-3">{history.data?.map((run) => <article key={run.id} className="rounded border border-slate-300 p-3"
        data-testid="evaluation-history-row">
        <div className="flex flex-wrap items-center gap-3">
          <input type="checkbox" aria-label={bi("Compare run", "পরীক্ষা তুলনা করুন")} checked={selected.includes(run.id)}
            disabled={run.status !== "completed" || (!selected.includes(run.id) && selected.length === 2)}
            onChange={(e) => setSelected(e.target.checked ? [...selected, run.id] : selected.filter((id) => id !== run.id))}/>
          <time className="text-sm">{new Date(run.created_at).toLocaleString(undefined, {timeZone: "Asia/Dhaka"})}</time>
          <Pill tone={run.status === "failed" || run.result?.passed === false ? "red" : run.result?.passed ? "emerald" : "amber"}>
            {run.status === "completed" ? (run.result?.passed ? bi("GREEN", "সবুজ") : bi("RED", "লাল")) :
              run.status === "failed" ? bi("Failed", "চালানো যায়নি") : bi("Processing", "চলছে")}
          </Pill><span className="font-mono text-xs">{run.id.slice(0, 8)}</span>
        </div>
        {run.error && <p className="text-red-600">{bi("Run failed; check the worker and model availability.", "পরীক্ষা ব্যর্থ; worker ও model আছে কি না দেখুন।")}</p>}
        {run.result?.rolls?.map((roll) => <div key={roll.dataset_id} className="mt-3 space-y-2 text-sm">
          <p className="font-semibold">{roll.dataset_id} · {roll.provider}</p>
          <p>{roll.simulated_detections ? bi("SIMULATED VIDEO + DETECTIONS", "ভিডিও ও শনাক্তকরণ সিমুলেটেড") :
            bi("SIMULATED VIDEO · REAL AI", "ভিডিও সিমুলেটেড · আসল AI")}</p>
          <p>TP {roll.evaluation.tp} · FP {roll.evaluation.fp} · FN {roll.evaluation.fn} ·
            {bi("Recall", "শনাক্তের হার")} {(roll.evaluation.recall * 100).toFixed(1)}% ·
            {bi("Precision", "সঠিক সতর্কতা")} {(roll.evaluation.precision * 100).toFixed(1)}%</p>
          <p>{bi("Model / truth score", "মডেল / উত্তর অনুযায়ী স্কোর")}: {roll.per_100.toFixed(2)} / {roll.truth_per_100.toFixed(2)} ·
            {roll.verdict} / {roll.truth_verdict} · {bi("Coverage", "কভারেজ")} {roll.coverage_pct}%</p>
          <p>{roll.reasons.map(reason).join(" · ")}</p>
          <details><summary>{bi("Pipeline and per-class results", "পাইপলাইন ও শ্রেণিভিত্তিক ফল")}</summary>
            <p>{Object.entries(roll.funnel).map(([key, value]) => `${key}: ${value}`).join(" → ")}</p>
            <p>{Object.entries(roll.evaluation.recall_per_class).map(([key, value]) => `${key}: ${(value * 100).toFixed(1)}%`).join(" · ")}</p>
            <p>{bi("False alarms by type", "ধরন অনুযায়ী ভুল সতর্কতা")}: {JSON.stringify(roll.evaluation.fp_by_type)}</p>
          </details>
        </div>)}
      </article>)}</div>
    </Card>
  </div>;
}
