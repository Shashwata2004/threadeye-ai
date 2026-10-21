"""Real AITEX defects, cut out along their masks, pasted onto clean AITEX weave: more examples of the tiny
defects (fuzzyball, nep, warp ball, knot) the detector misses.

    ml/.venv/bin/python ml/aitex_paste.py --external data/external --n 600

Donors are the defects of at most --max-side px in AITEX images of the train split, and the bases are clean
AITEX images of the train split (the split is computed as the build computes it, per source, so no val/test
pixels reach training; fabric 02, the demo roll's fabric, is always test). Each pasted defect keeps its own
pixels: it is moved to the brightness of its new place (the mean of a ring around it) and blended in with a
feathered mask, sometimes flipped. Writes data/external/aitex_paste/{images/, annotations.json, groups.json},
read by fabricdata.sources.read_aitex_paste; every image is forced into the train split.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabricdata import sources  # noqa: E402
from fabricdata.split import assign_splits  # noqa: E402

MARGIN = 6
"""Pixels of fabric kept around a donor defect (its ring sets the brightness match)."""
EDGE = 0.1
"""Share of an AITEX image's width at each end left alone: the left end of the strips is the selvage."""


def donors(records: list, split_of: dict, max_side: int) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """(AITEX code, patch, defect mask) of every small train-split defect, cut from its image and mask files."""
    out = []
    for r in records:
        if not r.boxes or split_of[r.key] != "train":
            continue
        img = np.asarray(Image.open(r.path).convert("L"), np.float32)
        masks = sorted(r.path.parents[1].glob(f"Mask_images/{r.path.stem}_mask*.png"))
        mask = np.zeros(img.shape, bool)
        for mp in masks:
            mask |= np.asarray(Image.open(mp).convert("L")) > 0
        h, w = img.shape
        for b in r.boxes:
            if max(b.w, b.h) > max_side or b.src_cls == "022":  # 022 is cut selvage: an edge, not a spot
                continue
            x0, y0 = max(0, int(b.x0) - MARGIN), max(0, int(b.y0) - MARGIN)
            x1, y1 = min(w, int(np.ceil(b.x1)) + MARGIN), min(h, int(np.ceil(b.y1)) + MARGIN)
            m = mask[y0:y1, x0:x1]
            if m.sum() < 2:
                continue
            out.append((b.src_cls, img[y0:y1, x0:x1].copy(), m.copy()))
    return out


def paste(base: np.ndarray, patch: np.ndarray, m: np.ndarray, x: int, y: int) -> tuple[float, float, float, float]:
    """Blend ``patch`` (its defect pixels ``m``) into ``base`` at (x, y); returns the defect's box there."""
    ph, pw = patch.shape
    region = base[y : y + ph, x : x + pw]
    ring = ~m
    shift = region[ring].mean() - patch[ring].mean() if ring.any() else 0.0
    alpha = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)), np.float32)
    alpha = np.clip(alpha / 255.0 * 1.6, 0.0, 1.0)  # full strength inside the defect, a soft one-pixel edge
    region[:] = region * (1 - alpha) + (patch + shift) * alpha
    ys, xs = np.nonzero(m)
    return float(x + xs.min()), float(y + ys.min()), float(x + xs.max() + 1), float(y + ys.max() + 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--n", type=int, default=600, help="pasted images to write")
    ap.add_argument("--per-image", type=int, default=3, help="defects pasted per image")
    ap.add_argument("--max-side", type=int, default=48, help="largest donor defect (px)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    records = list(sources.read_aitex(args.external / "aitex"))
    split_of = assign_splits(records, seed=0)  # the build's split (per source, seed 0)
    pool = donors(records, split_of, args.max_side)
    bases = [r for r in records if r.defect_free and split_of[r.key] == "train"]
    print(f"{len(pool)} donor defects {sorted({c for c, _, _ in pool})}, {len(bases)} clean train images", flush=True)
    out = args.external / "aitex_paste"
    (out / "images").mkdir(parents=True, exist_ok=True)
    coco: dict = {"images": [], "annotations": [], "categories": []}
    cats: list[str] = []
    groups = {}
    for i in range(args.n):
        base_rec = rng.choice(bases)
        base = np.asarray(Image.open(base_rec.path).convert("L"), np.float32).copy()
        h, w = base.shape
        placed: list[tuple[float, float, float, float]] = []
        boxes = []
        for _ in range(args.per_image):
            code, patch, m = rng.choice(pool)
            if rng.random() < 0.5:
                patch, m = patch[:, ::-1], m[:, ::-1]
            if rng.random() < 0.5:
                patch, m = patch[::-1], m[::-1]
            ph, pw = patch.shape
            for _ in range(20):  # a free place away from the edges and the other pastes
                x = rng.randint(int(w * EDGE), int(w * (1 - EDGE)) - pw)
                y = rng.randint(0, h - ph)
                spot = base[y : y + ph, x : x + pw]
                # Woven texture only: some AITEX images have blown-out white or black areas.
                if spot.std() < 4 or not 20 < spot.mean() < 230:
                    continue
                if all(x + pw + 20 < a or x > c + 20 or y + ph + 20 < b or y > d + 20 for a, b, c, d in placed):
                    break
            else:
                continue
            box = paste(base, np.ascontiguousarray(patch), np.ascontiguousarray(m), x, y)
            placed.append(box)
            boxes.append((code, box))
        name = f"paste_{i:05d}.png"
        Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).save(out / "images" / name)
        img_id = i + 1
        coco["images"].append({"id": img_id, "file_name": name, "width": w, "height": h})
        for code, (x0, y0, x1, y1) in boxes:
            if code not in cats:
                cats.append(code)
            coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": img_id,
                                        "category_id": cats.index(code) + 1,
                                        "bbox": [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)],
                                        "area": round((x1 - x0) * (y1 - y0), 1), "iscrowd": 0})
        groups[name] = {"group": base_rec.group, "base": base_rec.path.name}
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{args.n} images", flush=True)
    coco["categories"] = [{"id": k + 1, "name": c} for k, c in enumerate(cats)]
    (out / "annotations.json").write_text(json.dumps(coco))
    (out / "groups.json").write_text(json.dumps(groups))
    print(f"{len(coco['images'])} images, {len(coco['annotations'])} pasted defects -> {out}")


if __name__ == "__main__":
    main()
