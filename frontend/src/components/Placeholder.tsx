"use client";

import { useTranslations } from "next-intl";

/** Screens planned for later milestones (PLAN.md §8, §10). Says honestly what is not built yet. */
export function Placeholder({ titleKey, bodyKey, milestone }: { titleKey: string; bodyKey: string; milestone: string }) {
  const t = useTranslations();
  return (
    <section className="te-stitched max-w-2xl rounded-lg p-6">
      <h1 className="te-serif mb-2 text-2xl font-bold text-(--te-ink)">{t(titleKey)}</h1>
      <p className="te-serif mb-4 text-(--te-ink-soft)">{t(bodyKey)}</p>
      <p className="text-sm font-semibold text-brand-amber">{t("placeholder.comingIn", { milestone })}</p>
    </section>
  );
}
