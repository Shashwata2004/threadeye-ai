"use client";

import { useTranslations } from "next-intl";
import { ProviderBadge } from "@/components/badges";
import { FabricRollSketch, LoomSketch } from "@/components/FabricArt";
import { useMe, useProviders, useSystemStatus } from "@/lib/api/hooks";

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="p-4 sm:p-5">
      <p className="text-sm text-(--te-muted)">{label}</p>
      <p className="te-serif mt-1 text-4xl text-(--te-ink)">{value}</p>
      {hint && <p className="mt-1 text-xs text-(--te-faint)">{hint}</p>}
    </div>
  );
}

// Soft status pill; leading-5 keeps each row the same height as plain text-sm.
const PILL = "inline-flex w-fit rounded-full px-2 leading-5";
const PILL_OK = `${PILL} bg-emerald-100 text-emerald-800`;
const PILL_BAD = `${PILL} bg-red-100 text-red-800`;
const PILL_NEUTRAL = `${PILL} bg-stone-200/80 text-stone-700`;

export default function DashboardPage() {
  const t = useTranslations();
  const { data: me } = useMe();
  const { data: status } = useSystemStatus();
  const { data: providers } = useProviders();
  const dash = t("common.dash");

  return (
    // The background sketch sits in the bottom-right corner of the page, below the last box: the
    // page is at least screen height and keeps room for it at the bottom. It never takes clicks.
    <div className="relative z-[1] space-y-6 md:min-h-[calc(100vh-9rem)] md:pb-60">
      <div
        aria-hidden="true"
        className="te-sketch-checklist pointer-events-none absolute bottom-0 right-0 -z-10 hidden h-56 w-[210px] bg-contain bg-right-bottom bg-no-repeat opacity-30 md:block"
      />
      <div>
        <h1 className="te-serif text-2xl font-bold text-(--te-ink)">{t("dashboard.title")}</h1>
        {me && <p className="te-serif text-(--te-ink-soft)">{t("dashboard.welcome", { name: me.display_name })}</p>}
      </div>

      {/* Sample figures shown for the design preview; not yet read from the server. */}
      <section className="te-rope" data-testid="kpi-tiles">
        <div className="te-rope-inner">
          <FabricRollSketch className="te-watermark bottom-3 right-4 hidden h-[72%] opacity-25 md:block" />
          <div className="relative grid grid-cols-1 divide-y divide-(--te-line)/70 sm:grid-cols-2 sm:divide-y-0 md:w-[68%]">
            <div className="sm:border-b sm:border-r sm:border-(--te-line)/70">
              <Tile label={t("dashboard.rollsInspected")} value="147" hint={t("dashboard.noData")} />
            </div>
            <div className="sm:border-b sm:border-(--te-line)/70">
              <Tile label={t("dashboard.verdicts")} value="147 / 32 / 5" />
            </div>
            <div className="sm:border-r sm:border-(--te-line)/70">
              <Tile label={t("dashboard.avgPer100")} value={t("live.pts", { n: 18 })} />
            </div>
            <Tile label={t("dashboard.falseAlarms")} value={dash} />
          </div>
        </div>
      </section>
      <p className="text-sm text-(--te-muted)">{t("dashboard.noDataHint")}</p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="te-stitched overflow-hidden rounded-lg p-4">
          <LoomSketch className="te-watermark -bottom-3 right-2 h-24 opacity-15" />
          <h2 className="te-serif relative mb-2 text-lg font-semibold">{t("dashboard.verification")}</h2>
          <p className="relative inline-flex rounded-full bg-amber-100 px-3 py-1 text-sm font-semibold text-amber-900 ring-1 ring-amber-300">
            {t("dashboard.verificationNone")}
          </p>
        </section>

        <section className="te-stitched rounded-lg p-4" data-testid="system-status">
          <h2 className="te-serif mb-2 text-lg font-semibold">{t("dashboard.system")}</h2>
          {status ? (
            <dl className="grid grid-cols-2 gap-y-1 text-sm">
              <dt className="text-(--te-muted)">{t("dashboard.db")}</dt>
              <dd className={status.db === "ok" ? PILL_OK : PILL_BAD}>
                {status.db === "ok" ? t("dashboard.ok") : t("dashboard.down")}
              </dd>
              <dt className="text-(--te-muted)">{t("dashboard.worker")}</dt>
              <dd className={status.worker.alive ? PILL_OK : PILL_BAD}>
                {status.worker.alive ? t("dashboard.workerAlive") : t("dashboard.workerDown")}
              </dd>
              <dt className="text-(--te-muted)">{t("dashboard.profile")}</dt>
              <dd className={PILL_NEUTRAL}>{status.profile === "edge" ? t("mode.edge") : t("mode.cloud")}</dd>
              <dt className="text-(--te-muted)">{t("dashboard.version")}</dt>
              <dd className="w-fit rounded-full bg-stone-200/60 px-2 font-mono text-xs leading-6">{status.version}</dd>
            </dl>
          ) : (
            <p className="text-sm text-slate-500">{t("common.loading")}</p>
          )}
        </section>

        <section className="te-stitched rounded-lg p-4">
          <h2 className="te-serif mb-2 text-lg font-semibold">{t("dashboard.providers")}</h2>
          <ul className="space-y-2 text-sm">
            {providers?.map((p) => (
              <li key={p.provider_id} className="flex flex-wrap items-center gap-2">
                {p.active ? (
                  <ProviderBadge name={p.display_name} simulated={p.is_simulated} />
                ) : (
                  <span className="text-(--te-ink)">{p.display_name}</span>
                )}
                <span className="text-xs text-(--te-faint)">
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
