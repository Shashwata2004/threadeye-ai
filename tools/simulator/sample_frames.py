#!/usr/bin/env python3
"""
Pick the minimum set of frames that still covers every centimetre of the roll, the way the
ThreadEye app should before sending images to an AI model.

The fabric does not move at a constant speed (the operator stops at defects), so frames are chosen
by fabric position from frames.csv, not by a fixed frame step:
  take a frame whenever the fabric has moved view_length * (1 - overlap) since the last one taken.
While the machine is stopped no new frames are taken. Frames where the inspector's hand is in view
are avoided when a nearby clean frame exists.

Each saved image is the camera view only (the info bar is cropped off); index.csv maps every image
back to its roll position and the fabric's sideways offset so detections can be converted to yards.

Usage:
  python sample_frames.py --video sim_out/roll_video.mp4 --meta sim_out/roll_meta.json --out sim_out/sampled
"""

import argparse
import csv
import json
from pathlib import Path

import cv2

CM_PER_YARD = 91.44


def main():
    ap = argparse.ArgumentParser(description="Extract non-redundant frames from a roll video.")
    ap.add_argument("--video", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlap", type=float, default=0.15, help="fraction of each frame shared with the next one")
    ap.add_argument("--quality", type=int, default=92, help="JPEG quality")
    args = ap.parse_args()

    meta_path = Path(args.meta)
    meta = json.loads(meta_path.read_text())
    region = meta.get("view_region") or meta["fabric_region"]
    view_px = region["h"]
    ppc = meta["px_per_cm"]
    frames = list(csv.DictReader(open(meta_path.parent / meta.get("frames_csv", "frames.csv"))))
    tops = [int(r["roll_y_top_px"]) for r in frames]
    hands = [r.get("hand_visible", "0") == "1" for r in frames]
    advance = view_px * (1 - args.overlap)
    slack = view_px * args.overlap * 0.8

    wanted = []
    last_top = None
    i = 0
    while i < len(frames):
        if last_top is None or tops[i] - last_top >= advance:
            pick = i
            if hands[i]:
                j = i
                while j < len(frames) and tops[j] - (last_top if last_top is not None else 0) <= advance + slack:
                    if not hands[j]:
                        pick = j
                        break
                    j += 1
            wanted.append(pick)
            last_top = tops[pick]
            i = pick + 1
            continue
        i += 1
    if wanted[-1] != len(frames) - 1 and tops[-1] > tops[wanted[-1]]:
        wanted.append(len(frames) - 1)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    rows = []
    wanted_set = set(wanted)
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx in wanted_set:
            crop = frame[region["y"]:region["y"] + region["h"], region["x"]:region["x"] + region["w"]]
            name = f"frame_{idx:06d}.jpg"
            cv2.imwrite(str(out / name), crop, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
            r = frames[idx]
            top = int(r["roll_y_top_px"])
            rows.append([idx, name, top, round(top / ppc / CM_PER_YARD, 4),
                         round((top + view_px) / ppc / CM_PER_YARD, 4), r.get("fabric_x0_px", 0),
                         r.get("hand_visible", 0)])
        idx += 1

    with open(out / "index.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "file", "roll_y_top_px", "top_yd", "bottom_yd", "fabric_x0_px", "hand_visible"])
        w.writerows(rows)
    print(f"Video has {idx} frames; kept {len(rows)} ({args.overlap:.0%} overlap, no repeats while stopped).")
    print(f"That is {len(rows) / max(1, idx):.1%} of all frames. Images and index.csv are in {out.resolve()}")


if __name__ == "__main__":
    main()
