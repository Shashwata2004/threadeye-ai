"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ModeBanner } from "@/components/badges";
import { ThreadEyeMark } from "@/components/FabricArt";
import { LanguageToggle, setLocaleCookie } from "@/components/LanguageToggle";
import { LoginRobot } from "@/components/LoginRobot";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";
import { api } from "@/lib/api/client";
import "@/styles/fabric.css";

export default function LoginPage() {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const theme = useTheme();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, response } = await api.POST("/api/v1/auth/login", { body: { username, password } });
      if (data) {
        setLocaleCookie(data.locale);
        queryClient.setQueryData(["me"], data);
        router.replace("/");
        router.refresh();
        return;
      }
      setError(t(response.status === 429 ? "login.locked" : "login.invalid"));
    } catch {
      setError(t("login.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="te-linen relative min-h-screen overflow-hidden" data-theme={theme}>
      <ModeBanner />
      <div className="flex justify-end gap-2 p-4">
        <ThemeToggle />
        <LanguageToggle loggedIn={false} />
      </div>
      <main className="relative z-[1] mx-auto mt-8 w-full max-w-sm px-4 pb-8">
        <div className="flex items-center gap-2">
          <ThreadEyeMark className="h-9 w-9 shrink-0 text-(--te-ink)" />
          <h1 className="te-serif text-3xl font-bold text-(--te-ink)">{t("app.name")}</h1>
        </div>
        {/* The motto, set like a label sewn on: serif italic over a stitched line. */}
        <p className="te-serif te-motto te-stitch-underline mt-2 inline-block pb-1 text-lg italic text-(--te-ink-soft)">
          {t("app.tagline")}
        </p>
        {/* An AI robot holds up the login board. */}
        <LoginRobot>
        <form onSubmit={submit} className="te-rope">
        <div className="te-rope-inner space-y-4 p-6">
          <h2 className="te-serif text-xl font-semibold text-(--te-ink)">{t("login.title")}</h2>
          <label className="block">
            <span className="text-sm text-(--te-ink-soft)">{t("login.username")}</span>
            <input
              name="username"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 w-full rounded-md border border-(--te-line) bg-white px-3 py-2 focus:border-brand-teal focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-sm text-(--te-ink-soft)">{t("login.password")}</span>
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border border-(--te-line) bg-white px-3 py-2 focus:border-brand-teal focus:outline-none"
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-red-700">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-brand-navy px-4 py-2 font-semibold text-white shadow-md shadow-(--te-shadow)/20 hover:opacity-90 disabled:opacity-60"
          >
            {busy ? t("login.submitting") : t("login.submit")}
          </button>
        </div>
        </form>
        </LoginRobot>
        <p className="mt-4 text-xs text-(--te-faint)">{t("login.demoHint")}</p>
      </main>
      {/* Background drawing, centred at the bottom of the screen under the login box. Decorative. */}
      <div
        aria-hidden="true"
        className="te-sketch-login pointer-events-none absolute bottom-0 left-1/2 h-[max(240px,calc(100vh-43rem))] w-full max-w-[860px] -translate-x-1/2 bg-contain bg-bottom bg-no-repeat opacity-35"
      />
    </div>
  );
}
