"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { SampleBadge } from "@/components/badges";
import { Button, Field, inputClass } from "@/components/form";
import { api, hasPerm } from "@/lib/api/client";
import { errorDetail, useLots, useMasterData, useMe } from "@/lib/api/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function NewLotForm({ onDone }: { onDone: () => void }) {
  const t = useTranslations("lots");
  const router = useRouter();
  const queryClient = useQueryClient();
  const { suppliers, buyers, profiles } = useMasterData();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    challan_no: "",
    supplier_id: "",
    buyer_id: "",
    order_ref: "",
    fabric_type: "",
    colour: "",
    received_at: today(),
    declared_rolls: "",
    declared_total_yd: "",
    rule_profile_id: "",
  });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error: err } = await api.POST("/api/v1/lots", {
      body: {
        challan_no: form.challan_no,
        supplier_id: form.supplier_id,
        buyer_id: form.buyer_id,
        order_ref: form.order_ref || null,
        fabric_type: form.fabric_type,
        colour: form.colour || null,
        received_at: form.received_at,
        declared_rolls: Number(form.declared_rolls),
        declared_total_yd: form.declared_total_yd ? Number(form.declared_total_yd) : null,
        rule_profile_id: form.rule_profile_id || null,
      },
    });
    setBusy(false);
    if (!data) {
      setError(t("errorGeneric", { detail: errorDetail(err) }));
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["lots"] });
    onDone();
    router.push(`/lots/${data.id}`);
  }

  return (
    <form onSubmit={submit} className="grid gap-4 rounded-lg border border-slate-200 bg-white p-5 sm:grid-cols-2">
      <Field label={t("challan")}>
        <input required maxLength={64} value={form.challan_no} onChange={set("challan_no")} className={inputClass} />
      </Field>
      <Field label={t("received")}>
        <input type="date" required value={form.received_at} onChange={set("received_at")} className={inputClass} />
      </Field>
      <Field label={t("mill")}>
        <select required value={form.supplier_id} onChange={set("supplier_id")} className={inputClass}>
          <option value="">{t("choose")}</option>
          {suppliers.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("buyer")}>
        <select required value={form.buyer_id} onChange={set("buyer_id")} className={inputClass}>
          <option value="">{t("choose")}</option>
          {buyers.data?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("fabric")}>
        <input required maxLength={128} value={form.fabric_type} onChange={set("fabric_type")} className={inputClass} />
      </Field>
      <Field label={t("colour")}>
        <input maxLength={64} value={form.colour} onChange={set("colour")} className={inputClass} />
      </Field>
      <Field label={t("declaredRolls")}>
        <input
          type="number"
          required
          min={1}
          max={10000}
          value={form.declared_rolls}
          onChange={set("declared_rolls")}
          className={inputClass}
        />
      </Field>
      <Field label={t("declaredYd")}>
        <input
          type="number"
          min={0}
          step="0.01"
          value={form.declared_total_yd}
          onChange={set("declared_total_yd")}
          className={inputClass}
        />
      </Field>
      <Field label={t("orderRef")}>
        <input maxLength={64} value={form.order_ref} onChange={set("order_ref")} className={inputClass} />
      </Field>
      <Field label={t("profile")}>
        <select value={form.rule_profile_id} onChange={set("rule_profile_id")} className={inputClass}>
          <option value="">{t("profileAuto")}</option>
          {profiles.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {t("thresholdShort", { name: p.name, threshold: p.threshold_per_100 })}
            </option>
          ))}
        </select>
      </Field>
      {error && (
        <p role="alert" className="text-sm text-red-700 sm:col-span-2">
          {error}
        </p>
      )}
      <div className="flex gap-3 sm:col-span-2">
        <Button type="submit" disabled={busy}>
          {busy ? t("saving") : t("save")}
        </Button>
        <Button variant="secondary" onClick={onDone}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}

export default function LotsPage() {
  const t = useTranslations();
  const format = useFormatter();
  const { data: me } = useMe();
  const { data: lots, isLoading } = useLots();
  const [creating, setCreating] = useState(false);
  const canWrite = hasPerm(me, "lots.write");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">{t("lots.title")}</h1>
          <p className="text-sm text-slate-600">{t("lots.subtitle")}</p>
        </div>
        {canWrite && !creating && <Button onClick={() => setCreating(true)}>{t("lots.new")}</Button>}
      </div>
      {!canWrite && me && <p className="text-sm text-slate-500">{t("lots.readOnly")}</p>}
      {creating && <NewLotForm onDone={() => setCreating(false)} />}

      {isLoading ? (
        <p className="text-slate-500">{t("common.loading")}</p>
      ) : !lots?.length ? (
        <p className="text-slate-500">{t("lots.empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-left text-slate-700">
              <tr>
                <th className="px-3 py-2">{t("lots.challan")}</th>
                <th className="px-3 py-2">{t("lots.mill")}</th>
                <th className="px-3 py-2">{t("lots.buyer")}</th>
                <th className="px-3 py-2">{t("lots.fabric")}</th>
                <th className="px-3 py-2">{t("lots.rolls")}</th>
                <th className="px-3 py-2">{t("lots.received")}</th>
                <th className="px-3 py-2">{t("lots.status")}</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot) => (
                <tr key={lot.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <Link href={`/lots/${lot.id}`} className="font-semibold text-brand-blue hover:underline">
                      {lot.challan_no}
                    </Link>{" "}
                    {lot.is_sample_data && <SampleBadge />}
                  </td>
                  <td className="px-3 py-2">{lot.supplier.name}</td>
                  <td className="px-3 py-2">{lot.buyer.name}</td>
                  <td className="px-3 py-2">{lot.fabric_type}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {lot.rolls_registered}/{lot.declared_rolls}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {format.dateTime(new Date(lot.received_at), { dateStyle: "medium" })}
                  </td>
                  <td className="px-3 py-2">{t(`status.${lot.status}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
