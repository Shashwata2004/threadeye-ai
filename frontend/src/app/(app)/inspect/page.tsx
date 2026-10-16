"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, Field, inputClass } from "@/components/form";
import { api, hasPerm, type InspectionListItem } from "@/lib/api/client";
import { errorDetail, useDatasets, useInspections, useMachines, useMe } from "@/lib/api/hooks";

function InspectionList({ items, title }: { items: InspectionListItem[]; title: string }) {
  const t = useTranslations();
  return (
    // Stitched panel; rules are inset (mx-2) so they stop at the stitch line instead of crossing it.
    <section className="te-stitched rounded-lg py-1">
      <h2 className="te-serif mx-2 border-b border-(--te-line)/70 px-2 py-2 text-lg font-semibold text-(--te-ink)">{title}</h2>
      {!items.length ? (
        <p className="p-4 text-sm text-(--te-faint)">{t("inspect.none")}</p>
      ) : (
        <ul className="mx-2 divide-y divide-(--te-line-soft)/60">
          {items.map((i) => {
            const live = ["created", "running", "paused", "interrupted"].includes(i.status);
            return (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-2 py-2 text-sm text-(--te-ink)">
                <span>
                  <span className="font-mono font-semibold">{i.roll_code}</span> · {t(`istatus.${i.status}`)}
                  {i.system_verdict && ` · ${t(`verdicts.${i.system_verdict}`)}`}
                  {i.inspector && <span className="text-(--te-faint)"> · {i.inspector}</span>}
                </span>
                <Link
                  href={live ? `/inspect/${i.id}` : `/inspections/${i.id}`}
                  className="font-semibold text-brand-navy underline decoration-(--te-accent)/60 underline-offset-2 hover:decoration-brand-navy"
                >
                  {live ? t("inspect.continue") : t("inspect.view")}
                </Link>
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

  // Defaults: the first machine, and the first roll that has a video.
  const machineId = machineChoice || machines?.[0]?.id || "";
  const datasetId = datasetChoice || (datasets?.find((d) => d.has_video) ?? datasets?.[0])?.id || "";

  async function load(e: FormEvent) {
    e.preventDefault();
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
    // The background sketch sits in the bottom-right corner of the page, below the last box: the
    // page is at least screen height and keeps room for it at the bottom. It never takes clicks.
    <div className="relative z-[1] space-y-5 md:min-h-[calc(100vh-9rem)] md:pb-52">
      <div
        aria-hidden="true"
        className="te-sketch-magnifier pointer-events-none absolute bottom-0 right-0 -z-10 hidden h-52 w-[320px] bg-contain bg-right-bottom bg-no-repeat opacity-30 md:block"
      />
      <div>
        <h1 className="te-serif text-2xl font-bold text-(--te-ink)">{t("inspect.title")}</h1>
        <p className="te-serif text-(--te-ink-soft)">{t("inspect.subtitle")}</p>
      </div>

      {canRun ? (
        <form onSubmit={load} className="te-rope max-w-3xl">
        <div className="te-rope-inner grid gap-4 p-4 sm:grid-cols-2">
          <Field label={t("inspect.rollCode")} wide>
            <input
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
            <Button
              type="submit"
              disabled={busy || !datasetId || !machineId}
              data-testid="load-roll"
              className="shadow-md shadow-(--te-shadow)/20"
            >
              {busy ? t("inspect.loadingRoll") : t("inspect.load")}
            </Button>
          </div>
        </div>
        </form>
      ) : (
        <p className="text-sm text-(--te-muted)">{t("inspect.readOnly")}</p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <InspectionList items={open ?? []} title={t("inspect.open")} />
        <InspectionList items={recent ?? []} title={t("inspect.recent")} />
      </div>
    </div>
  );
}
