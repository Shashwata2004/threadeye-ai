"use client";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMe } from "@/lib/api/hooks";
import { hasPerm } from "@/lib/api/client";
import {
  Document,
  type Config,
  type DocumentData,
} from "@/components/docs/Document";
import {
  Card,
  Field,
  PageHeader,
  inputCls,
  primaryBtn,
  useBi,
} from "@/components/screenKit";

type Text = { en: string; bn: string };
function TextFields({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Text;
  onChange: (v: Text) => void;
}) {
  return (
    <fieldset className="grid gap-2 sm:grid-cols-2">
      <legend className="mb-1 font-medium">{label}</legend>
      {(["en", "bn"] as const).map((lang) => (
        <label key={lang} className="text-sm">
          {lang}
          <textarea
            className={inputCls}
            rows={3}
            value={value[lang]}
            onChange={(e) => onChange({ ...value, [lang]: e.target.value })}
          />
        </label>
      ))}
    </fieldset>
  );
}
export default function DocsAdmin() {
  const bi = useBi();
  const { data: me } = useMe();
  const allowed = hasPerm(me, "settings.manage");
  const client = useQueryClient();
  const [draft, setDraft] = useState<Config | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPreview, setPreview] = useState(false);
  const q = useQuery({
    queryKey: ["docs-admin"],
    enabled: allowed,
    queryFn: async () => {
      const r = await fetch("/api/v1/documentation/admin", {
        cache: "no-store",
      });
      if (!r.ok) throw new Error("Could not load documentation settings");
      return r.json() as Promise<Config>;
    },
  });
  const preview = useQuery({
    queryKey: ["docs-preview"],
    enabled: allowed && showPreview,
    queryFn: async () => {
      const r = await fetch("/api/v1/documentation/preview", {
        cache: "no-store",
      });
      if (!r.ok) throw new Error("Preview unavailable");
      return r.json() as Promise<DocumentData>;
    },
  });
  const c = draft ?? q.data;
  const change = (v: Partial<Config>) => {
    if (c) setDraft({ ...c, ...v });
  };
  async function save() {
    if (!c) return;
    setBusy(true);
    setNotice("");
    try {
      const r = await fetch("/api/v1/documentation/admin", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(c),
      });
      if (!r.ok) {
        const v = await r.json();
        throw new Error(
          typeof v.detail === "string" ? v.detail : JSON.stringify(v.detail),
        );
      }
      const v = (await r.json()) as Config;
      setDraft(null);
      client.setQueryData(["docs-admin"], v);
      await client.invalidateQueries({ queryKey: ["docs-preview"] });
      setNotice(
        bi(
          "Saved. Published changes apply immediately.",
          "সংরক্ষিত। প্রকাশিত পাতায় পরিবর্তন কার্যকর হয়েছে।",
        ),
      );
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function portrait(file: File, index: number) {
    if (!c) return;
    try {
      if (file.size > 5_000_000)
        throw new Error("Use an image smaller than 5 MB");
      const image = await createImageBitmap(file);
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 256 / Math.max(image.width, image.height));
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Image resizing unavailable");
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      image.close();
      change({
        members: (c.members ?? []).map((m, i) =>
          i === index
            ? { ...m, image_data: canvas.toDataURL("image/jpeg", 0.8) }
            : m,
        ),
      });
    } catch (e) {
      setNotice(String(e));
    }
  }
  if (!me) return <p>Loading…</p>;
  if (!allowed)
    return (
      <p role="note">
        {bi(
          "Only admins can manage public documentation.",
          "শুধু অ্যাডমিন public docs পরিচালনা করতে পারেন।",
        )}
      </p>
    );
  if (!c)
    return (
      <p role="status">
        {q.isError ? "Documentation settings could not be loaded." : "Loading…"}
      </p>
    );
  return (
    <div className="space-y-5">
      <PageHeader
        title={bi("Public documentation", "Public documentation")}
        sample={false}
        subtitle={bi(
          "Edit content, team and publication settings.",
          "বিবরণ, দল ও প্রকাশনা নিয়ন্ত্রণ করুন।",
        )}
      />
      <div className="flex flex-wrap gap-3">
        <Link href="/admin" className="underline">
          ← Admin
        </Link>
        <Link href="/docs" target="_blank" className="underline">
          Open /docs ↗
        </Link>
        <button className={primaryBtn} disabled={busy} onClick={save}>
          {busy ? "Saving…" : bi("Save documentation", "Docs সংরক্ষণ")}
        </button>
        <button className="underline" onClick={() => setPreview(!showPreview)}>
          Admin preview
        </button>
      </div>
      {notice && (
        <p role="status" className="rounded border border-amber-500 p-3">
          {notice}
        </p>
      )}
      <Card>
        <h2 className="mb-3 text-xl font-semibold">Publication</h2>
        <label>
          <input
            type="checkbox"
            checked={c.enabled}
            onChange={(e) => change({ enabled: e.target.checked })}
          />{" "}
          Publicly available
        </label>
        <p className="my-2 text-sm">
          Hidden until published. Optional time window uses your device
          timezone; server stores absolute time. End is exclusive.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {(["starts_at", "ends_at"] as const).map((key) => (
            <Field
              key={key}
              label={key === "starts_at" ? "Available from" : "Available until"}
            >
              <input
                type="datetime-local"
                className={inputCls}
                value={
                  c[key]
                    ? new Date(
                        Date.parse(c[key]!) -
                          new Date(c[key]!).getTimezoneOffset() * 60000,
                      )
                        .toISOString()
                        .slice(0, 16)
                    : ""
                }
                onChange={(e) =>
                  change({
                    [key]: e.target.value
                      ? new Date(e.target.value).toISOString()
                      : null,
                  })
                }
              />
            </Field>
          ))}
        </div>
        {(["show_live", "show_apis", "show_team"] as const).map((key) => (
          <label key={key} className="mr-4 mt-3 inline-block">
            <input
              type="checkbox"
              checked={c[key]}
              onChange={(e) => change({ [key]: e.target.checked })}
            />{" "}
            {key.replace("show_", "")}
          </label>
        ))}
      </Card>
      <Card>
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              "project_name",
              "team_name",
              "repository_url",
              "app_url",
              "video_url",
            ] as const
          ).map((key) => (
            <Field key={key} label={key.replaceAll("_", " ")}>
              <input
                className={inputCls}
                value={c[key] ?? ""}
                onChange={(e) => change({ [key]: e.target.value })}
              />
            </Field>
          ))}
        </div>
        <TextFields
          label="Tagline"
          value={c.tagline}
          onChange={(tagline) => change({ tagline })}
        />
      </Card>
      <Card>
        <h2 className="mb-3 text-xl font-semibold">
          Pitch & technical sections
        </h2>
        {c.sections.map((s, i) => (
          <details
            key={s.id}
            className="mb-3 rounded border border-slate-300 p-3"
          >
            <summary className="cursor-pointer font-semibold">
              {s.title.en}
            </summary>
            <label>
              <input
                type="checkbox"
                checked={s.visible}
                onChange={(e) =>
                  change({
                    sections: c.sections.map((x, j) =>
                      j === i ? { ...x, visible: e.target.checked } : x,
                    ),
                  })
                }
              />{" "}
              Visible
            </label>
            <div className="mt-3 space-y-3">
              <TextFields
                label="Title"
                value={s.title}
                onChange={(title) =>
                  change({
                    sections: c.sections.map((x, j) =>
                      j === i ? { ...x, title } : x,
                    ),
                  })
                }
              />
              <TextFields
                label="Content"
                value={s.body}
                onChange={(body) =>
                  change({
                    sections: c.sections.map((x, j) =>
                      j === i ? { ...x, body } : x,
                    ),
                  })
                }
              />
              {(s.steps ?? []).map((step, k) => (
                <TextFields
                  key={k}
                  label={`Diagram node ${k + 1}`}
                  value={step}
                  onChange={(v) =>
                    change({
                      sections: c.sections.map((x, j) =>
                        j === i
                          ? {
                              ...x,
                              steps: (x.steps ?? []).map((p, n) =>
                                n === k ? v : p,
                              ),
                            }
                          : x,
                      ),
                    })
                  }
                />
              ))}
            </div>
          </details>
        ))}
      </Card>
      <Card>
        <h2 className="mb-3 text-xl font-semibold">Team members</h2>
        {(c.members ?? []).map((m, i) => (
          <fieldset
            key={m.id}
            className="mb-4 space-y-3 rounded border border-slate-300 p-4"
          >
            <legend>{m.name}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {(["name", "email"] as const).map((key) => (
                <Field key={key} label={key}>
                  <input
                    className={inputCls}
                    value={m[key]}
                    onChange={(e) =>
                      change({
                        members: (c.members ?? []).map((x, j) =>
                          j === i ? { ...x, [key]: e.target.value } : x,
                        ),
                      })
                    }
                  />
                </Field>
              ))}
            </div>
            <TextFields
              label="Role"
              value={m.role}
              onChange={(role) =>
                change({
                  members: (c.members ?? []).map((x, j) =>
                    j === i ? { ...x, role } : x,
                  ),
                })
              }
            />
            <label className="block text-sm">
              Portrait (resized automatically)
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void portrait(f, i);
                }}
              />
            </label>
            {m.image_data && (
              <Image unoptimized
                src={m.image_data}
                alt={m.name}
                width={64}
                height={64}
                className="h-16 w-16 rounded-full"
              />
            )}
            <div className="flex gap-4">
              <button
                className="underline"
                onClick={() =>
                  change({
                    members: (c.members ?? []).map((x, j) =>
                      j === i ? { ...x, image_data: null } : x,
                    ),
                  })
                }
              >
                Remove photo
              </button>
              <button
                className="text-red-600 underline"
                onClick={() =>
                  change({
                    members: (c.members ?? []).filter((_, j) => i !== j),
                  })
                }
              >
                Remove member
              </button>
            </div>
          </fieldset>
        ))}
        <button
          className="underline"
          onClick={() =>
            change({
              members: [
                ...(c.members ?? []),
                {
                  id: `member-${Date.now()}`,
                  name: "New member",
                  email: "name@example.com",
                  role: { en: "Role", bn: "দায়িত্ব" },
                  image_data: null,
                },
              ],
            })
          }
        >
          + Add member
        </button>
      </Card>
      {showPreview &&
        (preview.isError ? (
          <p>Preview unavailable.</p>
        ) : (
          preview.data && (
            <Card>
              <p className="font-semibold">
                Admin preview — unsaved content shown; live data from server
              </p>
              <Document data={{ ...preview.data, content: c }} />
            </Card>
          )
        ))}
    </div>
  );
}
