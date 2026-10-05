"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ProviderBadge } from "@/components/badges";
import { Button, inputClass } from "@/components/form";
import { api, hasPerm, idempotencyKey, type Defect } from "@/lib/api/client";
import { errorDetail, useDefects, useInspection, useMe } from "@/lib/api/hooks";

const VERDICT_STYLE: Record<string, string> = {
  PASS: "bg-green-700 text-white",
  BORDERLINE: "bg-amber-500 text-amber-950",
  FAIL: "bg-red-700 text-white",
};
const STATUS_FILL: Record<string, string> = { confirmed: "#16a34a", pending: "#dc2626", rejected: "#94a3b8" };

function RollMap({
  defects,
  lengthYd,
  widthCm,
  onPick,
}: {
  defects: Defect[];
  lengthYd: number;
  widthCm: number;
  onPick: (d: Defect) => void;
}) {
  const W = 1000;
  const H = 150;
  const x = (yd: number) => (yd / lengthYd) * W;
  const y = (cm: number) => (cm / widthCm) * H;
  const step = Math.max(1, Math.round(lengthYd / 12));
  const ticks: number[] = [];
  for (let v = 0; v <= lengthYd + 1e-9; v += step) ticks.push(v);
  return (
    <svg viewBox={`-10 -10 ${W + 20} ${H + 40}`} className="w-full" role="img" aria-label="roll map" data-testid="roll-map">
      <rect x={0} y={0} width={W} height={H} fill="#f5efe4" stroke="#94a3b8" />
      {ticks.map((v) => (
        <g key={v}>
          <line x1={x(v)} x2={x(v)} y1={H} y2={H + 6} stroke="#475569" />
          <text x={x(v)} y={H + 20} fontSize={12} textAnchor="middle" fill="#334155">
            {v}
          </text>
        </g>
      ))}
      {defects.map((d) => {
        const x0 = x(d.start_yd);
        const w = Math.max(x(d.end_yd) - x0, 6);
        const y0 = y(d.across_start_cm);
        const h = Math.max(y(d.across_end_cm) - y0, 6);
        const nd = d.kind === "nondefect";
        return (
          <g key={d.id} onClick={() => onPick(d)} className="cursor-pointer">
            <rect
              x={x0 - (w <= 6 ? 3 : 0)}
              y={y0 - (h <= 6 ? 3 : 0)}
              width={w}
              height={h}
              fill={nd ? "none" : STATUS_FILL[d.status] ?? "#dc2626"}
              stroke={nd ? "#64748b" : "none"}
              strokeDasharray={nd ? "3 2" : undefined}
            >
              <title>{d.defect_no}</title>
            </rect>
            {!nd && (
              <text x={x0} y={Math.max(y0 - 3, 10)} fontSize={11} fill="#0f172a">
                {d.defect_no}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function DecisionPanel({ id, systemVerdict }: { id: string; systemVerdict: string }) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState(systemVerdict === "PASS" ? "ACCEPT" : "REJECT");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const override = (systemVerdict === "PASS" && choice === "REJECT") || (systemVerdict === "FAIL" && choice === "ACCEPT");
  async function save() {
    const { data, error: err } = await api.POST("/api/v1/inspections/{inspection_id}/decision", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
      body: { final_verdict: choice as "ACCEPT" | "ACCEPT_WITH_CLAIM" | "REJECT", reason: reason.trim() },
    });
    if (data) {
      queryClient.setQueryData(["inspection", id], data);
      setError(null);
    } else setError(errorDetail(err));
  }
  return (
    <section className="space-y-2 rounded-lg border border-slate-200 bg-white p-4" data-testid="decision">
      <h2 className="font-semibold">{t("verdict.decision")}</h2>
      <div className="flex flex-wrap gap-3">
        {["ACCEPT", "ACCEPT_WITH_CLAIM", "REJECT"].map((v) => (
          <label key={v} className="flex items-center gap-1 text-sm">
            <input type="radio" name="decision" value={v} checked={choice === v} onChange={() => setChoice(v)} />
            {t(`verdicts.${v}`)}
          </label>
        ))}
      </div>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={t("verdict.reason")}
        className={inputClass}
        rows={2}
      />
      {override && <p className="text-xs font-semibold text-amber-800">{t("verdict.override")}</p>}
      {error && <p className="text-sm text-red-700">{error}</p>}
      <Button onClick={() => void save()} disabled={reason.trim().length < 3}>
        {t("verdict.decide")}
      </Button>
    </section>
  );
}

export default function VerdictPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations();
  const { data: me } = useMe();
  const { data: insp } = useInspection(id);
  const { data: defects = [] } = useDefects(id);
  const [picked, setPicked] = useState<Defect | null>(null);

  if (!insp) return <p className="text-slate-500">{t("common.loading")}</p>;

  const r = insp.roll;
  const real = defects.filter((d) => d.kind === "defect").sort((a, b) => a.center_yd - b.center_yd);
  const ignored = defects.filter((d) => d.kind === "nondefect");
  const cells = Object.entries(insp.score?.cells ?? {})
    .map(([k, v]) => [Number(k), v] as const)
    .sort((a, b) => a[0] - b[0]);
  const lengthYd = Math.max(insp.yards_inspected ?? insp.score?.yards_inspected ?? 1, ...defects.map((d) => d.end_yd), 1);
  const widthCm = Math.max(r.declared_width_in * 2.54, ...defects.map((d) => d.across_end_cm), 1);
  const ignoredCounts = ignored.reduce<Record<string, number>>((acc, d) => {
    const k = d.nondefect_category ?? d.current_cls;
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">{t("verdict.title")}</h1>
          <p className="text-slate-600">
            {t("verdict.roll", { code: r.roll_code, challan: r.challan_no, mill: r.supplier, buyer: r.buyer })}
          </p>
          <p className="text-sm text-slate-500">
            {t("verdict.rules", { profile: r.rule_profile })}
            {insp.inspector && ` · ${t("verdict.inspector", { name: insp.inspector })}`}
          </p>
          <Link href={`/lots/${r.lot_id}`} className="text-sm text-brand-blue hover:underline">
            {t("lots.back")}
          </Link>
        </div>
        <ProviderBadge
          name={`${insp.provider.display_name}${insp.provider.preset ? ` (${insp.provider.preset})` : ""}`}
          simulated={insp.provider.is_simulated}
        />
      </div>

      {insp.system_verdict ? (
        <section className="flex flex-wrap items-center gap-4 rounded-lg border border-slate-200 bg-white p-4">
          <span
            className={`rounded-lg px-5 py-3 text-2xl font-bold ${VERDICT_STYLE[insp.system_verdict]}`}
            data-testid="system-verdict"
            data-verdict={insp.system_verdict}
          >
            {t("verdict.system")}: {t(`verdicts.${insp.system_verdict}`)}
          </span>
          <div>
            <p className="font-mono text-lg" data-testid="verdict-summary">
              {t("verdict.summary", {
                points: insp.points_total ?? 0,
                per100: (insp.points_per_100 ?? 0).toFixed(2),
                threshold: r.threshold_per_100,
              })}
            </p>
            <p className="text-sm text-slate-500">{t("verdict.yards", { yd: (insp.yards_inspected ?? 0).toFixed(2) })}</p>
            {insp.system_verdict === "BORDERLINE" && !insp.final_verdict && (
              <p className="font-semibold text-amber-800">{t("verdict.needSup")}</p>
            )}
            {insp.final_verdict && (
              <p className="font-semibold text-brand-navy">
                {t("verdict.decidedBy", {
                  decision: t(`verdicts.${insp.final_verdict}`),
                  by: insp.decision_by ?? "",
                  reason: insp.decision_reason ?? "",
                })}
              </p>
            )}
          </div>
          <div className="ml-auto flex gap-2 text-sm">
            <span className="text-slate-600">{t("verdict.report")}:</span>
            <a className="font-semibold text-brand-blue hover:underline" href={`/api/v1/inspections/${id}/report.pdf?lang=en`} target="_blank" rel="noopener">
              {t("verdict.reportEn")}
            </a>
            <a className="font-semibold text-brand-blue hover:underline" href={`/api/v1/inspections/${id}/report.pdf?lang=bn`} target="_blank" rel="noopener">
              {t("verdict.reportBn")}
            </a>
          </div>
        </section>
      ) : (
        <section className="rounded-lg border border-amber-300 bg-amber-50 p-4">
          <p className="text-amber-900">{t("verdict.notFinal")}</p>
          <Link href={`/inspect/${id}`} className="font-semibold text-brand-blue hover:underline">
            {t("verdict.backToLive")}
          </Link>
        </section>
      )}

      {insp.system_verdict && hasPerm(me, "verdict.decide") && (
        <DecisionPanel id={id} systemVerdict={insp.system_verdict} />
      )}

      {cells.length > 0 && (
        <section className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="font-semibold">{t("verdict.perYard")}</h2>
          <div className="flex flex-wrap gap-1">
            {cells.map(([yd, pts]) => (
              <div key={yd} className={`w-14 rounded border text-center ${pts >= 4 ? "border-red-400 bg-red-50" : "border-slate-200"}`}>
                <div className="text-[11px] text-slate-500">{yd}</div>
                <div className="font-mono font-bold">{pts}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500">{t("verdict.capNote")}</p>
        </section>
      )}

      <section className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="font-semibold">{t("verdict.map")}</h2>
        <p className="text-xs text-slate-500">{t("verdict.mapHint")}</p>
        <RollMap defects={defects} lengthYd={lengthYd} widthCm={widthCm} onPick={setPicked} />
        {picked && (
          <div className="flex gap-3 rounded border border-slate-200 bg-slate-50 p-3 text-sm">
            {picked.crop_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={picked.crop_url} alt={picked.defect_no} className="h-32 w-32 rounded object-cover" />
            )}
            <div className="space-y-1">
              <p className="font-semibold">
                {picked.defect_no} · {t(`cls.${picked.nondefect_category ?? picked.current_cls}`)} ·{" "}
                {t(`dstatus.${picked.status}`)}
              </p>
              <p>
                {t("live.at", { yd: picked.center_yd.toFixed(2) })} · {t("live.size", { len: picked.length_in.toFixed(2) })}
                {picked.points !== null && picked.points !== undefined && ` · ${t("live.pts", { n: picked.points })}`}
              </p>
              <p className="text-slate-600">{picked.points_reason ?? picked.excluded_reason}</p>
              <p className="text-xs text-slate-500">{picked.explanation}</p>
              <button type="button" onClick={() => setPicked(null)} className="text-xs text-brand-blue hover:underline">
                {t("verdict.close")}
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <h2 className="px-4 pt-3 font-semibold">
          {t("verdict.defects")} ({real.length})
        </h2>
        <table className="min-w-full text-sm" data-testid="defects-table">
          <thead className="text-left text-slate-600">
            <tr>
              <th className="px-3 py-2">{t("verdict.no")}</th>
              <th className="px-3 py-2">{t("verdict.type")}</th>
              <th className="px-3 py-2">{t("verdict.at")}</th>
              <th className="px-3 py-2">{t("verdict.size")}</th>
              <th className="px-3 py-2">{t("verdict.status")}</th>
              <th className="px-3 py-2">{t("verdict.points")}</th>
              <th className="px-3 py-2">{t("verdict.reasonCol")}</th>
            </tr>
          </thead>
          <tbody>
            {real.map((d) => (
              <tr key={d.id} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => setPicked(d)}>
                <td className="px-3 py-1.5 font-mono">{d.defect_no}</td>
                <td className="px-3 py-1.5">{t(`cls.${d.current_cls}`)}</td>
                <td className="px-3 py-1.5 font-mono">{d.center_yd.toFixed(2)}</td>
                <td className="px-3 py-1.5 font-mono">{d.length_in.toFixed(2)}</td>
                <td className="px-3 py-1.5">
                  {t(`dstatus.${d.status}`)}
                  {d.reject_reason && ` (${t(`reasons.${d.reject_reason}`)})`}
                </td>
                <td className="px-3 py-1.5 font-mono">{d.status === "rejected" ? "–" : d.points ?? "–"}</td>
                <td className="px-3 py-1.5 text-xs text-slate-600">{d.excluded_reason && d.status !== "confirmed" ? d.excluded_reason : d.points_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {ignored.length > 0 && (
          <p className="px-4 py-3 text-sm text-slate-600">
            {t("live.nondefects")}:{" "}
            {Object.entries(ignoredCounts)
              .map(([k, n]) => `${t(`cls.${k}`)} ${n}`)
              .join(" · ")}
          </p>
        )}
      </section>
    </div>
  );
}
