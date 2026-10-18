"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from "react";
import type { Defect, Track } from "@/lib/api/client";
import { defectBox, frameAt, inView, rawSize, timeOf } from "@/lib/live/geometry";

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
  /** The box drawn so far (shown until it is saved or cancelled). */
  draft?: ViewBox | null;
  onDrawn?: (box: ViewBox) => void;
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

type FrameCallbackVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number;
  cancelVideoFrameCallback?: (handle: number) => void;
};

/**
 * The simulated camera: the roll video, uncropped so its "SIMULATED FEED" bar stays visible, with a
 * canvas on top that draws each defect where it is on the fabric in the presented frame.
 */
export const LiveVideo = forwardRef<LiveVideoHandle, Props>(function LiveVideo(
  { src, type, track, defects, selectedId, onFrame, onEnded, drawing = false, draft = null, onDrawn },
  ref,
) {
  const videoRef = useRef<FrameCallbackVideo>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const defectsRef = useRef(defects);
  const selectedRef = useRef(selectedId);
  const onFrameRef = useRef(onFrame);
  const draftRef = useRef(draft);
  /** The box being dragged right now, in CSS pixels of the canvas. */
  const dragRef = useRef<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  defectsRef.current = defects;
  selectedRef.current = selectedId;
  onFrameRef.current = onFrame;
  draftRef.current = draft;

  const draw = useCallback(
    (frame: number) => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video) return;
      const cssW = video.clientWidth;
      const cssH = video.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(cssH * dpr);
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);
      const raw = rawSize(track, video);
      const s = cssW / raw.w;
      ctx.font = "600 12px system-ui, sans-serif";
      for (const d of defectsRef.current) {
        const b = defectBox(d, track, frame);
        if (!inView(b, track)) continue;
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
      const drag = dragRef.current;
      const rect = drag
        ? { x: Math.min(drag.x0, drag.x1), y: Math.min(drag.y0, drag.y1), w: Math.abs(drag.x1 - drag.x0), h: Math.abs(drag.y1 - drag.y0) }
        : d
          ? { x: (d[0] + vx) * s, y: (d[1] + vy) * s, w: (d[2] - d[0]) * s, h: (d[3] - d[1]) * s }
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
    [track],
  );

  // Pointer → view pixels of the raw video (clamped to the camera view, label bar excluded).
  const toView = useCallback(
    (cssX: number, cssY: number): [number, number] => {
      const video = videoRef.current;
      const [vx, vy, vw, vh] = track.view_region;
      const s = (video?.clientWidth ?? 1) / rawSize(track, video).w;
      return [Math.min(Math.max(cssX / s - vx, 0), vw), Math.min(Math.max(cssY / s - vy, 0), vh)];
    },
    [track],
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
    if (bx - ax >= MIN_DRAWN_PX && by - ay >= MIN_DRAWN_PX) onDrawn?.([ax, ay, bx, by]);
    draw(frameAt(track, videoRef.current?.currentTime ?? 0));
  }

  const currentFrame = useCallback(() => frameAt(track, videoRef.current?.currentTime ?? 0), [track]);

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
        ctx.drawImage(video, vx * k, vy * k, vw * k, vh * k, 0, 0, width, height);
        const blob = await new Promise<Blob | null>((resolve) => c.toBlob(resolve, "image/jpeg", 0.82));
        if (!blob) return null;
        const bytes = new Uint8Array(await blob.arrayBuffer());
        let bin = "";
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        return { frame, jpeg_b64: btoa(bin), width, height };
      },
    }),
    [draw, currentFrame, track],
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
    const onResize = () => draw(frameAt(track, video.currentTime));
    window.addEventListener("resize", onResize);
    return () => {
      if (handle && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(handle);
      if (raf) cancelAnimationFrame(raf);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("loadeddata", onSeeked);
      window.removeEventListener("resize", onResize);
    };
  }, [track, draw]);

  // Redraw when the defect list, the selection or the drawn box changes while the video is paused.
  useEffect(() => {
    draw(currentFrame());
  }, [defects, selectedId, draft, drawing, draw, currentFrame]);

  return (
    <div className="relative w-full overflow-hidden rounded-md bg-black">
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
