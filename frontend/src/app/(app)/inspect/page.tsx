"use client";

import { useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { Button, Field, inputClass } from "@/components/form";
import { api, hasPerm, idempotencyKey, type InspectionListItem } from "@/lib/api/client";
import { errorDetail, useDatasets, useInspections, useMachines, useMe } from "@/lib/api/hooks";
import { useBi } from "@/components/screenKit";

function InspectionList({ items, title, canRun, abortingId, disabled, onAbort }: {
  items: InspectionListItem[]; title: string; canRun: boolean; abortingId: string | null;
  disabled: boolean; onAbort: (item: InspectionListItem) => Promise<void>;
}) {
  const t = useTranslations();
  const bi = useBi();
  return (
    <section aria-label={title} className="rounded-lg border border-slate-200 bg-white">
      <h2 className="border-b border-slate-100 px-4 py-2 font-semibold">{title}</h2>
      {!items.length ? (
        <p className="p-4 text-sm text-slate-500">{t("inspect.none")}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {items.map((i) => {
            const live = ["created", "running", "paused", "interrupted"].includes(i.status);
            return (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
                <div className="min-w-0 space-y-1">
                <div>
                  <span className="font-mono font-semibold">{i.roll_code}</span> · {t(`istatus.${i.status}`)}
                  {i.system_verdict && ` · ${bi("System: ", "সিস্টেম: ")}${t(`verdicts.${i.system_verdict}`)}`}
                  {i.inspector && <span className="text-slate-500"> · {i.inspector}</span>}
                  {live && i.model_outdated && <span className="text-amber-700"> · {t("inspect.oldModel")}</span>}
                </div>
                {i.status === "completed" && <div className="flex flex-wrap gap-2 text-xs" data-testid={`inspection-progress-${i.id}`}>
                  <span className="rounded border border-slate-400/40 px-2 py-1">
                    {bi("QC decision: ", "QC সিদ্ধান্ত: ")}{i.final_verdict ? t(`verdicts.${i.final_verdict}`) : bi("Pending", "অপেক্ষমাণ")}
                  </span>
                  <span className="rounded border border-slate-400/40 px-2 py-1">
                    {bi("Cutting instructions: ", "কাটিং নির্দেশনা: ")}{i.cutting_status === "approved" || i.cutting_status === "acknowledged" ?
                      bi("Approved", "অনুমোদিত") : i.cutting_status === "not_ready" ? bi("Inspection not finalized", "পরিদর্শন চূড়ান্ত হয়নি") :
                      i.cutting_status === "draft" ? bi("Draft, awaiting approval", "খসড়া, অনুমোদন হয়নি") :
                      bi("Not issued", "দেওয়া হয়নি")}
                  </span>
                  <span className="rounded border border-slate-400/40 px-2 py-1">
                    {bi("Cutting master receipt: ", "কাটিং মাস্টারের গ্রহণ: ")}{i.cutting_status === "acknowledged" ?
                      bi("Acknowledged", "নিশ্চিত করেছেন") : i.cutting_status === "approved" ? bi("Awaiting receipt", "অপেক্ষমাণ") :
                      bi("Instructions not yet approved", "নির্দেশনা এখনও অনুমোদিত নয়")}
                  </span>
                </div>}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Link
                    href={live ? `/inspect/${i.id}` : `/inspections/${i.id}`}
                    aria-disabled={abortingId === i.id || undefined}
                    onClick={(event) => { if (abortingId === i.id) event.preventDefault(); }}
                    className={`font-semibold text-brand-blue hover:underline ${abortingId === i.id ? "opacity-50" : ""}`}
                  >
                    {live ? t(i.model_outdated ? "inspect.restartNewModel" : "inspect.continue") : t("inspect.view")}
                  </Link>
                  {live && canRun && <button type="button" disabled={disabled}
                    onClick={() => void onAbort(i)}
                    className="rounded border border-red-500/40 px-2 py-1 font-semibold text-red-700 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50">
                    {t(abortingId === i.id ? "inspect.aborting" : "live.abort")}
                  </button>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function InspectPage() {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const rollCodeInput = useRef<HTMLInputElement>(null);
  const { data: me } = useMe();
  const canRun = hasPerm(me, "inspections.run");
  const { data: datasets } = useDatasets();
  const { data: machines } = useMachines();
  const { data: open } = useInspections({ open_only: true });
  const { data: recent } = useInspections({ limit: 10 });

  const [rollCode, setRollCode] = useState("");
  const [machineChoice, setMachineId] = useState("");
  const [datasetChoice, setDatasetId] = useState("");
  const [preset, setPreset] = useState<"realistic" | "perfect">("realistic");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [abortingId, setAbortingId] = useState<string | null>(null);
  const [abortError, setAbortError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function abortInspection(item: InspectionListItem) {
    if (!canRun || busy || abortingId || !window.confirm(t("inspect.abortConfirm", {roll: item.roll_code}))) return;
    setAbortingId(item.id);
    setAbortError(null);
    setNotice(null);
    try {
      const {error: err, response} = await api.POST("/api/v1/inspections/{inspection_id}/abort", {
        params: {path: {inspection_id: item.id}}, headers: {"Idempotency-Key": idempotencyKey()},
      });
      if (!response.ok) {
        setAbortError(t("inspect.abortError", {detail: errorDetail(err, response.status)}));
        return;
      }
      setError(null);
      setRollCode(item.roll_code);
      setNotice(t("inspect.abortedNotice", {roll: item.roll_code}));
      await Promise.all([
        queryClient.invalidateQueries({queryKey: ["inspections"]}),
        queryClient.invalidateQueries({queryKey: ["inspection", item.id]}),
        queryClient.invalidateQueries({queryKey: ["lot-rolls"]}),
        queryClient.invalidateQueries({queryKey: ["dashboard"]}),
      ]);
      rollCodeInput.current?.focus();
      rollCodeInput.current?.select();
    } catch {
      setAbortError(t("inspect.abortNetworkError"));
    } finally {
      setAbortingId(null);
    }
  }

  // Defaults: the first machine, and the first roll that has a video.
  const machineId = machineChoice || machines?.[0]?.id || "";
  const datasetId = datasetChoice || (datasets?.find((d) => d.has_video) ?? datasets?.[0])?.id || "";

  async function load(e: FormEvent) {
    e.preventDefault();
    if (busy || abortingId) return;
    setBusy(true);
    setError(null);
    const { data, error: err, response } = await api.POST("/api/v1/inspections", {
      body: {
        roll_code: rollCode.trim().toUpperCase(),
        machine_id: machineId,
        source: { kind: "video_file", dataset_id: datasetId },
        preset,
      },
    });
    setBusy(false);
    if (data) {
      router.push(`/inspect/${data.id}`);
      return;
    }
    const detail = (err as { detail?: { inspection_id?: string } } | undefined)?.detail;
    if (response.status === 409 && detail && typeof detail === "object" && detail.inspection_id) {
      router.push(`/inspect/${detail.inspection_id}`);
      return;
    }
    setError(t("inspect.error", { detail: errorDetail(err, response.status) }));
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t("inspect.title")}</h1>
        <p className="text-slate-600">{t("inspect.subtitle")}</p>
      </div>

      {canRun ? (
        <form onSubmit={load} className="grid max-w-3xl gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2">
          <Field label={t("inspect.rollCode")} wide>
            <input
              ref={rollCodeInput}
              autoFocus
              required
              value={rollCode}
              onChange={(e) => setRollCode(e.target.value)}
              placeholder="TE-000001"
              className={`${inputClass} font-mono text-lg uppercase`}
              data-testid="roll-code"
            />
          </Field>
          <Field label={t("inspect.machine")}>
            <select required value={machineId} onChange={(e) => setMachineId(e.target.value)} className={inputClass}>
              {machines?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.code} · {m.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("inspect.source")}>
            <select
              required
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              className={inputClass}
              data-testid="dataset"
            >
              {datasets?.map((d) => (
                <option key={d.id} value={d.id}>
                  {t("inspect.sourceOption", { id: d.id, yd: d.roll_length_yd })}
                  {!d.has_video && ` ${t("inspect.noVideoTag")}`}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs font-semibold text-amber-800">{t("inspect.sourceHint")}</span>
          </Field>
          <Field label={t("inspect.preset")} wide>
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value as "realistic" | "perfect")}
              className={inputClass}
              data-testid="preset"
            >
              <option value="realistic">{t("inspect.presetRealistic")}</option>
              <option value="perfect">{t("inspect.presetPerfect")}</option>
            </select>
          </Field>
          {datasets && !datasets.length && <p className="text-sm text-red-700 sm:col-span-2">{t("inspect.noDatasets")}</p>}
          {error && (
            <p role="alert" className="text-sm text-red-700 sm:col-span-2">
              {error}
            </p>
          )}
          <div className="sm:col-span-2">
            <Button type="submit" disabled={busy || !!abortingId || !datasetId || !machineId} data-testid="load-roll">
              {busy ? t("inspect.loadingRoll") : t("inspect.load")}
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-slate-600">{t("inspect.readOnly")}</p>
      )}

      {abortError && <p role="alert" className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-700">{abortError}</p>}
      {notice && <p role="status" className="rounded border border-teal-500/40 bg-teal-500/10 p-3 text-sm text-teal-700">{notice}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <InspectionList items={open ?? []} title={t("inspect.open")} canRun={canRun}
          abortingId={abortingId} disabled={busy || !!abortingId} onAbort={abortInspection}/>
        <InspectionList items={recent ?? []} title={t("inspect.recent")} canRun={canRun}
          abortingId={abortingId} disabled={busy || !!abortingId} onAbort={abortInspection}/>
      </div>
    </div>
  );
}
