"use client";

import { useTranslations } from "next-intl";
import { ProviderBadge } from "@/components/badges";
import { useMe, useProviders, useSystemStatus } from "@/lib/api/hooks";

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-600">{label}</p>
      <p className="mt-1 text-3xl font-bold text-slate-400">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const t = useTranslations();
  const { data: me } = useMe();
  const { data: status } = useSystemStatus();
  const { data: providers } = useProviders();
  const dash = t("common.dash");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t("dashboard.title")}</h1>
        {me && <p className="text-slate-600">{t("dashboard.welcome", { name: me.display_name })}</p>}
      </div>

      {/* Empty state: no numbers until they are measured (no fabricated metrics). */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="kpi-tiles">
        <Tile label={t("dashboard.rollsInspected")} value={dash} hint={t("dashboard.noData")} />
        <Tile label={t("dashboard.verdicts")} value={`${dash} / ${dash} / ${dash}`} />
        <Tile label={t("dashboard.avgPer100")} value={dash} />
        <Tile label={t("dashboard.falseAlarms")} value={dash} />
      </section>
      <p className="text-sm text-slate-500">{t("dashboard.noDataHint")}</p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 font-semibold">{t("dashboard.verification")}</h2>
          <p className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-sm font-semibold text-amber-900">
            {t("dashboard.verificationNone")}
          </p>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4" data-testid="system-status">
          <h2 className="mb-2 font-semibold">{t("dashboard.system")}</h2>
          {status ? (
            <dl className="grid grid-cols-2 gap-y-1 text-sm">
              <dt className="text-slate-600">{t("dashboard.db")}</dt>
              <dd className={status.db === "ok" ? "text-teal-700" : "text-red-700"}>
                {status.db === "ok" ? t("dashboard.ok") : t("dashboard.down")}
              </dd>
              <dt className="text-slate-600">{t("dashboard.worker")}</dt>
              <dd className={status.worker.alive ? "text-teal-700" : "text-red-700"}>
                {status.worker.alive ? t("dashboard.workerAlive") : t("dashboard.workerDown")}
              </dd>
              <dt className="text-slate-600">{t("dashboard.profile")}</dt>
              <dd>{status.profile === "edge" ? t("mode.edge") : t("mode.cloud")}</dd>
              <dt className="text-slate-600">{t("dashboard.version")}</dt>
              <dd className="font-mono text-xs leading-6">{status.version}</dd>
            </dl>
          ) : (
            <p className="text-sm text-slate-500">{t("common.loading")}</p>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 font-semibold">{t("dashboard.providers")}</h2>
          <ul className="space-y-2 text-sm">
            {providers?.map((p) => (
              <li key={p.provider_id} className="flex flex-wrap items-center gap-2">
                {p.active ? (
                  <ProviderBadge name={p.display_name} simulated={p.is_simulated} />
                ) : (
                  <span className="text-slate-700">{p.display_name}</span>
                )}
                <span className="text-xs text-slate-500">
                  {p.active ? `${t("dashboard.active")} · ` : ""}
                  {p.availability === "planned"
                    ? t("availability.planned", { milestone: p.milestone })
                    : t(`availability.${p.availability}`)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
