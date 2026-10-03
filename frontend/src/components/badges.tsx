"use client";

import { useTranslations } from "next-intl";
import { useHealth } from "@/lib/api/hooks";

/**
 * Honesty rule (PLAN.md §2, brief §11): every screen shows this banner while the detector or the
 * video source is simulated. It reads the public /health endpoint, so it also shows on the login
 * page. If the status is unknown it is shown anyway: we never risk hiding it.
 */
export function ModeBanner() {
  const t = useTranslations("mode");
  const { data } = useHealth();
  if (data && !data.simulated_mode) return null;
  return (
    <div
      role="status"
      data-testid="simulated-banner"
      className="w-full bg-amber-500 px-4 py-1.5 text-center text-sm font-bold text-amber-950"
    >
      {t("simulatedBanner")}
    </div>
  );
}

export function ProviderBadge({ name, simulated }: { name: string; simulated: boolean }) {
  const t = useTranslations("mode");
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        simulated ? "bg-amber-100 text-amber-900 ring-1 ring-amber-400" : "bg-teal-100 text-teal-900"
      }`}
    >
      {t("provider", { name })}
    </span>
  );
}

/** Shown on any sample/fictional entity or aggregate that contains one. */
export function SampleBadge() {
  const t = useTranslations("mode");
  return (
    <span className="inline-flex rounded bg-slate-200 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-700">
      {t("sampleData")}
    </span>
  );
}
