"use client";

import { useTranslations } from "next-intl";

/** Screens planned for later milestones (PLAN.md §8, §10). Says honestly what is not built yet. */
export function Placeholder({ titleKey, bodyKey, milestone }: { titleKey: string; bodyKey: string; milestone: string }) {
  const t = useTranslations();
  return (
    <section className="max-w-2xl rounded-lg border border-dashed border-slate-300 bg-white p-6">
      <h1 className="mb-2 text-2xl font-bold text-brand-navy">{t(titleKey)}</h1>
      <p className="mb-4 text-slate-700">{t(bodyKey)}</p>
      <p className="text-sm font-semibold text-brand-amber">{t("placeholder.comingIn", { milestone })}</p>
    </section>
  );
}
