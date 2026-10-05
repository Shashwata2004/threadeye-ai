"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ProviderBadge } from "@/components/badges";
import { Button, inputClass } from "@/components/form";
import { DefectCard, PointsMeter, YardTape } from "@/components/live/LivePanels";
import { LiveVideo, type Capture, type LiveVideoHandle } from "@/components/live/LiveVideo";
import {
  api,
  DEFECT_CLASSES,
  hasPerm,
  idempotencyKey,
  REJECT_REASONS,
  type Defect,
  type EventEnvelope,
  type ScoreSummary,
} from "@/lib/api/client";
import { errorDetail, useDefects, useInspection, useMe, usePlan, useTrack } from "@/lib/api/hooks";
import { viewCentreYd } from "@/lib/live/geometry";

const TICK_MS = 300; // how often the browser asks the server to process the frames played so far
const MAX_CAPTURES = 8;
const SPEEDS = [1, 2, 4];

export default function LiveInspectionPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const { data: insp, refetch: refetchInsp } = useInspection(id);
  const { data: track, error: trackError } = useTrack(id);
  const { data: plan } = usePlan(id);
  const { data: defects = [] } = useDefects(id);

  const videoRef = useRef<LiveVideoHandle>(null);
  const frameRef = useRef(0);
  const lastSeqRef = useRef(0);
  const checkpointRef = useRef(-1);
  const inFlightRef = useRef(false);
  const capturesRef = useRef<Capture[]>([]);
  const nextSampleRef = useRef(0);
  const drivingRef = useRef(false);
  const lastCaptureTopRef = useRef<number | null>(null);

  const [frame, setFrame] = useState(0);
  const [score, setScore] = useState<ScoreSummary | null>(null);
  const [driving, setDriving] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [checkpoint, setCheckpoint] = useState(-1);
  const [rate, setRate] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rejectFor, setRejectFor] = useState<string | null>(null);
  const [reclassFor, setReclassFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [manualCls, setManualCls] = useState<string>("hole");
  const [manualLen, setManualLen] = useState("1");

  const canRun = hasPerm(me, "inspections.run");
  const canDecide = hasPerm(me, "defects.confirm");
  const samples = useMemo(() => plan?.frames ?? [], [plan]);

  // Seed state from the snapshot once.
  const seeded = useRef(false);
  useEffect(() => {
    if (!insp || seeded.current) return;
    seeded.current = true;
    lastSeqRef.current = insp.last_seq;
    checkpointRef.current = insp.checkpoint_frame;
    setCheckpoint(insp.checkpoint_frame);
    setScore(insp.score ?? null);
    frameRef.current = Math.max(insp.checkpoint_frame, 0);
    setFrame(frameRef.current);
  }, [insp]);

  // After a reload, show the fabric where the inspection stopped.
  const shownCheckpoint = useRef(false);
  useEffect(() => {
    if (!track || !insp || shownCheckpoint.current || insp.checkpoint_frame < 0) return;
    shownCheckpoint.current = true;
    const timer = setTimeout(() => videoRef.current?.seek(insp.checkpoint_frame), 300);
    return () => clearTimeout(timer);
  }, [track, insp]);

  const applyEvents = useCallback(
    (events: EventEnvelope[]) => {
      let defectsChanged = false;
      let sessionChanged = false;
      for (const ev of events) {
        if (ev.seq <= lastSeqRef.current) continue; // idempotent by seq
        lastSeqRef.current = ev.seq;
        if (ev.type === "score.updated") setScore(ev.payload as unknown as ScoreSummary);
        else if (ev.type === "defect.upserted") defectsChanged = true;
        else if (ev.type.startsWith("session.") || ev.type.startsWith("verdict.")) sessionChanged = true;
      }
      if (defectsChanged) void queryClient.invalidateQueries({ queryKey: ["defects", id] });
      if (sessionChanged) void refetchInsp();
    },
    [id, queryClient, refetchInsp],
  );

  const pullEvents = useCallback(async () => {
    const { data } = await api.GET("/api/v1/inspections/{inspection_id}/events", {
      params: { path: { inspection_id: id }, query: { after_seq: lastSeqRef.current } },
    });
    if (data) applyEvents(data.events);
  }, [id, applyEvents]);

  const stopDriving = useCallback(() => {
    drivingRef.current = false;
    setDriving(false);
    videoRef.current?.pause();
  }, []);

  // ------------------------------------------------------------------------- the advance loop
  const advance = useCallback(async () => {
    if (!drivingRef.current || inFlightRef.current || !track) return;
    const until = Math.max(frameRef.current, checkpointRef.current);
    if (until <= checkpointRef.current && !capturesRef.current.length) return;
    inFlightRef.current = true;
    const captures = capturesRef.current.splice(0, MAX_CAPTURES);
    try {
      const { data, error: err, response } = await api.POST("/api/v1/inspections/{inspection_id}/advance", {
        params: { path: { inspection_id: id } },
        body: { until_frame: until, after_seq: lastSeqRef.current, captures },
      });
      if (data) {
        checkpointRef.current = data.checkpoint_frame;
        setCheckpoint(data.checkpoint_frame);
        applyEvents(data.events);
        if (captures.length) void queryClient.invalidateQueries({ queryKey: ["defects", id] }); // new photos
        setError(null);
      } else if (response.status === 409) {
        stopDriving();
        setError(errorDetail(err, response.status));
        void refetchInsp();
      } else if (response.status === 422) {
        setError(errorDetail(err, response.status)); // a bad capture is dropped, the run goes on
      } else {
        capturesRef.current.unshift(...captures); // try again on the next tick
      }
    } catch {
      capturesRef.current.unshift(...captures);
    } finally {
      inFlightRef.current = false;
    }
  }, [id, track, applyEvents, stopDriving, refetchInsp, queryClient]);

  useEffect(() => {
    const timer = setInterval(() => void advance(), TICK_MS);
    return () => clearInterval(timer);
  }, [advance]);

  // Re-render the tape and counters at ~5 Hz (the overlay itself is drawn on every video frame).
  useEffect(() => {
    const timer = setInterval(() => setFrame(frameRef.current), 200);
    return () => clearInterval(timer);
  }, []);

  const onFrame = useCallback(
    (f: number) => {
      frameRef.current = f;
      if (!drivingRef.current || !track) return;
      // Evidence photos: at each frame of the sampling plan, and whenever the fabric has moved 40 % of a
      // view since the last photo. Browsers may skip video frames (fast demo speeds, busy laptops), so
      // the travel rule guarantees every defect is fully inside at least one photo.
      let due = false;
      while (nextSampleRef.current < samples.length && samples[nextSampleRef.current] <= f) {
        due = true;
        nextSampleRef.current += 1;
      }
      const top = track.roll_y_top_px[f];
      if (lastCaptureTopRef.current === null || Math.abs(top - lastCaptureTopRef.current) >= 0.4 * track.view_region[3]) {
        due = true;
      }
      if (due) {
        lastCaptureTopRef.current = top;
        void videoRef.current?.capture(f).then((c) => {
          if (c) capturesRef.current.push(c);
        });
      }
    },
    [samples, track],
  );

  // ------------------------------------------------------------------------- lifecycle
  async function begin(takeover = false) {
    if (!insp || !track) return;
    setBusy(true);
    setError(null);
    const action = insp.status === "created" ? "start" : "resume";
    const opts = {
      params: { path: { inspection_id: id }, query: { takeover } },
      headers: { "Idempotency-Key": idempotencyKey() },
    };
    const res =
      action === "start"
        ? await api.POST("/api/v1/inspections/{inspection_id}/start", opts)
        : await api.POST("/api/v1/inspections/{inspection_id}/resume", opts);
    setBusy(false);
    if (!res.data) {
      setError(errorDetail(res.error));
      return;
    }
    const snap = res.data;
    queryClient.setQueryData(["inspection", id], snap);
    checkpointRef.current = snap.checkpoint_frame;
    setCheckpoint(snap.checkpoint_frame);
    const from = Math.min(snap.checkpoint_frame + 1, track.frame_count - 1);
    nextSampleRef.current = samples.findIndex((s) => s > snap.checkpoint_frame);
    if (nextSampleRef.current < 0) nextSampleRef.current = samples.length;
    if (videoRef.current) {
      drivingRef.current = true;
      setDriving(true);
      setEnded(false);
      await videoRef.current.playFrom(Math.max(from, 0), rate);
    }
    await pullEvents();
  }

  async function pause() {
    stopDriving();
    await advance();
    await api.POST("/api/v1/inspections/{inspection_id}/pause", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
    });
    void refetchInsp();
  }

  async function onEnded() {
    setEnded(true);
    setPlaying(false);
    if (track) frameRef.current = track.frame_count - 1;
    // Let the loop flush the last frames and captures.
    for (let i = 0; i < 20 && drivingRef.current && checkpointRef.current < (track?.frame_count ?? 0) - 1; i++) {
      await advance();
      await new Promise((r) => setTimeout(r, 150));
    }
  }

  async function finish() {
    setBusy(true);
    setError(null);
    drivingRef.current = false;
    setDriving(false);
    const { data, error: err } = await api.POST("/api/v1/inspections/{inspection_id}/complete", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
    });
    setBusy(false);
    if (data) queryClient.setQueryData(["inspection", id], data);
    else setError(errorDetail(err));
    await pullEvents();
  }

  async function computeVerdict() {
    setBusy(true);
    setError(null);
    const { data, error: err } = await api.POST("/api/v1/inspections/{inspection_id}/finalize", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
    });
    setBusy(false);
    if (data) router.push(`/inspections/${id}`);
    else setError(errorDetail(err));
  }

  // ------------------------------------------------------------------------- inspector decisions
  const decide = useCallback(
    async (d: Defect, action: string, body: Record<string, unknown> = {}) => {
      const opts = { params: { path: { defect_id: d.id } }, headers: { "Idempotency-Key": idempotencyKey() } };
      let res: { data?: unknown; error?: unknown };
      if (action === "confirm") res = await api.POST("/api/v1/defects/{defect_id}/confirm", { ...opts, body: {} });
      else if (action === "reject")
        res = await api.POST("/api/v1/defects/{defect_id}/reject", {
          ...opts,
          body: { reason_category: body.reason_category as (typeof REJECT_REASONS)[number] },
        });
      else if (action === "reclassify")
        res = await api.POST("/api/v1/defects/{defect_id}/reclassify", {
          ...opts,
          body: { to_cls: String(body.to_cls) },
        });
      else if (action === "promote") res = await api.POST("/api/v1/defects/{defect_id}/promote", { ...opts, body: {} });
      else res = await api.POST("/api/v1/defects/{defect_id}/reopen", opts);
      if (!res.data) setError(errorDetail(res.error));
      await queryClient.invalidateQueries({ queryKey: ["defects", id] });
      await pullEvents();
    },
    [id, queryClient, pullEvents],
  );

  async function addManual() {
    if (!track) return;
    const { error: err } = await api.POST("/api/v1/inspections/{inspection_id}/defects", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
      body: { cls: manualCls, center_yd: viewCentreYd(track, frame), length_in: Number(manualLen) },
    });
    if (err) setError(errorDetail(err));
    setAddOpen(false);
    await queryClient.invalidateQueries({ queryKey: ["defects", id] });
    await pullEvents();
  }

  // ------------------------------------------------------------------------- queue and keys
  const real = useMemo(() => defects.filter((d) => d.kind === "defect"), [defects]);
  const queue = useMemo(
    () => [
      ...real.filter((d) => d.status === "pending").sort((a, b) => a.center_yd - b.center_yd),
      ...real.filter((d) => d.status !== "pending").sort((a, b) => b.center_yd - a.center_yd),
    ],
    [real],
  );
  const nondefects = defects.filter((d) => d.kind === "nondefect");
  const pending = real.filter((d) => d.status === "pending").length;
  const selected = queue.find((d) => d.id === selectedId) ?? queue[0] ?? null;

  const togglePlay = useCallback(() => {
    const video = videoRef.current?.video;
    if (!video) return;
    if (driving && !video.paused) void pause();
    else void begin();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [driving, insp, track, rate, samples]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) return;
      const i = selected ? queue.findIndex((d) => d.id === selected.id) : -1;
      if (e.key === " ") {
        e.preventDefault();
        if (canRun) togglePlay();
      } else if (e.key === "j" || e.key === "k") {
        const next = queue[Math.min(Math.max(i + (e.key === "j" ? 1 : -1), 0), queue.length - 1)];
        if (next) setSelectedId(next.id);
      } else if (selected && canDecide && selected.status === "pending") {
        if (e.key === "c" || e.key === "Enter") void decide(selected, "confirm");
        else if (e.key === "x") setRejectFor(rejectFor === selected.id ? null : selected.id);
        else if (e.key === "t") setReclassFor(selected.id);
        else if (rejectFor === selected.id && /^[1-8]$/.test(e.key)) {
          setRejectFor(null);
          void decide(selected, "reject", { reason_category: REJECT_REASONS[Number(e.key) - 1] });
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [queue, selected, canDecide, canRun, rejectFor, decide, togglePlay]);

  // ------------------------------------------------------------------------- render
  if (!insp) return <p className="text-slate-500">{t("common.loading")}</p>;
  if (insp.finalized_at) {
    return (
      <div className="space-y-3">
        <p>{t("istatus.completed")}</p>
        <Link href={`/inspections/${id}`} className="font-semibold text-brand-blue hover:underline">
          {t("live.seeVerdict")}
        </Link>
      </div>
    );
  }
  if (trackError) return <p className="text-red-700">{t("live.videoMissing", { id: insp.dataset_id ?? "" })}</p>;
  if (!track) return <p className="text-slate-500">{t("common.loading")}</p>;

  const status = insp.status;
  const open = ["created", "running", "paused", "interrupted"].includes(status);
  const stopped = track.state[frame] === "stopped";
  const atEnd = checkpoint >= track.frame_count - 1;
  const leaseElsewhere = insp.lease_held_elsewhere && !driving;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-brand-navy">
            <span className="font-mono">{insp.roll_code}</span> · {t(`istatus.${driving ? "running" : status}`)}
          </h1>
          <p className="text-sm text-slate-600">
            {insp.roll.challan_no} · {insp.roll.supplier} → {insp.roll.buyer} · {insp.roll.rule_profile}
          </p>
        </div>
        <ProviderBadge
          name={`${insp.provider.display_name}${insp.provider.preset ? ` (${insp.provider.preset})` : ""}`}
          simulated={insp.provider.is_simulated}
        />
      </div>

      {error && (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {t("live.error", { detail: error })}
        </p>
      )}

      {canRun && open && !driving && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
          <p className="text-amber-900">
            {leaseElsewhere
              ? t("live.leaseLost")
              : status === "created"
                ? ""
                : status === "paused"
                  ? t("live.pausedBanner", { yd: insp.checkpoint_yd.toFixed(2) })
                  : t("live.resumeBanner")}
          </p>
          <Button onClick={() => void begin(leaseElsewhere)} disabled={busy} data-testid="start">
            {leaseElsewhere
              ? t("live.takeOver")
              : status === "created"
                ? t("live.start")
                : t("live.resumeButton", { yd: insp.checkpoint_yd.toFixed(2) })}
          </Button>
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-[1fr_380px]">
        <div className="space-y-2">
          <div className="flex gap-2">
            <YardTape track={track} frame={frame} defects={defects} />
            <div className="min-w-0 flex-1">
              {track.video_url ? (
                <LiveVideo
                  ref={videoRef}
                  src={track.video_url}
                  type={track.video_type}
                  track={track}
                  defects={defects}
                  selectedId={selected?.id ?? null}
                  onFrame={onFrame}
                  onEnded={() => void onEnded()}
                />
              ) : (
                <p className="rounded bg-slate-100 p-6 text-slate-600">{t("live.videoMissing", { id: track.dataset_id })}</p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
            <span className="font-mono text-3xl font-bold text-brand-navy" data-testid="yard-counter">
              {t("live.yard", { yd: (track.bottom_yd[frame] ?? 0).toFixed(2) })}
            </span>
            <span
              className={`rounded-full px-3 py-1 text-sm font-semibold ${
                stopped ? "bg-amber-100 text-amber-900" : "bg-green-100 text-green-900"
              }`}
            >
              {stopped ? t("live.stopped") : t("live.running")} · {t("live.speed", { v: track.speed_m_min[frame]?.toFixed(1) ?? "0" })}
            </span>
            {canRun && open && (
              <Button variant="secondary" onClick={togglePlay} disabled={busy || leaseElsewhere}>
                {driving && playing ? t("live.pause") : t("live.play")}
              </Button>
            )}
            <label className="flex items-center gap-1 text-sm text-slate-600">
              {t("live.demoSpeed")}
              <select
                value={rate}
                onChange={(e) => {
                  const r = Number(e.target.value);
                  setRate(r);
                  videoRef.current?.setRate(r);
                }}
                className="rounded border border-slate-300 px-1 py-0.5"
                title={t("live.demoSpeedNote")}
              >
                {SPEEDS.map((s) => (
                  <option key={s} value={s}>
                    {s}×
                  </option>
                ))}
              </select>
            </label>
            <span className="text-xs text-slate-500">{t("live.shortcuts")}</span>
          </div>
          <PlayingTracker videoRef={videoRef} onChange={setPlaying} />

          {(ended || atEnd || status === "completed") && canRun && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-teal-300 bg-teal-50 px-4 py-3">
              <p className="text-teal-900">
                {t("live.ended")} {pending > 0 && t("live.pendingLeft", { n: pending })}
              </p>
              {status !== "completed" ? (
                <Button onClick={() => void finish()} disabled={busy || !atEnd} data-testid="finish">
                  {t("live.finish")}
                </Button>
              ) : (
                <Button onClick={() => void computeVerdict()} disabled={busy || pending > 0} data-testid="compute-verdict">
                  {t("live.computeVerdict")}
                </Button>
              )}
            </div>
          )}
        </div>

        <aside className="space-y-3">
          <PointsMeter score={score} />
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{t("live.queue", { n: real.length })}</h2>
              {canDecide && (status === "running" || status === "paused" || status === "completed" || driving) && (
                <button
                  type="button"
                  onClick={() => setAddOpen(!addOpen)}
                  className="text-sm font-semibold text-brand-blue hover:underline"
                >
                  + {t("live.addMissed")}
                </button>
              )}
            </div>
            {addOpen && (
              <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
                <p className="text-xs text-slate-600">{t("live.addMissedHint", { yd: viewCentreYd(track, frame).toFixed(2) })}</p>
                <div className="flex gap-2">
                  <select value={manualCls} onChange={(e) => setManualCls(e.target.value)} className={inputClass}>
                    {DEFECT_CLASSES.map((c) => (
                      <option key={c} value={c}>
                        {t(`cls.${c}`)}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    min={0.05}
                    step="0.05"
                    value={manualLen}
                    onChange={(e) => setManualLen(e.target.value)}
                    className={`${inputClass} w-24`}
                    aria-label={t("live.lengthIn")}
                  />
                </div>
                <div className="flex gap-2">
                  <Button onClick={() => void addManual()}>{t("live.add")}</Button>
                  <Button variant="secondary" onClick={() => setAddOpen(false)}>
                    {t("live.cancel")}
                  </Button>
                </div>
              </div>
            )}
            {!queue.length ? (
              <p className="text-sm text-slate-500">{t("live.noDefects")}</p>
            ) : (
              <ul className="max-h-[60vh] space-y-2 overflow-y-auto pr-1" data-testid="defect-queue">
                {queue.map((d) => (
                  <DefectCard
                    key={d.id}
                    d={d}
                    selected={selected?.id === d.id}
                    onSelect={() => setSelectedId(d.id)}
                    decide={decide}
                    canDecide={canDecide && !insp.finalized_at}
                    rejectOpen={rejectFor === d.id}
                    setRejectOpen={(o) => setRejectFor(o ? d.id : null)}
                    reclassOpen={reclassFor === d.id}
                    setReclassOpen={(o) => setReclassFor(o ? d.id : null)}
                  />
                ))}
              </ul>
            )}
          </section>
          {nondefects.length > 0 && (
            <details className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <summary className="cursor-pointer text-slate-700">{t("live.ignored", { n: nondefects.length })}</summary>
              <ul className="mt-2 space-y-1">
                {nondefects.map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-2">
                    <span>
                      <span className="font-mono text-xs text-slate-500">{d.defect_no}</span>{" "}
                      {t(`cls.${d.nondefect_category ?? d.current_cls}`)} · {t("live.at", { yd: d.center_yd.toFixed(2) })}
                    </span>
                    {canDecide && (
                      <button
                        type="button"
                        onClick={() => void decide(d, "promote")}
                        className="text-xs text-brand-blue hover:underline"
                      >
                        {t("live.promote")}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </aside>
      </div>
    </div>
  );
}

/** Mirrors the video element's play/pause state into React. */
function PlayingTracker({
  videoRef,
  onChange,
}: {
  videoRef: React.RefObject<LiveVideoHandle | null>;
  onChange: (playing: boolean) => void;
}) {
  useEffect(() => {
    const timer = setInterval(() => {
      const v = videoRef.current?.video;
      onChange(!!v && !v.paused && !v.ended);
    }, 250);
    return () => clearInterval(timer);
  }, [videoRef, onChange]);
  return null;
}
