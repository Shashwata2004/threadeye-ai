"use client";

import { useId, useState } from "react";
import type { Cutting } from "@/lib/api/operations";
import { useBi } from "@/components/screenKit";

export function CuttingRollMap({data}: {data: Cutting}) {
  const bi = useBi();
  const clip = useId();
  const [opacity, setOpacity] = useState(0.3);
  const [zoom, setZoom] = useState(1);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const fabric = data.fabric;
  const length = data.plan.length_yd;
  const height = Math.max(90, Math.min(400, 1000 * (fabric?.width_cm ?? 150) / (length * 91.44)));
  const x = (yd: number) => yd / length * 1000;
  const ticks = Array.from({length: 6}, (_, i) => length * i / 5);
  return <div className="mb-4 space-y-3">
    <div className="flex flex-wrap items-center gap-5 text-sm">
      <span><span aria-hidden="true" className="mr-2 inline-block h-3 w-4 border border-red-500 bg-red-500/30"/>{bi("Red: skip zone", "লাল: বাদ দেওয়ার অংশ")}</span>
      <span><span aria-hidden="true" className="mr-2 inline-block h-3 w-4 border-2 border-dashed border-amber-400"/>{bi("Yellow box: confirmed defect", "হলুদ বক্স: নিশ্চিত ত্রুটি")}</span>
      <label className="flex items-center gap-2">{bi("Overlay opacity", "লাল রঙের গাঢ়ত্ব")}
        <input aria-label={bi("Overlay opacity", "লাল রঙের গাঢ়ত্ব")} type="range" min="0" max="0.7" step="0.05" value={opacity} onChange={e => setOpacity(Number(e.target.value))}/>
      </label>
      <label className="flex items-center gap-2">{bi("Zoom", "বড় করে দেখুন")}
        <input aria-label={bi("Zoom", "বড় করে দেখুন")} type="range" min="1" max="4" step="0.5" value={zoom} onChange={e => setZoom(Number(e.target.value))}/>
      </label>
    </div>
    <p className="text-sm text-slate-500" role="status">{!fabric || failed
      ? bi("Fabric image unavailable here; showing the cutting diagram.", "এখানে কাপড়ের ছবি পাওয়া যাচ্ছে না; কাটিংয়ের মানচিত্র দেখানো হচ্ছে।")
      : !loaded ? bi("Building the fabric strip from the video…", "ভিডিও থেকে কাপড়ের ছবি তৈরি হচ্ছে…")
      : bi("Fabric strips stitched from the simulated video. Grey areas have no unobstructed image. Only confirmed inspection defects are boxed; red zones include cutting margins. Yards run left to right; fabric width runs top to bottom.",
        "সিমুলেটেড ভিডিওর কাপড় জোড়া দিয়ে তৈরি ছবি। ধূসর অংশে বাধাহীন ছবি পাওয়া যায়নি। বক্সে শুধু পরীক্ষায় নিশ্চিত করা ত্রুটি; লাল অংশে কাটিং মার্জিনও আছে। বাম থেকে ডানে গজ, ওপর থেকে নিচে কাপড়ের প্রস্থ।")}</p>
    <div className="overflow-x-auto rounded border border-slate-500">
      <div style={{width: `${zoom * 100}%`, minWidth: 800}}>
        <svg viewBox={`0 0 1000 ${height + 34}`} role="img" aria-label={bi("Fabric roll with transparent cutting overlays", "স্বচ্ছ কাটিং চিহ্নসহ কাপড়ের রোল")} className="block w-full">
          <defs><clipPath id={clip}><rect width="1000" height={height}/></clipPath></defs>
          <g clipPath={`url(#${clip})`}>
            <rect width="1000" height={height} fill={fabric && !failed ? "#414141" : "#50645a"}/>
            {fabric && !failed && <image href={fabric.image_url} width={x(fabric.length_yd)} height={height}
              preserveAspectRatio="none" onLoad={() => setLoaded(true)} onError={() => setFailed(true)}/>
            }
            {data.plan.segments.filter(s => s.action === "skip").map((s, i) => <rect key={i} data-testid="skip-overlay"
              x={x(s.start_yd)} y="0" width={x(s.end_yd - s.start_yd)} height={height}
              fill="#ef4444" fillOpacity={opacity} stroke="#f87171" strokeWidth="1" vectorEffect="non-scaling-stroke">
              <title>{bi("Skip", "বাদ দিন")}: {s.start_yd.toFixed(3)}–{s.end_yd.toFixed(3)} {bi("yd", "গজ")}</title>
            </rect>)}
            {fabric && (data.defects ?? []).map(d => {
              const y = Math.max(0, d.across_start_cm / fabric.width_cm * height);
              return <g key={d.id}>
                <rect data-testid="confirmed-defect-box" x={x(d.start_yd)} y={y}
                  width={Math.max(2, x(d.end_yd - d.start_yd))} height={Math.max(2, (d.across_end_cm - d.across_start_cm) / fabric.width_cm * height)}
                  fill="none" stroke="#fbbf24" strokeWidth="2" strokeDasharray="4 2" vectorEffect="non-scaling-stroke">
                  <title>#{d.number} · {d.cls} · {d.start_yd.toFixed(3)}–{d.end_yd.toFixed(3)} {bi("yd", "গজ")}</title>
                </rect>
                <text x={Math.min(968, x(d.start_yd))} y={Math.max(15, y - 4)} fontSize="12" fill="#fbbf24" stroke="#111" strokeWidth="3" paintOrder="stroke">#{d.number}</text>
              </g>;
            })}
          </g>
          {ticks.map((yd, i) => <g key={i}>
            <line x1={x(yd)} x2={x(yd)} y1={height} y2={height + 6} stroke="currentColor"/>
            <text x={x(yd)} y={height + 23} fontSize="12" fill="currentColor" textAnchor={i === 0 ? "start" : i === 5 ? "end" : "middle"}>{yd.toFixed(2)} {bi("yd", "গজ")}</text>
          </g>)}
        </svg>
      </div>
    </div>
  </div>;
}
