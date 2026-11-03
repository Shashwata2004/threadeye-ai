"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { hasPerm, type Inspection, type Defect } from "@/lib/api/client";
import { useMe, useTrack } from "@/lib/api/hooks";
import { request, useRuns, type Run } from "@/lib/api/operations";
import { Card, CardTitle, Field, inputCls, primaryBtn, ghostBtn, screenRoot, useBi } from "./screenKit";

export function VerificationWarning({machineId}: {machineId: string}) {
  const bi = useBi();
  const runs = useRuns("verification", machineId);
  const today = new Date().toLocaleDateString("en-CA", {timeZone: "Asia/Dhaka"});
  const latest = runs.data?.find((r) => new Date(r.created_at).toLocaleDateString("en-CA", {timeZone: "Asia/Dhaka"}) === today);
  if (!latest || (latest.status !== "failed" && latest.result?.passed !== false)) return null;
  return <p role="alert" className="rounded border border-red-500 bg-red-500/10 p-3 text-red-600">
    {bi("Today's reference check failed for this machine. Review verification before trusting detections.",
      "এই মেশিনের আজকের রেফারেন্স পরীক্ষা ব্যর্থ। শনাক্তকরণে নির্ভর করার আগে যাচাই দেখুন।")} <Link href="/verification" className="underline">{bi("Open", "খুলুন")}</Link>
  </p>;
}

export function MeasurementPanel({inspection}: {inspection: Inspection}) {
  const bi = useBi();
  const {data: me} = useMe();
  const client = useQueryClient();
  const [kind, setKind] = useState("width");
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!hasPerm(me, "inspections.run")) return null;
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await request(`/api/v1/inspections/${inspection.id}/measurements`, {kind, value: +value, unit: kind === "width" ? "in" : "yd"});
      await client.invalidateQueries({queryKey: ["inspection", inspection.id]}); setValue("");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally {setBusy(false);}
  }
  return <details className={`${screenRoot} rounded border border-slate-300 p-3`}>
    <summary className="cursor-pointer">{bi("Measured length / width", "মাপা দৈর্ঘ্য / প্রস্থ")}</summary>
    <p className="my-2 text-sm">{bi("Recorded width", "মাপা প্রস্থ")}: {inspection.measured_width_in ?? "—"} in · {bi("Recorded length", "মাপা দৈর্ঘ্য")}: {inspection.measured_length_yd ?? "—"} yd</p>
    {inspection.measurement_checks?.width_delta_in != null && <p className="mb-2 text-sm">
      {bi("Width difference", "প্রস্থের পার্থক্য")}: {String(inspection.measurement_checks.width_delta_in)} in ·
      {inspection.measurement_checks.width_within_tolerance ? bi("Within buyer tolerance", "বায়ারের সীমার মধ্যে") : bi("Outside buyer tolerance", "বায়ারের সীমার বাইরে")}</p>}
    {inspection.measurement_checks?.length_delta_yd != null && <p className="mb-2 text-sm">
      {bi("Length difference from source reference", "উৎসের দৈর্ঘ্যের সঙ্গে পার্থক্য")}: {String(inspection.measurement_checks.length_delta_yd)} yd</p>}
    <p className="mb-2 text-sm text-slate-500">{bi("For a simulated source, enter the length visible in the video, not an unrelated physical roll's length.",
      "সিমুলেটেড উৎস হলে ভিডিওর রোলের দৈর্ঘ্য দিন; অন্য বাস্তব রোলের দৈর্ঘ্য নয়।")}</p>
    <p className="mb-2 text-sm text-slate-500">{bi("Scoring uses the buyer profile's declared, measured or cuttable width basis.", "স্কোরে বায়ারের নিয়ম অনুযায়ী ঘোষিত, মাপা অথবা কাটার উপযোগী প্রস্থ ব্যবহৃত হয়।")}</p>
    {!inspection.finalized_at && <form onSubmit={save} className="flex flex-wrap items-end gap-2">
      <Field label={bi("Measurement", "মাপ")}><select className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}>
        <option value="width">{bi("Width (in)", "প্রস্থ (ইঞ্চি)")}</option><option value="length">{bi("Length (yd)", "দৈর্ঘ্য (গজ)")}</option></select></Field>
      <Field label={bi("Value", "মান")}><input required className={inputCls} type="number" min={0.001} step="any" max={kind === "width" ? 200 : 2000} value={value} onChange={(e) => setValue(e.target.value)}/></Field>
      <button className={primaryBtn} disabled={busy}>{bi("Record measurement", "মাপ সংরক্ষণ")}</button>
    </form>}
    {error && <p role="alert" className="text-red-600">{error}</p>}
  </details>;
}

export function InspectionEvidenceTools({inspection, defects}: {inspection: Inspection; defects: Defect[]}) {
  const bi = useBi();
  const {data: me} = useMe();
  const {data: track} = useTrack(inspection.id);
  const client = useQueryClient();
  const [defectId, setDefectId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const clips = useQuery({queryKey: ["clips", inspection.id], enabled: hasPerm(me, "reports.read"),
    queryFn: () => request<Run[]>(`/api/v1/inspections/${inspection.id}/clips`),
    refetchInterval: (q) => q.state.data?.some((r) => ["queued", "running"].includes(r.status)) ? 1500 : false});
  const selected = defects.find((d) => d.id === defectId) ?? defects[0];
  const frame = selected?.best_frame ?? 0;
  const fps = track?.fps ?? 1;
  const start = Math.max(0, frame / fps - 1.5);
  return <div className={`${screenRoot} space-y-3`}>
    {inspection.finalized_at && hasPerm(me, "cutting.read") && <Link className={primaryBtn} href={`/inspections/${inspection.id}/cutting`}>{bi("Cutting sheet", "কাটিং নির্দেশনা")}</Link>}
    {hasPerm(me, "label_data.export") && <a className={`${ghostBtn} ml-2`} href={`/api/v1/inspections/${inspection.id}/labels.zip`}>{bi("Export reviewed labels", "যাচাইকৃত লেবেল ডাউনলোড")}</a>}
    {!!defects.length && <Card><CardTitle>{bi("Defect video evidence", "ত্রুটির ভিডিও প্রমাণ")}</CardTitle>
      <select aria-label={bi("Defect clip", "ত্রুটির ক্লিপ")} className={inputCls} value={selected?.id ?? ""} onChange={(e) => setDefectId(e.target.value)}>
        {defects.map((d) => <option key={d.id} value={d.id}>#{d.defect_no} {d.current_cls} · {d.center_yd.toFixed(2)} yd</option>)}</select>
      {track?.video_url && <video key={selected?.id} controls preload="metadata" className="my-3 max-h-72 w-full" src={`${track.video_url}#t=${start},${start + 4}`}/>}
      {hasPerm(me, "reports.generate") && <button className={ghostBtn} disabled={busy || !selected} onClick={async () => {
        setBusy(true); setError("");
        try {await request(`/api/v1/inspections/${inspection.id}/defects/${selected?.id}/clip`, {});
          await client.invalidateQueries({queryKey: ["clips", inspection.id]});}
        catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
      }}>{bi("Export MP4 on edge laptop", "এজ ল্যাপটপে MP4 তৈরি")}</button>}
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {clips.data?.map((r) => <p className="mt-2 text-sm" key={r.id}>{r.status === "completed" ?
        <a className="text-brand-teal underline" href={`/api/v1/inspections/${inspection.id}/clips/${r.id}.mp4`} download>{bi("Download clip", "ক্লিপ ডাউনলোড")}</a> :
        r.status === "failed" ? bi("Clip failed; inspect local worker logs.", "ক্লিপ তৈরি হয়নি; worker পরীক্ষা করুন।") : bi("Clip processing…", "ক্লিপ তৈরি হচ্ছে…")}</p>)}
    </Card>}
  </div>;
}
