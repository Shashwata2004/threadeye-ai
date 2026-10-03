"use client";

import { useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { api, hasPerm, type AuditVerify } from "@/lib/api/client";
import { useAudit, useMe } from "@/lib/api/hooks";

export default function AuditPage() {
  const t = useTranslations("audit");
  const tc = useTranslations("common");
  const format = useFormatter();
  const { data: me } = useMe();
  const allowed = hasPerm(me, "audit.read");
  const { data: rows, isLoading } = useAudit(allowed);
  const [verify, setVerify] = useState<AuditVerify | null>(null);

  if (me && !allowed) return <p className="text-red-700">{t("forbidden")}</p>;

  async function runVerify() {
    const { data } = await api.GET("/api/v1/audit/verify");
    setVerify(data ?? null);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">{t("title")}</h1>
          <p className="text-sm text-slate-600">{t("subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={runVerify}
          className="rounded-md bg-brand-teal px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
        >
          {t("verify")}
        </button>
      </div>
      {verify && (
        <p
          role="status"
          className={`rounded-md px-3 py-2 text-sm font-semibold ${verify.ok ? "bg-teal-50 text-teal-800" : "bg-red-50 text-red-800"}`}
        >
          {verify.ok
            ? t("verifyOk", { count: verify.checked })
            : t("verifyBad", { id: verify.first_bad_id ?? 0, reason: verify.reason ?? "" })}
        </p>
      )}
      {isLoading ? (
        <p className="text-slate-500">{tc("loading")}</p>
      ) : !rows?.length ? (
        <p className="text-slate-500">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-left text-slate-700">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">{t("when")}</th>
                <th className="px-3 py-2">{t("action")}</th>
                <th className="px-3 py-2">{t("actor")}</th>
                <th className="px-3 py-2">{t("entity")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="px-3 py-1.5 font-mono text-xs text-slate-500">{r.id}</td>
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    {format.dateTime(new Date(r.at), { dateStyle: "medium", timeStyle: "medium" })}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs">{r.action}</td>
                  <td className="px-3 py-1.5">{r.actor_role ?? tc("dash")}</td>
                  <td className="px-3 py-1.5 font-mono text-xs text-slate-600">
                    {r.entity_type ? `${r.entity_type}:${r.entity_id ?? ""}` : tc("dash")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
