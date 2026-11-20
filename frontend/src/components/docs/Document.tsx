"use client";
import Image from "next/image";
import { useLocale } from "next-intl";
import type { components } from "@/lib/api/schema";
export type Config = components["schemas"]["DocsConfig"];
export type DocumentData = components["schemas"]["DocsDocument"];
export function Document({ data }: { data: DocumentData }) {
  const locale = useLocale() === "bn" ? "bn" : "en";
  const c = data.content;
  return (
    <article className="mx-auto max-w-6xl space-y-8 p-5 sm:p-10">
      <header className="rounded-2xl bg-teal-950 p-8 text-white">
        <p className="text-teal-200">{c.team_name}</p>
        <h1 className="my-3 text-4xl font-bold">{c.project_name}</h1>
        <p className="text-xl">{c.tagline[locale]}</p>
        <div className="mt-6 flex flex-wrap gap-4">
          <a className="underline" href={c.app_url}>
            Open app ↗
          </a>
          <a className="underline" href={c.repository_url}>
            GitHub ↗
          </a>
          {c.video_url && (
            <a
              className="underline"
              href={c.video_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Presentation video ↗
            </a>
          )}
        </div>
      </header>
      <nav
        aria-label="Documentation sections"
        className="flex flex-wrap gap-3 text-sm"
      >
        {c.sections
          .filter((s) => s.visible)
          .map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="rounded border border-slate-300 px-3 py-2"
            >
              {s.title[locale]}
            </a>
          ))}
        <a href="#live">Live</a>
        <a href="#team">Team</a>
        <a href="#apis">APIs</a>
      </nav>
      <p className="text-sm text-slate-500">
        {locale === "bn"
          ? "প্রকল্পের বিবরণ সম্পাদনাযোগ্য; নিচের Live অংশ বর্তমান সিস্টেম থেকে আসে।"
          : "Project narrative is authored content; the live panel below is computed from current system data."}
      </p>
      <div className="grid gap-5 md:grid-cols-2">
        {c.sections
          .filter((s) => s.visible)
          .map((s) => (
            <section
              id={s.id}
              key={s.id}
              className={`scroll-mt-5 rounded-xl border border-slate-300 p-6 ${s.diagram ? "md:col-span-2" : ""}`}
            >
              <h2 className="mb-3 text-xl font-semibold">{s.title[locale]}</h2>
              <p className="whitespace-pre-wrap leading-7">{s.body[locale]}</p>
              {s.diagram && (
                <div role="img" aria-label={s.title[locale]} className="mt-5">
                  <ol
                    className={`grid gap-3 ${s.diagram === "architecture" ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}
                  >
                    {(s.steps ?? []).map((step, i) => (
                      <li
                        className="rounded-lg border border-teal-500 bg-teal-500/10 p-4"
                        key={i}
                      >
                        <strong className="mr-2 text-teal-600">{i + 1}</strong>
                        {step[locale]}
                      </li>
                    ))}
                  </ol>
                  <p className="mt-3 font-mono text-sm">
                    {s.diagram === "architecture"
                      ? "1 → 2 → 3 · 2 → 4"
                      : (s.steps ?? []).map((_, i) => i + 1).join(" → ")}
                  </p>
                </div>
              )}
            </section>
          ))}
      </div>
      {data.live && (
        <section id="live" className="rounded-xl border border-teal-500 p-6">
          <h2 className="text-2xl font-bold">
            {locale === "bn" ? "বর্তমান সিস্টেম" : "Live system"}
          </h2>
          <p className="mt-2 text-sm">
            {new Date(data.live.generated_at).toLocaleString(locale)} ·{" "}
            {data.live.profile} · {data.live.version}
          </p>
          <p className="my-3">
            Database: {data.live.database} · Worker:{" "}
            {data.live.worker_alive ? "Online" : "Not connected"} · Detector:{" "}
            {data.live.active_provider} (
            {data.live.detector_is_simulated
              ? "answer-key simulation"
              : "trained model configured"}
            )
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries({
              Rolls: data.live.registered_rolls,
              Inspections: data.live.inspections,
              Finalized: data.live.finalized_inspections,
              "Active accounts": data.live.active_users,
              "Audit events": data.live.audit_events,
              "Simulated footage": data.live.simulated_video_inspections,
            }).map(([k, v]) => (
              <div key={k} className="rounded bg-teal-500/10 p-4">
                <strong className="block text-2xl">{v}</strong>
                {k}
              </div>
            ))}
          </div>
          <p className="mt-3 text-sm">
            {locale === "bn"
              ? "Demo-সহ সামগ্রিক রেকর্ড; কারখানার impact নয়। Detector configuration বাস্তব inference সফল হওয়ার প্রমাণ নয়।"
              : "Aggregate records include demos; these are not factory-impact measurements. Detector configuration is not a live inference attestation."}
          </p>
          <p className="mt-3 text-sm">
            {Object.entries(data.live.runtime)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ")}
          </p>
        </section>
      )}
      {c.show_team && (c.members ?? []).length > 0 && (
        <section id="team">
          <h2 className="mb-5 text-2xl font-bold">{c.team_name}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(c.members ?? []).map((m) => (
              <div
                key={m.id}
                className="rounded-xl border border-slate-300 p-5"
              >
                {m.image_data ? (
                  <Image unoptimized
                    src={m.image_data}
                    alt={m.name}
                    width={80}
                    height={80}
                    className="mb-3 h-20 w-20 rounded-full object-cover"
                  />
                ) : (
                  <div
                    aria-hidden
                    className="mb-3 flex h-20 w-20 items-center justify-center rounded-full bg-teal-600 text-2xl text-white"
                  >
                    {m.name
                      .split(" ")
                      .map((w) => w[0])
                      .slice(0, 2)
                      .join("")}
                  </div>
                )}
                <h3 className="font-semibold">{m.name}</h3>
                <p className="my-2">{m.role[locale]}</p>
                <a
                  className="break-all text-sm text-teal-600 underline"
                  href={`mailto:${m.email}`}
                >
                  {m.email}
                </a>
              </div>
            ))}
          </div>
        </section>
      )}
      {c.show_apis && (
        <section id="apis">
          <h2 className="mb-3 text-2xl font-bold">Live API inventory</h2>
          <div className="max-h-96 overflow-auto rounded border border-slate-300">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th className="p-3">Method</th>
                  <th>Path</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {(data.apis ?? []).map((r) => (
                  <tr
                    key={r.path + r.methods.join()}
                    className="border-t border-slate-300"
                  >
                    <td className="p-3">{r.methods.join(", ")}</td>
                    <td className="font-mono">{r.path}</td>
                    <td className="p-3">{r.access}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </article>
  );
}
