"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { api, hasPerm, type AuditEntry } from "@/lib/api/client";
import { useAudit, useMe } from "@/lib/api/hooks";
import { Card, PageHeader, Pill, inputCls, primaryBtn, screenRoot, useBi } from "@/components/screenKit";
import { PermissionNotice } from "@/components/PermissionNotice";

type Row = AuditEntry & { actor_name?: string };

// Roles without audit.read see no entries: the API refuses them the ledger.

const ROLE_TONE: Record<string, "navy" | "teal" | "amber" | "slate" | "emerald"> = {
  admin: "navy",
  qc_supervisor: "teal",
  inspector: "amber",
  system: "slate",
};

function entityHref(r: Row, live: boolean): string | null {
  if (!live || !r.entity_id) return null;
  if (r.entity_type === "lot") return `/lots/${r.entity_id}`;
  if (r.entity_type === "inspection") return `/inspections/${r.entity_id}`;
  return null;
}

/** "user:01a102d8-f6ce-…" → "user:01a102d8…": UUIDs are cut, roll codes and challans stay whole. */
function shortEntity(entity: string): string {
  return entity.length > 24 ? `${entity.slice(0, 22)}…` : entity;
}

type VerifyState =
  | { phase: "idle" }
  | { phase: "running"; progress: number }
  | { phase: "done"; ok: boolean; checked: number; total: number; at: Date; reason?: string; badId?: number | null };

export default function AuditPage() {
  const t = useTranslations("audit");
  const tc = useTranslations("common");
  const tr = useTranslations("roles");
  const tn = useTranslations("nav");
  const bi = useBi();
  const format = useFormatter();
  const { data: me } = useMe();
  const live = hasPerm(me, "audit.read");
  const { data: liveRows, isLoading, isError } = useAudit(live);
  // Names for actor ids: the full user list is admin-only, everyone else at least sees their own name.
  const { data: users } = useQuery({
    queryKey: ["users"],
    enabled: live && hasPerm(me, "users.manage"),
    queryFn: async () => (await api.GET("/api/v1/users")).data ?? [],
  });
  const names = useMemo(() => {
    const m = new Map<string, string>((users ?? []).map((u) => [u.id, u.display_name]));
    if (me) m.set(me.id, me.display_name);
    return m;
  }, [users, me]);

  const rows: Row[] = useMemo(() => (live ? (liveRows ?? []) : []), [live, liveRows]);
  const total = rows.length;

  const [roleFilter, setRoleFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<Row | null>(null);
  const [verify, setVerify] = useState<VerifyState>({ phase: "idle" });

  const actions = useMemo(
    () =>
      Array.from(
        new Set(["inspection.approve", "defect.confirm", "verdict.override", "challan.new", "auth.login", ...rows.map((r) => r.action)]),
      ).sort(),
    [rows],
  );
  const roles = useMemo(
    () => Array.from(new Set(["admin", "qc_supervisor", "inspector", "system", ...rows.map((r) => r.actor_role ?? "system")])),
    [rows],
  );

  const filtered = rows.filter((r) => {
    const role = r.actor_role ?? "system";
    const q = search.trim().toLowerCase();
    return (
      (!roleFilter || role === roleFilter) &&
      (!actionFilter || r.action === actionFilter) &&
      (!q || `${r.entity_type ?? ""}:${r.entity_id ?? ""}`.toLowerCase().includes(q))
    );
  });

  const byId = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function runVerify() {
    setVerify({ phase: "running", progress: 0 });
    const ticker = window.setInterval(
      () => setVerify((v) => (v.phase === "running" ? { phase: "running", progress: Math.min(95, v.progress + 7) } : v)),
      60,
    );
    const minWait = new Promise((r) => window.setTimeout(r, 1100));
    try {
      if (live) {
        const [{ data }] = await Promise.all([api.GET("/api/v1/audit/verify"), minWait]);
        setVerify(
          data
            ? { phase: "done", ok: data.ok, checked: data.checked, total: data.checked, at: new Date(), reason: data.reason ?? undefined, badId: data.first_bad_id }
            : { phase: "done", ok: false, checked: 0, total, at: new Date(), reason: bi("The server did not answer.", "সার্ভার সাড়া দেয়নি।") },
        );
      } else {
        await minWait;
        setVerify({
          phase: "done",
          ok: false,
          checked: 0,
          total: 0,
          at: new Date(),
          reason: bi("Your role cannot read the ledger, so it cannot be verified here.", "আপনার ভূমিকায় লেজার দেখা যায় না, তাই এখানে যাচাই করা যাবে না।"),
        });
      }
    } finally {
      window.clearInterval(ticker);
    }
  }

  if (!me || !live) return (
    <div className={`${screenRoot} space-y-4`}>
      <PageHeader title={t("title")} subtitle={t("subtitle")} sample={false} />
      {!me ? <p className="text-slate-500">{tc("loading")}</p> :
        <PermissionNotice title={bi("You do not have permission to view audit entries.", "এন্ট্রি দেখার অনুমতি নেই।")}>
          <p>{bi("This does not mean the log is empty. Sign in with an admin or management account to view entries.",
            "এর অর্থ লগ খালি নয়। এন্ট্রি দেখতে অ্যাডমিন বা ম্যানেজমেন্ট অ্যাকাউন্টে লগইন করুন।")}</p>
        </PermissionNotice>}
    </div>
  );

  const actorLabel = (r: Row) =>
    r.actor_name ??
    (r.actor_user_id ? (names.get(r.actor_user_id) ?? `${r.actor_user_id.slice(0, 8)}…`) : bi("System", "সিস্টেম"));
  const roleLabel = (role: string) => (role === "system" ? bi("System", "সিস্টেম") : tr(role));

  return (
    <div className={`${screenRoot} space-y-4`}>
      <PageHeader title={t("title")} subtitle={t("subtitle")} sample={false} />

      <Card
        className={
          verify.phase === "done"
            ? verify.ok
              ? "border-emerald-500/40 bg-emerald-500/5"
              : "border-red-500/40 bg-red-500/5"
            : ""
        }
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-xl font-bold text-white ${
                verify.phase === "done" ? (verify.ok ? "bg-emerald-500" : "bg-red-500") : "bg-slate-400"
              } ${verify.phase === "running" ? "animate-pulse" : ""}`}
            >
              {verify.phase === "done" ? (verify.ok ? "✓" : "!") : "#"}
            </span>
            <div>
              <p className="text-lg font-semibold text-brand-navy" role="status">
                {verify.phase === "idle" && bi("Hash chain not checked yet", "হ্যাশ চেইন এখনো যাচাই হয়নি")}
                {verify.phase === "running" && bi("Re-computing every hash…", "প্রতিটি হ্যাশ আবার হিসাব হচ্ছে…")}
                {verify.phase === "done" &&
                  (verify.ok
                    ? bi(
                        `Hash chain intact (${verify.checked}/${verify.total} entries verified)`,
                        `হ্যাশ চেইন অক্ষত (${verify.checked}/${verify.total}টি এন্ট্রি যাচাই হয়েছে)`,
                      )
                    : t("verifyBad", { id: verify.badId ?? 0, reason: verify.reason ?? "" }))}
              </p>
              <p className="text-xs text-slate-500">
                {verify.phase === "done"
                  ? `${bi("Last verified", "সর্বশেষ যাচাই")}: ${format.dateTime(verify.at, { dateStyle: "medium", timeStyle: "medium" })}`
                  : bi(
                      "Each entry stores the SHA-256 of the one before it, so any edit breaks the chain.",
                      "প্রতিটি এন্ট্রিতে আগেরটির SHA-256 থাকে, তাই কোনো পরিবর্তন হলে চেইন ভেঙে যায়।",
                    )}
              </p>
            </div>
          </div>
          <button type="button" onClick={runVerify} disabled={verify.phase === "running"} className={primaryBtn}>
            {verify.phase === "running" && (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {t("verify")}
          </button>
        </div>
        {verify.phase === "running" && (
          <div className="mt-3 h-1.5 overflow-hidden rounded bg-slate-100">
            <div className="h-full bg-brand-teal transition-all duration-100" style={{ width: `${verify.progress}%` }} />
          </div>
        )}
      </Card>

      <Card className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">{bi("Actor role", "ভূমিকা")}</span>
          <select className={inputCls} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">{bi("All roles", "সব ভূমিকা")}</option>
            {roles.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">{t("action")}</span>
          <select className={`${inputCls} font-mono`} value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}>
            <option value="">{bi("All actions", "সব কাজ")}</option>
            {actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">{bi("Entity ID / roll code", "এন্টিটি আইডি / রোল কোড")}</span>
          <input
            type="search"
            className={`${inputCls} font-mono`}
            placeholder="TE-000001"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </Card>

      {isError ? (
        <p role="alert" className="text-red-700">{bi("Could not load audit entries. Please try again.", "এন্ট্রি লোড করা যায়নি। আবার চেষ্টা করুন।")}</p>
      ) : isLoading ? (
        <p className="text-slate-500">{tc("loading")}</p>
      ) : !filtered.length ? (
        <p className="text-slate-500">{rows.length ? bi("No entries match these filters.", "এই ফিল্টারে কোনো এন্ট্রি নেই।") : t("empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-xs">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-left text-slate-700">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">{t("when")}</th>
                <th className="px-3 py-2">{t("actor")}</th>
                <th className="px-3 py-2">{t("action")}</th>
                <th className="px-3 py-2">{t("entity")}</th>
                <th className="px-3 py-2">SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const role = r.actor_role ?? "system";
                const href = entityHref(r, live);
                const entity = r.entity_type ? `${r.entity_type}:${r.entity_id ?? ""}` : null;
                return (
                  <tr
                    key={r.id}
                    tabIndex={0}
                    onClick={() => setOpen(r)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setOpen(r))}
                    className={`cursor-pointer border-t border-slate-100 hover:bg-teal-500/5 focus:bg-teal-500/10 focus:outline-none ${
                      open?.id === r.id ? "bg-teal-500/10" : ""
                    }`}
                  >
                    <td className="px-3 py-1.5 font-mono text-xs text-slate-500">{r.id}</td>
                    <td className="px-3 py-1.5 whitespace-nowrap">
                      {format.dateTime(new Date(r.at), { dateStyle: "medium", timeStyle: "medium" })}
                    </td>
                    <td className="px-3 py-1.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="whitespace-nowrap text-slate-800">{actorLabel(r)}</span>
                        <Pill tone={ROLE_TONE[role] ?? "slate"}>{roleLabel(role)}</Pill>
                      </div>
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs">{r.action}</td>
                    <td className="px-3 py-1.5">
                      {!entity ? (
                        tc("dash")
                      ) : href ? (
                        <Link
                          href={href}
                          title={entity}
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex whitespace-nowrap rounded-full bg-brand-navy/10 px-2 py-0.5 font-mono text-xs text-brand-navy hover:underline"
                        >
                          {shortEntity(entity)}
                        </Link>
                      ) : (
                        <span title={entity} className="inline-flex whitespace-nowrap rounded-full bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-700">
                          {shortEntity(entity)}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs text-slate-500" title={r.hash}>
                      {r.hash.slice(0, 10)}…
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {open && (
        <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="audit-drawer-title">
          <button type="button" aria-label={bi("Close", "বন্ধ করুন")} className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(null)} />
          <aside className="relative flex h-full w-full max-w-lg flex-col overflow-y-auto bg-white shadow-xl">
            <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {tn("audit")} · #{open.id}
                </p>
                <h2 id="audit-drawer-title" className="font-mono text-lg font-semibold text-brand-navy">
                  {open.action}
                </h2>
                <p className="text-sm text-slate-600">
                  {actorLabel(open)} · {roleLabel(open.actor_role ?? "system")} ·{" "}
                  {format.dateTime(new Date(open.at), { dateStyle: "medium", timeStyle: "medium" })}
                </p>
              </div>
              <button type="button" onClick={() => setOpen(null)} className="rounded-md px-2 py-1 text-xl leading-none text-slate-500 hover:bg-slate-100">
                ×
              </button>
            </div>

            <div className="space-y-4 px-5 py-4">
              <div>
                <p className="mb-1 text-sm font-semibold text-slate-700">{t("entity")}</p>
                <p className="font-mono text-sm text-slate-800">
                  {open.entity_type ? `${open.entity_type}:${open.entity_id ?? ""}` : tc("dash")}
                </p>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {(
                  [
                    [bi("Before", "আগে"), open.before, "border-red-500/30 bg-red-500/5"],
                    [bi("After", "পরে"), open.after, "border-emerald-500/30 bg-emerald-500/5"],
                  ] as const
                ).map(([label, value, cls]) => (
                  <div key={label}>
                    <p className="mb-1 text-sm font-semibold text-slate-700">{label}</p>
                    <pre className={`max-h-64 overflow-auto rounded-md border p-2 font-mono text-xs text-slate-800 ${cls}`}>
                      {value ? JSON.stringify(value, null, 2) : "null"}
                    </pre>
                  </div>
                ))}
              </div>

              <div className="space-y-2 rounded-md border border-slate-200 p-3">
                <p className="text-sm font-semibold text-slate-700">{bi("Chain continuity", "চেইনের ধারাবাহিকতা")}</p>
                <div>
                  <p className="text-xs text-slate-500">
                    {bi("Previous hash", "আগের হ্যাশ")} (#{open.id - 1})
                  </p>
                  <p className="break-all font-mono text-xs text-slate-700">
                    {byId.get(open.id - 1)?.hash ?? bi("Older than the entries loaded here", "এখানে লোড হওয়া এন্ট্রির চেয়ে পুরোনো")}
                  </p>
                </div>
                <div className="flex justify-center text-slate-400" aria-hidden="true">
                  ↓
                </div>
                <div>
                  <p className="text-xs text-slate-500">
                    {bi("Current hash", "বর্তমান হ্যাশ")} (#{open.id})
                  </p>
                  <p className="break-all font-mono text-xs font-semibold text-brand-teal">{open.hash}</p>
                </div>
                <p className="text-xs text-slate-500">
                  {bi(
                    "The current hash covers this record and the previous hash, so changing either breaks every hash after it.",
                    "বর্তমান হ্যাশে এই রেকর্ড ও আগের হ্যাশ দুটোই আছে, তাই যেকোনোটি বদলালে পরের সব হ্যাশ ভেঙে যায়।",
                  )}
                </p>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
