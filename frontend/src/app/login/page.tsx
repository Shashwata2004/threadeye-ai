"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ModeBanner } from "@/components/badges";
import { LanguageToggle, setLocaleCookie } from "@/components/LanguageToggle";
import { api } from "@/lib/api/client";

export default function LoginPage() {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    <div className="min-h-screen bg-slate-50">
      <ModeBanner />
      <div className="flex justify-end p-4">
        <LanguageToggle loggedIn={false} />
      </div>
      <main className="mx-auto mt-8 w-full max-w-sm px-4">
        <h1 className="text-3xl font-bold text-brand-navy">{t("app.name")}</h1>
        <p className="mb-8 text-brand-teal">{t("app.tagline")}</p>
        <form onSubmit={submit} className="space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">{t("login.title")}</h2>
          <label className="block">
            <span className="text-sm text-slate-700">{t("login.username")}</span>
            <input
              name="username"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="block">
            <span className="text-sm text-slate-700">{t("login.password")}</span>
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
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
            className="w-full rounded-md bg-brand-navy px-4 py-2 font-semibold text-white hover:opacity-90 disabled:opacity-60"
          >
            {busy ? t("login.submitting") : t("login.submit")}
          </button>
        </form>
        <p className="mt-4 text-xs text-slate-500">{t("login.demoHint")}</p>
      </main>
    </div>
  );
}
