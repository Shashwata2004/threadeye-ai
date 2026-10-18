"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ProviderBadge } from "@/components/badges";
import { Button, inputClass } from "@/components/form";
import { DefectCard, PointsMeter, YardTape } from "@/components/live/LivePanels";
import { LiveVideo, type Capture, type LiveVideoHandle, type ViewBox } from "@/components/live/LiveVideo";
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
import { defectBox, frameAt, inView, YARD_CM } from "@/lib/live/geometry";

/** The fields of a defect.upserted event the overlay needs to draw a box. */
type LiveBox = Pick<
  Defect,
  "defect_no" | "kind" | "status" | "start_yd" | "end_yd" | "center_yd" | "across_start_cm" | "across_end_cm"
>;

const TICK_MS = 300; // how often the browser asks the server to process the frames played so far
const MAX_CAPTURES = 8;
const SPEEDS = [1, 2, 4];
// The server works ahead of the video the inspector watches, like a camera mounted before the
// inspection board: a defect is already known when its fabric reaches the view, so its box shows at
// once even over a slow link. How far ahead follows the measured round-trip time.
const AHEAD_MIN_S = 1;
const AHEAD_MAX_S = 8;

export default function LiveInspectionPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const { data: insp, refetch: refetchInsp } = useInspection(id);
  const { data: track, error: trackError } = useTrack(id);
  const { data: plan } = usePlan(id);
  const { data: fetched } = useDefects(id);
  // Decisions still saving: the card keeps the inspector's choice even if the list is fetched again in
  // the meantime (over a slow link the server answers with the old state for a few seconds).
  const [edits, setEdits] = useState<ReadonlyMap<string, Partial<Defect>>>(new Map());
  const defects = useMemo(
    () => (fetched ?? []).map((d) => (edits.has(d.id) ? ({ ...d, ...edits.get(d.id) } as Defect) : d)),
    [fetched, edits],
  );

  const videoRef = useRef<LiveVideoHandle>(null);
  const frameRef = useRef(0);
  const lastSeqRef = useRef(0);
  const checkpointRef = useRef(-1);
  const inFlightRef = useRef(false);
  const capturesRef = useRef<Capture[]>([]);
  const nextSampleRef = useRef(0);
  const drivingRef = useRef(false);
  /** Start/resume pressed, the server has not answered yet. */
  const startingRef = useRef(false);
  const [liveBoxes, setLiveBoxes] = useState<ReadonlyMap<string, LiveBox>>(new Map());
  const lastCaptureTopRef = useRef<number | null>(null);
  const rateRef = useRef(1);
  const latencyRef = useRef(0.5); // seconds per /advance round trip (moving average)
  /** Scores the server computed ahead of the video: shown when the video reaches their frame. */
  const heldScoresRef = useRef<ScoreSummary[]>([]);
  const workAheadRef = useRef(true);

  const [frame, setFrame] = useState(0);
  const [score, setScore] = useState<ScoreSummary | null>(null);
  const [driving, setDriving] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [checkpoint, setCheckpoint] = useState(-1);
  const [rate, setRate] = useState(1);
  /** The video has been driven on this page: resume from where it shows, not from the server's frame. */
  const [played, setPlayed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rejectFor, setRejectFor] = useState<string | null>(null);
  const [reclassFor, setReclassFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [manualCls, setManualCls] = useState<string>("hole");
  /** The box drawn around a missed defect, and the frame it was drawn on. */
  const [draft, setDraft] = useState<{ frame: number; box: ViewBox } | null>(null);
  const [confirmAllAsk, setConfirmAllAsk] = useState(false);

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
    // Only for the snapshot the page opened with: later snapshots carry the server's checkpoint, which
    // runs ahead of the video while it plays.
    if (!track || !insp || shownCheckpoint.current) return;
    shownCheckpoint.current = true;
    if (insp.checkpoint_frame < 0) return;
    const timer = setTimeout(() => videoRef.current?.seek(insp.checkpoint_frame), 300);
    return () => clearTimeout(timer);
  }, [track, insp]);

  const applyEvents = useCallback(
    (events: EventEnvelope[]) => {
      let defectsChanged = false;
      let sessionChanged = false;
      const fresh: LiveBox[] = [];
      for (const ev of events) {
        if (ev.seq <= lastSeqRef.current) continue; // idempotent by seq
        lastSeqRef.current = ev.seq;
        if (ev.type === "score.updated") {
          const sc = ev.payload as unknown as ScoreSummary;
          if (ev.actor.kind === "engine" && (sc.at_frame ?? -1) > frameRef.current) heldScoresRef.current.push(sc);
          else {
            heldScoresRef.current = []; // a decision rescored everything: older held scores are stale
            setScore(sc);
          }
        } else if (ev.type === "defect.upserted") {
          defectsChanged = true;
          // The event already carries where the defect is: draw its box now, without waiting for the
          // defect list to be fetched again (that round trip took the defect out of view on a slow link).
          fresh.push((ev.payload as { defect: LiveBox }).defect);
        }
        else if (ev.type.startsWith("session.") || ev.type.startsWith("verdict.")) sessionChanged = true;
      }
      if (fresh.length)
        setLiveBoxes((prev) => {
          const next = new Map(prev);
          for (const v of fresh) next.set(v.defect_no, v);
          return next;
        });
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
  /** How many frames ahead of the video the server should work (0 for detectors that need the picture:
   * they can only see frames the browser has shown). */
  const aheadFrames = useCallback(() => {
    if (!track || !workAheadRef.current) return 0;
    const seconds = Math.min(AHEAD_MAX_S, AHEAD_MIN_S + 2 * latencyRef.current);
    return Math.round(seconds * track.fps * rateRef.current);
  }, [track]);

  /** The frame the video is at. requestVideoFrameCallback stops when the page is not painted (another tab
   * in front, a minimised window) while the video keeps playing, so the clock is read from the video too. */
  const syncFrame = useCallback(() => {
    const video = videoRef.current?.video;
    if (track && video && !video.paused && !video.ended) frameRef.current = frameAt(track, video.currentTime);
  }, [track]);

  const advance = useCallback(async () => {
    if (!drivingRef.current || inFlightRef.current || !track) return;
    syncFrame();
    const until = Math.min(Math.max(frameRef.current + aheadFrames(), checkpointRef.current), track.frame_count - 1);
    if (until <= checkpointRef.current && !capturesRef.current.length) return;
    inFlightRef.current = true;
    const captures = capturesRef.current.splice(0, MAX_CAPTURES);
    const started = performance.now();
    try {
      const { data, error: err, response } = await api.POST("/api/v1/inspections/{inspection_id}/advance", {
        params: { path: { inspection_id: id } },
        body: { until_frame: until, after_seq: lastSeqRef.current, captures, takeover: false },
      });
      latencyRef.current = 0.7 * latencyRef.current + 0.3 * ((performance.now() - started) / 1000);
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
  }, [id, track, applyEvents, stopDriving, refetchInsp, queryClient, aheadFrames, syncFrame]);

  useEffect(() => {
    const timer = setInterval(() => void advance(), TICK_MS);
    return () => clearInterval(timer);
  }, [advance]);

  // Re-render the tape and counters at ~5 Hz (the overlay itself is drawn on every video frame), and
  // show the scores the server computed ahead once the video reaches their frame.
  useEffect(() => {
    const timer = setInterval(() => {
      syncFrame();
      setFrame(frameRef.current);
      const held = heldScoresRef.current;
      let due: ScoreSummary | undefined;
      while (held.length && (held[0].at_frame ?? -1) <= frameRef.current) due = held.shift();
      if (due) setScore(due);
    }, 200);
    return () => clearInterval(timer);
  }, [syncFrame]);

  useEffect(() => {
    if (insp) workAheadRef.current = !insp.provider.requires_image;
  }, [insp]);

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
    if (!insp || !track || startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setBusy(true);
    setError(null);
    // Paused on this page: go on from the frame on screen (the server has already worked further ahead).
    // After a reload or a power cut: from the server's checkpoint.
    const from = Math.max(played ? frameRef.current : Math.min(insp.checkpoint_frame + 1, track.frame_count - 1), 0);
    nextSampleRef.current = samples.findIndex((s) => s >= from);
    if (nextSampleRef.current < 0) nextSampleRef.current = samples.length;
    // One request starts (or resumes) the inspection and already processes the fabric ahead, so the
    // video plays with its defect boxes from the first frame.
    const until = Math.min(from + aheadFrames(), track.frame_count - 1);
    const sent = performance.now();
    const { data, error: err, response } = await api.POST("/api/v1/inspections/{inspection_id}/advance", {
      params: { path: { inspection_id: id } },
      body: { until_frame: until, after_seq: lastSeqRef.current, captures: [], start_key: idempotencyKey(), takeover },
    });
    latencyRef.current = (performance.now() - sent) / 1000;
    startingRef.current = false;
    setStarting(false);
    setBusy(false);
    if (!data) {
      setError(errorDetail(err, response.status));
      void refetchInsp();
      return;
    }
    checkpointRef.current = data.checkpoint_frame;
    setCheckpoint(data.checkpoint_frame);
    applyEvents(data.events);
    drivingRef.current = true;
    setDriving(true);
    setEnded(false);
    setPlayed(true);
    await videoRef.current?.playFrom(from, rate);
    void refetchInsp();
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
    const held = heldScoresRef.current;
    if (held.length) setScore(held[held.length - 1]);
    heldScoresRef.current = [];
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
  // Decisions update the card at once (optimistic) and save in the background: over a slow link a
  // round trip takes seconds, and the inspector must be able to keep working through the queue.
  const setEditing = useCallback((ids: string[], change: Partial<Defect> | null) => {
    setEdits((m) => {
      const next = new Map(m);
      for (const i of ids) {
        if (change) next.set(i, change);
        else next.delete(i);
      }
      return next;
    });
  }, []);
  const decide = useCallback(
    async (d: Defect, action: string, body: Record<string, unknown> = {}) => {
      const key = ["defects", id];
      const optimistic: Partial<Defect> =
        action === "confirm"
          ? { status: "confirmed", reject_reason: null }
          : action === "reject"
            ? { status: "rejected", reject_reason: String(body.reason_category) }
            : action === "reclassify"
              ? { status: "confirmed", current_cls: String(body.to_cls), reject_reason: null }
              : action === "promote"
                ? { status: "confirmed", kind: "defect", nondefect_category: null }
                : { status: "pending", reject_reason: null };
      await queryClient.cancelQueries({ queryKey: key });
      queryClient.setQueryData<Defect[]>(key, (old) => old?.map((x) => (x.id === d.id ? { ...x, ...optimistic } : x)));
      setEditing([d.id], optimistic);

      const opts = { params: { path: { defect_id: d.id } }, headers: { "Idempotency-Key": idempotencyKey() } };
      let res: { data?: Defect; error?: unknown; response: Response };
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

      setEditing([d.id], null);
      if (res.data) {
        const saved = res.data;
        queryClient.setQueryData<Defect[]>(key, (old) => old?.map((x) => (x.id === saved.id ? saved : x)));
      } else {
        setError(errorDetail(res.error, res.response.status));
      }
      // Points of other defects can change too (per-yard cap): refresh quietly.
      void queryClient.invalidateQueries({ queryKey: key });
      void pullEvents();
    },
    [id, queryClient, pullEvents, setEditing],
  );

  // Missed defects: the video stops, the inspector drags a box around the defect on it. The box gives
  // the exact yard, position and size, and a photo of that frame becomes the evidence (and a label for
  // training the next model).
  function openAddMissed() {
    // The panel opens at once; the video stops at once; telling the server happens in the background.
    setDraft(null);
    setAddOpen(true);
    const video = videoRef.current?.video;
    if (driving) void pause();
    else if (video && !video.paused) videoRef.current?.pause();
  }

  function closeAddMissed() {
    setAddOpen(false);
    setDraft(null);
  }

  async function addManual() {
    if (!draft) return;
    setBusy(true);
    const capture = await videoRef.current?.capture(draft.frame);
    const { error: err, response } = await api.POST("/api/v1/inspections/{inspection_id}/defects", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
      body: { cls: manualCls, frame: draft.frame, bbox_px: draft.box, capture: capture ?? undefined },
    });
    setBusy(false);
    if (err) {
      setError(errorDetail(err, response.status));
      return;
    }
    closeAddMissed();
    await queryClient.invalidateQueries({ queryKey: ["defects", id] });
    await pullEvents();
  }

  // Confirm every pending defect seen so far in one step (the inspector has rejected the false alarms).
  async function confirmAll(upToYd: number | null) {
    setConfirmAllAsk(false);
    const key = ["defects", id];
    const hit = (d: Defect) => d.kind === "defect" && d.status === "pending" && (upToYd === null || d.center_yd <= upToYd);
    const ids = defects.filter(hit).map((d) => d.id);
    setEditing(ids, { status: "confirmed", reject_reason: null });
    await queryClient.cancelQueries({ queryKey: key });
    queryClient.setQueryData<Defect[]>(key, (old) =>
      old?.map((x) => (hit(x) ? { ...x, status: "confirmed", reject_reason: null } : x)),
    );
    const { error: err, response } = await api.POST("/api/v1/inspections/{inspection_id}/defects/confirm-pending", {
      params: { path: { inspection_id: id } },
      headers: { "Idempotency-Key": idempotencyKey() },
      body: upToYd === null ? {} : { up_to_yd: upToYd },
    });
    setEditing(ids, null);
    if (err) setError(errorDetail(err, response.status));
    void queryClient.invalidateQueries({ queryKey: key });
    void pullEvents();
  }

  // ------------------------------------------------------------------------- queue and keys
  // The server works ahead of the video: list a defect once its fabric has reached the camera view on
  // screen (the overlay draws every known defect, but only where it is in view). At the end of the
  // roll, or once the inspection is completed, everything is listed.
  const lastFrame = (track?.frame_count ?? 1) - 1;
  const showAll = !track || insp?.status === "completed" || ended || (checkpoint >= lastFrame && frame >= lastFrame - 1);
  const seen = useCallback(
    (d: Defect) =>
      showAll ||
      d.origin === "manual" ||
      d.status !== "pending" ||
      (d.first_frame ?? 0) <= frame ||
      (!!track && inView(defectBox(d, track, frame), track)),
    [showAll, frame, track],
  );
  const real = useMemo(() => defects.filter((d) => d.kind === "defect" && seen(d)), [defects, seen]);
  // For the overlay: the fetched defects, plus boxes known from events that the list does not have yet.
  const overlay = useMemo(() => {
    const known = new Set(defects.map((d) => d.defect_no));
    const extra = [...liveBoxes.values()]
      .filter((v) => !known.has(v.defect_no))
      .map((v) => ({ ...v, id: `live-${v.defect_no}` }) as unknown as Defect);
    return [...defects, ...extra];
  }, [defects, liveBoxes]);
  const queue = useMemo(
    () => [
      ...real.filter((d) => d.status === "pending").sort((a, b) => a.center_yd - b.center_yd),
      ...real.filter((d) => d.status !== "pending").sort((a, b) => b.center_yd - a.center_yd),
    ],
    [real],
  );
  const nondefects = defects.filter((d) => d.kind === "nondefect" && seen(d));
  const pending = real.filter((d) => d.status === "pending").length;
  const selected = queue.find((d) => d.id === selectedId) ?? queue[0] ?? null;

  const togglePlay = useCallback(() => {
    const video = videoRef.current?.video;
    if (!video || !track || startingRef.current) return;
    setAddOpen(false); // the video moves on: a box drawn on the old frame no longer fits
    setDraft(null);
    const lastFrame = track.frame_count - 1;
    // Done = the video has shown the whole roll (the server may have finished processing earlier).
    const done = insp?.status === "completed" || (checkpointRef.current >= lastFrame && frameRef.current >= lastFrame - 1);
    if (done) {
      // Review replay after the roll has run: only the video plays again (with its boxes). The
      // inspection is not touched: no frames are processed, no photos taken.
      drivingRef.current = false;
      setDriving(false);
      if (!video.paused && !video.ended) videoRef.current?.pause();
      else if (video.ended || frameRef.current >= lastFrame) void videoRef.current?.playFrom(0, rate);
      else void videoRef.current?.playFrom(frameRef.current, rate);
      return;
    }
    if (driving && !video.paused) void pause();
    else void begin();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [driving, insp, track, rate, samples]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) return;
      if (e.key === "Escape") {
        setAddOpen(false);
        setDraft(null);
        setConfirmAllAsk(false);
        return;
      }
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
  const atEnd = checkpoint >= track.frame_count - 1 && (ended || frame >= track.frame_count - 2);
  const finished = atEnd || status === "completed";
  const leaseElsewhere = insp.lease_held_elsewhere && !driving;
  // Where the inspector will continue: the fabric on screen (the server's checkpoint may be ahead of it).
  const resumeYd = (played ? (track.bottom_yd[frame] ?? 0) : insp.checkpoint_yd).toFixed(2);
  // Confirm-all covers what has passed the camera (up to the bottom of the view), or everything at the end.
  const upToYd = finished ? null : (track.bottom_yd[frame] ?? 0);
  const bulkCount = real.filter((d) => d.status === "pending" && (upToYd === null || d.center_yd <= upToYd)).length;
  // Pending defects block the verdict only while they could still change it.
  const settled = pending > 0 && !!score?.verdict_settled;
  const draftInfo =
    draft && track
      ? {
          yd: (track.roll_y_top_px[draft.frame] + (draft.box[1] + draft.box[3]) / 2) / track.px_per_cm / YARD_CM,
          len: Math.max(draft.box[2] - draft.box[0], draft.box[3] - draft.box[1]) / track.px_per_cm / 2.54,
        }
      : null;

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
                  ? t("live.pausedBanner", { yd: resumeYd })
                  : t("live.resumeBanner")}
          </p>
          <Button onClick={() => void begin(leaseElsewhere)} disabled={busy} data-testid="start">
            {leaseElsewhere
              ? t("live.takeOver")
              : starting
                ? t("live.starting")
                : status === "created"
                ? t("live.start")
                : t("live.resumeButton", { yd: resumeYd })}
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-2">
          <div className="flex gap-2">
            <YardTape track={track} frame={frame} defects={overlay} />
            <div className="min-w-0 flex-1">
              {track.video_url ? (
                <LiveVideo
                  ref={videoRef}
                  src={track.video_url}
                  type={track.video_type}
                  track={track}
                  defects={overlay}
                  selectedId={selected?.id ?? null}
                  onFrame={onFrame}
                  onEnded={() => void onEnded()}
                  drawing={addOpen}
                  draft={draft?.box ?? null}
                  onDrawn={(box) => setDraft({ frame: frameRef.current, box })}
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
            {((canRun && open) || finished) && (
              <button
                type="button"
                onClick={togglePlay}
                disabled={busy || (leaseElsewhere && !finished)}
                data-testid="play-pause"
                title={finished ? t("live.replayNote") : undefined}
                className={`rounded-md px-5 py-2 text-base font-bold text-white disabled:opacity-50 ${
                  playing ? "bg-amber-600 hover:bg-amber-700" : "bg-green-700 hover:bg-green-800"
                }`}
              >
                {starting
                  ? t("live.starting")
                  : playing
                  ? `⏸ ${t("live.pause")}`
                  : finished && (ended || frame >= track.frame_count - 1)
                    ? `↻ ${t("live.playAgain")}`
                    : `▶ ${t("live.play")}`}
              </button>
            )}
            <label className="flex items-center gap-1 text-sm text-slate-600">
              {t("live.demoSpeed")}
              <select
                value={rate}
                onChange={(e) => {
                  const r = Number(e.target.value);
                  setRate(r);
                  rateRef.current = r;
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
            <span className="hidden text-xs text-slate-500 md:inline">{t("live.shortcuts")}</span>
          </div>
          <PlayingTracker videoRef={videoRef} onChange={setPlaying} />

          {(ended || atEnd || status === "completed") && canRun && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-teal-300 bg-teal-50 px-4 py-3">
              <div className="text-teal-900">
                <p>
                  {t("live.ended")} {pending > 0 && t("live.pendingLeft", { n: pending })}
                </p>
                {status === "completed" && pending > 0 && (
                  <p className="text-sm" data-testid="settled-note">
                    {settled
                      ? t("live.settled", {
                          n: pending,
                          verdict: t(`verdicts.${score?.confirmed_verdict ?? "FAIL"}`),
                        })
                      : t("live.notSettled")}
                  </p>
                )}
              </div>
              {status !== "completed" ? (
                <Button onClick={() => void finish()} disabled={busy || !atEnd} data-testid="finish">
                  {t("live.finish")}
                </Button>
              ) : (
                <Button onClick={() => void computeVerdict()} disabled={busy || (pending > 0 && !settled)} data-testid="compute-verdict">
                  {t("live.computeVerdict")}
                </Button>
              )}
            </div>
          )}
        </div>

        <aside className="min-w-0 space-y-3">
          <PointsMeter score={score} />
          <section className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">{t("live.queue", { n: real.length })}</h2>
              {canDecide && track.video_url && (status === "running" || status === "paused" || status === "completed" || driving) && (
                <button
                  type="button"
                  onClick={() => (addOpen ? closeAddMissed() : openAddMissed())}
                  className="text-sm font-semibold text-brand-blue hover:underline"
                  data-testid="add-missed"
                >
                  + {t("live.addMissed")}
                </button>
              )}
            </div>
            {canDecide && bulkCount > 0 && !insp.finalized_at && (
              <div className="rounded-lg border border-green-200 bg-green-50 p-2 text-sm">
                {confirmAllAsk ? (
                  <div className="space-y-2">
                    <p className="text-green-950">{t("live.confirmAllAsk", { n: bulkCount })}</p>
                    <div className="flex gap-2">
                      <Button onClick={() => void confirmAll(upToYd)} data-testid="confirm-all-yes">
                        {t("live.confirmAllYes", { n: bulkCount })}
                      </Button>
                      <Button variant="secondary" onClick={() => setConfirmAllAsk(false)}>
                        {t("live.cancel")}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmAllAsk(true)}
                    className="w-full text-left font-semibold text-green-800 hover:underline"
                    data-testid="confirm-all"
                  >
                    ✓ {t("live.confirmAll", { n: bulkCount })}
                  </button>
                )}
              </div>
            )}
            {addOpen && (
              <div className="space-y-2 rounded-lg border-2 border-amber-400 bg-amber-50 p-3" data-testid="add-missed-panel">
                <p className="text-sm text-amber-950">
                  {draftInfo
                    ? t("live.drawnAt", { yd: draftInfo.yd.toFixed(2), len: draftInfo.len.toFixed(2) })
                    : t("live.drawHint")}
                </p>
                <select
                  value={manualCls}
                  onChange={(e) => setManualCls(e.target.value)}
                  className={inputClass}
                  aria-label={t("live.type")}
                >
                  {DEFECT_CLASSES.map((c) => (
                    <option key={c} value={c}>
                      {t(`cls.${c}`)}
                    </option>
                  ))}
                </select>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => void addManual()} disabled={!draft || busy} data-testid="add-missed-save">
                    {t("live.add")}
                  </Button>
                  {draft && (
                    <Button variant="secondary" onClick={() => setDraft(null)}>
                      {t("live.redraw")}
                    </Button>
                  )}
                  <Button variant="secondary" onClick={closeAddMissed}>
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
                    saving={edits.has(d.id)}
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
