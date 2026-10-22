#!/usr/bin/env python3
"""
ThreadEye roll simulator.

Builds a long "virtual fabric roll" from procedurally generated fabric (synthetic) or a public defect
dataset (AITEX or a YOLO-format export) and renders a video of the roll moving under a fixed top-down
camera, the way fabric crosses an inspection machine.

Realistic mode (default) adds what a camera on a real inspection machine sees: the operator slowing down
and stopping at defects, pausing, then ramping back up; occasional stops for no reason; small speed
wobble; sideways wander of the fabric; the back-lit board beside both fabric edges; the selvage band with
stenter pin holes and wavy edges; handling wrinkles; loose threads lying on the fabric; stickers the
inspector places on the selvage at each stop; the inspector's forearm reaching in; slow exposure drift.
Wrinkles, threads, stickers and pin holes are NOT defects - they are there to test false alarms.

Outputs (in --out directory):
  roll_video.mp4      the video (fabric enters at the bottom, exits at the top)
  ground_truth.csv    every defect with roll position in yards, size, 4-point points, stop frame
  nuisance.csv        things that look suspicious but are not defects (wrinkles, threads, stickers)
  frames.csv          per frame: fabric position, speed, running/stopped, sideways offset, hand in view
  roll_meta.json      parameters, geometry and the expected 4-point roll score
  roll_preview.png    the whole roll as one strip (red = defects, orange = non-defects)

Position of a pixel (x, y) in frame i:
  roll_y_px = frames.roll_y_top_px[i] + y          yard = roll_y_px / px_per_cm / 91.44
  x_on_fabric_px = x - frames.fabric_x0_px[i]      across_cm = x_on_fabric_px / px_per_cm
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import shutil
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

CM_PER_YARD = 91.44
CM_PER_INCH = 2.54
IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

AITEX_CODES = {
    "002": "broken_end",
    "006": "broken_yarn",
    "010": "broken_pick",
    "016": "weft_curling",
    "019": "fuzzyball",
    "022": "cut_selvage",
    "023": "crease",
    "025": "warp_ball",
    "027": "knots",
    "029": "contamination",
    "030": "nep",
    "036": "weft_crack",
}


@dataclass
class Box:
    cls: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Cell:
    key: str
    boxes: list[Box] = field(default_factory=list)
    params: dict = field(default_factory=dict)


def hex_to_bgr(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected a hex colour like #3b5b8c, got {value!r}")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return b, g, r


def ramp(n: int, overlap: int) -> np.ndarray:
    w = np.ones(n, dtype=np.float32)
    if overlap <= 0:
        return w
    r = (np.arange(overlap, dtype=np.float32) + 0.5) / overlap
    w[:overlap] = np.minimum(w[:overlap], r)
    w[-overlap:] = np.minimum(w[-overlap:], r[::-1])
    return w


# --------------------------------------------------------------------------
# Synthetic source
# --------------------------------------------------------------------------


class SyntheticSource:
    name = "synthetic"
    classes = ["hole", "stain", "yarn_defect", "knot"]
    class_weights = [0.25, 0.30, 0.30, 0.15]

    def __init__(self, args, frame_w: int, px_per_cm: float):
        self.cols = 1
        self.overlap = 0
        self.cell_w = frame_w
        self.cell_h = 256
        self.px_per_cm = px_per_cm
        self.seed = args.seed
        self.base = np.array(hex_to_bgr(args.fabric_color), dtype=np.float32)
        self.weave_period = args.weave_period_px
        gen = np.random.default_rng(self.seed)
        self.warp_profile = gen.normal(0.0, 4.0, size=frame_w).astype(np.float32)
        self.warp_profile = cv2.GaussianBlur(self.warp_profile.reshape(1, -1), (0, 0), 1.2).ravel()

    def plan(self, n_rows: int, rng: random.Random, p_defect: float) -> list[list[Cell]]:
        rows = []
        for r in range(n_rows):
            cell = Cell(key=f"synthetic_row_{r}")
            if rng.random() < p_defect:
                cls = rng.choices(self.classes, weights=self.class_weights)[0]
                spec, box = self._make_defect(cls, rng)
                cell.params["defects"] = [spec]
                cell.boxes.append(box)
            rows.append([cell])
        return rows

    def _make_defect(self, cls: str, rng: random.Random):
        ppc = self.px_per_cm
        h, w = self.cell_h, self.cell_w
        if cls == "hole":
            d = rng.uniform(0.25, 3.5) * ppc
            a, b = d / 2, d / 2 * rng.uniform(0.6, 1.0)
            pad = a + 6
        elif cls == "stain":
            d = rng.uniform(1.0, 7.0) * ppc
            a, b = d / 2, d / 2 * rng.uniform(0.5, 1.0)
            pad = a + 6
        elif cls == "knot":
            d = rng.uniform(0.3, 1.0) * ppc
            a, b = d / 2, max(1.5, d / 2 * rng.uniform(0.3, 0.6))
            pad = a + 4
        else:
            length = rng.uniform(4.0, 40.0) * ppc
            a, b = length / 2, 1.5
            pad = 6
        pad = min(pad, h / 2 - 2)
        cx = rng.uniform(max(pad, a + 4), w - max(pad, a + 4))
        cy = rng.uniform(pad, h - pad)
        angle = rng.uniform(-25, 25) if cls in ("hole", "stain", "knot") else rng.uniform(-1.5, 1.5)
        spec = {
            "cls": cls,
            "cx": cx,
            "cy": cy,
            "a": a,
            "b": b,
            "angle": angle,
            "seed": rng.randrange(1 << 30),
            "dark": rng.random() < 0.6,
        }
        ext_x, ext_y = self._extent(a, b, angle)
        box = Box(cls, max(0, cx - ext_x), max(0, cy - ext_y), min(w, cx + ext_x), min(h, cy + ext_y))
        return spec, box

    @staticmethod
    def _extent(a: float, b: float, angle_deg: float) -> tuple[float, float]:
        t = math.radians(angle_deg)
        ex = math.sqrt((a * math.cos(t)) ** 2 + (b * math.sin(t)) ** 2) + 2
        ey = math.sqrt((a * math.sin(t)) ** 2 + (b * math.cos(t)) ** 2) + 2
        return ex, ey

    def cell_image(self, r: int, c: int, cell: Cell) -> np.ndarray:
        h, w = self.cell_h, self.cell_w
        y0 = r * h
        gen = np.random.default_rng((self.seed * 1_000_003 + r) & 0xFFFFFFFF)
        yy = (y0 + np.arange(h, dtype=np.float32)).reshape(-1, 1)
        xx = np.arange(w, dtype=np.float32).reshape(1, -1)
        p = self.weave_period
        weave = 3.5 * (np.sin(2 * np.pi * xx / p) + np.sin(2 * np.pi * yy / p + 0.7))
        weft = gen.normal(0.0, 4.0, size=(h, 1)).astype(np.float32)
        shade = 3.0 * np.sin(2 * np.pi * yy / (self.px_per_cm * 45.0))
        noise = gen.normal(0.0, 2.5, size=(h, w)).astype(np.float32)
        tex = weave + weft + shade + noise + self.warp_profile.reshape(1, -1)
        img = self.base.reshape(1, 1, 3) * (1.0 + tex[..., None] / 110.0)
        for spec in cell.params.get("defects", []):
            img = self._paint(img, spec)
        return np.clip(img, 0, 255).astype(np.uint8)

    def _paint(self, img: np.ndarray, s: dict) -> np.ndarray:
        h, w = img.shape[:2]
        gen = np.random.default_rng(s["seed"])
        cls = s["cls"]
        center = (int(round(s["cx"])), int(round(s["cy"])))
        axes = (max(1, int(round(s["a"]))), max(1, int(round(s["b"]))))
        if cls == "hole":
            m = np.zeros((h, w), np.float32)
            cv2.ellipse(m, center, axes, s["angle"], 0, 360, 1.0, -1, cv2.LINE_AA)
            m = cv2.GaussianBlur(m, (0, 0), 1.0)
            m = m + gen.normal(0, 0.18, size=m.shape).astype(np.float32) * (m > 0.05)
            core = (m > 0.5).astype(np.float32)
            ring = cv2.dilate(core, np.ones((5, 5), np.uint8)) - core
            img = img * (1 - 0.35 * ring[..., None])
            img = img * (1 - core[..., None]) + core[..., None] * gen.uniform(225, 245)
        elif cls == "stain":
            m = np.zeros((h, w), np.float32)
            for _ in range(4):
                off = (center[0] + int(gen.normal(0, s["a"] * 0.3)), center[1] + int(gen.normal(0, s["b"] * 0.3)))
                ax = (max(1, int(axes[0] * gen.uniform(0.5, 0.9))), max(1, int(axes[1] * gen.uniform(0.5, 0.9))))
                cv2.ellipse(m, off, ax, s["angle"] + gen.uniform(-30, 30), 0, 360, 1.0, -1, cv2.LINE_AA)
            m = cv2.GaussianBlur(m, (0, 0), max(1.0, s["a"] * 0.25))
            m = np.clip(m, 0, 1) * gen.uniform(0.35, 0.6)
            colour = np.array([40, 70, 95], np.float32) if s["dark"] else np.array([60, 110, 140], np.float32)
            img = img * (1 - m[..., None]) + colour.reshape(1, 1, 3) * m[..., None]
        elif cls == "knot":
            m = np.zeros((h, w), np.float32)
            cv2.ellipse(m, center, axes, s["angle"], 0, 360, 1.0, -1, cv2.LINE_AA)
            m = cv2.GaussianBlur(m, (0, 0), 0.8) * 0.55
            img = img * (1 - m[..., None])
        else:
            n = max(2, int(2 * s["a"]))
            xs = np.linspace(s["cx"] - s["a"], s["cx"] + s["a"], n)
            t = math.tan(math.radians(s["angle"]))
            ys = s["cy"] + (xs - s["cx"]) * t + 0.8 * np.sin(xs / gen.uniform(15, 40))
            pts = np.stack([xs, ys], axis=1).round().astype(np.int32).reshape(-1, 1, 2)
            m = np.zeros((h, w), np.float32)
            cv2.polylines(m, [pts], False, 1.0, int(gen.integers(1, 3)), cv2.LINE_AA)
            m = cv2.GaussianBlur(m, (0, 0), 0.6)
            if s["dark"]:
                img = img * (1 - 0.45 * m[..., None])
            else:
                img = img + (255 - img) * 0.45 * m[..., None]
        return img


# --------------------------------------------------------------------------
# Dataset sources (YOLO export / AITEX)
# --------------------------------------------------------------------------


class DatasetSource:
    def __init__(self, args, frame_w: int, good: list[Path], defects: list[tuple[Path, list[Box] | None]],
                 native_size: tuple[int, int], name: str):
        if not good:
            raise SystemExit(
                "No defect-free images found. Add a folder of defect-free fabric images with --good-dir "
                "(the simulator needs clean fabric between defects)."
            )
        if not defects:
            raise SystemExit("No defect images with labels were found in the dataset.")
        self.name = name
        self.good = good
        self.trim_l, self.trim_r = args.trim_left, args.trim_right
        keep = 1.0 - self.trim_l - self.trim_r
        if keep <= 0.05:
            raise SystemExit("--trim-left + --trim-right leave nothing of the image")
        self.defects = []
        for path, boxes in defects:
            moved = []
            for b in boxes or []:
                x0, x1 = (b.x0 - self.trim_l) / keep, (b.x1 - self.trim_l) / keep
                if x1 <= 0 or x0 >= 1:
                    continue
                moved.append(Box(b.cls, max(0.0, x0), b.y0, min(1.0, x1), b.y1))
            if moved:
                self.defects.append((path, moved))
        if not self.defects:
            raise SystemExit("All labelled defects fall inside the trimmed edges; reduce --trim-left/--trim-right")
        nw, nh = native_size
        nw = nw * keep
        self.overlap = args.overlap
        if args.tiles_across == "auto":
            self.cols = max(1, round(frame_w / nw))
        else:
            self.cols = max(1, int(args.tiles_across))
        o = self.overlap if self.cols > 1 else 0
        self.cell_w = int(math.ceil((frame_w + (self.cols - 1) * o) / self.cols))
        self.cell_h = max(16, int(round(self.cell_w * nh / nw)))
        self.tint = np.array(hex_to_bgr(args.tint), np.float32) if args.tint else None
        self.flatten = not args.no_flatten
        self.cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.target = self._target_stats()

    def _profiles(self, img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        h, w = img.shape[:2]
        rows = img.mean(axis=(1, 2)).astype(np.float32).reshape(-1, 1)
        rows = cv2.GaussianBlur(rows, (1, 0), sigmaX=0.1, sigmaY=max(2.0, h / 6), borderType=cv2.BORDER_REFLECT)
        cols = img.mean(axis=(0, 2)).astype(np.float32).reshape(1, -1)
        cols = cv2.GaussianBlur(cols, (0, 1), sigmaX=max(4.0, w / 30), sigmaY=0.1, borderType=cv2.BORDER_REFLECT)
        return np.maximum(rows.ravel(), 1.0), np.maximum(cols.ravel(), 1.0)

    def _flat_field(self, img: np.ndarray) -> np.ndarray:
        """Give every tile the same slow lighting profile (the median of the defect-free tiles) so neighbouring
        tiles blend without banding. Heavy smoothing keeps thin defect lines intact."""
        rows, cols = self._profiles(img)
        ref_rows, ref_cols = self.ref_profiles
        img = img * (ref_rows / rows)[:, None, None]
        return img * (ref_cols / cols)[None, :, None]

    def _load(self, path: Path) -> np.ndarray:
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            raise SystemExit(f"Could not read image: {path}")
        w = img.shape[1]
        img = img[:, int(round(w * self.trim_l)) : w - int(round(w * self.trim_r))]
        return cv2.resize(img, (self.cell_w, self.cell_h), interpolation=cv2.INTER_AREA)

    def _target_stats(self):
        sample = self.good[:: max(1, len(self.good) // 20)][:20]
        imgs = [self._load(p).astype(np.float32) for p in sample]
        profs = [self._profiles(im) for im in imgs]
        self.ref_profiles = (np.median([p[0] for p in profs], axis=0), np.median([p[1] for p in profs], axis=0))
        if self.flatten:
            imgs = [self._flat_field(im) for im in imgs]
        means = [im.reshape(-1, 3).mean(0) for im in imgs]
        stds = [im.reshape(-1, 3).std(0) for im in imgs]
        return np.median(means, axis=0), np.median(stds, axis=0)

    def plan(self, n_rows: int, rng: random.Random, p_defect: float) -> list[list[Cell]]:
        rows = []
        for _ in range(n_rows):
            row = []
            for _ in range(self.cols):
                if rng.random() < p_defect:
                    path, boxes = rng.choice(self.defects)
                    if boxes is None:
                        boxes = []
                    row.append(Cell(key=str(path), boxes=[Box(b.cls, b.x0 * self.cell_w, b.y0 * self.cell_h,
                                                              b.x1 * self.cell_w, b.y1 * self.cell_h) for b in boxes]))
                else:
                    row.append(Cell(key=str(rng.choice(self.good))))
            rows.append(row)
        return rows

    def cell_image(self, r: int, c: int, cell: Cell) -> np.ndarray:
        if cell.key in self.cache:
            self.cache.move_to_end(cell.key)
            return self.cache[cell.key]
        img = self._load(Path(cell.key)).astype(np.float32)
        if self.flatten:
            img = self._flat_field(img)
        m = img.reshape(-1, 3).mean(0)
        s = np.maximum(img.reshape(-1, 3).std(0), 1.0)
        tm, ts = self.target
        img = (img - m) / s * ts + tm
        if self.tint is not None:
            gray = img.mean(axis=2, keepdims=True)
            img = gray / 128.0 * self.tint.reshape(1, 1, 3)
        out = np.clip(img, 0, 255).astype(np.uint8)
        self.cache[cell.key] = out
        if len(self.cache) > 96:
            self.cache.popitem(last=False)
        return out


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXTS)


def load_yolo(args, frame_w: int) -> DatasetSource:
    root = Path(args.dataset)
    names: list[str] = []
    yaml_files = list(root.glob("data.yaml")) + list(root.glob("*.yaml"))
    if yaml_files:
        try:
            import yaml
        except ImportError:
            raise SystemExit("pip install pyyaml (needed to read data.yaml)")
        data = yaml.safe_load(yaml_files[0].read_text())
        raw = data.get("names", [])
        names = [raw[k] for k in sorted(raw)] if isinstance(raw, dict) else list(raw)
    good, defects = [], []
    sizes = []
    for img_path in list_images(root):
        parts = list(img_path.parts)
        if "images" not in parts:
            continue
        i = len(parts) - 1 - parts[::-1].index("images")
        label = Path(*parts[:i], "labels", *parts[i + 1 :]).with_suffix(".txt")
        boxes = []
        if label.exists():
            for line in label.read_text().split("\n"):
                vals = line.split()
                if len(vals) < 5:
                    continue
                cid = int(float(vals[0]))
                nums = [float(v) for v in vals[1:]]
                if len(nums) == 4:
                    cx, cy, bw, bh = nums
                    x0, y0, x1, y1 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
                else:
                    xs, ys = nums[0::2], nums[1::2]
                    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                cls = names[cid] if cid < len(names) else f"class_{cid}"
                boxes.append(Box(cls, max(0, x0), max(0, y0), min(1, x1), min(1, y1)))
        if boxes:
            defects.append((img_path, boxes))
        else:
            good.append(img_path)
        if len(sizes) < 5:
            im = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
            if im is not None:
                sizes.append((im.shape[1], im.shape[0]))
    if args.good_dir:
        good = list_images(Path(args.good_dir))
    if not sizes:
        raise SystemExit(f"No images under an 'images' folder in {root}")
    return DatasetSource(args, frame_w, good, defects, sizes[0], f"yolo:{root.name}")


def load_aitex(args, frame_w: int) -> DatasetSource:
    root = Path(args.dataset)
    defect_dir, mask_dir, good_dir = root / "Defect_images", root / "Mask_images", root / "NODefect_images"
    if not defect_dir.exists():
        raise SystemExit(f"{defect_dir} not found (expected the AITEX folder layout)")
    defects = []
    native = None
    for img_path in list_images(defect_dir):
        im = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        h, w = im.shape
        native = native or (w, h)
        code = img_path.stem.split("_")[1] if "_" in img_path.stem else "unknown"
        cls = AITEX_CODES.get(code, f"aitex_{code}")
        boxes = []
        merged = np.zeros((h, w), np.uint8)
        for mp in sorted(mask_dir.glob(img_path.stem + "_mask*")):
            m = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
            if m is not None and m.shape == merged.shape:
                merged |= (m > 0).astype(np.uint8)
        if merged.any():
            grouped = cv2.dilate(merged, np.ones((31, 61), np.uint8))
            n, labels = cv2.connectedComponents(grouped)
            for k in range(1, n):
                ys, xs = np.nonzero((labels == k) & (merged > 0))
                if len(xs) < 4:
                    continue
                boxes.append(Box(cls, xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h))
        if boxes:
            defects.append((img_path, boxes))
    good = list_images(Path(args.good_dir)) if args.good_dir else (list_images(good_dir) if good_dir.exists() else [])
    if native is None:
        raise SystemExit("No readable defect images found")

    def fabric_of(p: Path) -> str:
        parts = p.stem.split("_")
        return parts[2][:2] if len(parts) > 2 else "?"

    fabric = args.fabric_id
    if fabric == "auto":
        good_ids = {fabric_of(p) for p in good}
        counts: dict[str, int] = {}
        for p, _ in defects:
            if fabric_of(p) in good_ids or args.good_dir:
                counts[fabric_of(p)] = counts.get(fabric_of(p), 0) + 1
        fabric = max(counts, key=counts.get) if counts else "all"
    if fabric != "all":
        defects = [d for d in defects if fabric_of(d[0]) == fabric]
        if not args.good_dir:
            good = [p for p in good if fabric_of(p) == fabric]
    print(f"AITEX fabric type {fabric}: {len(defects)} defect images, {len(good)} defect-free images")
    return DatasetSource(args, frame_w, good, defects, native, f"aitex-fabric-{fabric}")


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


SEAM_SHIFT = 8
"""Largest sideways shift (px) tried to line a picture's weave up with the one above it (--seam-cut)."""


def seam_path(err: np.ndarray, keep_a: np.ndarray, keep_b: np.ndarray) -> np.ndarray:
    """Per column, the overlap row where the lower picture takes over: the path of least squared difference
    that moves at most one row per column (image quilting's minimum-error boundary cut). ``keep_a[x]``: the
    upper picture's defect pixels reach down to that overlap row (the cut must lie below); ``keep_b[x]``: the
    lower picture's defect pixels start at that row (the cut must not lie below it)."""
    oy, w = err.shape
    rows = np.arange(oy)[:, None]
    cost = np.where((rows <= keep_a[None, :]) | (rows > keep_b[None, :]), 1e12, err.astype(np.float64))
    acc = cost.copy()
    back = np.zeros((oy, w), np.int64)
    idx = np.arange(oy)
    for x in range(1, w):
        prev = acc[:, x - 1]
        cand = np.stack([np.r_[np.inf, prev[:-1]], prev, np.r_[prev[1:], np.inf]])
        i = cand.argmin(0)
        acc[:, x] += cand[i, idx]
        back[:, x] = idx + i - 1
    k = np.empty(w, np.int64)
    k[-1] = int(acc[:, -1].argmin())
    for x in range(w - 1, 0, -1):
        k[x - 1] = back[k[x], x]
    return k



class RollRenderer:
    def __init__(self, source, plan: list[list[Cell]], seam_cut: bool = False):
        self.src = source
        self.plan = plan
        self.o = source.overlap if source.cols > 1 else 0
        self.stride_x = source.cell_w - self.o
        self.stride_y = source.cell_h - (source.overlap if len(plan) > 1 and source.name != "synthetic" else 0)
        self.width = (source.cols - 1) * self.stride_x + source.cell_w
        self.length = (len(plan) - 1) * self.stride_y + source.cell_h
        oy = source.cell_h - self.stride_y
        self.weight = np.outer(ramp(source.cell_h, oy), ramp(source.cell_w, self.o)).astype(np.float32)
        self.row_cache: dict[tuple[int, int], np.ndarray] = {}
        # --seam-cut (one picture across, overlapping rows): instead of cross-fading two weaves that do not line
        # up (which leaves a smooth grey band a detector reads as a broken pick), shift each picture sideways
        # to continue the weave above it and switch pictures along the least visible path.
        self.shift = [0] * len(plan)
        self.cut: dict[int, np.ndarray] = {}
        if seam_cut and source.cols == 1 and oy > 0 and len(plan) > 1:
            self._plan_seams(oy)

    def _row_image(self, r: int) -> np.ndarray:
        img = self.src.cell_image(r, 0, self.plan[r][0])
        return np.roll(img, self.shift[r], axis=1) if self.shift[r] else img

    def _plan_seams(self, oy: int) -> None:
        ch, w = self.src.cell_h, self.src.cell_w
        inner = slice(SEAM_SHIFT, w - SEAM_SHIFT)
        prev = self._row_image(0)
        for r in range(1, len(self.plan)):
            a = prev[ch - oy:].astype(np.float32)
            raw = self.src.cell_image(r, 0, self.plan[r][0])
            b_raw = raw[:oy].astype(np.float32)
            errs = {s: float(((a[:, inner] - np.roll(b_raw, s, axis=1)[:, inner]) ** 2).mean())
                    for s in range(-SEAM_SHIFT, SEAM_SHIFT + 1)}
            self.shift[r] = min(errs, key=errs.get)
            b = np.roll(b_raw, self.shift[r], axis=1)
            keep_a = np.full(w, -1, np.int64)
            keep_b = np.full(w, oy, np.int64)
            for box in self.plan[r - 1][0].boxes:  # the upper picture's defects in the overlap stay its own
                if box.y1 > ch - oy:
                    xs = slice(max(0, int(box.x0) - 2), min(w, int(np.ceil(box.x1)) + 2))
                    keep_a[xs] = np.maximum(keep_a[xs], min(oy - 1, int(np.ceil(box.y1)) - (ch - oy) + 1))
            for box in self.plan[r][0].boxes:  # and the lower picture's
                if box.y0 < oy:
                    x0, x1 = box.x0 + self.shift[r], box.x1 + self.shift[r]
                    xs = slice(max(0, int(x0) - 2), min(w, int(np.ceil(x1)) + 2))
                    keep_b[xs] = np.minimum(keep_b[xs], max(0, int(box.y0) - 1))
            self.cut[r] = seam_path(((a - b) ** 2).sum(-1), keep_a, keep_b)
            prev = np.roll(raw, self.shift[r], axis=1)

    def window(self, y: int, height: int) -> np.ndarray:
        if self.src.cols == 1 and self.stride_y == self.src.cell_h:
            return self._window_fast(y, height)
        acc = np.zeros((height, self.width, 3), np.float32)
        wsum = np.zeros((height, self.width), np.float32)
        ch, cw = self.src.cell_h, self.src.cell_w
        r_first = max(0, (y - ch) // self.stride_y + 1)
        r_last = min(len(self.plan) - 1, (y + height - 1) // self.stride_y)
        for key in [k for k in self.row_cache if k[0] < r_first]:
            del self.row_cache[key]
        for r in range(r_first, r_last + 1):
            ry = r * self.stride_y
            a0, a1 = max(y, ry), min(y + height, ry + ch)
            if a1 <= a0:
                continue
            for c, cell in enumerate(self.plan[r]):
                if (r, c) not in self.row_cache:
                    self.row_cache[(r, c)] = self._row_image(r) if self.cut else self.src.cell_image(r, c, cell)
                img = self.row_cache[(r, c)]
                cx = c * self.stride_x
                wpart = self._seam_weight(r)[a0 - ry : a1 - ry] if self.cut else self.weight[a0 - ry : a1 - ry]
                acc[a0 - y : a1 - y, cx : cx + cw] += img[a0 - ry : a1 - ry].astype(np.float32) * wpart[..., None]
                wsum[a0 - y : a1 - y, cx : cx + cw] += wpart
        return acc / np.maximum(wsum, 1e-6)[..., None]

    def _seam_weight(self, r: int) -> np.ndarray:
        """1 where picture r shows, 0 where its neighbour does (the two seams of its overlaps)."""
        ch, w = self.src.cell_h, self.src.cell_w
        oy = ch - self.stride_y
        wt = np.ones((ch, w), np.float32)
        rows = np.arange(oy)[:, None]
        if r in self.cut:  # seam with the picture above: picture r from its cut row down
            wt[:oy] = rows >= self.cut[r][None, :]
        if r + 1 in self.cut:  # seam with the picture below: picture r above that cut row
            wt[ch - oy:] = rows < self.cut[r + 1][None, :]
        return wt

    def _window_fast(self, y: int, height: int) -> np.ndarray:
        """Single column, no overlap (synthetic source): rows tile exactly, so just copy slices."""
        out = np.empty((height, self.width, 3), np.float32)
        ch = self.src.cell_h
        r_first = max(0, y // ch)
        for key in [k for k in self.row_cache if k[0] < r_first]:
            del self.row_cache[key]
        filled = 0
        r = r_first
        while filled < height and r < len(self.plan):
            if (r, 0) not in self.row_cache:
                self.row_cache[(r, 0)] = self.src.cell_image(r, 0, self.plan[r][0])
            img = self.row_cache[(r, 0)]
            a = max(0, y + filled - r * ch)
            take = min(ch - a, height - filled)
            out[filled:filled + take] = img[a:a + take]
            filled += take
            r += 1
        if filled < height:
            out[filled:] = out[filled - 1:filled] if filled else 0
        return out

    def boxes(self) -> list[tuple[Box, str]]:
        out = []
        for r, row in enumerate(self.plan):
            for c, cell in enumerate(row):
                ox, oy = c * self.stride_x + self.shift[r], r * self.stride_y
                for b in cell.boxes:
                    out.append((Box(b.cls, b.x0 + ox, b.y0 + oy, b.x1 + ox, b.y1 + oy), cell.key))
        return out


class VideoSink:
    def __init__(self, path: Path, w: int, h: int, fps: float, use_ffmpeg: bool):
        self.proc = None
        self.writer = None
        if use_ffmpeg and shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                   "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        else:
            self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            if not self.writer.isOpened():
                raise SystemExit("Could not open a video writer (install ffmpeg)")

    def write(self, frame: np.ndarray):
        if self.proc:
            self.proc.stdin.write(frame.tobytes())
        else:
            self.writer.write(frame)

    def close(self):
        if self.proc:
            self.proc.stdin.close()
            if self.proc.wait() != 0:
                raise SystemExit("ffmpeg failed while encoding the video")
        else:
            self.writer.release()


def four_point(length_in: float, is_hole: bool) -> int:
    if is_hole:
        return 2 if length_in <= 1.0 else 4
    if length_in <= 3:
        return 1
    if length_in <= 6:
        return 2
    if length_in <= 9:
        return 3
    return 4


# --------------------------------------------------------------------------
# Industry realism: operator motion, fabric surface details, board, hands
# --------------------------------------------------------------------------


@dataclass
class Stop:
    target_top: float
    pause_frames: int
    defect_id: int | None


def plan_motion(args, roll_px: int, view_h: int, px_per_cm: float, defects: list[dict], rng: random.Random):
    """Frame-by-frame fabric position. Clean mode: constant speed.
    Realistic mode: the operator stops when a defect is in view, pauses, then the machine ramps back up;
    there are also occasional random stops, and the running speed wobbles a little."""
    fps = args.fps
    dt = 1.0 / fps
    vmax = args.speed_m_min / 60.0 * 100 * px_per_cm
    end = roll_px - view_h
    if not args.realistic:
        n = int(end // (vmax * dt)) + 1
        tops = np.arange(n, dtype=np.float64) * vmax * dt
        return tops, np.full(n, args.speed_m_min), np.zeros(n, bool), []

    accel = args.accel_m_s2 * 100 * px_per_cm
    lo, hi = (float(v) for v in args.pause_s.split(","))
    stops: list[Stop] = []
    for d in sorted(defects, key=lambda d: d["y0_px"]):
        if rng.random() < args.stop_prob:
            centre = (d["y0_px"] + d["y1_px"]) / 2
            target = centre - view_h * rng.uniform(0.35, 0.65)
            stops.append(Stop(max(0.0, target), int(rng.uniform(lo, hi) * fps), d["defect_id"]))
    n_random = int(round(roll_px / px_per_cm / 1000 * args.random_stops_per_10m))
    for _ in range(n_random):
        stops.append(Stop(rng.uniform(0.1, 0.95) * end, int(rng.uniform(1.0, 3.0) * fps), None))
    stops.sort(key=lambda s: s.target_top)
    merged: list[Stop] = []
    for s in stops:
        if merged and s.target_top - merged[-1].target_top < view_h * 0.3:
            if s.defect_id is not None and merged[-1].defect_id is None:
                merged[-1] = s
            continue
        merged.append(s)
    stops = [s for s in merged if s.target_top < end]

    tops, speeds, paused = [], [], []
    events = []
    pos, v, i = 0.0, vmax, 0
    pause_left = 0
    current: Stop | None = None
    queue = list(stops)
    wobble_phase = rng.uniform(0, 2 * math.pi)
    while pos < end:
        tops.append(pos)
        speeds.append(v / (100 * px_per_cm) * 60)
        paused.append(pause_left > 0)
        if pause_left > 0:
            pause_left -= 1
            i += 1
            continue
        t = i * dt
        v_target = vmax * (1 + 0.04 * math.sin(2 * math.pi * t / 9.0 + wobble_phase))
        while queue and queue[0].target_top < pos - 0.5:
            queue.pop(0)
        if queue:
            dist = queue[0].target_top - pos
            if dist <= 0.5 or dist <= v * dt:
                pos = queue[0].target_top
                current = queue.pop(0)
                v = 0.0
                pause_left = current.pause_frames
                events.append({"frame": i + 1, "pause_frames": current.pause_frames,
                               "defect_id": current.defect_id, "top": pos})
                i += 1
                continue
            if dist <= v * v / (2 * accel) + v * dt:
                v = max(v - accel * dt, min(dist / dt, 0.05 * vmax))
            else:
                v = min(v_target, v + accel * dt)
        else:
            v = min(v_target, v + accel * dt)
        pos += v * dt
        i += 1
    tops.append(end)
    speeds.append(v / (100 * px_per_cm) * 60)
    paused.append(False)
    return np.array(tops), np.array(speeds), np.array(paused), events


class FabricDecor:
    """Surface details that exist on real rolls but are NOT defects: selvage band with stenter pin holes,
    wavy fabric edges, handling wrinkles, loose threads lying on the fabric, and the stickers an inspector
    puts on the selvage after stopping at a defect. All positions are in roll coordinates."""

    STICKER_COLOURS = [(60, 235, 250), (40, 150, 255), (190, 110, 255), (90, 230, 120)]

    def __init__(self, fab_w: int, roll_px: int, ppc: float, seed: int, realistic: bool):
        self.on = realistic
        self.fab_w, self.roll_px, self.ppc = fab_w, roll_px, ppc
        rng = np.random.default_rng(seed + 501)
        self.sw = max(4, int(round(0.9 * ppc)))
        cols = np.arange(self.sw, dtype=np.float32)
        self.selvage_profile = (0.84 + 0.05 * np.sin(cols * 1.9) + 0.03 * np.sin(cols * 0.7)).astype(np.float32)
        pitch = 1.25 * ppc
        n = int(roll_px / pitch) + 2
        ys = np.arange(n) * pitch + rng.normal(0, 0.06 * ppc, n)
        inset = 0.45 * ppc
        self.pins = np.concatenate([
            np.stack([ys, np.full(n, inset) + rng.normal(0, 0.03 * ppc, n)], 1),
            np.stack([ys + pitch * 0.3, np.full(n, fab_w - inset) + rng.normal(0, 0.03 * ppc, n)], 1),
        ])
        self.pins = self.pins[np.argsort(self.pins[:, 0])]
        self.pin_r = max(1, int(round(0.07 * ppc)))
        self.edge_phase = rng.uniform(0, 2 * np.pi, 4)
        self.edge_amp = 0.12 * ppc
        metres = roll_px / ppc / 100
        self.wrinkles = []
        for _ in range(int(rng.poisson(metres / 2.5))):
            self.wrinkles.append({
                "y": rng.uniform(0, roll_px), "x": rng.uniform(0.15, 0.85) * fab_w,
                "angle": rng.normal(0, 12), "length": rng.uniform(12, 70) * ppc,
                "width": rng.uniform(0.8, 2.5) * ppc, "amp": rng.uniform(0.05, 0.11),
            })
        self.threads = []
        for _ in range(int(rng.poisson(metres / 1.8))):
            n_pts = 18
            L = rng.uniform(1.0, 5.0) * ppc
            ang = rng.uniform(0, np.pi)
            x0, y0 = rng.uniform(0.05, 0.95) * fab_w, rng.uniform(0, roll_px)
            s = np.linspace(0, 1, n_pts)
            bend = rng.normal(0, 0.25 * L) * np.sin(np.pi * s) + rng.normal(0, 0.05 * L) * np.sin(3 * np.pi * s)
            px = x0 + np.cos(ang) * L * s - np.sin(ang) * bend
            py = y0 + np.sin(ang) * L * s + np.cos(ang) * bend
            colour = rng.choice([0, 1, 2])
            self.threads.append({"pts": np.stack([px, py], 1), "kind": int(colour),
                                 "tint": rng.uniform(0, 1, 3)})
        self.stickers: list[dict] = []

    def add_sticker(self, defect: dict, frame: int, rng: random.Random):
        cx = (defect["x0_px"] + defect["x1_px"]) / 2
        left = cx < self.fab_w / 2
        x = (rng.uniform(0.9, 1.6) * self.ppc) if left else self.fab_w - rng.uniform(0.9, 1.6) * self.ppc
        y = (defect["y0_px"] + defect["y1_px"]) / 2 + rng.uniform(-0.5, 0.5) * self.ppc
        self.stickers.append({"x": x, "y": y, "frame": frame, "angle": rng.uniform(-12, 12),
                              "colour": rng.choice(self.STICKER_COLOURS), "left": left,
                              "defect_id": defect["defect_id"]})

    def edges(self, y_top: int, h: int) -> tuple[np.ndarray, np.ndarray]:
        yy = (y_top + np.arange(h)) / self.ppc
        p = self.edge_phase
        el = self.edge_amp * (1.2 + np.sin(yy / 23.0 + p[0]) + 0.5 * np.sin(yy / 5.3 + p[1]))
        er = self.edge_amp * (1.2 + np.sin(yy / 19.0 + p[2]) + 0.5 * np.sin(yy / 6.1 + p[3]))
        return el, er

    def nuisance_list(self) -> list[dict]:
        out = []
        for w in self.wrinkles:
            out.append({"type": "wrinkle", "y": w["y"], "x": w["x"], "extent_px": w["length"] / 2})
        for t in self.threads:
            c = t["pts"].mean(0)
            out.append({"type": "loose_thread", "y": c[1], "x": c[0],
                        "extent_px": float(np.ptp(t["pts"], axis=0).max() / 2)})
        for s in self.stickers:
            out.append({"type": "sticker", "y": s["y"], "x": s["x"], "extent_px": 1.5 * self.ppc,
                        "frame": s["frame"]})
        return out

    def apply(self, img: np.ndarray, y_top: int, frame: int):
        h, w = img.shape[:2]
        if not self.on:
            return img, None
        sw = self.sw
        img[:, :sw] *= self.selvage_profile[None, :, None]
        img[:, w - sw:] *= self.selvage_profile[::-1][None, :, None]
        for wr in self.wrinkles:
            self._wrinkle(img, wr, y_top)
        lo = np.searchsorted(self.pins[:, 0], y_top - 5)
        hi = np.searchsorted(self.pins[:, 0], y_top + h + 5)
        for py, px in self.pins[lo:hi]:
            c = (int(round(px)), int(round(py - y_top)))
            cv2.circle(img, c, self.pin_r + 1, (55.0, 55.0, 55.0), -1)
            cv2.circle(img, c, self.pin_r, (225.0, 225.0, 225.0), -1)
        for t in self.threads:
            self._thread(img, t, y_top)
        for s in self.stickers:
            if s["frame"] <= frame:
                self._sticker(img, s, y_top)
        el, er = self.edges(y_top, h)
        band = int(np.ceil(max(el.max(), er.max()))) + 2
        xs = np.arange(band, dtype=np.float32)[None, :]
        left = np.clip(xs - el[:, None] + 0.5, 0, 1).astype(np.float32)
        right = np.clip((band - er[:, None]) - xs + 0.5, 0, 1).astype(np.float32)
        return img, (band, left, right)

    def _wrinkle(self, img, wr, y_top):
        h, w = img.shape[:2]
        if "map" not in wr:
            half = wr["length"] / 2 + 3 * wr["width"]
            y0, y1 = int(max(0, wr["y"] - half)), int(min(self.roll_px, wr["y"] + half))
            x0, x1 = int(max(0, wr["x"] - half)), int(min(w, wr["x"] + half))
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            t = math.radians(wr["angle"])
            dx, dy = xx - wr["x"], yy - wr["y"]
            along = dx * math.sin(t) + dy * math.cos(t)
            across = dx * math.cos(t) - dy * math.sin(t)
            fade = np.exp(-(along / (wr["length"] / 2)) ** 4)
            d = across / wr["width"]
            wr["map"] = (1.0 + wr["amp"] * 2.33 * d * np.exp(-d * d) * fade).astype(np.float32)
            wr["box"] = (y0, y1, x0, x1)
        y0, y1, x0, x1 = wr["box"]
        a, b = max(y0, y_top), min(y1, y_top + h)
        if b <= a or x1 <= x0:
            return
        img[a - y_top:b - y_top, x0:x1] *= wr["map"][a - y0:b - y0, :, None]

    def _thread(self, img, t, y_top):
        h, w = img.shape[:2]
        pts = t["pts"]
        if pts[:, 1].max() < y_top - 2 or pts[:, 1].min() > y_top + h + 2:
            return
        x0, y0 = np.floor(pts.min(0)).astype(int) - 3
        x1, y1 = np.ceil(pts.max(0)).astype(int) + 3
        mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        local = np.round(pts - [x0, y0]).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(mask, [local], False, 255, 1, cv2.LINE_AA)
        shadow = np.roll(np.roll(mask, 1, 0), 1, 1)
        ya, yb = max(y0, y_top), min(y1, y_top + h)
        xa, xb = max(x0, 0), min(x1, w)
        if yb <= ya or xb <= xa:
            return
        m = mask[ya - y0:yb - y0, xa - x0:xb - x0].astype(np.float32)[..., None] / 255.0
        s = shadow[ya - y0:yb - y0, xa - x0:xb - x0].astype(np.float32)[..., None] / 255.0
        region = img[ya - y_top:yb - y_top, xa:xb]
        region *= 1 - 0.25 * s
        if t["kind"] == 0:
            colour = region.mean(axis=(0, 1)) * 0.45
        elif t["kind"] == 1:
            colour = np.full(3, 215.0)
        else:
            colour = 60 + 170 * t["tint"]
        region[:] = region * (1 - 0.85 * m) + colour.reshape(1, 1, 3) * 0.85 * m

    def _sticker(self, img, s, y_top):
        h, w = img.shape[:2]
        ppc = self.ppc
        cy = s["y"] - y_top
        if cy < -3 * ppc or cy > h + 3 * ppc:
            return
        rect = ((s["x"], cy), (2.6 * ppc, 1.6 * ppc), s["angle"])
        box = cv2.boxPoints(rect).astype(np.int32)
        cv2.fillConvexPoly(img, box + 2, (40.0, 40.0, 40.0))
        cv2.fillConvexPoly(img, box, tuple(float(c) for c in s["colour"]))
        direction = 1 if s["left"] else -1
        tip = (int(s["x"] + direction * 0.9 * ppc), int(cy))
        tail = (int(s["x"] - direction * 0.7 * ppc), int(cy))
        cv2.arrowedLine(img, tail, tip, (30.0, 30.0, 30.0), max(1, int(0.12 * ppc)), tipLength=0.45)


def draw_hand(frame: np.ndarray, target: tuple[float, float], progress: float, ppc: float, seed: int):
    """Inspector's forearm reaching in from the bottom of the view towards the selvage (to place a sticker)."""
    h, w = frame.shape[:2]
    rng = np.random.default_rng(seed)
    base_x = target[0] + (w / 2 - target[0]) * rng.uniform(0.45, 0.7)
    base = np.array([base_x, h + 14 * ppc])
    tip_full = np.array(target, dtype=np.float64) + [0, 1.5 * ppc]
    tip = base + (tip_full - base) * progress
    arm_w = int(round(8.5 * ppc))
    mask = np.zeros((h, w), np.uint8)
    cv2.line(mask, tuple(base.astype(int)), tuple(tip.astype(int)), 255, arm_w, cv2.LINE_AA)
    direction = (tip - base) / (np.linalg.norm(tip - base) + 1e-6)
    palm = tip + direction * 2.0 * ppc
    ang = math.degrees(math.atan2(direction[1], direction[0]))
    cv2.ellipse(mask, tuple(palm.astype(int)), (int(4.2 * ppc), int(3.6 * ppc)), ang, 0, 360, 255, -1, cv2.LINE_AA)
    for k in range(4):
        off = (k - 1.5) * 1.6 * ppc
        perp = np.array([-direction[1], direction[0]])
        f0 = palm + direction * 3.0 * ppc + perp * off
        f1 = f0 + direction * rng.uniform(3.0, 4.2) * ppc
        cv2.line(mask, tuple(f0.astype(int)), tuple(f1.astype(int)), 255, int(1.5 * ppc), cv2.LINE_AA)
    m = mask.astype(np.float32) / 255.0
    shadow = cv2.GaussianBlur(np.roll(np.roll(m, int(1.2 * ppc), 0), int(1.0 * ppc), 1), (0, 0), 1.2 * ppc)
    frame *= (1 - 0.35 * shadow * (1 - m))[..., None]
    shade = cv2.GaussianBlur(m, (0, 0), 1.5 * ppc)
    skin = np.array([105, 140, 190], np.float32) * rng.uniform(0.85, 1.1)
    arm = skin.reshape(1, 1, 3) * (0.75 + 0.35 * shade[..., None])
    frame[:] = frame * (1 - m[..., None]) + arm * m[..., None]
    return frame


def make_board(h: int, w: int, seed: int) -> np.ndarray:
    """Back-lit inspection board seen beside the fabric edges."""
    rng = np.random.default_rng(seed + 77)
    yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    base = 236 - 10 * yy ** 2 - 6 * xx ** 2
    board = np.repeat(base[..., None], 3, axis=2) * np.array([0.98, 1.0, 1.0], np.float32)
    board += rng.normal(0, 1.2, size=(h, w, 1)).astype(np.float32)
    return board


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="Generate a simulated fabric-roll inspection video with ground truth.")
    ap.add_argument("--source", choices=["synthetic", "yolo", "aitex"], default="synthetic")
    ap.add_argument("--dataset", help="dataset root folder (for --source yolo / aitex)")
    ap.add_argument("--good-dir", help="folder of defect-free fabric images (overrides the dataset's own)")
    ap.add_argument("--out", default="sim_out", help="output folder")
    ap.add_argument("--mode", choices=["realistic", "clean"], default="realistic",
                    help="realistic: operator stops, drift, selvage, wrinkles, threads, stickers, hands; "
                         "clean: constant speed, fabric only")
    ap.add_argument("--roll-length-m", type=float, default=30.0)
    ap.add_argument("--fabric-width-cm", type=float, default=150.0)
    ap.add_argument("--board-margin-cm", type=float, default=None,
                    help="inspection board visible on each side of the fabric (realistic default 6, clean 0)")
    ap.add_argument("--frame-width", type=int, default=1920, help="output frame width in pixels")
    ap.add_argument("--view-length-cm", type=float, default=85.0, help="fabric length visible in one frame")
    ap.add_argument("--speed-m-min", type=float, default=20.0, help="running speed in metres per minute")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--defects-per-10m", type=float, default=4.0, help="expected number of defect tiles per 10 m")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--stop-prob", type=float, default=0.85, help="chance the operator stops at a defect")
    ap.add_argument("--pause-s", default="2.5,5", help="min,max seconds the operator stays stopped")
    ap.add_argument("--random-stops-per-10m", type=float, default=0.6, help="stops not caused by defects")
    ap.add_argument("--accel-m-s2", type=float, default=0.35, help="machine acceleration/braking")
    ap.add_argument("--drift-cm", type=float, default=1.5, help="max sideways wander of the fabric")
    ap.add_argument("--no-hands", action="store_true", help="do not draw the inspector's hand at stops")
    ap.add_argument("--no-stickers", action="store_true", help="do not place stickers at stops")
    ap.add_argument("--tiles-across", default="auto", help="dataset tiles placed side by side across the width")
    ap.add_argument("--overlap", type=int, default=12, help="feathered overlap between dataset tiles (px)")
    ap.add_argument("--seam-cut", action="store_true",
                    help="join stacked tiles along the least visible path, weave lined up, instead of cross-fading")
    ap.add_argument("--tint", help="colourise grayscale datasets, e.g. #3b5b8c")
    ap.add_argument("--no-flatten", action="store_true", help="keep each dataset tile's own lighting gradient")
    ap.add_argument("--trim-left", type=float, default=None,
                    help="fraction of each dataset image cut from the left (AITEX default 0.10 removes the "
                         "background beside the fabric edge; other sources default 0)")
    ap.add_argument("--trim-right", type=float, default=0.0, help="fraction of each dataset image cut from the right")
    ap.add_argument("--fabric-id", default="auto",
                    help="AITEX only: fabric type code (00-06) so the roll is one fabric; 'all' mixes them")
    ap.add_argument("--fabric-color", default="#3b5b8c", help="base colour for synthetic fabric")
    ap.add_argument("--weave-period-px", type=float, default=3.3)
    ap.add_argument("--noise", type=float, default=2.0, help="per-frame camera noise (std, 0-255 scale)")
    ap.add_argument("--vignette", type=float, default=0.12, help="lighting fall-off toward the edges (0-0.5)")
    ap.add_argument("--exposure-s", type=float, default=1 / 500, help="shutter time used for motion blur")
    ap.add_argument("--threshold", type=float, default=40.0, help="acceptance limit in points per 100 sq yd")
    ap.add_argument("--hole-classes", default="", help="comma-separated class names scored as holes")
    ap.add_argument("--no-label", action="store_true", help="omit the 'SIMULATED FEED' info bar")
    ap.add_argument("--debug-boxes", action="store_true", help="draw ground-truth boxes in the video")
    ap.add_argument("--no-ffmpeg", action="store_true", help="write mp4v with OpenCV instead of H.264 via ffmpeg")
    args = ap.parse_args()
    args.realistic = args.mode == "realistic"
    if args.board_margin_cm is None:
        args.board_margin_cm = 6.0 if args.realistic else 0.0
    if args.trim_left is None:
        args.trim_left = 0.10 if args.source == "aitex" else 0.0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    board_cm = args.fabric_width_cm + 2 * args.board_margin_cm
    req_fab_w = int(round(args.frame_width * args.fabric_width_cm / board_cm))
    req_fab_w -= req_fab_w % 2
    if args.source == "synthetic":
        source = SyntheticSource(args, req_fab_w, req_fab_w / args.fabric_width_cm)
    else:
        if not args.dataset:
            raise SystemExit("--dataset is required for --source yolo / aitex")
        source = load_yolo(args, req_fab_w) if args.source == "yolo" else load_aitex(args, req_fab_w)

    probe = RollRenderer(source, [[Cell("x")] * source.cols] * 2)
    fab_w = probe.width - probe.width % 2
    px_per_cm = fab_w / args.fabric_width_cm
    if args.source == "synthetic":
        source.px_per_cm = px_per_cm
    margin_px = int(round(args.board_margin_cm * px_per_cm))
    frame_w = fab_w + 2 * margin_px
    frame_w -= frame_w % 2

    roll_px = int(round(args.roll_length_m * 100 * px_per_cm))
    view_h = int(round(args.view_length_cm * px_per_cm))
    view_h -= view_h % 2
    n_rows = int(math.ceil(roll_px / probe.stride_y)) + 1
    cells_per_10m = 1000 * px_per_cm / probe.stride_y * source.cols
    p_defect = min(0.9, args.defects_per_10m / cells_per_10m)

    plan = source.plan(n_rows, rng, p_defect)
    renderer = RollRenderer(source, plan, seam_cut=args.seam_cut)
    roll_px = min(roll_px, renderer.length)
    if roll_px <= view_h + 2:
        raise SystemExit("Roll is shorter than one camera view; increase --roll-length-m")

    holes = {c.strip().lower() for c in args.hole_classes.split(",") if c.strip()}

    def is_hole(cls: str) -> bool:
        return cls.lower() in holes if holes else "hole" in cls.lower()

    decor = FabricDecor(fab_w, roll_px, px_per_cm, args.seed, args.realistic)
    sel = decor.sw if args.realistic else 0
    defects = []
    for b, key in renderer.boxes():
        if b.y1 > roll_px or b.x0 >= fab_w - sel or b.x1 <= sel:
            continue
        x0, x1 = max(b.x0, sel), min(b.x1, fab_w - sel)
        w_cm, h_cm = (x1 - x0) / px_per_cm, (b.y1 - b.y0) / px_per_cm
        length_in = max(w_cm, h_cm) / CM_PER_INCH
        defects.append({
            "defect_id": len(defects) + 1,
            "class": b.cls,
            "x0_px": round(x0, 1), "y0_px": round(b.y0, 1), "x1_px": round(x1, 1), "y1_px": round(b.y1, 1),
            "across_cm": round((x0 + x1) / 2 / px_per_cm, 2),
            "start_yd": round(b.y0 / px_per_cm / CM_PER_YARD, 3),
            "end_yd": round(b.y1 / px_per_cm / CM_PER_YARD, 3),
            "center_yd": round((b.y0 + b.y1) / 2 / px_per_cm / CM_PER_YARD, 3),
            "length_in": round(length_in, 2),
            "points": four_point(length_in, is_hole(b.cls)),
            "source": Path(key).name,
        })

    tops, speeds, paused, events = plan_motion(args, roll_px, view_h, px_per_cm, defects, rng)
    n_frames = len(tops)
    by_id = {d["defect_id"]: d for d in defects}
    hands = []
    for ev in events:
        d = by_id.get(ev["defect_id"]) if ev["defect_id"] else None
        if ev["defect_id"]:
            by_id[ev["defect_id"]]["operator_stop_frame"] = ev["frame"]
        if d is None or args.no_stickers:
            continue
        stick_frame = ev["frame"] + int(ev["pause_frames"] * 0.55)
        decor.add_sticker(d, stick_frame, rng)
        if not args.no_hands:
            hands.append({"start": ev["frame"] + int(ev["pause_frames"] * 0.15),
                          "end": ev["frame"] + int(ev["pause_frames"] * 0.9),
                          "sticker": decor.stickers[-1], "seed": rng.randrange(1 << 30)})

    drift_px = args.drift_cm * px_per_cm if args.realistic else 0.0
    ph = [rng.uniform(0, 2 * math.pi) for _ in range(2)]
    dx = drift_px * (0.6 * np.sin(2 * np.pi * tops / (520 * px_per_cm) + ph[0])
                     + 0.4 * np.sin(2 * np.pi * tops / (135 * px_per_cm) + ph[1]))
    fabric_x0 = np.round(margin_px + dx).astype(int)

    for d in defects:
        full = np.where((tops <= d["y0_px"]) & (tops + view_h >= d["y1_px"]))[0]
        d["first_full_frame"] = int(full[0]) if len(full) else ""
        d["last_full_frame"] = int(full[-1]) if len(full) else ""
        d.setdefault("operator_stop_frame", "")

    roll_yd = roll_px / px_per_cm / CM_PER_YARD
    width_in = args.fabric_width_cm / CM_PER_INCH
    per_yard: dict[int, int] = {}
    for d in defects:
        k = int(d["center_yd"])
        per_yard[k] = per_yard.get(k, 0) + d["points"]
    total_points = sum(min(4, v) for v in per_yard.values())
    per_100 = total_points * 3600 / (roll_yd * width_in)

    label_h = 0 if args.no_label else 36
    out_h = view_h + label_h
    yy = np.linspace(-1, 1, view_h).reshape(-1, 1)
    xx = np.linspace(-1, 1, frame_w).reshape(1, -1)
    light = (1.0 - args.vignette * (0.6 * xx ** 2 + 0.4 * yy ** 2) - (0.04 * yy if args.realistic else 0))
    light = light.astype(np.float32)[..., None]
    board = make_board(view_h, frame_w, args.seed) if margin_px > 0 else None
    noise_rng = np.random.default_rng(args.seed + 99)
    noise_bank = [noise_rng.normal(0, args.noise, size=(view_h, frame_w, 3)).astype(np.float32)
                  for _ in range(6)] if args.noise > 0 else []
    exp_phase = rng.uniform(0, 2 * math.pi)

    sink = VideoSink(out / "roll_video.mp4", frame_w, out_h, args.fps, not args.no_ffmpeg)
    frames_csv = open(out / "frames.csv", "w", newline="")
    fw = csv.writer(frames_csv)
    fw.writerow(["frame", "time_s", "roll_y_top_px", "top_yd", "bottom_yd", "speed_m_min", "state",
                 "fabric_x0_px", "hand_visible"])
    stops_n = sum(1 for e in events)
    print(f"Rendering {n_frames} frames ({n_frames / args.fps:.1f} s) at {frame_w}x{out_h}, "
          f"{len(defects)} defects, {stops_n} operator stops, roll {roll_yd:.1f} yd, mode {args.mode}")

    step = max(1, n_frames // 10)
    cache_key, cached = None, None
    for i in range(n_frames):
        y = int(round(tops[i]))
        x0 = int(fabric_x0[i])
        visible_stickers = sum(1 for s in decor.stickers if s["frame"] <= i)
        key = (y, x0, visible_stickers)
        if key == cache_key:
            frame = cached.copy()
        else:
            fab = np.ascontiguousarray(renderer.window(y, view_h)[:, :fab_w])
            fab, edge = decor.apply(fab, y, i)
            if board is not None:
                frame = board.copy()
                frame[:, x0:x0 + fab_w] = fab
                if edge is not None:
                    band, left, right = edge
                    seg = frame[:, x0:x0 + band]
                    seg[:] = board[:, x0:x0 + band] * (1 - left[..., None]) + fab[:, :band] * left[..., None]
                    r0 = x0 + fab_w - band
                    seg = frame[:, r0:r0 + band]
                    seg[:] = board[:, r0:r0 + band] * (1 - right[..., None]) + fab[:, fab_w - band:] * right[..., None]
            else:
                frame = fab
            cache_key, cached = key, frame.copy()
        hand_on = False
        for hd in hands:
            if hd["start"] <= i <= hd["end"]:
                span = hd["end"] - hd["start"]
                k = (i - hd["start"]) / max(1, span)
                progress = min(1.0, k / 0.3) if k < 0.7 else max(0.0, (1 - k) / 0.3)
                s = hd["sticker"]
                target = (s["x"] + fabric_x0[i], s["y"] - y)
                frame = draw_hand(frame, target, 0.25 + 0.75 * progress, px_per_cm, hd["seed"])
                hand_on = True
        blur_px = speeds[i] / 60 * 100 * px_per_cm * args.exposure_s
        if blur_px > 1.0:
            frame = cv2.blur(frame, (1, int(round(blur_px))))
        gain = 1.0 + noise_rng.normal(0, 0.006)
        if args.realistic:
            gain *= 1.0 + 0.025 * math.sin(2 * math.pi * i / args.fps / 37.0 + exp_phase)
        frame *= light
        frame *= gain
        if noise_bank:
            frame += noise_bank[int(noise_rng.integers(len(noise_bank)))]
        np.clip(frame, 0, 255, out=frame)
        frame = frame.astype(np.uint8)
        if args.debug_boxes:
            for d in defects:
                if d["y1_px"] >= y and d["y0_px"] <= y + view_h:
                    p0 = (int(d["x0_px"] + fabric_x0[i]), int(d["y0_px"] - y))
                    p1 = (int(d["x1_px"] + fabric_x0[i]), int(d["y1_px"] - y))
                    cv2.rectangle(frame, p0, p1, (0, 0, 255), 2)
                    cv2.putText(frame, f'{d["class"]} {d["center_yd"]:.2f}yd', (p0[0], max(14, p0[1] - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        top_yd = y / px_per_cm / CM_PER_YARD
        bottom_yd = (y + view_h) / px_per_cm / CM_PER_YARD
        state = "stopped" if paused[i] else "running"
        if label_h:
            bar = np.full((label_h, frame_w, 3), 18, np.uint8)
            text = (f"SIMULATED FEED | {source.name} | {top_yd:6.2f}-{bottom_yd:6.2f} yd | "
                    f"{speeds[i]:4.1f} m/min {state.upper():8s} | frame {i}")
            cv2.putText(bar, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (235, 235, 235), 1, cv2.LINE_AA)
            frame = np.vstack([frame, bar])
        sink.write(frame)
        fw.writerow([i, round(i / args.fps, 3), y, round(top_yd, 4), round(bottom_yd, 4), round(float(speeds[i]), 2),
                     state, int(fabric_x0[i]), int(hand_on)])
        if i % step == 0:
            print(f"  {100 * i / n_frames:5.1f}%")
    sink.close()
    frames_csv.close()

    with open(out / "ground_truth.csv", "w", newline="") as f:
        cols = ["defect_id", "class", "center_yd", "start_yd", "end_yd", "across_cm", "length_in", "points",
                "first_full_frame", "last_full_frame", "operator_stop_frame",
                "x0_px", "y0_px", "x1_px", "y1_px", "source"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(defects)

    nuisances = decor.nuisance_list() if args.realistic else []
    with open(out / "nuisance.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["type", "center_yd", "across_cm", "extent_cm", "appears_frame"])
        for n in nuisances:
            w.writerow([n["type"], round(n["y"] / px_per_cm / CM_PER_YARD, 3), round(n["x"] / px_per_cm, 2),
                        round(n["extent_px"] / px_per_cm, 2), n.get("frame", "")])

    meta = {
        "simulated": True,
        "mode": args.mode,
        "source": source.name,
        "seed": args.seed,
        "video": "roll_video.mp4",
        "frames_csv": "frames.csv",
        "nuisance_csv": "nuisance.csv",
        "fps": args.fps,
        "frames": n_frames,
        "duration_s": round(n_frames / args.fps, 2),
        "frame_size": [frame_w, out_h],
        "view_region": {"x": 0, "y": 0, "w": frame_w, "h": view_h},
        "fabric_width_px": fab_w,
        "selvage_band_px": sel,
        "label_bar_height": label_h,
        "fabric_motion": "fabric enters at the bottom of the frame and exits at the top",
        "px_per_cm": px_per_cm,
        "px_per_frame_at_full_speed": args.speed_m_min / 60 * 100 * px_per_cm / args.fps,
        "speed_m_min": args.speed_m_min,
        "operator_stops": stops_n,
        "view_length_cm": view_h / px_per_cm,
        "board_margin_cm": args.board_margin_cm,
        "roll_length_px": roll_px,
        "roll_length_yd": round(roll_yd, 3),
        "fabric_width_cm": args.fabric_width_cm,
        "fabric_width_in": round(width_in, 2),
        "tiles_across": source.cols,
        "defect_count": len(defects),
        "nuisance_count": len(nuisances),
        "classes": sorted({d["class"] for d in defects}),
        "hole_classes": sorted(holes) if holes else "any class name containing 'hole'",
        "expected_score": {
            "total_points": total_points,
            "points_per_100_sq_yd": round(per_100, 2),
            "threshold": args.threshold,
            "verdict": "PASS" if per_100 <= args.threshold else "FAIL",
            "rule": "4-point: <=3in 1, 3-6in 2, 6-9in 3, >9in 4; holes <=1in 2, >1in 4; max 4 points per linear yard",
        },
        "position_formula": "use frames.csv: roll_y_px = roll_y_top_px[frame] + y_in_view; "
                            "x_on_fabric_px = x_in_view - fabric_x0_px[frame]; yard = roll_y_px / px_per_cm / 91.44; "
                            "across_cm = x_on_fabric_px / px_per_cm",
    }
    (out / "roll_meta.json").write_text(json.dumps(meta, indent=2))

    make_preview(renderer, decor, defects, nuisances, roll_px, fab_w, view_h, px_per_cm, out / "roll_preview.png")
    s = meta["expected_score"]
    print(f"Done. {len(defects)} defects, {len(nuisances)} non-defect distractions, {s['total_points']} points, "
          f"{s['points_per_100_sq_yd']} pts/100 sq yd -> {s['verdict']}")
    print(f"Files written to {out.resolve()}")


def make_preview(renderer: RollRenderer, decor: FabricDecor, defects: list[dict], nuisances: list[dict], roll_px: int,
                 fab_w: int, view_h: int, px_per_cm: float, path: Path, strip_h: int = 260):
    scale = strip_h / fab_w
    pieces = []
    y = 0
    while y < roll_px:
        h = min(view_h, roll_px - y)
        win = renderer.window(y, h)[:, :fab_w]
        win, _ = decor.apply(np.ascontiguousarray(win), y, 10 ** 9)
        win = np.clip(win, 0, 255).astype(np.uint8)
        pieces.append(cv2.resize(win, (strip_h, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA))
        y += h
    strip = np.vstack(pieces)
    for n in nuisances:
        r = max(3, int(n["extent_px"] * scale))
        c = (int(n["x"] * scale), int(n["y"] * scale))
        cv2.rectangle(strip, (c[0] - r, c[1] - r), (c[0] + r, c[1] + r), (0, 200, 255), 1)
    for d in defects:
        p0 = (int(d["x0_px"] * scale), int(d["y0_px"] * scale))
        p1 = (max(p0[0] + 3, int(d["x1_px"] * scale)), max(p0[1] + 3, int(d["y1_px"] * scale)))
        cv2.rectangle(strip, p0, p1, (0, 0, 255), 2)
    strip = cv2.flip(cv2.rotate(strip, cv2.ROTATE_90_COUNTERCLOCKWISE), 0)
    pad = np.full((50, strip.shape[1], 3), 255, np.uint8)
    px_per_yd = px_per_cm * CM_PER_YARD * scale
    for yd in range(0, int(strip.shape[1] / px_per_yd) + 1, 5):
        x = int(yd * px_per_yd)
        cv2.line(pad, (x, 0), (x, 8), (0, 0, 0), 1)
        cv2.putText(pad, f"{yd}yd", (x + 2, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(pad, "red = defect (ground truth)    orange = not a defect (loose thread, wrinkle, sticker)",
                (4, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), np.vstack([strip, pad]))


if __name__ == "__main__":
    sys.exit(main())
