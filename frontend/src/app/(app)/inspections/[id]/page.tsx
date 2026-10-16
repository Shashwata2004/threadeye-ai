"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ProviderBadge } from "@/components/badges";
import { Button, inputClass } from "@/components/form";
import { Lightbox, largePhoto } from "@/components/Lightbox";
import { api, hasPerm, idempotencyKey, type Defect, type Inspection } from "@/lib/api/client";
import { errorDetail, useDefects, useInspection, useMe } from "@/lib/api/hooks";

const VERDICT_STYLE: Record<string, string> = {
  PASS: "bg-green-700 text-white",
  BORDERLINE: "bg-amber-500 text-amber-950",
  FAIL: "bg-red-700 text-white",
};

const GALLERY_BORDER: Record<string, string> = {
  confirmed: "border-green-500",
  pending: "border-red-500",
  rejected: "border-slate-300 opacity-70",
};
function DecisionPanel({ id, insp }: { id: string; insp: Inspection }) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const systemVerdict = insp.system_verdict ?? "";
  const [choice, setChoice] = useState<string>(insp.final_verdict ?? (systemVerdict === "PASS" ? "ACCEPT" : "REJECT"));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const override = (systemVerdict === "PASS" && choice === "REJECT") || (systemVerdict === "FAIL" && choice === "ACCEPT");
  async function save() {
    setSaving(true);
    setSaved(false);
    setError(null);
    const { data, error: err, response } = await api.POST("/api/v1/inspections/{inspection_id}/decision", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
      body: { final_verdict: choice as "ACCEPT" | "ACCEPT_WITH_CLAIM" | "REJECT", reason: reason.trim() },
    });
    setSaving(false);
    if (data) {
      queryClient.setQueryData(["inspection", id], data);
      setSaved(true);
      setReason("");
    } else setError(errorDetail(err, response.status));
  }
  return (
    <section className="te-stitched space-y-2 rounded-lg p-4" data-testid="decision">
      <h2 className="te-serif text-lg font-semibold text-(--te-ink)">{t("verdict.decision")}</h2>
      {insp.final_verdict && (
        <p className="rounded bg-teal-50 px-3 py-2 text-sm text-teal-900" data-testid="decision-current">
          ✓{" "}
          {t("verdict.decidedBy", {
            decision: t(`verdicts.${insp.final_verdict}`),
            by: insp.decision_by ?? "",
            reason: insp.decision_reason ?? "",
          })}
          {saved && <span className="ml-2 font-semibold">{t("verdict.saved")}</span>}
        </p>
      )}
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
      <Button onClick={() => void save()} disabled={saving || reason.trim().length < 3}>
        {saving ? t("live.saving") : insp.final_verdict ? t("verdict.change") : t("verdict.decide")}
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
  const [zoomed, setZoomed] = useState<Defect | null>(null);

  if (!insp) return <p className="text-(--te-muted)">{t("common.loading")}</p>;

  const r = insp.roll;
  const real = defects.filter((d) => d.kind === "defect").sort((a, b) => a.center_yd - b.center_yd);
  const ignored = defects.filter((d) => d.kind === "nondefect");
  const cells = Object.entries(insp.score?.cells ?? {})
    .map(([k, v]) => [Number(k), v] as const)
    .sort((a, b) => a[0] - b[0]);
  const ignoredCounts = ignored.reduce<Record<string, number>>((acc, d) => {
    const k = d.nondefect_category ?? d.current_cls;
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="te-serif text-2xl font-bold text-(--te-ink)">{t("verdict.title")}</h1>
          <p className="te-serif text-(--te-ink-soft)">
            {t("verdict.roll", { code: r.roll_code, challan: r.challan_no, mill: r.supplier, buyer: r.buyer })}
          </p>
          <p className="text-sm text-(--te-faint)">
            {t("verdict.rules", { profile: r.rule_profile })}
            {insp.inspector && ` · ${t("verdict.inspector", { name: insp.inspector })}`}
          </p>
          <Link href={`/lots/${r.lot_id}`} className="text-sm text-brand-navy underline decoration-(--te-accent)/60 underline-offset-2 hover:decoration-brand-navy">
            {t("lots.back")}
          </Link>
        </div>
        <ProviderBadge
          name={`${insp.provider.display_name}${insp.provider.preset ? ` (${insp.provider.preset})` : ""}`}
          simulated={insp.provider.is_simulated}
        />
      </div>

      {insp.system_verdict ? (
        <section className="te-rope">
        <div className="te-rope-inner flex flex-wrap items-center gap-4 p-4">
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
            <p className="text-sm text-(--te-faint)">{t("verdict.yards", { yd: (insp.yards_inspected ?? 0).toFixed(2) })}</p>
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
            <span className="text-(--te-muted)">{t("verdict.report")}:</span>
            <a className="font-semibold text-brand-navy underline decoration-(--te-accent)/60 underline-offset-2 hover:decoration-brand-navy" href={`/api/v1/inspections/${id}/report.pdf?lang=en`} target="_blank" rel="noopener">
              {t("verdict.reportEn")}
            </a>
            <a className="font-semibold text-brand-navy underline decoration-(--te-accent)/60 underline-offset-2 hover:decoration-brand-navy" href={`/api/v1/inspections/${id}/report.pdf?lang=bn`} target="_blank" rel="noopener">
              {t("verdict.reportBn")}
            </a>
          </div>
        </div>
        </section>
      ) : (
        <section className="te-stitched rounded-lg p-4">
          <p className="te-serif text-lg text-amber-900">{t("verdict.notFinal")}</p>
          <Link href={`/inspect/${id}`} className="font-semibold text-brand-navy underline decoration-(--te-accent)/60 underline-offset-2 hover:decoration-brand-navy">
            {t("verdict.backToLive")}
          </Link>
        </section>
      )}

      {insp.system_verdict && hasPerm(me, "verdict.decide") && (
        <DecisionPanel id={id} insp={insp} />
      )}

      {cells.length > 0 && (
        <section className="te-stitched space-y-2 rounded-lg p-4">
          <h2 className="te-serif text-lg font-semibold text-(--te-ink)">{t("verdict.perYard")}</h2>
          <div className="flex flex-wrap gap-1">
            {cells.map(([yd, pts]) => (
              <div key={yd} className={`w-14 rounded border text-center ${pts >= 4 ? "border-red-400 bg-red-50" : "border-(--te-line) bg-(--te-linen)/60"}`}>
                <div className="text-[11px] text-(--te-faint)">{yd}</div>
                <div className="font-mono font-bold">{pts}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-(--te-faint)">{t("verdict.capNote")}</p>
        </section>
      )}

      <section className="te-stitched space-y-2 rounded-lg p-4">
        <h2 className="te-serif text-lg font-semibold text-(--te-ink)">
          {t("verdict.photos")} ({real.length})
        </h2>
        <p className="text-xs text-(--te-faint)">{t("verdict.photosHint")}</p>
        {zoomed?.crop_url && (
          <Lightbox src={largePhoto(zoomed.crop_url)} alt={zoomed.defect_no} onClose={() => setZoomed(null)}>
            <p className="font-semibold">
              {zoomed.defect_no} · {t(`cls.${zoomed.current_cls}`)} ({t(`dstatus.${zoomed.status}`)})
            </p>
            <p className="text-slate-600">
              {t("live.at", { yd: zoomed.center_yd.toFixed(2) })} · {t("live.size", { len: zoomed.length_in.toFixed(2) })}
              {zoomed.status !== "rejected" && zoomed.points !== null && zoomed.points !== undefined &&
                ` · ${t("live.pts", { n: zoomed.points })}`}
            </p>
            <p className="text-slate-600">{zoomed.points_reason ?? zoomed.excluded_reason}</p>
            <p className="text-xs text-slate-500">{zoomed.explanation}</p>
          </Lightbox>
        )}
        <div className="grid grid-cols-2 gap-2 pt-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-7" data-testid="defect-gallery">
          {real.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => {
                setPicked(d);
                if (d.crop_url) setZoomed(d);
              }}
              className={`overflow-hidden rounded-lg border-2 bg-white text-left shadow-sm shadow-(--te-shadow)/15 ${
                picked?.id === d.id ? "border-yellow-400 ring-2 ring-yellow-300" : GALLERY_BORDER[d.status] ?? "border-slate-200"
              }`}
            >
              <div className="aspect-square w-full bg-slate-100">
                {d.crop_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={d.crop_url} alt={d.defect_no} className="h-full w-full object-cover" loading="lazy" />
                ) : (
                  <span className="flex h-full items-center justify-center text-xs text-slate-400">{t("live.noPhoto")}</span>
                )}
              </div>
              <div className="space-y-0.5 p-1.5 text-xs">
                <p className="font-semibold">
                  <span className="font-mono text-(--te-faint)">{d.defect_no}</span> {t(`cls.${d.current_cls}`)}
                </p>
                <p className="text-(--te-muted)">
                  {t("live.at", { yd: d.center_yd.toFixed(2) })} · {t("live.size", { len: d.length_in.toFixed(2) })}
                </p>
                <p>
                  {t(`dstatus.${d.status}`)}
                  {d.status !== "rejected" && d.points !== null && d.points !== undefined && ` · ${t("live.pts", { n: d.points })}`}
                </p>
              </div>
            </button>
          ))}
        </div>
        {picked && (
          <div className="flex gap-3 rounded border border-(--te-line-soft) bg-(--te-linen)/60 p-3 text-sm">
            {picked.crop_url && (
              <button type="button" className="cursor-zoom-in" title={t("live.zoom")} onClick={() => setZoomed(picked)}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={picked.crop_url} alt={picked.defect_no} className="h-32 w-32 rounded object-cover" />
              </button>
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
              <p className="text-(--te-muted)">{picked.points_reason ?? picked.excluded_reason}</p>
              <p className="text-xs text-(--te-faint)">{picked.explanation}</p>
              <button type="button" onClick={() => setPicked(null)} className="text-xs text-brand-navy underline decoration-(--te-accent)/60 underline-offset-2 hover:decoration-brand-navy">
                {t("verdict.close")}
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="te-rope">
        <div className="te-rope-inner">
        <div className="overflow-x-auto">
        <h2 className="te-serif text-lg font-semibold text-(--te-ink) px-4 pb-2 pt-3">
          {t("verdict.defects")} ({real.length})
        </h2>
        <table className="min-w-full text-sm text-(--te-ink)" data-testid="defects-table">
          <thead className="border-y border-(--te-line)/70 bg-(--te-head)/60 text-left text-(--te-ink-soft)">
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
              <tr key={d.id} className="cursor-pointer border-t border-(--te-line-soft)/60 first:border-t-0 hover:bg-(--te-head)/40" onClick={() => setPicked(d)}>
                <td className="px-3 py-1.5 font-mono">{d.defect_no}</td>
                <td className="px-3 py-1.5">{t(`cls.${d.current_cls}`)}</td>
                <td className="px-3 py-1.5 font-mono">{d.center_yd.toFixed(2)}</td>
                <td className="px-3 py-1.5 font-mono">{d.length_in.toFixed(2)}</td>
                <td className="px-3 py-1.5">
                  {t(`dstatus.${d.status}`)}
                  {d.reject_reason && ` (${t(`reasons.${d.reject_reason}`)})`}
                </td>
                <td className="px-3 py-1.5 font-mono">{d.status === "rejected" ? "–" : d.points ?? "–"}</td>
                <td className="px-3 py-1.5 text-xs text-(--te-muted)">{d.excluded_reason && d.status !== "confirmed" ? d.excluded_reason : d.points_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {ignored.length > 0 && (
          <p className="px-4 py-3 text-sm text-(--te-muted)">
            {t("live.nondefects")}:{" "}
            {Object.entries(ignoredCounts)
              .map(([k, n]) => `${t(`cls.${k}`)} ${n}`)
              .join(" · ")}
          </p>
        )}
        </div>
        </div>
      </section>
    </div>
  );
}
