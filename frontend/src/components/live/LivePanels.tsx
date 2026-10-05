"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { Lightbox, largePhoto } from "@/components/Lightbox";
import { DEFECT_CLASSES, REJECT_REASONS, type Defect, type ScoreSummary, type Track } from "@/lib/api/client";

/** Vertical yard tape beside the video: the part of the roll in view, with defects marked. */
export function YardTape({ track, frame, defects }: { track: Track; frame: number; defects: Defect[] }) {
  const top = track.top_yd[frame] ?? 0;
  const bottom = track.bottom_yd[frame] ?? 0;
  const span = Math.max(bottom - top, 0.01);
  const ticks: number[] = [];
  for (let v = Math.ceil(top * 10) / 10; v <= bottom + 1e-9; v += 0.1) ticks.push(Math.round(v * 10) / 10);
  const pos = (yd: number) => `${((yd - top) / span) * 100}%`;
  return (
    <div className="relative w-14 shrink-0 rounded-md border border-slate-300 bg-amber-50" aria-label="yard tape">
      {ticks.map((v) => {
        const major = Math.abs(v * 2 - Math.round(v * 2)) < 1e-6;
        return (
          <div key={v} className="absolute left-0 right-0" style={{ top: pos(v) }}>
            <div className={`h-px ${major ? "w-6 bg-slate-800" : "w-3 bg-slate-500"}`} />
            {major && <span className="absolute left-7 -top-2 font-mono text-[11px] text-slate-800">{v.toFixed(1)}</span>}
          </div>
        );
      })}
      {defects
        .filter((d) => d.kind === "defect" && d.center_yd >= top && d.center_yd <= bottom)
        .map((d) => (
          <div
            key={d.id}
            className={`absolute right-0.5 h-2 w-2 rounded-full ${
              d.status === "confirmed" ? "bg-green-600" : d.status === "rejected" ? "bg-slate-400" : "bg-red-600"
            }`}
            style={{ top: pos(d.center_yd) }}
            title={d.defect_no}
          />
        ))}
    </div>
  );
}

/** Points so far against the roll's budget, and the running per-100 against the buyer's limit. */
export function PointsMeter({ score }: { score: ScoreSummary | null }) {
  const t = useTranslations("live");
  if (!score) return null;
  const pts = score.provisional_points;
  const budget = score.points_budget ?? 0;
  const p100 = score.per_100_provisional;
  const showColour = score.yards_inspected >= 5 && p100 !== null && p100 !== undefined;
  const tone = !showColour
    ? "bg-slate-500"
    : p100 <= score.threshold - score.borderline_below
      ? "bg-green-600"
      : p100 <= score.threshold + score.borderline_above
        ? "bg-amber-500"
        : "bg-red-600";
  const fill = budget ? Math.min(100, (pts / budget) * 100) : 0;
  return (
    <section className="space-y-2 rounded-lg border border-slate-200 bg-white p-3" data-testid="points-meter">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-slate-600">{t("points")}</span>
        <span className="font-mono text-3xl font-bold" data-testid="points-total">
          {pts}
        </span>
      </div>
      {budget > 0 && (
        <>
          <div className="h-3 overflow-hidden rounded-full bg-slate-200">
            <div className={`h-full ${tone}`} style={{ width: `${fill}%` }} />
          </div>
          <p className="text-right text-xs text-slate-500">{t("budget", { budget: budget.toFixed(1) })}</p>
        </>
      )}
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-slate-600">{t("per100")}</span>
        <span className={`rounded px-2 py-0.5 font-mono text-lg font-bold text-white ${tone}`}>
          {p100 === null || p100 === undefined ? "–" : p100.toFixed(2)}
        </span>
      </div>
      <p className="text-xs text-slate-500">
        {t("threshold", { t: score.threshold })} · {t("coverage", { pct: score.coverage_pct })}
        {!showColour && ` · ${t("colourAfter")}`}
      </p>
    </section>
  );
}

type DecideFn = (d: Defect, action: string, body?: Record<string, unknown>) => Promise<void>;

/** One defect in the queue: photo, type, position, size, points, why, and the inspector's buttons. */
export function DefectCard({
  d,
  selected,
  onSelect,
  decide,
  canDecide,
  rejectOpen,
  setRejectOpen,
  reclassOpen,
  setReclassOpen,
  saving = false,
}: {
  d: Defect;
  selected: boolean;
  onSelect: () => void;
  decide: DecideFn;
  canDecide: boolean;
  rejectOpen: boolean;
  setRejectOpen: (open: boolean) => void;
  reclassOpen: boolean;
  setReclassOpen: (open: boolean) => void;
  saving?: boolean;
}) {
  const t = useTranslations();
  const [imgFailed, setImgFailed] = useState(false);
  const [zoom, setZoom] = useState(false);
  const border =
    d.status === "confirmed" ? "border-green-600" : d.status === "rejected" ? "border-slate-300" : "border-red-600";
  return (
    <li
      className={`flex gap-3 rounded-lg border-2 bg-white p-2 ${border} ${selected ? "ring-2 ring-brand-teal" : ""}`}
      onClick={onSelect}
      data-testid={`defect-${d.defect_no}`}
      data-status={d.status}
    >
      <div className="h-20 w-20 shrink-0 overflow-hidden rounded bg-slate-100">
        {d.crop_url && !imgFailed ? (
          <button
            type="button"
            className="h-full w-full cursor-zoom-in"
            title={t("live.zoom")}
            onClick={(e) => {
              e.stopPropagation();
              setZoom(true);
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${d.crop_url}?v=${d.best_frame}`}
              alt={d.defect_no}
              className="h-full w-full object-cover"
              onError={() => setImgFailed(true)}
            />
          </button>
        ) : (
          <span className="flex h-full items-center justify-center p-1 text-center text-[10px] text-slate-400">
            {t("live.noPhoto")}
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-mono text-xs text-slate-500">{d.defect_no}</span>
          <span className="font-semibold">{t(`cls.${d.current_cls}`)}</span>
          <span className="text-xs text-slate-500">({t(`dstatus.${d.status}`)})</span>
        </div>
        <p className="text-sm text-slate-700">
          {t("live.at", { yd: d.center_yd.toFixed(2) })} · {t("live.size", { len: d.length_in.toFixed(2) })} ·{" "}
          <span className="font-semibold">
            {d.points !== null && d.points !== undefined ? t("live.pts", { n: d.points }) : t("live.noPoints")}
          </span>
        </p>
        {d.excluded_reason && d.status !== "rejected" && (
          <p className="text-xs font-semibold text-amber-800">
            {d.excluded_reason.includes("selvage") ? t("live.selvageRule") : d.excluded_reason}
          </p>
        )}
        {d.origin === "manual" && <p className="text-xs text-teal-700">{t("live.manual")}</p>}
        {d.uncertain === "hand_in_view" && <p className="text-xs font-semibold text-amber-700">{t("live.uncertainHand")}</p>}
        <p className="truncate text-[11px] text-slate-500" title={d.explanation ?? ""}>
          {d.explanation}
        </p>
        {saving && <p className="text-xs font-semibold text-slate-500">{t("live.saving")}</p>}
        {canDecide && !saving && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {d.status === "pending" ? (
              <>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    void decide(d, "confirm", {});
                  }}
                  className="rounded-md bg-green-700 px-3 py-1.5 text-sm font-bold text-white hover:bg-green-800"
                  data-testid="confirm"
                >
                  {t("live.confirm")}
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setRejectOpen(!rejectOpen);
                  }}
                  className="rounded-md bg-slate-700 px-3 py-1.5 text-sm font-bold text-white hover:bg-slate-800"
                  data-testid="reject"
                >
                  {t("live.reject")}
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setReclassOpen(!reclassOpen);
                  }}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
                >
                  {t("live.reclass")}
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  void decide(d, "reopen");
                }}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
              >
                {t("live.undo")}
              </button>
            )}
          </div>
        )}
        {rejectOpen && (
          <div className="flex flex-wrap gap-1 rounded bg-slate-50 p-1.5" onClick={(e) => e.stopPropagation()}>
            <span className="w-full text-xs text-slate-600">{t("live.rejectWhy")}</span>
            {REJECT_REASONS.map((r, i) => (
              <button
                key={r}
                type="button"
                onClick={() => {
                  setRejectOpen(false);
                  void decide(d, "reject", { reason_category: r });
                }}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-100"
              >
                <span className="font-mono text-slate-400">{i + 1}</span> {t(`reasons.${r}`)}
              </button>
            ))}
          </div>
        )}
        {zoom && d.crop_url && (
          <Lightbox src={largePhoto(`${d.crop_url}?v=${d.best_frame}`)} alt={d.defect_no} onClose={() => setZoom(false)}>
            <p className="font-semibold">
              {d.defect_no} · {t(`cls.${d.current_cls}`)} ({t(`dstatus.${d.status}`)})
            </p>
            <p className="text-slate-600">
              {t("live.at", { yd: d.center_yd.toFixed(2) })} · {t("live.size", { len: d.length_in.toFixed(2) })}
              {d.points !== null && d.points !== undefined && ` · ${t("live.pts", { n: d.points })}`}
            </p>
            <p className="text-xs text-slate-500">{d.explanation}</p>
          </Lightbox>
        )}
        {reclassOpen && (
          <select
            autoFocus
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            defaultValue=""
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => {
              setReclassOpen(false);
              if (e.target.value) void decide(d, "reclassify", { to_cls: e.target.value });
            }}
          >
            <option value="" disabled>
              {t("live.changeTo")}
            </option>
            {DEFECT_CLASSES.filter((c) => c !== d.current_cls).map((c) => (
              <option key={c} value={c}>
                {t(`cls.${c}`)}
              </option>
            ))}
          </select>
        )}
      </div>
    </li>
  );
}
