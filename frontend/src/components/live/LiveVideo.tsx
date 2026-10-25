"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from "react";
import type { Defect, Track } from "@/lib/api/client";
import { defectBox, frameAt, isLineScan, rawSize, timeOf } from "@/lib/live/geometry";

export type Capture = { frame: number; jpeg_b64: string; width: number; height: number };

/** A box in view pixels (inside ``view_region``, at the video's own scale): x0, y0, x1, y1. */
export type ViewBox = [number, number, number, number];

export type LiveVideoHandle = {
  video: HTMLVideoElement | null;
  /** JPEG of the camera view (label bar cropped off) at 960 px wide, for evidence photos. */
  capture: (frame: number) => Promise<Capture | null>;
  redraw: () => void;
  /** Seek to a roll frame and play at ``rate`` (1× = real machine speed). */
  playFrom: (frame: number, rate: number) => Promise<void>;
  pause: () => void;
  setRate: (rate: number) => void;
  /** Show a roll frame without playing (e.g. the checkpoint after a reload). */
  seek: (frame: number) => void;
};

type Props = {
  src: string;
  type?: string | null;
  track: Track;
  defects: Defect[];
  selectedId: string | null;
  /** Called on every presented video frame (requestVideoFrameCallback), with the roll frame index. */
  onFrame: (frame: number) => void;
  onEnded: () => void;
  /** Drawing mode: the inspector drags a box around a defect the detector missed. */
  drawing?: boolean;
  /** The box drawn so far (shown until it is saved or cancelled), in view pixels of ``draftFrame``. */
  draft?: ViewBox | null;
  draftFrame?: number | null;
  /** A drawn box, in view pixels of ``frame``: the frame on screen, or for a line-scan roll the strip it was
   * drawn on (older strips stay on screen above the newest). */
  onDrawn?: (box: ViewBox, frame: number) => void;
};

const COLOURS = {
  pending: "#dc2626",
  confirmed: "#16a34a",
  rejected: "#94a3b8",
  nondefect: "#64748b",
};
const MIN_BOX_PX = 18; // tiny defects (a few raw pixels) still get a visible box
const DRAFT_COLOUR = "#f59e0b";
const MIN_DRAWN_PX = 6; // a click without a drag is not a box

/** Line-scan rolls: the screen shows the fabric of this many raw pixels per raw pixel of width (16:9), the
 * newest strip (the video itself) at the bottom and the strips before it stacked above, as a line-scan
 * inspection screen builds its picture. */
const SCREEN_ASPECT = 9 / 16;

type Strip = { top: number; bitmap: ImageBitmap };

type FrameCallbackVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number;
  cancelVideoFrameCallback?: (handle: number) => void;
};

/**
 * The simulated camera: the roll video, uncropped so its "SIMULATED FEED" bar stays visible, with a
 * canvas on top that draws each defect where it is on the fabric in the presented frame. A line-scan roll's
 * frames are thin strips: the strips already seen are kept and drawn above the video (a waterfall).
 */
export const LiveVideo = forwardRef<LiveVideoHandle, Props>(function LiveVideo(
  { src, type, track, defects, selectedId, onFrame, onEnded, drawing = false, draft = null, draftFrame = null, onDrawn },
  ref,
) {
  const videoRef = useRef<FrameCallbackVideo>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const historyRef = useRef<HTMLCanvasElement>(null);
  /** Line-scan: the strips seen so far that are still on screen, keyed by their roll position. */
  const stripsRef = useRef<Strip[]>([]);
  /** Line-scan: the newest frame handed to paintHistory (the stack is painted up to it). */
  const latestRef = useRef(0);
  /** Line-scan: a hidden second copy of the video, for strips the browser skipped. */
  const helperRef = useRef<HTMLVideoElement>(null);
  const fillingRef = useRef(false);
  const lineScan = isLineScan(track);
  const [vx0, vy0, vw0, vh0] = track.view_region;
  /** Raw pixels of fabric shown above the video (0 for an ordinary camera view). */
  const above = lineScan ? Math.max(0, Math.round((vx0 + vw0) * SCREEN_ASPECT) - (vh0 + vy0 + 36)) : 0;
  const defectsRef = useRef(defects);
  const selectedRef = useRef(selectedId);
  const onFrameRef = useRef(onFrame);
  const draftRef = useRef(draft);
  const draftFrameRef = useRef(draftFrame);
  /** The box being dragged right now, in CSS pixels of the canvas. */
  const dragRef = useRef<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  defectsRef.current = defects;
  selectedRef.current = selectedId;
  onFrameRef.current = onFrame;
  draftRef.current = draft;
  draftFrameRef.current = draftFrame;

  const draw = useCallback(
    (frame: number) => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video) return;
      const cssW = video.clientWidth;
      const raw = rawSize(track, video);
      const s = cssW / raw.w;
      const cssH = video.clientHeight + above * s;
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(cssH * dpr);
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);
      ctx.font = "600 12px system-ui, sans-serif";
      for (const d of defectsRef.current) {
        const b = defectBox(d, track, frame);
        const [, vy, , vh] = track.view_region;
        if (b.x1 < 0 || b.x0 > raw.w || b.y1 < vy - above || b.y0 > vy + vh) continue;
        b.y0 += above;
        b.y1 += above;
        const colour =
          d.kind === "nondefect" ? COLOURS.nondefect : COLOURS[d.status as keyof typeof COLOURS] ?? COLOURS.pending;
        let x0 = b.x0 * s;
        let y0 = b.y0 * s;
        let w = (b.x1 - b.x0) * s;
        let h = (b.y1 - b.y0) * s;
        if (w < MIN_BOX_PX) {
          x0 -= (MIN_BOX_PX - w) / 2;
          w = MIN_BOX_PX;
        }
        if (h < MIN_BOX_PX) {
          y0 -= (MIN_BOX_PX - h) / 2;
          h = MIN_BOX_PX;
        }
        const selected = d.id === selectedRef.current;
        ctx.strokeStyle = colour;
        ctx.lineWidth = selected ? 4 : 2.5;
        ctx.setLineDash(d.kind === "nondefect" || d.status === "rejected" ? [6, 4] : []);
        ctx.strokeRect(x0, y0, w, h);
        ctx.setLineDash([]);
        const label = d.defect_no;
        const tw = ctx.measureText(label).width + 8;
        ctx.fillStyle = colour;
        ctx.fillRect(x0, Math.max(0, y0 - 17), tw, 16);
        ctx.fillStyle = "#fff";
        ctx.fillText(label, x0 + 4, Math.max(12, y0 - 5));
      }
      // The missed defect being drawn (amber): the finished draft, or the box under the pointer.
      const [vx, vy] = track.view_region;
      const d = draftRef.current;
      const shift = above + track.roll_y_top_px[draftFrameRef.current ?? frame] - track.roll_y_top_px[frame];
      const drag = dragRef.current;
      const rect = drag
        ? { x: Math.min(drag.x0, drag.x1), y: Math.min(drag.y0, drag.y1), w: Math.abs(drag.x1 - drag.x0), h: Math.abs(drag.y1 - drag.y0) }
        : d
          ? { x: (d[0] + vx) * s, y: (d[1] + vy + shift) * s, w: (d[2] - d[0]) * s, h: (d[3] - d[1]) * s }
          : null;
      if (rect) {
        ctx.strokeStyle = DRAFT_COLOUR;
        ctx.lineWidth = 3;
        ctx.setLineDash([8, 4]);
        ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
        ctx.setLineDash([]);
        ctx.fillStyle = "rgba(245, 158, 11, 0.15)";
        ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
      }
    },
    [track, above],
  );

  /** Line-scan: drop the strips that left the screen and paint the stack up to the newest frame. */
  const paintStack = useCallback(() => {
    const canvas = historyRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;
    const [vx, , vw, vh] = track.view_region;
    const top = track.roll_y_top_px[latestRef.current];
    const keep = stripsRef.current.filter((st) => st.top < top + vh && st.top + vh > top - above);
    for (const st of stripsRef.current) if (!keep.includes(st)) st.bitmap.close();
    stripsRef.current = keep;
    const cssW = video.clientWidth;
    const s = cssW / (vx + vw);
    const dpr = window.devicePixelRatio || 1;
    const h = Math.round(above * s);
    if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, cssW, h);
    // The newest strip is the video below; the ones before it go above, oldest at the top.
    for (const st of keep) {
      if (st.top >= top) continue;
      ctx.drawImage(st.bitmap, vx * s, (above - (top - st.top)) * s, vw * s, vh * s);
    }
  }, [track, above]);

  /** Copy the view region of ``source`` (showing ``frame``) into the stack, unless that strip is there. */
  const keepStrip = useCallback(
    async (source: HTMLVideoElement, frame: number) => {
      const [vx, vy, vw, vh] = track.view_region;
      const top = track.roll_y_top_px[frame];
      if (stripsRef.current.some((st) => st.top === top) || !source.videoWidth) return;
      const k = source.videoWidth / (vx + vw);
      // The picture is taken now; the await only waits for the copy. Calls overlap, so the strip joins the
      // list as it is then, never a list read before the wait.
      const bitmap = await createImageBitmap(source, vx * k, vy * k, vw * k, vh * k);
      if (stripsRef.current.some((st) => st.top === top)) bitmap.close();
      else stripsRef.current = [...stripsRef.current, { top, bitmap }];
    },
    [track],
  );

  /** Strips the browser skipped (it may not present every frame on a busy machine): a second, hidden copy
   * of the video seeks to each missing frame and lends its picture, newest first. One at a time. */
  const fillGaps = useCallback(async () => {
    const helper = helperRef.current;
    if (!helper || fillingRef.current) return;
    fillingRef.current = true;
    const tops = track.roll_y_top_px;
    const vh = track.view_region[3];
    try {
      for (;;) {
        const now = latestRef.current;
        const have = new Set(stripsRef.current.map((st) => st.top));
        let missing = -1;
        for (let f = now - 1; f >= 0 && tops[f] + vh > tops[now] - above; f--) {
          if (tops[f] < tops[now] && !have.has(tops[f])) {
            missing = f;
            break;
          }
        }
        if (missing < 0) break;
        const seeked = new Promise<boolean>((resolve) => {
          const timer = setTimeout(() => resolve(false), 4000);
          helper.addEventListener("seeked", () => {
            clearTimeout(timer);
            resolve(true);
          }, { once: true });
        });
        helper.currentTime = timeOf(track, missing);
        if (!(await seeked)) break;
        await keepStrip(helper, missing);
        if (!stripsRef.current.some((st) => st.top === tops[missing])) break; // could not copy: give up for now
        paintStack();
      }
    } catch {
      // the helper is not ready yet: the next frame tries again
    } finally {
      fillingRef.current = false;
    }
  }, [track, above, keepStrip, paintStack]);

  /** Line-scan: keep the strip on screen now and paint the stack (filling any strip the browser skipped). */
  const paintHistory = useCallback(
    async (frame: number) => {
      const video = videoRef.current;
      if (!lineScan || !video || !video.videoWidth) return;
      latestRef.current = frame;
      try {
        await keepStrip(video, frame);
      } catch {
        // not decodable yet (seeking): the next frame fills it in
      }
      paintStack();
      void fillGaps();
    },
    [lineScan, keepStrip, paintStack, fillGaps],
  );

  // Pointer → view pixels of the raw video (clamped to the camera view, label bar excluded).
  const toView = useCallback(
    (cssX: number, cssY: number): [number, number] => {
      const video = videoRef.current;
      const [vx, vy, vw, vh] = track.view_region;
      const s = (video?.clientWidth ?? 1) / rawSize(track, video).w;
      return [Math.min(Math.max(cssX / s - vx, 0), vw), Math.min(Math.max(cssY / s - above - vy, -above), vh)];
    },
    [track, above],
  );

  function pointerAt(e: React.PointerEvent<HTMLCanvasElement>): [number, number] {
    const r = e.currentTarget.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const [x, y] = pointerAt(e);
    dragRef.current = { x0: x, y0: y, x1: x, y1: y };
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing || !dragRef.current) return;
    const [x, y] = pointerAt(e);
    dragRef.current = { ...dragRef.current, x1: x, y1: y };
    draw(frameAt(track, videoRef.current?.currentTime ?? 0));
  }

  function onPointerUp(e: React.PointerEvent<HTMLCanvasElement>) {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drawing || !drag) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    const [ax, ay] = toView(Math.min(drag.x0, drag.x1), Math.min(drag.y0, drag.y1));
    const [bx, by] = toView(Math.max(drag.x0, drag.x1), Math.max(drag.y0, drag.y1));
    const now = frameAt(track, videoRef.current?.currentTime ?? 0);
    if (bx - ax >= MIN_DRAWN_PX && by - ay >= MIN_DRAWN_PX) {
      // On a line-scan roll the box may lie on an older strip: give it in view pixels of that strip's frame.
      const f = lineScan ? stripFrame(now, (ay + by) / 2) : now;
      const dy = track.roll_y_top_px[now] - track.roll_y_top_px[f];
      onDrawn?.([ax, ay + dy, bx, by + dy], f);
    }
    draw(now);
  }

  const currentFrame = useCallback(() => frameAt(track, videoRef.current?.currentTime ?? 0), [track]);

  /** The latest frame up to ``frame`` whose strip holds view row ``y`` of ``frame`` (y < 0: above the video). */
  function stripFrame(frame: number, y: number): number {
    const want = track.roll_y_top_px[frame] + y;
    for (let f = frame; f >= 0; f--) {
      const top = track.roll_y_top_px[f];
      if (top <= want && want < top + track.view_region[3]) return f;
      if (top + track.view_region[3] <= want - above) break;
    }
    return frame;
  }

  useImperativeHandle(
    ref,
    () => ({
      get video() {
        return videoRef.current;
      },
      redraw: () => draw(currentFrame()),
      playFrom: async (frame: number, rate: number) => {
        const video = videoRef.current;
        if (!video) return;
        video.currentTime = timeOf(track, frame);
        video.playbackRate = rate;
        await video.play().catch(() => undefined);
      },
      pause: () => videoRef.current?.pause(),
      seek: (frame: number) => {
        if (videoRef.current) videoRef.current.currentTime = timeOf(track, frame);
      },
      setRate: (rate: number) => {
        if (videoRef.current) videoRef.current.playbackRate = rate;
      },
      capture: async (frame: number) => {
        const video = videoRef.current;
        if (!video || !video.videoWidth) return null;
        const [vx, vy, vw, vh] = track.view_region;
        const k = video.videoWidth / (vx + vw);
        const width = 960;
        const height = Math.round((vh * width) / vw);
        const c = document.createElement("canvas");
        c.width = width;
        c.height = height;
        const ctx = c.getContext("2d");
        if (!ctx) return null;
        const older = lineScan && frame !== currentFrame() ? stripsRef.current.find((st) => st.top === track.roll_y_top_px[frame]) : undefined;
        if (older) ctx.drawImage(older.bitmap, 0, 0, width, height);
        else ctx.drawImage(video, vx * k, vy * k, vw * k, vh * k, 0, 0, width, height);
        const blob = await new Promise<Blob | null>((resolve) => c.toBlob(resolve, "image/jpeg", 0.82));
        if (!blob) return null;
        const bytes = new Uint8Array(await blob.arrayBuffer());
        let bin = "";
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        return { frame, jpeg_b64: btoa(bin), width, height };
      },
    }),
    [draw, currentFrame, track, lineScan],
  );

  // Per presented frame: draw boxes and report the frame (requestVideoFrameCallback when available).
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let handle = 0;
    let raf = 0;
    const tick = (mediaTime: number) => {
      const f = frameAt(track, mediaTime);
      draw(f);
      void paintHistory(f);
      onFrameRef.current(f);
    };
    if (video.requestVideoFrameCallback) {
      const cb = (_now: number, meta: { mediaTime: number }) => {
        tick(meta.mediaTime);
        handle = video.requestVideoFrameCallback!(cb);
      };
      handle = video.requestVideoFrameCallback(cb);
    } else {
      const loop = () => {
        tick(video.currentTime);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    }
    const onSeeked = () => tick(video.currentTime);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("loadeddata", onSeeked);
    const onResize = () => {
      draw(frameAt(track, video.currentTime));
      void paintHistory(frameAt(track, video.currentTime));
    };
    window.addEventListener("resize", onResize);
    return () => {
      if (handle && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(handle);
      if (raf) cancelAnimationFrame(raf);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("loadeddata", onSeeked);
      window.removeEventListener("resize", onResize);
    };
  }, [track, draw, paintHistory]);

  useEffect(
    () => () => {
      for (const st of stripsRef.current) st.bitmap.close();
      stripsRef.current = [];
    },
    [track],
  );

  // Redraw when the defect list, the selection or the drawn box changes while the video is paused.
  useEffect(() => {
    draw(currentFrame());
  }, [defects, selectedId, draft, drawing, draw, currentFrame]);

  return (
    <div className="relative w-full overflow-hidden rounded-md bg-black">
      {lineScan && (
        <canvas
          ref={historyRef}
          className="block w-full"
          style={{ aspectRatio: `${vx0 + vw0} / ${above}` }}
          aria-hidden
          data-testid="line-scan-history"
        />
      )}
      {lineScan && (
        <video ref={helperRef} className="hidden" muted playsInline preload="auto" aria-hidden>
          <source src={src} type={type ?? undefined} />
        </video>
      )}
      <video
        ref={videoRef}
        className="block h-auto w-full"
        muted
        playsInline
        preload="auto"
        onEnded={onEnded}
        data-testid="roll-video"
      >
        <source src={src} type={type ?? undefined} />
      </video>
      <canvas
        ref={canvasRef}
        className={`absolute inset-0 h-full w-full ${drawing ? "cursor-crosshair touch-none" : "pointer-events-none"}`}
        aria-hidden
        data-testid="video-overlay"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          dragRef.current = null;
        }}
      />
    </div>
  );
});
