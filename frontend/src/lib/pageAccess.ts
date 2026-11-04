import { hasPerm, type Me } from "@/lib/api/client";

export interface PageAccess {
  key: string;
  permissions: string[];
}

/** UI access only: the API remains the authority for every read and write. */
export function pageAccess(pathname: string): PageAccess | null {
  if (pathname === "/") return {key: "dashboard", permissions: ["dashboard.read", "dashboard.own_shift"]};
  if (/^\/inspections\/[^/]+\/cutting(?:\/|$)/.test(pathname)) return {key: "cutting", permissions: ["cutting.read"]};
  const rules: [string, string, string[]][] = [
    ["/cutting", "cutting", ["cutting.read"]],
    ["/admin", "admin", ["users.manage", "machines.manage", "profiles.write", "providers.manage", "settings.manage"]],
    ["/audit", "audit", ["audit.read"]],
    ["/suppliers", "suppliers", ["suppliers.scorecard"]],
    ["/benchmark", "benchmark", ["benchmark.read"]],
    ["/verification", "verification", ["verification.read"]],
    ["/lots", "lots", ["lots.read"]],
    ["/inspect", "inspect", ["inspections.read"]],
    ["/inspections", "inspect", ["inspections.read"]],
  ];
  const match = rules.find(([prefix]) => pathname === prefix || pathname.startsWith(prefix + "/"));
  return match ? {key: match[1], permissions: match[2]} : null;
}

export function canOpenPage(me: Me | null | undefined, pathname: string): boolean {
  const access = pageAccess(pathname);
  return !access || access.permissions.some(permission => hasPerm(me, permission));
}

export function permittedLanding(me: Me | null | undefined, current: string): {href: string; key: string} {
  const choices = [{href: "/", key: "dashboard"}, {href: "/lots", key: "lots"},
    {href: "/inspect", key: "inspect"}, {href: "/verification", key: "verification"}];
  return choices.find(item => item.href !== current && canOpenPage(me, item.href)) ?? {href: "/about", key: "about"};
}
