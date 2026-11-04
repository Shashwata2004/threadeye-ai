"use client";

import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMe, useProviders, useMasterData } from "@/lib/api/hooks";
import { hasPerm, type Role } from "@/lib/api/client";
import { PermissionNotice } from "@/components/PermissionNotice";
import { request, type User, type MachineDetail, type Profile, type Rules } from "@/lib/api/operations";
import { Card, CardTitle, Field, PageHeader, inputCls, primaryBtn, ghostBtn, screenRoot, useBi } from "@/components/screenKit";

const ROLES: Role[] = ["inspector", "qc_supervisor", "store_incharge", "cutting_master", "merchandiser", "management", "admin"];

export default function AdminPage() {
  const bi = useBi();
  const {data: me} = useMe();
  const canUsers = hasPerm(me, "users.manage");
  const canMachines = hasPerm(me, "machines.manage");
  const canProfiles = hasPerm(me, "profiles.write");
  const client = useQueryClient();
  const [tabChoice, setTab] = useState<string | null>(null);
  const tab = tabChoice ?? (canUsers ? "users" : canMachines ? "machines" : canProfiles ? "profiles" : hasPerm(me, "providers.manage") ? "detectors" : "sample");
  const tabAllowed = ({users: canUsers, machines: canMachines, profiles: hasPerm(me, "profiles.read"),
    detectors: hasPerm(me, "master_data.read"), sample: hasPerm(me, "settings.manage")} as Record<string, boolean>)[tab];
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const users = useQuery({queryKey: ["admin-users"], enabled: canUsers,
    queryFn: () => request<User[]>("/api/v1/users")});
  const machines = useQuery({queryKey: ["admin-machines"], enabled: canMachines,
    queryFn: () => request<MachineDetail[]>("/api/v1/admin/machines")});
  const profiles = useQuery({queryKey: ["admin-profiles"], enabled: hasPerm(me, "profiles.read"),
    queryFn: () => request<Profile[]>("/api/v1/admin/rule-profiles")});
  const {buyers} = useMasterData();
  const {data: providers} = useProviders();
  const archiveSchedule = useQuery({queryKey: ["demo-archive-schedule"], enabled: hasPerm(me, "settings.manage"),
    queryFn: () => request<{enabled: boolean; start_date?: string}>("/api/v1/admin/demo-archive/schedule")});
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("inspector");
  const [machineId, setMachineId] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [active, setActive] = useState(true);
  const [px, setPx] = useState("");
  const [viewPx, setViewPx] = useState("");
  const [profileId, setProfileId] = useState("");
  const [rulesText, setRulesText] = useState("");
  const [buyer, setBuyer] = useState("");
  const [length, setLength] = useState(100);
  const [width, setWidth] = useState(60);
  const [defectLength, setDefectLength] = useState(4);
  const [preview, setPreview] = useState<{points: number; per_100: number; verdict: string; explanation: string[]}|null>(null);

  async function action(work: () => Promise<unknown>, persist = true) {
    setBusy(true); setError(""); setNotice("");
    try { await work(); setNotice(persist ? bi("Saved on the server.", "সার্ভারে সংরক্ষিত হয়েছে।") : bi("Preview computed.", "সম্ভাব্য ফল গণনা হয়েছে।")); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function addUser(e: FormEvent) {
    e.preventDefault();
    await action(async () => {
      await request("/api/v1/users", {username, display_name: displayName, role, password});
      setPassword(""); setUsername(""); setDisplayName("");
      await client.invalidateQueries({queryKey: ["admin-users"]});
    });
  }
  async function saveMachine(e: FormEvent) {
    e.preventDefault();
    await action(async () => {
      await request(`/api/v1/admin/machines${machineId ? `/${machineId}` : ""}`, {code, name, active,
        calibration: px && viewPx ? {px_per_cm: +px, view_width_px: +viewPx, note: ""} : null}, machineId ? "PATCH" : "POST");
      await client.invalidateQueries({queryKey: ["admin-machines"]});
      await client.invalidateQueries({queryKey: ["machines"]});
    });
  }
  function selectProfile(id: string) {
    setProfileId(id); setPreview(null);
    const profile = profiles.data?.find((p) => p.id === id);
    if (profile) { setRulesText(JSON.stringify(profile.rules, null, 2)); setBuyer(profile.buyer_id ?? ""); }
  }
  const current = profiles.data?.find((p) => p.id === profileId);
  let parsedRules: Rules | null = null;
  try { parsedRules = JSON.parse(rulesText) as Rules; } catch { /* Keep invalid edits visible for correction. */ }
  function changeRule(field: keyof Rules, value: string | number) {
    if (parsedRules) setRulesText(JSON.stringify({...parsedRules, [field]: value}, null, 2));
  }
  return <div className={`${screenRoot} space-y-4`}>
    <PageHeader title={bi("Administration", "অ্যাডমিন")} sample={false}
      subtitle={bi("Server-backed users, machines and versioned buyer rules.", "ব্যবহারকারী, মেশিন ও বায়ারের নিয়ম সার্ভারে সংরক্ষণ করুন।")}/>
    <nav className="flex flex-wrap gap-2">{[
      ["users", bi("Users", "ব্যবহারকারী")], ["machines", bi("Machines", "মেশিন")],
      ["profiles", bi("Buyer rules", "বায়ারের নিয়ম")], ["detectors", bi("Detectors", "শনাক্তকারী")],
      ["sample", bi("Sample data", "নমুনা তথ্য")],
    ].map(([id, label]) => <button key={id} className={tab === id ? primaryBtn : ghostBtn} onClick={() => setTab(id)}>{label}</button>)}</nav>
    {error && <p role="alert" className="text-red-600">{error}</p>}
    {notice && <p role="status" className="text-emerald-600">{notice}</p>}
    {!tabAllowed && <PermissionNotice title={bi("Your account cannot view this administration section.", "অ্যাডমিনের এই অংশ দেখার অনুমতি আপনার অ্যাকাউন্টে নেই।")}/>}
    {(users.isError || machines.isError || profiles.isError) && <p role="alert">{bi("Some records could not be loaded.", "কিছু তথ্য আনা যায়নি।")}</p>}
    {tab === "users" && tabAllowed && <Card><CardTitle>{bi("Accounts", "অ্যাকাউন্ট")}</CardTitle>
      {canUsers ? <>
        <form onSubmit={addUser} className="mb-5 grid gap-3 sm:grid-cols-2">
          <Field label={bi("Username", "ইউজারনেম")}><input required minLength={3} pattern="[a-z0-9_.-]+" className={inputCls} value={username} onChange={(e) => setUsername(e.target.value)}/></Field>
          <Field label={bi("Display name", "নাম")}><input required className={inputCls} value={displayName} onChange={(e) => setDisplayName(e.target.value)}/></Field>
          <Field label={bi("Initial password (10+ characters)", "প্রথম পাসওয়ার্ড (১০+ অক্ষর)")}><input required type="password" autoComplete="new-password" minLength={10} className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)}/></Field>
          <Field label={bi("Role", "ভূমিকা")}><select className={inputCls} value={role} onChange={(e) => setRole(e.target.value as Role)}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></Field>
          <button disabled={busy} className={primaryBtn}>{bi("Create account", "অ্যাকাউন্ট তৈরি")}</button>
        </form>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>{bi("User", "ব্যবহারকারী")}</th><th>{bi("Role", "ভূমিকা")}</th><th>{bi("Status", "অবস্থা")}</th></tr></thead><tbody>
          {users.data?.map((u) => <tr key={u.id} className="border-t border-slate-300"><td className="py-3">{u.display_name} · {u.username}</td><td>
            <select aria-label={`${u.username} ${bi("role", "ভূমিকা")}`} className={inputCls} value={u.role} disabled={busy || u.id === me?.id}
              onChange={(e) => void action(async () => {await request(`/api/v1/users/${u.id}`, {role: e.target.value}, "PATCH"); await users.refetch();})}>
              {ROLES.map((r) => <option key={r}>{r}</option>)}</select></td><td><button disabled={busy || u.id === me?.id} className={ghostBtn}
              onClick={() => void action(async () => {await request(`/api/v1/users/${u.id}`, {active: !u.active}, "PATCH"); await users.refetch();})}>
              {u.active ? bi("Active · disable", "সক্রিয় · বন্ধ করুন") : bi("Disabled · enable", "বন্ধ · চালু করুন")}</button></td></tr>)}
        </tbody></table></div>
      </> : <p>{bi("User management permission is required.", "ব্যবহারকারী পরিচালনার অনুমতি প্রয়োজন।")}</p>}
    </Card>}
    {tab === "machines" && tabAllowed && <Card><CardTitle>{bi("Machines and calibration", "মেশিন ও ক্যালিব্রেশন")}</CardTitle>
      {canMachines ? <>
        <select aria-label={bi("Edit machine", "মেশিন সম্পাদনা")} className={`${inputCls} mb-4`} value={machineId} onChange={(e) => {
          const m = machines.data?.find((x) => x.id === e.target.value); setMachineId(e.target.value);
          setCode(m?.code ?? ""); setName(m?.name ?? ""); setActive(m?.active ?? true);
          setPx(m?.calibration?.px_per_cm.toString() ?? ""); setViewPx(m?.calibration?.view_width_px.toString() ?? "");
        }}><option value="">{bi("New machine", "নতুন মেশিন")}</option>{machines.data?.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}</select>
        <form onSubmit={saveMachine} className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("Code", "কোড")}><input required pattern="[A-Za-z0-9_-]+" className={inputCls} value={code} onChange={(e) => setCode(e.target.value)}/></Field>
          <Field label={bi("Name", "নাম")}><input required className={inputCls} value={name} onChange={(e) => setName(e.target.value)}/></Field>
          <Field label={bi("Measured pixels / cm (optional)", "মাপা পিক্সেল / সেমি (ঐচ্ছিক)")}><input type="number" min={0.001} step="any" required={!!viewPx} className={inputCls} value={px} onChange={(e) => setPx(e.target.value)}/></Field>
          <Field label={bi("View width in pixels", "দৃশ্যের প্রস্থ পিক্সেলে")}><input type="number" min={1} max={16384} required={!!px} className={inputCls} value={viewPx} onChange={(e) => setViewPx(e.target.value)}/></Field>
          <label><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)}/> {bi("Active", "সক্রিয়")}</label>
          <button disabled={busy} className={primaryBtn}>{bi("Save machine", "মেশিন সংরক্ষণ")}</button>
        </form>
        <p className="mt-3 text-sm text-slate-500">{bi("Calibration is recorded for the machine. Simulated video retains its own known geometry.", "ক্যালিব্রেশন মেশিনের তথ্য হিসেবে থাকবে। সিমুলেটেড ভিডিওর নিজস্ব মাপ অপরিবর্তিত থাকে।")}</p>
      </> : <p>{bi("Machine management permission is required.", "মেশিন পরিচালনার অনুমতি প্রয়োজন।")}</p>}
    </Card>}
    {tab === "profiles" && tabAllowed && <Card><CardTitle>{bi("Versioned buyer rules and preview", "বায়ারের নিয়মের সংস্করণ ও প্রিভিউ")}</CardTitle>
      <select className={`${inputCls} mb-3`} aria-label={bi("Rule profile", "রুল প্রোফাইল")} value={profileId} onChange={(e) => selectProfile(e.target.value)}>
        <option value="">{bi("Select a profile", "প্রোফাইল বাছুন")}</option>{profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name} · v{p.version} · {p.status}</option>)}
      </select>
      {current && <div className="space-y-3">
        {parsedRules && <div className="grid gap-3 sm:grid-cols-2">
          <Field label={bi("Profile name", "প্রোফাইলের নাম")}><input className={inputCls} disabled={!canProfiles} value={parsedRules.name ?? ""}
            onChange={(e) => changeRule("name", e.target.value)}/></Field>
          <Field label={bi("Fail threshold / 100 sq yd", "প্রতি ১০০ বর্গগজে ফেল সীমা")}><input type="number" min={0.01} step="any" className={inputCls}
            disabled={!canProfiles} value={parsedRules.threshold_per_100 ?? 40} onChange={(e) => changeRule("threshold_per_100", +e.target.value)}/></Field>
          <Field label={bi("Width basis", "প্রস্থের ভিত্তি")}><select disabled={!canProfiles} className={inputCls} value={parsedRules.width_basis ?? "declared"}
            onChange={(e) => changeRule("width_basis", e.target.value)}><option value="declared">{bi("Declared", "ঘোষিত")}</option>
            <option value="measured">{bi("Measured", "মাপা")}</option><option value="cuttable">{bi("Cuttable (excluding edges)", "কাটার উপযোগী (কিনারা বাদ)")}</option></select></Field>
          <Field label={bi("Length basis", "দৈর্ঘ্যের ভিত্তি")}><select disabled={!canProfiles} className={inputCls} value={parsedRules.length_basis ?? "inspected"}
            onChange={(e) => changeRule("length_basis", e.target.value)}><option value="inspected">{bi("Inspected", "পরীক্ষিত")}</option>
            <option value="declared">{bi("Source / recorded length", "উৎস / সংরক্ষিত দৈর্ঘ্য")}</option></select></Field>
        </div>}
        <Field label={bi("Buyer", "বায়ার")}><select className={inputCls} disabled={!canProfiles} value={buyer} onChange={(e) => setBuyer(e.target.value)}>
          <option value="">{bi("Any buyer", "সব বায়ার")}</option>{buyers.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
        <Field label={bi("Rules (validated JSON)", "নিয়ম (যাচাইকৃত JSON)")}><textarea className={`${inputCls} font-mono`} rows={18} readOnly={!canProfiles} value={rulesText} onChange={(e) => setRulesText(e.target.value)}/></Field>
        <p className="text-sm text-slate-500">{bi("Saving creates a new version. Existing lots keep their original profile. Change the name to create a separate profile.", "সংরক্ষণে নতুন সংস্করণ তৈরি হবে। পুরোনো চালানে আগের নিয়ম থাকবে। আলাদা প্রোফাইল তৈরি করতে নাম বদলান।")}</p>
        {canProfiles && <button disabled={busy} className={primaryBtn} onClick={() => void action(async () => {
          await request("/api/v1/admin/rule-profiles", {buyer_id: buyer || null, rules: JSON.parse(rulesText) as Rules});
          await profiles.refetch(); await client.invalidateQueries({queryKey: ["rule-profiles"]});
        })}>{bi("Save as new version", "নতুন সংস্করণ সংরক্ষণ")}</button>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={bi("Roll length (yd)", "রোলের দৈর্ঘ্য (গজ)")}><input type="number" min={1} className={inputCls} value={length} onChange={(e) => setLength(+e.target.value)}/></Field>
          <Field label={bi("Width (in)", "প্রস্থ (ইঞ্চি)")}><input type="number" min={1} className={inputCls} value={width} onChange={(e) => setWidth(+e.target.value)}/></Field>
          <Field label={bi("Test stain size (in)", "পরীক্ষার দাগের মাপ (ইঞ্চি)")}><input type="number" min={0.01} step="any" className={inputCls} value={defectLength} onChange={(e) => setDefectLength(+e.target.value)}/></Field>
        </div>
        <button className={ghostBtn} disabled={busy} onClick={() => void action(async () => {
          const result = await request<NonNullable<typeof preview>>("/api/v1/admin/rule-profiles/preview", {
            rules: JSON.parse(rulesText), length_yd: length, width_in: width,
            defects: [{cls: "stain", start_yd: 0, end_yd: defectLength / 36, length_in: defectLength,
              across_start_cm: width * 2.54 / 2, across_end_cm: width * 2.54 / 2 + 0.1}]}); setPreview(result);
        }, false)}>{bi("What-if preview", "সম্ভাব্য ফল দেখুন")}</button>
        {preview && <div data-testid="profile-preview">{preview.points} pt · {preview.per_100.toFixed(2)} /100 · {preview.verdict}<p>{preview.explanation.join(" · ")}</p></div>}
      </div>}
    </Card>}
    {tab === "detectors" && tabAllowed && <Card><CardTitle>{bi("Installed detector configuration", "ইনস্টল করা শনাক্তকারীর অবস্থা")}</CardTitle>
      {providers?.map((p) => <div key={p.provider_id} className="mb-3 rounded border border-slate-300 p-3"><strong>{p.display_name}</strong>
        <p>{p.active ? bi("Active", "সক্রিয়") : bi("Inactive", "নিষ্ক্রিয়")} · {p.availability}</p><p className="text-sm">{p.note}</p>
        {hasPerm(me, "providers.manage") && !p.active && p.availability === "available" && <button disabled={busy} className={ghostBtn}
          onClick={() => void action(async () => {await request("/api/v1/admin/provider", {provider_id: p.provider_id}, "PUT");
            await client.invalidateQueries({queryKey: ["providers"]}); await client.invalidateQueries({queryKey: ["health"]});
            await client.invalidateQueries({queryKey: ["system-status"]});})}>{bi("Use for new inspections", "নতুন পরীক্ষায় ব্যবহার করুন")}</button>}
        </div>)}
      <p>{bi("Changes apply to new inspections on this deployment; open inspections keep their original detector. Cloud and edge defaults are separate.", "এই সার্ভারের নতুন পরীক্ষায় পরিবর্তন কার্যকর হবে; খোলা পরীক্ষায় আগের শনাক্তকারী থাকবে। ক্লাউড ও এজের সেটিংস আলাদা।")}</p>
    </Card>}
    {tab === "sample" && tabAllowed && <Card><CardTitle>{bi("Archive demo deliveries", "ডেমো চালান আর্কাইভ")}</CardTitle>
      <p className="mb-3 text-sm">{bi("Archiving hides SAMPLE deliveries from current lists and scorecards and aborts their open inspections. Reports and audit history are retained; unmarked real deliveries are untouched.",
        "আর্কাইভ করলে নমুনা চালান বর্তমান তালিকা ও স্কোরকার্ড থেকে সরবে এবং তাদের খোলা পরীক্ষা বন্ধ হবে। রিপোর্ট ও অডিট ইতিহাস থাকবে; বাস্তব চালান বদলাবে না।")}</p>
      {hasPerm(me, "settings.manage") ? <div className="space-y-3">
        <button className={ghostBtn} disabled={busy} onClick={() => void action(async () => {
          await request("/api/v1/admin/demo-archive", {}); await client.invalidateQueries({queryKey: ["lots"]});
          await client.invalidateQueries({queryKey: ["dashboard"]});
        })}>{bi("Archive sample deliveries now", "এখন নমুনা চালান আর্কাইভ করুন")}</button>
        <p>{archiveSchedule.data?.enabled ? bi("Nightly archive enabled from ", "রাতের আর্কাইভ চালু হবে: ") + archiveSchedule.data.start_date : bi("Nightly archive is off.", "রাতের আর্কাইভ বন্ধ আছে।")}</p>
        <button className={ghostBtn} disabled={busy} onClick={() => void action(async () => {
          await request("/api/v1/admin/demo-archive/schedule", {enabled: !archiveSchedule.data?.enabled}, "PUT");
          await archiveSchedule.refetch();
        })}>{archiveSchedule.data?.enabled ? bi("Disable nightly archive", "রাতের আর্কাইভ বন্ধ করুন") : bi("Enable nightly archive", "রাতের আর্কাইভ চালু করুন")}</button>
        <p className="text-sm text-slate-500">{bi("When enabled, the edge worker archives samples once per Dhaka day after 03:00, starting tomorrow. It is off by default.",
          "চালু করলে আগামীকাল থেকে এজ worker ঢাকার সময় রাত ৩টার পরে প্রতিদিন একবার নমুনা চালান আর্কাইভ করবে। শুরুতে বন্ধ থাকে।")}</p>
      </div> : <p>{bi("Settings permission is required.", "সেটিংস পরিবর্তনের অনুমতি প্রয়োজন।")}</p>}
    </Card>}
  </div>;
}
