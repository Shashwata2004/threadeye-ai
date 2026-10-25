import type { Defect, Track } from "@/lib/api/client";

// Roll coordinates → pixels of the raw video frame (PLAN.md §6.1 step 5, inverse mapping). Boxes stay
// attached to the moving fabric because they are stored in roll coordinates and projected per frame:
//   y = along_cm × px_per_cm − roll_y_top_px[f] + view_y      x = across_cm × px_per_cm + fabric_x0_px[f] + view_x

export const YARD_CM = 91.44;

export type Box = { x0: number; y0: number; x1: number; y1: number };

/** The frame the video shows at ``mediaTime`` (seconds). */
export function frameAt(track: Track, mediaTime: number): number {
  const f = Math.round(mediaTime * track.fps);
  return Math.min(Math.max(f, 0), track.frame_count - 1);
}

/** Seek position for a frame: a little after its start, so the browser lands on that frame. */
export function timeOf(track: Track, frame: number): number {
  return (frame + 0.25) / track.fps;
}

/** Raw video width/height (the view region plus the simulator's label bar). */
export function rawSize(track: Track, video?: HTMLVideoElement | null): { w: number; h: number } {
  const [vx, , vw, vh] = track.view_region;
  const w = vx + vw;
  const ratio = video && video.videoWidth ? video.videoHeight / video.videoWidth : (vh + 36) / w;
  return { w, h: Math.round(w * ratio) };
}

export function defectBox(d: Pick<Defect, "start_yd" | "end_yd" | "across_start_cm" | "across_end_cm">, track: Track, frame: number): Box {
  const ppc = track.px_per_cm;
  const [vx, vy] = track.view_region;
  const top = track.roll_y_top_px[frame];
  const x0f = track.fabric_x0_px[frame];
  return {
    x0: d.across_start_cm * ppc + x0f + vx,
    x1: d.across_end_cm * ppc + x0f + vx,
    y0: d.start_yd * YARD_CM * ppc - top + vy,
    y1: d.end_yd * YARD_CM * ppc - top + vy,
  };
}

/** A line-scan camera's frames: strips far wider than high (each frame is the next strip of fabric). */
export function isLineScan(track: Track): boolean {
  const [, , vw, vh] = track.view_region;
  return vw > 4 * vh;
}

/** Is any part of the box inside the camera view (excluding the label bar)? */
export function inView(b: Box, track: Track): boolean {
  const [vx, vy, vw, vh] = track.view_region;
  return b.x1 >= vx && b.x0 <= vx + vw && b.y1 >= vy && b.y0 <= vy + vh;
}

/** Middle of the view along the roll, in yards: where the inspector is looking. */
export function viewCentreYd(track: Track, frame: number): number {
  return (track.top_yd[frame] + track.bottom_yd[frame]) / 2;
}
