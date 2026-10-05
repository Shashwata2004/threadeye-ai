"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ClipboardEvent } from "react";
import { SampleBadge } from "@/components/badges";
import { Button, inputClass } from "@/components/form";
import { api, hasPerm } from "@/lib/api/client";
import { errorDetail, useInspections, useLot, useLotRolls, useMe, useSampling } from "@/lib/api/hooks";

type Row = { mill_roll_no: string; declared_length_yd: string; declared_width_in: string; dye_lot: string };
const blank = (): Row => ({ mill_roll_no: "", declared_length_yd: "", declared_width_in: "", dye_lot: "" });

function AddRolls({ lotId, onSaved }: { lotId: string; onSaved: () => void }) {
  const t = useTranslations("lots");
  const [rows, setRows] = useState<Row[]>([blank(), blank(), blank()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const update = (i: number, k: keyof Row, v: string) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  // Paste from Excel/Sheets: tab-separated columns, one roll per line.
  function onPaste(e: ClipboardEvent<HTMLInputElement>, start: number) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const parsed = text
      .trim()
      .split(/\r?\n/)
      .map((line) => line.split("\t"))
      .map(([no = "", yd = "", w = "", dl = ""]) => ({
        mill_roll_no: no.trim(),
        declared_length_yd: yd.trim(),
        declared_width_in: w.trim(),
        dye_lot: dl.trim(),
      }));
    setRows((rs) => [...rs.slice(0, start), ...parsed, ...rs.slice(start + parsed.length)]);
  }

  async function save() {
    const filled = rows.filter((r) => r.mill_roll_no.trim());
    if (!filled.length) return;
    setBusy(true);
    setError(null);
    const { data, error: err } = await api.POST("/api/v1/lots/{lot_id}/rolls", {
      params: { path: { lot_id: lotId } },
      body: {
        rolls: filled.map((r) => ({
          mill_roll_no: r.mill_roll_no.trim(),
          declared_length_yd: Number(r.declared_length_yd),
          declared_width_in: Number(r.declared_width_in),
          dye_lot: r.dye_lot.trim() || null,
        })),
      },
    });
    setBusy(false);
    if (!data) {
      setError(t("errorGeneric", { detail: errorDetail(err) }));
      return;
    }
    setRows([blank(), blank(), blank()]);
    onSaved();
  }

  return (
    <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">{t("addRolls")}</h2>
      <p className="text-xs text-slate-500">{t("pasteHint")}</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-slate-600">
            <tr>
              <th className="pr-2">{t("millRollNo")}</th>
              <th className="pr-2">{t("lengthYd")}</th>
              <th className="pr-2">{t("widthIn")}</th>
              <th className="pr-2">{t("dyeLot")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="pr-2">
                  <input
                    value={r.mill_roll_no}
                    onChange={(e) => update(i, "mill_roll_no", e.target.value)}
                    onPaste={(e) => onPaste(e, i)}
                    className={inputClass}
                  />
                </td>
                <td className="pr-2">
                  <input
                    type="number"
                    min={0.01}
                    step="0.01"
                    required={!!r.mill_roll_no}
                    value={r.declared_length_yd}
                    onChange={(e) => update(i, "declared_length_yd", e.target.value)}
                    className={inputClass}
                  />
                </td>
                <td className="pr-2">
                  <input
                    type="number"
                    min={0.01}
                    step="0.01"
                    required={!!r.mill_roll_no}
                    value={r.declared_width_in}
                    onChange={(e) => update(i, "declared_width_in", e.target.value)}
                    className={inputClass}
                  />
                </td>
                <td className="pr-2">
                  <input
                    value={r.dye_lot}
                    onChange={(e) => update(i, "dye_lot", e.target.value)}
                    className={inputClass}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                    className="text-xs text-slate-500 hover:text-red-700"
                  >
                    {t("removeRow")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <Button variant="secondary" onClick={() => setRows((rs) => [...rs, blank()])}>
          {t("addRow")}
        </Button>
        <Button onClick={save} disabled={busy}>
          {busy ? t("saving") : t("saveRolls")}
        </Button>
      </div>
    </section>
  );
}

export default function LotDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations();
  const format = useFormatter();
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const { data: lot, isLoading } = useLot(id);
  const { data: rolls } = useLotRolls(id);
  const { data: sampling } = useSampling(id);
  const { data: inspections } = useInspections({ limit: 500 });
  // Latest inspection per roll (the list is newest first).
  const latest = new Map<string, NonNullable<typeof inspections>[number]>();
  for (const i of inspections ?? []) if (!latest.has(i.roll_id)) latest.set(i.roll_id, i);

  const refresh = () =>
    Promise.all(
      [["lot", id], ["lot-rolls", id], ["lot-sampling", id], ["lots"]].map((queryKey) =>
        queryClient.invalidateQueries({ queryKey }),
      ),
    );

  function openPdf(url: string) {
    window.open(url, "_blank", "noopener");
    setTimeout(refresh, 1500); // label_printed_at is set when the PDF is generated
  }

  if (isLoading) return <p className="text-slate-500">{t("common.loading")}</p>;
  if (!lot) return <p className="text-red-700">{t("common.error")}</p>;

  const canWriteRolls = hasPerm(me, "rolls.write");
  const canPrint = hasPerm(me, "labels.print");

  return (
    <div className="space-y-5">
      <Link href="/lots" className="text-sm text-brand-blue hover:underline">
        {t("lots.back")}
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">
            {lot.challan_no} {lot.is_sample_data && <SampleBadge />}
          </h1>
          <p className="text-slate-600">
            {lot.supplier.name} → {lot.buyer.name} · {lot.fabric_type}
            {lot.colour ? ` · ${lot.colour}` : ""}
          </p>
          <p className="text-sm text-slate-500">
            {format.dateTime(new Date(lot.received_at), { dateStyle: "long" })} ·{" "}
            {t("lots.registeredOf", { count: lot.rolls_registered, declared: lot.declared_rolls })}
            {lot.rule_profile &&
              ` · ${t("lots.thresholdShort", { name: lot.rule_profile.name, threshold: lot.rule_profile.threshold_per_100 })}`}
          </p>
        </div>
        {canPrint && (rolls?.length ?? 0) > 0 && (
          <Button onClick={() => openPdf(`/api/v1/lots/${lot.id}/labels.pdf`)}>{t("lots.printAll")}</Button>
        )}
      </div>

      {sampling && (
        <section className="rounded-lg border border-teal-200 bg-teal-50 p-4" data-testid="sampling">
          <h2 className="font-semibold text-teal-900">{t("lots.sampling")}</h2>
          <p className="text-teal-900">
            {t("lots.samplingText", {
              count: sampling.suggested_count,
              total: sampling.total_rolls,
              pct: sampling.sampling_pct,
            })}
          </p>
          <p className="text-xs text-teal-800">{t("lots.millHistory", { count: sampling.mill_recent_rolls })}</p>
        </section>
      )}

      <section className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        {!rolls?.length ? (
          <p className="p-4 text-slate-500">{t("lots.noRolls")}</p>
        ) : (
          <table className="min-w-full text-sm" data-testid="rolls-table">
            <thead className="bg-slate-100 text-left text-slate-700">
              <tr>
                <th className="px-3 py-2">{t("lots.rollCode")}</th>
                <th className="px-3 py-2">{t("lots.millRollNo")}</th>
                <th className="px-3 py-2">{t("lots.lengthYd")}</th>
                <th className="px-3 py-2">{t("lots.widthIn")}</th>
                <th className="px-3 py-2">{t("lots.dyeLot")}</th>
                <th className="px-3 py-2">{t("lots.status")}</th>
                <th className="px-3 py-2">{t("lots.label")}</th>
                <th className="px-3 py-2">{t("lots.inspection")}</th>
              </tr>
            </thead>
            <tbody>
              {rolls.map((r) => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-mono font-semibold">{r.roll_code}</td>
                  <td className="px-3 py-2">{r.mill_roll_no}</td>
                  <td className="px-3 py-2 font-mono">{r.declared_length_yd}</td>
                  <td className="px-3 py-2 font-mono">{r.declared_width_in}</td>
                  <td className="px-3 py-2">{r.dye_lot ?? t("common.dash")}</td>
                  <td className="px-3 py-2">{t(`status.${r.status}`)}</td>
                  <td className="px-3 py-2">
                    {canPrint ? (
                      <button
                        type="button"
                        onClick={() => openPdf(`/api/v1/rolls/${r.id}/label.pdf`)}
                        className="text-brand-blue hover:underline"
                      >
                        {t("lots.labelPrint")}
                      </button>
                    ) : null}
                    {r.label_printed_at && <span className="ml-2 text-xs text-teal-700">✓ {t("lots.labelPrinted")}</span>}
                  </td>
                  <td className="px-3 py-2">
                    {(() => {
                      const i = latest.get(r.id);
                      if (!i) return t("common.dash");
                      const open = ["created", "running", "paused", "interrupted"].includes(i.status);
                      return (
                        <Link
                          href={open ? `/inspect/${i.id}` : `/inspections/${i.id}`}
                          className="text-brand-blue hover:underline"
                        >
                          {i.system_verdict ? t(`verdicts.${i.system_verdict}`) : t(`istatus.${i.status}`)}
                          {i.points_per_100 !== null && i.points_per_100 !== undefined && ` · ${i.points_per_100.toFixed(2)}`}
                        </Link>
                      );
                    })()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {canWriteRolls && <AddRolls lotId={lot.id} onSaved={refresh} />}
    </div>
  );
}
