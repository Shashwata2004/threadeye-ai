"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { api } from "@/lib/api/client";
import { LOCALE_COOKIE } from "@/i18n/constants";

export function setLocaleCookie(locale: "bn" | "en") {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
}

export function LanguageToggle({ loggedIn }: { loggedIn: boolean }) {
  const locale = useLocale();
  const t = useTranslations("app");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pending, startTransition] = useTransition();

  async function choose(next: "bn" | "en") {
    if (next === locale) return;
    setLocaleCookie(next);
    if (loggedIn) {
      await api.PATCH("/api/v1/auth/me", { body: { locale: next } });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    }
    startTransition(() => router.refresh());
  }

  return (
    <div role="group" aria-label={t("language")} className="inline-flex overflow-hidden rounded-md border border-slate-300">
      {(["bn", "en"] as const).map((l) => (
        <button
          key={l}
          type="button"
          disabled={pending}
          onClick={() => choose(l)}
          aria-pressed={locale === l}
          className={`px-3 py-1 text-sm ${locale === l ? "bg-slate-800 text-white" : "bg-white text-slate-700 hover:bg-slate-100"}`}
        >
          {l === "bn" ? "বাংলা" : "English"}
        </button>
      ))}
    </div>
  );
}
