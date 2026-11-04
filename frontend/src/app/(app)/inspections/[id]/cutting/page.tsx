"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useMe } from "@/lib/api/hooks";
import { hasPerm } from "@/lib/api/client";
import { request, type Cutting } from "@/lib/api/operations";
import { CuttingRollMap } from "@/components/CuttingRollMap";
import { Card, CardTitle, KpiCard, PageHeader, primaryBtn, ghostBtn, inputCls, screenRoot, useBi } from "@/components/screenKit";

export default function CuttingPage() {
  const {id} = useParams<{id: string}>();
  const bi = useBi();
  const {data: me} = useMe();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const query = useQuery({queryKey: ["cutting", id], queryFn: () => request<Cutting>(`/api/v1/inspections/${id}/cutting`)});
  async function decide(action: "approve" | "acknowledge") {
    setBusy(true); setError("");
    try {await request(`/api/v1/inspections/${id}/cutting/${action}`, {}); await Promise.all([
      client.invalidateQueries({queryKey: ["cutting", id]}), client.invalidateQueries({queryKey: ["cutting-work"]}),
    ]);}
    catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
  }
  async function selectPolicy(selection: string) {
    setBusy(true); setError("");
    try {
      const updated = await request<Cutting>(`/api/v1/inspections/${id}/cutting/policy`, {selection}, "PUT");
      client.setQueryData(["cutting", id], updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await client.invalidateQueries({queryKey: ["cutting", id]});
    } finally {setBusy(false);}
  }
  const data = query.data;
  return <div className={`${screenRoot} space-y-4`}>
    <Link className={ghostBtn} href="/cutting">{bi("Back to cutting work", "কাটিং কাজের তালিকায় ফিরুন")}</Link>
    <PageHeader title={bi("Cutting sheet", "কাটিং নির্দেশনা")} sample={!!data?.simulated}
      subtitle={bi("Whole-width skip zones from confirmed defects, buyer margins and minimum usable pieces.",
        "নিশ্চিত ত্রুটি, বায়ারের মার্জিন ও ন্যূনতম টুকরোর দৈর্ঘ্য অনুযায়ী পুরো প্রস্থজুড়ে বাদ দেওয়ার অংশ।")}/>
    <Link href={`/inspections/${id}`} className={ghostBtn}>{bi("Back to inspection", "পরীক্ষায় ফিরুন")}</Link>
    {(error || query.error) && <p role="alert" className="text-red-600">{error || query.error?.message}</p>}
    {query.isLoading && <p>{bi("Loading…", "লোড হচ্ছে…")}</p>}
    {data && <>
      <Card><label className="block space-y-2">
        <span className="font-semibold">{bi("Cutting policy", "কাটিং নীতি")}</span>
        <select aria-label={bi("Cutting policy", "কাটিং নীতি")} className={inputCls}
          value={data.policy_selection ?? "buyer"}
          disabled={busy || data.policy_locked || data.status !== "draft" || !hasPerm(me, "cutting.approve")}
          onChange={e => void selectPolicy(e.target.value)}>
          <option value="buyer">{bi("Buyer policy (automatic default)", "বায়ারের নিয়ম (স্বয়ংক্রিয় নির্বাচন)")}</option>
          <option value="all">{bi("Skip every confirmed defect (1–4 points)", "সব নিশ্চিত ত্রুটি বাদ (১–৪ পয়েন্ট)")}</option>
          <option value="two_plus">{bi("Skip defects of 2 points or more", "২ পয়েন্ট বা বেশি হলে বাদ")}</option>
          <option value="three_plus">{bi("Skip defects of 3 points or more", "৩ পয়েন্ট বা বেশি হলে বাদ")}</option>
          <option value="four_plus">{bi("Skip 4-point defects only", "শুধু ৪ পয়েন্টের ত্রুটি বাদ")}</option>
        </select>
      </label><p className="mt-2 text-sm text-slate-500">{data.policy_locked || data.status !== "draft"
        ? bi("This cutting policy is locked after approval.", "অনুমোদনের পর এই কাটিং নীতি স্থির করা হয়েছে; বদলানো যাবে না।")
        : bi("The buyer policy is selected automatically. A supervisor can select another policy before approval; it saves automatically and updates the red zones. Roll PASS/FAIL rules stay the same.",
          "বায়ারের নিয়ম নিজে থেকেই নির্বাচিত থাকে। অনুমোদনের আগে সুপারভাইজার অন্য নীতি বাছলে সেটি স্বয়ংক্রিয়ভাবে সেভ হবে ও লাল অংশ বদলাবে। রোলের PASS/FAIL-এর নিয়ম একই থাকবে।")}</p></Card>
      <div className="grid gap-3 sm:grid-cols-3"><KpiCard label={bi("Usable (yd)", "ব্যবহারযোগ্য (গজ)")} value={data.plan.usable_yd.toFixed(3)}/>
        <KpiCard label={bi("Skip (yd)", "বাদ (গজ)")} value={data.plan.skipped_yd.toFixed(3)} tone="red"/>
        <KpiCard label={bi("Status", "অবস্থা")} value={data.status === "draft" ? bi("Draft", "খসড়া") : data.status === "approved" ? bi("Approved", "অনুমোদিত") : bi("Acknowledged", "গ্রহণ নিশ্চিত")}/></div>
      <Card><CardTitle>{bi("Roll strip and segments", "রোলের মানচিত্র ও অংশ")}</CardTitle>
        <CuttingRollMap key={data.source_hash} data={data}/>
        <table className="w-full text-left text-sm"><thead><tr><th>{bi("From (yd)", "শুরু (গজ)")}</th><th>{bi("To (yd)", "শেষ (গজ)")}</th><th>{bi("Action", "করণীয়")}</th></tr></thead>
          <tbody>{data.plan.segments.map((s, i) => <tr key={i} className="border-t border-slate-300"><td className="py-2">{s.start_yd.toFixed(3)}</td><td>{s.end_yd.toFixed(3)}</td><td>{s.action === "keep" ? bi("KEEP", "রাখুন") : bi("SKIP", "বাদ দিন")}</td></tr>)}</tbody></table>
        <p className="mt-3 text-sm text-slate-500">{bi("Margin / minimum piece / minimum defect points", "মার্জিন / ন্যূনতম টুকরো / ন্যূনতম ত্রুটি পয়েন্ট")}: {data.plan.policy.margin_in} in / {data.plan.policy.min_piece_yd} yd / {data.plan.policy.min_points_to_cut} pt</p>
      </Card>
      <div className="flex flex-wrap gap-3">
        {hasPerm(me, "cutting.approve") && data.status === "draft" && <button className={primaryBtn} disabled={busy} onClick={() => void decide("approve")}>{bi("Approve cutting plan", "কাটিং অনুমোদন")}</button>}
        {hasPerm(me, "cutting.acknowledge") && data.status === "approved" && <button className={primaryBtn} disabled={busy} onClick={() => void decide("acknowledge")}>{bi("Acknowledge instructions", "নির্দেশনা গ্রহণ নিশ্চিত")}</button>}
        <a className={ghostBtn} target="_blank" rel="noopener" href={`/api/v1/inspections/${id}/cutting.pdf?lang=en`}>PDF · English</a>
        <a className={ghostBtn} target="_blank" rel="noopener" href={`/api/v1/inspections/${id}/cutting.pdf?lang=bn`}>PDF · বাংলা</a>
      </div>
      <p className="break-all font-mono text-xs text-slate-500">SHA256: {data.source_hash}</p>
    </>}
  </div>;
}
