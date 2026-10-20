"""Cut real hands out of EgoHands (Indiana University, CC BY 4.0) for fabricdata.nuisance.hand.

    python ml/scripts/egohands_cutouts.py EGOHANDS_ROOT OUT_DIR [--max 1500]

EGOHANDS_ROOT holds _LABELLED_SAMPLES/<video>/frame_*.jpg and polygons.mat (one row per frame, in file-name
order; fields myleft, myright, yourleft, yourright: polygon x, y in pixels). Only hands whose polygon touches
an image border are kept: the forearm continues off the frame there, so pasted at a tile edge the hand
enters the view naturally instead of floating. Writes OUT_DIR/hand_NNNNN.png (RGBA, feathered edge) and
OUT_DIR/hands.json ([{file, edge, video}]).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import scipy.io as sio
from PIL import Image, ImageDraw, ImageFilter

FIELDS = ("myleft", "myright", "yourleft", "yourright")
BORDER_PX = 4
MIN_AREA = 2500


def entry_edge(poly: np.ndarray, w: int, h: int) -> str | None:
    near = {"left": (poly[:, 0] <= BORDER_PX).sum(), "right": (poly[:, 0] >= w - 1 - BORDER_PX).sum(),
            "top": (poly[:, 1] <= BORDER_PX).sum(), "bottom": (poly[:, 1] >= h - 1 - BORDER_PX).sum()}
    edge, n = max(near.items(), key=lambda kv: kv[1])
    return edge if n >= 2 else None


def cutouts(video: Path) -> list[tuple[np.ndarray, str]]:
    frames = sorted(video.glob("frame_*.jpg"))
    polys = sio.loadmat(video / "polygons.mat")["polygons"][0]
    out = []
    for frame, row in zip(frames, polys, strict=False):
        img = None
        for field in FIELDS:
            poly = np.asarray(row[field], dtype=np.float64)
            if poly.ndim != 2 or poly.shape[0] < 3:
                continue
            if img is None:
                img = Image.open(frame).convert("RGB")
            w, h = img.size
            edge = entry_edge(poly, w, h)
            if edge is None:
                continue
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).polygon([tuple(p) for p in poly], fill=255)
            m = np.asarray(mask)
            if (m > 0).sum() < MIN_AREA:
                continue
            ys, xs = np.nonzero(m)
            x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
            soft = mask.filter(ImageFilter.GaussianBlur(1.2))
            rgba = np.dstack([np.asarray(img), np.asarray(soft)])[y0:y1, x0:x1]
            out.append((rgba, edge))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--max", type=int, default=1500)
    args = ap.parse_args()
    videos = sorted(p.parent for p in args.root.rglob("polygons.mat"))
    per_video = max(1, args.max // max(len(videos), 1))
    args.out.mkdir(parents=True, exist_ok=True)
    meta = []
    for i, video in enumerate(videos):
        print(f"  video {i + 1}/{len(videos)}: {len(meta)} cutouts so far", flush=True)
        found = cutouts(video)
        step = max(1, len(found) // per_video)
        for rgba, edge in found[::step][:per_video]:
            name = f"hand_{len(meta):05d}.png"
            Image.fromarray(rgba, "RGBA").save(args.out / name)
            meta.append({"file": name, "edge": edge, "video": video.name})
    (args.out / "hands.json").write_text(json.dumps(meta))
    print(f"{len(meta)} hand cutouts from {len(videos)} videos -> {args.out}")


if __name__ == "__main__":
    main()
