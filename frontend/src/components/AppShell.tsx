"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { ModeBanner } from "@/components/badges";
import { LanguageToggle } from "@/components/LanguageToggle";
import { api, hasPerm } from "@/lib/api/client";
import { useMe } from "@/lib/api/hooks";

// Navigation follows server-side permissions (from /auth/me). Hiding a link is only UX:
// the API enforces every permission itself.
const NAV: { href: string; key: string; perm: string | string[] }[] = [
  { href: "/", key: "dashboard", perm: ["dashboard.read", "dashboard.own_shift"] },
  { href: "/lots", key: "lots", perm: "lots.read" },
  { href: "/inspect", key: "inspect", perm: "inspections.read" },
  { href: "/verification", key: "verification", perm: "verification.read" },
  { href: "/benchmark", key: "benchmark", perm: "benchmark.read" },
  { href: "/suppliers", key: "suppliers", perm: "suppliers.scorecard" },
  { href: "/audit", key: "audit", perm: "audit.read" },
  { href: "/admin", key: "admin", perm: "users.manage" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: me, isLoading } = useMe();

  useEffect(() => {
    if (!isLoading && me === null) router.replace("/login");
  }, [isLoading, me, router]);

  // Roles without a dashboard (e.g. Store In-charge) land on their first screen instead.
  const items = me
    ? NAV.filter((n) => (Array.isArray(n.perm) ? n.perm : [n.perm]).some((p) => hasPerm(me, p)))
    : [];
  const landing = items[0]?.href;
  useEffect(() => {
    if (pathname === "/" && landing && landing !== "/") router.replace(landing);
  }, [pathname, landing, router]);

  async function logout() {
    await api.POST("/api/v1/auth/logout");
    queryClient.clear();
    router.replace("/login");
  }

  if (isLoading || !me) {
    return <div className="p-8 text-slate-500">{t("common.loading")}</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <ModeBanner />
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex items-baseline gap-3">
          <span className="text-xl font-bold text-brand-navy">{t("app.name")}</span>
          <span className="hidden text-sm text-brand-teal sm:inline">{t("app.tagline")}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600" data-testid="current-user">
            {me.display_name} · {t(`roles.${me.role}`)}
          </span>
          <LanguageToggle loggedIn />
          <button
            type="button"
            onClick={logout}
            className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-100"
          >
            {t("nav.logout")}
          </button>
        </div>
      </header>
      <div className="flex flex-col sm:flex-row">
        <nav aria-label="main" className="border-b border-slate-200 bg-white sm:min-h-[calc(100vh-7rem)] sm:w-56 sm:border-b-0 sm:border-r">
          <ul className="flex gap-1 overflow-x-auto p-2 sm:flex-col">
            {items.map((n) => {
              const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
              return (
                <li key={n.href}>
                  <Link
                    href={n.href}
                    className={`block whitespace-nowrap rounded-md px-3 py-2 text-sm ${
                      active ? "bg-brand-navy text-white" : "text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    {t(`nav.${n.key}`)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <main className="flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
