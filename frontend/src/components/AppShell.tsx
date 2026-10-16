"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { ModeBanner } from "@/components/badges";
import { ThreadSpool } from "@/components/FabricArt";
import { LanguageToggle } from "@/components/LanguageToggle";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";
import { api, hasPerm } from "@/lib/api/client";
import { useMe } from "@/lib/api/hooks";
import "@/styles/fabric.css";

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
  const theme = useTheme();

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
    <div className="te-linen min-h-screen" data-theme={theme}>
      <ModeBanner />
      <header className="te-header flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-baseline gap-3">
          <span className="te-serif text-xl font-bold text-brand-navy">{t("app.name")}</span>
          <span className="hidden text-sm text-(--te-faint) sm:inline">{t("app.tagline")}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <span className="text-sm text-(--te-ink-soft)" data-testid="current-user">
            {me.display_name} · {t(`roles.${me.role}`)}
          </span>
          <ThemeToggle />
          <LanguageToggle loggedIn />
          <button
            type="button"
            onClick={logout}
            className="te-btn rounded-md px-3 py-1 text-sm"
          >
            {t("nav.logout")}
          </button>
        </div>
      </header>
      <div className="flex flex-col sm:flex-row">
        <nav aria-label="main" className="te-denim flex flex-col justify-between sm:min-h-[calc(100vh-7rem)] sm:w-56">
          <ul className="flex gap-1 overflow-x-auto p-2 sm:flex-col">
            {items.map((n) => {
              const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
              return (
                <li key={n.href}>
                  <Link
                    href={n.href}
                    aria-current={active ? "page" : undefined}
                    className="te-nav-link block whitespace-nowrap rounded-md px-3 py-2 text-sm"
                  >
                    {t(`nav.${n.key}`)}
                  </Link>
                </li>
              );
            })}
          </ul>
          <ThreadSpool className="hidden h-24 w-20 self-start p-2 drop-shadow-lg sm:block" />
        </nav>
        <main className="min-w-0 flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
