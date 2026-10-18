"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { hasPerm, type Role } from "@/lib/api/client";
import { useMe } from "@/lib/api/hooks";
import {
  Card,
  CardTitle,
  Field,
  PageHeader,
  Pill,
  ViewOnlyNote,
  ghostBtn,
  inputCls,
  primaryBtn,
  screenRoot,
  useBi,
} from "@/components/screenKit";

// Plant settings: no data yet (the M4 admin endpoints fill the lists below). Edits stay in this tab.
type TabId = "users" | "machines" | "profiles" | "detectors";

interface UserRow {
  name: string;
  username: string;
  role: Role;
  shift: "A" | "B" | "C" | "General";
  lang: "en" | "bn";
  digits: "latin" | "bangla";
  active: boolean;
}

// Filled from the users endpoint (M4).
const USERS: UserRow[] = [];

const ROLES: Role[] = ["inspector", "qc_supervisor", "store_incharge", "cutting_master", "merchandiser", "management", "admin"];

interface MachineRow {
  code: string;
  nameEn: string;
  nameBn: string;
  pxPerCm: number;
  viewPx: number;
  source: string;
  calibrated: string;
  status: "online" | "calibration_due";
}

// Filled from the machines endpoint (M4).
const MACHINES: MachineRow[] = [];

interface Profile {
  id: string;
  name: string;
  buyerEn: string;
  buyerBn: string;
  lengthBands: [number, number][]; // [max inches, points]; the last band is "longer than that"
  holeBands: [number, number][];
  continuousIn: number;
  selvageIn: number;
  failPts: number;
}

// The system's default 4-point rules (backend default rule profile); buyer profiles come from the
// rule-profiles endpoint (M4) and are added to this list.
const PROFILES: Profile[] = [
  {
    id: "default",
    name: "Default 4-point profile",
    buyerEn: "Any buyer without its own profile",
    buyerBn: "নিজস্ব প্রোফাইল নেই এমন যেকোনো বায়ার",
    lengthBands: [[3, 1], [6, 2], [9, 3], [Infinity, 4]],
    holeBands: [[1, 2], [Infinity, 4]],
    continuousIn: 36,
    selvageIn: 1.0,
    failPts: 40,
  },
];

const DETECTORS = [
  {
    nameEn: "Simulated Detector (rad-02)",
    nameBn: "সিমুলেটেড ডিটেক্টর (rad-02)",
    descEn: "Replays the answer key with realistic mistakes. Used for demos and the benchmark.",
    descBn: "বাস্তবসম্মত ভুলসহ উত্তর-চাবি চালায়। ডেমো ও বেঞ্চমার্কে ব্যবহৃত।",
    state: "active" as const,
    details: [["Mode", "—"], ["Seed", "—"], ["Latency", "—"]],
  },
  {
    nameEn: "Local Model (ONNX, CPU)",
    nameBn: "লোকাল মডেল (ONNX, CPU)",
    descEn: "Runs on the factory edge box with no internet. Model file not installed on this server.",
    descBn: "ইন্টারনেট ছাড়া ফ্যাক্টরির এজ বক্সে চলে। এই সার্ভারে মডেল ফাইল নেই।",
    state: "ready" as const,
    details: [["Runtime", "—"], ["Device", "CPU"], ["Model", "—"]],
  },
  {
    nameEn: "External API",
    nameBn: "এক্সটার্নাল API",
    descEn: "Sends frames to a hosted vision API. Needs an endpoint and key in the server config.",
    descBn: "হোস্টেড ভিশন API-তে ফ্রেম পাঠায়। সার্ভার কনফিগে এন্ডপয়েন্ট ও কী লাগবে।",
    state: "stub" as const,
    details: [["Endpoint", "—"], ["Key", "—"], ["Timeout", "—"]],
  },
];

type TestDefect = { kind: "length" | "hole"; inches: number; selvage: boolean };

function bandPoints(bands: [number, number][], inches: number): number {
  return (bands.find(([max]) => inches <= max) ?? bands[bands.length - 1])[1];
}

function defectPoints(p: Profile, d: TestDefect): { pts: number; noteEn: string; noteBn: string } {
  if (d.selvage) return { pts: 0, noteEn: `inside ${p.selvageIn}" selvage zone`, noteBn: `${p.selvageIn}" সেলভেজ এলাকার ভিতরে` };
  if (d.kind === "hole") return { pts: bandPoints(p.holeBands, d.inches), noteEn: "hole band", noteBn: "ছিদ্রের ধাপ" };
  if (d.inches >= p.continuousIn) {
    const yards = Math.ceil(d.inches / 36);
    return { pts: 4 * yards, noteEn: `continuous: 4 pts × ${yards} yd`, noteBn: `চলমান: ৪ পয়েন্ট × ${yards} গজ` };
  }
  return { pts: bandPoints(p.lengthBands, d.inches), noteEn: "length band", noteBn: "দৈর্ঘ্যের ধাপ" };
}

function bandLabel(bands: [number, number][]) {
  return bands.map(([max, pts], i) => (max === Infinity ? `>${bands[i - 1][0]}" → ${pts}` : `≤${max}" → ${pts}`));
}

export default function AdminPage() {
  const t = useTranslations();
  const bi = useBi();
  const { data: me } = useMe();
  const canManage = hasPerm(me, "users.manage");

  const [tab, setTab] = useState<TabId>("users");
  const [recalibrating, setRecalibrating] = useState<Set<string>>(new Set());
  const [users, setUsers] = useState<UserRow[]>(USERS);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<UserRow>({ name: "", username: "", role: "inspector", shift: "A", lang: "bn", digits: "bangla", active: true });

  const [profileId, setProfileId] = useState("default");
  const profile = PROFILES.find((p) => p.id === profileId) ?? PROFILES[0];
  const [defects, setDefects] = useState<TestDefect[]>([
    { kind: "length", inches: 2.5, selvage: false },
    { kind: "length", inches: 7, selvage: false },
    { kind: "hole", inches: 0.5, selvage: false },
  ]);
  const [rollYd, setRollYd] = useState(100);
  const [widthIn, setWidthIn] = useState(58);

  const scored = defects.map((d) => ({ ...d, ...defectPoints(profile, d) }));
  const totalPts = scored.reduce((s, d) => s + d.pts, 0);
  const per100 = rollYd > 0 && widthIn > 0 ? (totalPts * 3600) / (rollYd * widthIn) : 0;
  const passes = per100 <= profile.failPts;

  const tabs: { id: TabId; label: string }[] = [
    { id: "users", label: bi("Users & permissions", "ব্যবহারকারী ও অনুমতি") },
    { id: "machines", label: bi("Inspection machines", "ইন্সপেকশন মেশিন") },
    { id: "profiles", label: bi("Buyer rule profiles", "বায়ার রুল প্রোফাইল") },
    { id: "detectors", label: bi("Detector settings", "ডিটেক্টর সেটিংস") },
  ];

  function addUser() {
    if (!draft.name.trim() || !draft.username.trim()) return;
    setUsers((u) => [...u, { ...draft, name: draft.name.trim(), username: draft.username.trim() }]);
    setDraft({ name: "", username: "", role: "inspector", shift: "A", lang: "bn", digits: "bangla", active: true });
    setAdding(false);
  }

  return (
    <div className={`${screenRoot} space-y-4`}>
      <PageHeader title={t("nav.admin")} subtitle={t("placeholder.admin")} sample={false} />

      {!canManage && (
        <ViewOnlyNote>
          {bi(
            "View only: you can see how the plant is set up, but only an admin can change it.",
            "শুধু দেখার জন্য: প্ল্যান্টের সেটআপ দেখতে পারবেন, কিন্তু বদলাতে পারবেন শুধু অ্যাডমিন।",
          )}
        </ViewOnlyNote>
      )}

      <div role="tablist" aria-label={t("nav.admin")} className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {tabs.map((x) => (
          <button
            key={x.id}
            type="button"
            role="tab"
            aria-selected={tab === x.id}
            onClick={() => setTab(x.id)}
            className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-semibold transition ${
              tab === x.id ? "border-brand-teal text-brand-navy" : "border-transparent text-slate-500 hover:text-brand-navy"
            }`}
          >
            {x.label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <Card>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <CardTitle hint={bi(`${users.filter((u) => u.active).length} active accounts`, `${users.filter((u) => u.active).length}টি সক্রিয় অ্যাকাউন্ট`)}>
              {bi("Accounts", "অ্যাকাউন্ট")}
            </CardTitle>
            <button type="button" className={primaryBtn} disabled={!canManage || adding} onClick={() => setAdding(true)}>
              + {bi("Add user", "ব্যবহারকারী যোগ করুন")}
            </button>
          </div>

          {adding && (
            <div className="mb-4 grid grid-cols-1 gap-3 rounded-md border border-teal-500/30 bg-teal-500/5 p-3 sm:grid-cols-3 lg:grid-cols-6 lg:items-end">
              <Field label={bi("Full name", "পূর্ণ নাম")}>
                <input className={inputCls} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} autoFocus />
              </Field>
              <Field label={bi("Username", "ইউজারনেম")}>
                <input className={`${inputCls} font-mono`} value={draft.username} onChange={(e) => setDraft({ ...draft, username: e.target.value })} />
              </Field>
              <Field label={bi("Role", "ভূমিকা")}>
                <select className={inputCls} value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`roles.${r}`)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={bi("Shift", "শিফট")}>
                <select className={inputCls} value={draft.shift} onChange={(e) => setDraft({ ...draft, shift: e.target.value as UserRow["shift"] })}>
                  {["A", "B", "C", "General"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <Field label={bi("Language", "ভাষা")}>
                <select
                  className={inputCls}
                  value={draft.lang}
                  onChange={(e) => {
                    const lang = e.target.value as "en" | "bn";
                    setDraft({ ...draft, lang, digits: lang === "bn" ? "bangla" : "latin" });
                  }}
                >
                  <option value="bn">বাংলা (bn)</option>
                  <option value="en">English (en)</option>
                </select>
              </Field>
              <div className="flex gap-2">
                <button type="button" className={primaryBtn} onClick={addUser} disabled={!draft.name.trim() || !draft.username.trim()}>
                  {bi("Save", "সংরক্ষণ")}
                </button>
                <button type="button" className={ghostBtn} onClick={() => setAdding(false)}>
                  {bi("Cancel", "বাতিল")}
                </button>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-100 text-left text-slate-700">
                <tr>
                  <th className="px-3 py-2">{bi("Name", "নাম")}</th>
                  <th className="px-3 py-2">{bi("Username", "ইউজারনেম")}</th>
                  <th className="px-3 py-2">{bi("Role", "ভূমিকা")}</th>
                  <th className="px-3 py-2">{bi("Shift", "শিফট")}</th>
                  <th className="px-3 py-2">{bi("UI language", "ভাষা")}</th>
                  <th className="px-3 py-2">{bi("Digits", "অঙ্ক")}</th>
                  <th className="px-3 py-2">{bi("Status", "অবস্থা")}</th>
                </tr>
              </thead>
              <tbody>
                {!users.length && (
                  <tr>
                    <td colSpan={7} className="px-3 py-4 text-center text-sm text-slate-500">
                      {bi("No accounts loaded yet.", "এখনো কোনো অ্যাকাউন্ট লোড হয়নি।")}
                    </td>
                  </tr>
                )}
                {users.map((u, i) => (
                  <tr key={u.username} className="border-t border-slate-100">
                    <td className="px-3 py-2 whitespace-nowrap font-medium text-slate-800">{u.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-600">{u.username}</td>
                    <td className="px-3 py-2">
                      <Pill tone={u.role === "admin" ? "navy" : u.role === "inspector" ? "amber" : "teal"}>{t(`roles.${u.role}`)}</Pill>
                    </td>
                    <td className="px-3 py-2 font-mono">{u.shift}</td>
                    <td className="px-3 py-2 font-mono">{u.lang}</td>
                    <td className="px-3 py-2">{u.digits === "bangla" ? bi("Bangla (০১২)", "বাংলা (০১২)") : bi("Latin (012)", "ল্যাটিন (012)")}</td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        disabled={!canManage || u.username === me?.username}
                        onClick={() => setUsers((list) => list.map((x, j) => (j === i ? { ...x, active: !x.active } : x)))}
                        className="disabled:cursor-not-allowed"
                        title={canManage ? bi("Click to switch", "বদলাতে ক্লিক করুন") : undefined}
                      >
                        {u.active ? <Pill tone="emerald">{bi("Active", "সক্রিয়")}</Pill> : <Pill tone="slate">{bi("Disabled", "নিষ্ক্রিয়")}</Pill>}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === "machines" && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {!MACHINES.length && (
            <Card>
              <p className="text-sm text-slate-500">{bi("No machines loaded yet.", "এখনো কোনো মেশিন লোড হয়নি।")}</p>
            </Card>
          )}
          {MACHINES.map((m) => (
            <Card key={m.code}>
              <div className="mb-3 flex items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-xs text-slate-500">{m.code}</p>
                  <h2 className="text-base font-semibold text-brand-navy">{bi(m.nameEn, m.nameBn)}</h2>
                </div>
                {m.status === "online" ? (
                  <Pill tone="emerald">● {bi("Online", "চালু")}</Pill>
                ) : (
                  <Pill tone="amber">{bi("Calibration due", "ক্যালিব্রেশন বাকি")}</Pill>
                )}
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-slate-500">{bi("Pixels per cm", "প্রতি সেমি-তে পিক্সেল")}</dt>
                <dd className="font-mono text-slate-800">{m.pxPerCm.toFixed(1)}</dd>
                <dt className="text-slate-500">{bi("View width", "দৃশ্যের প্রস্থ")}</dt>
                <dd className="font-mono text-slate-800">{m.viewPx} px ({(m.viewPx / m.pxPerCm).toFixed(1)} cm)</dd>
                <dt className="text-slate-500">{bi("Default source", "ডিফল্ট উৎস")}</dt>
                <dd className="font-mono text-xs text-slate-800">{m.source}</dd>
                <dt className="text-slate-500">{bi("Last calibrated", "সর্বশেষ ক্যালিব্রেশন")}</dt>
                <dd className="font-mono text-slate-800">{m.calibrated}</dd>
              </dl>
              <div className="mt-4 flex items-center gap-2">
                {recalibrating.has(m.code) ? (
                  <Pill tone="teal">✓ {bi("Recalibration requested", "পুনঃক্যালিব্রেশনের অনুরোধ হয়েছে")}</Pill>
                ) : (
                  <button
                    type="button"
                    className={ghostBtn}
                    disabled={!canManage}
                    onClick={() => setRecalibrating((s) => new Set(s).add(m.code))}
                  >
                    {bi("Recalibrate", "পুনরায় ক্যালিব্রেট")}
                  </button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {tab === "profiles" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {PROFILES.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setProfileId(p.id)}
                className={`rounded-lg border bg-white p-4 text-left shadow-xs transition ${
                  p.id === profileId ? "border-brand-teal ring-2 ring-brand-teal/30" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <p className="font-semibold text-brand-navy">{p.name}</p>
                <p className="text-xs text-slate-500">{bi(p.buyerEn, p.buyerBn)}</p>
                <p className="mt-2 text-sm text-slate-700">
                  {bi("Fail above", "এর বেশি হলে ফেল")} <span className="font-mono font-semibold">{p.failPts}</span>{" "}
                  {bi("pts / 100 sq yd", "পয়েন্ট / ১০০ বর্গগজ")}
                </p>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardTitle hint={bi("4-point engine settings for this buyer.", "এই বায়ারের ৪-পয়েন্ট সেটিংস।")}>{profile.name}</CardTitle>
              <dl className="space-y-3 text-sm">
                <div>
                  <dt className="mb-1 text-slate-500">{bi("Length penalty bands", "দৈর্ঘ্যের পয়েন্ট ধাপ")}</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    {bandLabel(profile.lengthBands).map((b) => (
                      <span key={b} className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs">
                        {b} {bi("pt", "পয়েন্ট")}
                      </span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt className="mb-1 text-slate-500">{bi("Hole bands", "ছিদ্রের ধাপ")}</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    {bandLabel(profile.holeBands).map((b) => (
                      <span key={b} className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs">
                        {b} {bi("pt", "পয়েন্ট")}
                      </span>
                    ))}
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-3 border-t border-slate-100 pt-3">
                  <div>
                    <dt className="text-xs text-slate-500">{bi("Continuous defect", "চলমান ত্রুটি")}</dt>
                    <dd className="font-mono font-semibold text-slate-800">≥ {profile.continuousIn}&quot;</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">{bi("Selvage exclusion", "সেলভেজ বাদ")}</dt>
                    <dd className="font-mono font-semibold text-slate-800">{profile.selvageIn.toFixed(1)}&quot;</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">{bi("Fail threshold", "ফেল সীমা")}</dt>
                    <dd className="font-mono font-semibold text-red-600">{profile.failPts} / 100 yd²</dd>
                  </div>
                </div>
              </dl>
            </Card>

            <Card>
              <CardTitle hint={bi("Try sample defects against this profile.", "নমুনা ত্রুটি দিয়ে এই প্রোফাইল পরীক্ষা করুন।")}>
                {bi("Test profile", "প্রোফাইল পরীক্ষা")}
              </CardTitle>
              <div className="mb-3 grid grid-cols-2 gap-3">
                <Field label={bi("Roll length (yd)", "রোলের দৈর্ঘ্য (গজ)")}>
                  <input type="number" min={1} className={`${inputCls} font-mono`} value={rollYd} onChange={(e) => setRollYd(Number(e.target.value) || 0)} />
                </Field>
                <Field label={bi("Width (in)", "প্রস্থ (ইঞ্চি)")}>
                  <input type="number" min={1} className={`${inputCls} font-mono`} value={widthIn} onChange={(e) => setWidthIn(Number(e.target.value) || 0)} />
                </Field>
              </div>
              <ul className="space-y-2">
                {scored.map((d, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                    <select
                      aria-label={bi("Defect kind", "ত্রুটির ধরন")}
                      className={inputCls.replace("w-full", "w-28")}
                      value={d.kind}
                      onChange={(e) => setDefects((l) => l.map((x, j) => (j === i ? { ...x, kind: e.target.value as TestDefect["kind"] } : x)))}
                    >
                      <option value="length">{bi("Length", "দৈর্ঘ্য")}</option>
                      <option value="hole">{bi("Hole", "ছিদ্র")}</option>
                    </select>
                    <input
                      aria-label={bi("Size in inches", "ইঞ্চিতে মাপ")}
                      type="number"
                      min={0}
                      step={0.25}
                      className={`${inputCls.replace("w-full", "w-24")} font-mono`}
                      value={d.inches}
                      onChange={(e) => setDefects((l) => l.map((x, j) => (j === i ? { ...x, inches: Number(e.target.value) || 0 } : x)))}
                    />
                    <span className="text-slate-500">in</span>
                    <label className="inline-flex items-center gap-1 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        checked={d.selvage}
                        onChange={(e) => setDefects((l) => l.map((x, j) => (j === i ? { ...x, selvage: e.target.checked } : x)))}
                      />
                      {bi("selvage", "সেলভেজ")}
                    </label>
                    <span className="ml-auto text-right">
                      <span className="font-mono font-semibold text-brand-navy">{d.pts} pt</span>
                      <span className="block text-xs text-slate-500">{bi(d.noteEn, d.noteBn)}</span>
                    </span>
                    <button
                      type="button"
                      aria-label={bi("Remove", "সরান")}
                      className="rounded px-1.5 text-slate-400 hover:bg-slate-100 hover:text-red-600"
                      onClick={() => setDefects((l) => l.filter((_, j) => j !== i))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className={`${ghostBtn} mt-3`}
                onClick={() => setDefects((l) => [...l, { kind: "length", inches: 1, selvage: false }])}
              >
                + {bi("Add defect", "ত্রুটি যোগ করুন")}
              </button>
              <div
                className={`mt-4 flex flex-wrap items-center justify-between gap-2 rounded-md px-3 py-2 ${
                  passes ? "bg-emerald-500/10 text-emerald-800" : "bg-red-500/10 text-red-700"
                }`}
              >
                <span className="text-sm">
                  {bi("Total", "মোট")} <span className="font-mono font-semibold">{totalPts} pt</span> →{" "}
                  <span className="font-mono font-semibold">{per100.toFixed(2)}</span> / 100 yd²
                </span>
                <span className={`rounded px-2 py-0.5 text-xs font-bold text-white ${passes ? "bg-emerald-500" : "bg-red-500"}`}>
                  {passes ? bi("PASS", "পাস") : bi("FAIL", "ফেল")}
                </span>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                {bi("Points per 100 sq yd = total points × 3600 ÷ (yards × width in inches).", "প্রতি ১০০ বর্গগজে পয়েন্ট = মোট পয়েন্ট × ৩৬০০ ÷ (গজ × ইঞ্চিতে প্রস্থ)।")}
              </p>
            </Card>
          </div>
        </div>
      )}

      {tab === "detectors" && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {DETECTORS.map((d) => (
            <Card key={d.nameEn} className={d.state === "active" ? "border-brand-teal ring-2 ring-brand-teal/20" : ""}>
              <div className="mb-2 flex items-start justify-between gap-2">
                <h2 className="text-base font-semibold text-brand-navy">{bi(d.nameEn, d.nameBn)}</h2>
                {d.state === "active" ? (
                  <Pill tone="emerald">● {bi("Active", "সক্রিয়")}</Pill>
                ) : d.state === "ready" ? (
                  <Pill tone="teal">{bi("Ready for edge", "এজের জন্য প্রস্তুত")}</Pill>
                ) : (
                  <Pill tone="slate">{bi("Stub · not configured", "স্টাব · কনফিগার হয়নি")}</Pill>
                )}
              </div>
              <p className="mb-3 text-sm text-slate-600">{bi(d.descEn, d.descBn)}</p>
              <dl className="grid grid-cols-2 gap-y-1 text-sm">
                {d.details.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-slate-500">{k}</dt>
                    <dd className="font-mono text-xs text-slate-800">{v}</dd>
                  </div>
                ))}
              </dl>
              {d.state === "active" && (
                <p className="mt-3 rounded bg-amber-500/10 px-2 py-1 text-xs font-semibold text-brand-amber">
                  {bi("Simulated: not real AI.", "সিমুলেটেড: আসল AI নয়।")}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
