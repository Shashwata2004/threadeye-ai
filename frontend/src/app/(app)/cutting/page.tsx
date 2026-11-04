"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { request, type CuttingWork } from "@/lib/api/operations";
import { Card, PageHeader, Pill, ghostBtn, inputCls, screenRoot, useBi } from "@/components/screenKit";

export default function CuttingWorkPage() {
  const bi = useBi();
  const [filter, setFilter] = useState("approved");
  const query = useQuery({queryKey: ["cutting-work"], queryFn: () => request<CuttingWork[]>("/api/v1/cutting"),
    refetchInterval: 15000});
  const items = (query.data ?? []).filter(item => filter === "all" || item.status === filter);
  return <div className={`${screenRoot} space-y-4`}>
    <PageHeader title={bi("Cutting work", "কাটিং কাজ")} sample={false}
      subtitle={bi("Open QC-approved instructions, check the roll and acknowledge receipt. Receipt does not mean cutting is complete.",
        "QC অনুমোদিত নির্দেশনা খুলুন, রোল মিলিয়ে দেখুন ও গ্রহণ নিশ্চিত করুন। গ্রহণ নিশ্চিত করা মানে কাপড় কাটা শেষ নয়।")}/>
    <Card>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm">{bi("Show", "দেখান")}
          <select className={inputCls} value={filter} onChange={event => setFilter(event.target.value)}>
            <option value="approved">{bi("Awaiting receipt", "গ্রহণের অপেক্ষায়")}</option>
            <option value="acknowledged">{bi("Receipt acknowledged", "গ্রহণ নিশ্চিত করা হয়েছে")}</option>
            <option value="all">{bi("All approved instructions", "সব অনুমোদিত নির্দেশনা")}</option>
          </select>
        </label>
        <button className={ghostBtn} disabled={query.isFetching} onClick={() => void query.refetch()}>{bi("Refresh", "আবার দেখুন")}</button>
      </div>
      {query.isPending ? <p>{bi("Loading cutting work…", "কাটিং কাজ লোড হচ্ছে…")}</p> : query.isError ?
        <p role="alert">{bi("Could not load cutting work. Please try again.", "কাটিং কাজ আনা যায়নি। আবার চেষ্টা করুন।")}</p> :
        !items.length ? <p>{bi("No instructions in this list. Only current QC-approved plans appear here.",
          "এই তালিকায় নির্দেশনা নেই। শুধু বর্তমান QC অনুমোদিত প্ল্যান এখানে দেখাবে।")}</p> :
        <div className="overflow-x-auto"><table className="w-full text-left text-sm" data-testid="cutting-work-list">
          <thead><tr><th>{bi("Roll / delivery", "রোল / চালান")}</th><th>{bi("Approved", "অনুমোদনের সময়")}</th>
            <th>{bi("Usable / skip (yd)", "ব্যবহারযোগ্য / বাদ (গজ)")}</th><th>{bi("Status", "অবস্থা")}</th><th>{bi("Instructions", "নির্দেশনা")}</th></tr></thead>
          <tbody>{items.map(item => <tr key={item.inspection_id} className="border-t border-slate-300">
            <td className="py-3"><strong className="font-mono">{item.roll_code}</strong><p>{item.challan}</p></td>
            <td>{new Date(item.approved_at).toLocaleString(bi("en-GB", "bn-BD"))}</td>
            <td>{item.usable_yd.toFixed(3)} / {item.skipped_yd.toFixed(3)}</td>
            <td><Pill tone={item.status === "approved" ? "amber" : "teal"}>{item.status === "approved" ?
              bi("Awaiting receipt", "গ্রহণের অপেক্ষায়") : bi("Receipt acknowledged", "গ্রহণ নিশ্চিত")}</Pill></td>
            <td><Link className={ghostBtn} href={`/inspections/${item.inspection_id}/cutting`}>{bi("Open instructions", "নির্দেশনা খুলুন")}</Link></td>
          </tr>)}</tbody>
        </table></div>}
    </Card>
  </div>;
}
