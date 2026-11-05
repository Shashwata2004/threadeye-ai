"""Camera training examples through the simulator's actual raster and camera pipeline.

Every rendered pixel donor and every lighting-reference/background original is recorded. Full AITEX
train originals/masks come from the existing private round-two bundle, never the regression donors.
Other existing sources use their labelled native tiles through the same DatasetSource/RollRenderer.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from fabricdata.classes import SOURCE_CLASS_MAP

sys.path.insert(0, str(Path(__file__).parents[1] / "tools/simulator"))
from make_roll_video import (
    Box,
    Cell,
    DatasetSource,
    FabricDecor,
    RollRenderer,
    apply_camera_effects,
    load_aitex,
    make_board,
    render_fabric_view,
)


def thin_vertical(annotations, category):
    return any(
        a["category_id"] == category
        and a["bbox"][2] <= 16
        and a["bbox"][3] >= max(64, 4 * a["bbox"][2])
        for a in annotations
    )


class UnrenderableTarget(ValueError):
    """An annotation is outside the simulator's trimmed/scored fabric region."""


def clip_annotation(cls, box, left, top, width, height, category):
    x0, y0, x1, y1 = box
    x0, x1 = max(0, x0 - left), min(width, x1 - left)
    y0, y1 = max(0, y0 - top), min(height, y1 - top)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return {
        "category_id": category[cls],
        "bbox": [float(x0), float(y0), float(x1 - x0), float(y1 - y0)],
        "area": float((x1 - x0) * (y1 - y0)),
    }


class RenderedViews:
    def __init__(self, raw, out, pools, categories, full_aitex, seed):
        self.raw, self.out, self.pools = Path(raw), Path(out), pools
        self.names = categories
        self.category = {name: cid for cid, name in categories.items()}
        self.seed = seed
        self.sources = {}
        self.path_info = {}
        self.crops = {}
        self.appearance_cache = {}
        self.background_cache = {}
        self.aitex = {}
        self.full = Path(full_aitex)
        records = json.loads((self.full / "sources.json").read_text())
        by_original = {
            i["manifest"]["original"]: i["manifest"]
            for pool in pools.values()
            for i in pool["replay"]
        }
        self.allowed = {
            s: {i["manifest"]["group"] for i in p["replay"]} for s, p in pools.items()
        }
        assert not self.allowed["train"] & self.allowed["val"]
        for split in ("train", "val"):
            tree = self.out / "full_aitex" / split
            for directory in ("Defect_images", "NODefect_images", "Mask_images"):
                (tree / directory).mkdir(parents=True, exist_ok=True)
            for record in records:
                info = by_original.get(record["original"])
                if info is None or info["group"] not in self.allowed[split]:
                    continue
                source = self.full / record["path"]
                if hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]:
                    raise ValueError(
                        "full AITEX original differs from frozen private bundle"
                    )
                folder = (
                    "Defect_images" if record["kind"] == "defect" else "NODefect_images"
                )
                path = tree / folder / source.name
                if not path.exists():
                    path.symlink_to(source.resolve())
                elif path.resolve() != source.resolve():
                    raise ValueError("unexpected preexisting AITEX source link")
                self.path_info[str(path)] = info
                self.aitex[(split, record["original"])] = path
                for mask in record["masks"]:
                    source_mask = self.full / mask["path"]
                    if (
                        hashlib.sha256(source_mask.read_bytes()).hexdigest()
                        != mask["sha256"]
                    ):
                        raise ValueError("AITEX mask differs")
                    target = tree / "Mask_images" / source_mask.name
                    if not target.exists():
                        target.symlink_to(source_mask.resolve())
                    elif target.resolve() != source_mask.resolve():
                        raise ValueError("unexpected preexisting AITEX mask link")

    def args(self, split, **changes):
        return SimpleNamespace(
            dataset=str(self.out / "full_aitex" / split),
            good_dir=None,
            trim_left=0.1,
            trim_right=0.0,
            overlap=0,
            tiles_across="1",
            tint=None,
            no_flatten=False,
            fabric_id="all",
            **changes,
        )

    def crop(self, item, chosen):
        key = (item["image"]["file_name"], chosen)
        if key in self.crops:
            return self.crops[key]
        image = cv2.imread(str(self.raw / key[0]))
        if image is None:
            raise ValueError("source tile missing")
        aa = item["annotations"]
        focal = next(
            (a for a in aa if self.names[a["category_id"]] == chosen),
            next(iter(aa), None),
        )
        top = int(
            np.clip(
                round(focal["bbox"][1] + focal["bbox"][3] / 2 - 124) if focal else 0,
                0,
                max(0, image.shape[0] - 248),
            )
        )
        image = image[top : top + 248, :640]
        h, w = image.shape[:2]
        image = cv2.copyMakeBorder(
            image, 0, 248 - h, 0, 640 - w, cv2.BORDER_REFLECT_101
        )
        path = (
            self.out
            / "cropped_sources"
            / (hashlib.sha256(repr(key).encode()).hexdigest()[:20] + ".png")
        )
        path.parent.mkdir(exist_ok=True)
        cv2.imwrite(str(path), image)
        boxes = []
        for a in aa:
            x, y, bw, bh = a["bbox"]
            ann = clip_annotation(
                self.names[a["category_id"]],
                (x, y, x + bw, y + bh),
                0,
                top,
                640,
                248,
                self.category,
            )
            if ann:
                x, y, bw, bh = ann["bbox"]
                boxes.append(
                    Box(
                        self.names[a["category_id"]],
                        x / 640,
                        y / 248,
                        (x + bw) / 640,
                        (y + bh) / 248,
                    )
                )
        self.path_info[str(path)] = item["manifest"]
        self.crops[key] = (path, boxes)
        return path, boxes

    def source(self, split, item, chosen):
        domain = item["manifest"]["source"]
        original = item["manifest"]["original"]
        if domain == "aitex":
            path = self.aitex[(split, original)]
            family = path.stem.split("_")[2][:2]
            key = (split, domain, family)
            if key not in self.sources:
                args = self.args(split)
                good = list(
                    (self.out / "full_aitex" / split / "NODefect_images").glob("*")
                )
                defective = list(
                    (self.out / "full_aitex" / split / "Defect_images").glob("*")
                )
                args.fabric_id = (
                    family
                    if any(p.stem.split("_")[2][:2] == family for p in good)
                    and any(p.stem.split("_")[2][:2] == family for p in defective)
                    else "all"
                )
                src = load_aitex(args, 3556)
                matching = [p for p in good if p.stem.split("_")[2][:2] == family]
                if matching:
                    src.good = matching
                    src.target = src._target_stats()
                src.overlap = 0
                if src.cell_h % 2:
                    src.cell_h += 1
                    src.target = src._target_stats()
                self.sources[key] = src
            src = self.sources[key]
            boxes = next((boxes for p, boxes in src.defects if p == path), [])
            canonical = SOURCE_CLASS_MAP["aitex"].get(path.stem.split("_")[1])
            boxes = (
                [Box(canonical, b.x0, b.y0, b.x1, b.y1) for b in boxes]
                if canonical
                else []
            )
            return src, path, boxes
        path, boxes = self.crop(item, chosen)
        descriptor = self.appearance(path)
        family = item["manifest"]["group"].split(":")[1] if domain == "wfdd" else ""
        key = (
            split,
            domain,
            family,
            *np.floor(descriptor[:3] / 24).astype(int).tolist(),
            int(descriptor[3] // 12),
        )
        if key not in self.sources:
            good_items = [
                i
                for i in self.pools[split]["replay"]
                if not i["annotations"] and i["manifest"]["source"] == domain
            ] or self.pools[split]["clean"]
            if domain == "wfdd":
                same_family = [
                    i
                    for i in good_items
                    if i["manifest"]["source"] == domain
                    and i["manifest"]["group"].split(":")[1] == family
                ]
                if same_family:
                    good_items = same_family
            # One coherent weave per scene. Mixing unrelated clean fabrics made artificial colour
            # quilts and extreme flat-field corrections in the first preview; select within the
            # fabric family, then choose the nearest clean appearance using this split only.
            pool_key = (split, domain, family)
            if pool_key not in self.background_cache:
                candidate_paths = [self.crop(i, None)[0] for i in good_items]
                self.background_cache[pool_key] = (
                    candidate_paths,
                    np.stack([self.appearance(p) for p in candidate_paths]),
                )
            candidate_paths, descriptors = self.background_cache[pool_key]
            distances = np.linalg.norm(
                (descriptors - descriptor) * np.array([1, 0.7, 0.7, 0.7, 0.7, 0.7]),
                axis=1,
            )
            nearest = candidate_paths[int(distances.argmin())]
            good_paths = [nearest]
            # DatasetSource requires a labelled donor at construction, even for a clean-only draw.
            donor = next(
                i
                for values in self.pools[split]["target"].values()
                for i in values
                if i["manifest"]["source"] == domain
            )
            donor_path, donor_boxes = self.crop(donor, None)
            args = SimpleNamespace(
                trim_left=0.0,
                trim_right=0.0,
                overlap=0,
                tiles_across="6",
                tint=None,
                no_flatten=False,
            )
            self.sources[key] = DatasetSource(
                args, 3556, good_paths, [(donor_path, donor_boxes)], (640, 248), domain
            )
        return self.sources[key], path, boxes

    def appearance(self, path):
        key = str(path)
        if key not in self.appearance_cache:
            image = cv2.imread(key)
            if image is None:
                raise ValueError("appearance reference missing")
            lab = cv2.cvtColor(cv2.resize(image, (32, 32)), cv2.COLOR_BGR2LAB).astype(
                np.float32
            )
            self.appearance_cache[key] = np.r_[
                lab.mean(axis=(0, 1)), lab.std(axis=(0, 1))
            ]
        return self.appearance_cache[key]

    def render(self, split, item, chosen, index, kind):
        src, path, boxes = self.source(split, item, chosen)
        rng = random.Random(self.seed + index + (100000 if split == "val" else 0))
        noise_rng = np.random.default_rng(
            self.seed + index + 99 + (100000 if split == "val" else 0)
        )
        rows = [
            [Cell(str(rng.choice(src.good))) for _ in range(src.cols)] for _ in range(3)
        ]
        column = rng.randrange(src.cols)
        if kind == "target":
            rows[1][column] = Cell(
                str(path),
                [
                    Box(
                        b.cls,
                        b.x0 * src.cell_w,
                        b.y0 * src.cell_h,
                        b.x1 * src.cell_w,
                        b.y1 * src.cell_h,
                    )
                    for b in boxes
                ],
            )
        else:
            rows[1][column] = Cell(str(path))
        renderer = RollRenderer(src, rows, seam_cut=True)
        fab_w = renderer.width - renderer.width % 2
        ppc = fab_w / 150
        phase_index = (index // 10) % 5
        aligned = phase_index < 3
        view_h = src.cell_h if aligned else (248, 318)[(index // 10) % 2]
        view_h -= view_h % 2
        frame_boxes = [
            (b, key) for b, key in renderer.boxes() if b.cls in self.category
        ]
        focal = next((b for b, _ in frame_boxes if b.cls == chosen), None)
        if kind == "target" and focal is None:
            raise UnrenderableTarget("target outside simulator trim/scored region")
        centre_y = (focal.y0 + focal.y1) / 2 if focal else src.cell_h * 1.5
        phase = (0.0, 0.0, 0.0, -0.45, 0.45)[phase_index]
        top = int(
            np.clip(
                src.cell_h
                if aligned
                else round(centre_y - view_h / 2 + phase * view_h),
                0,
                max(0, renderer.length - view_h),
            )
        )
        margin = round(6 * ppc)
        frame_w = fab_w + 2 * margin
        x0 = round(
            margin
            + 1.5
            * ppc
            * (0.6 * math.sin(top / (520 * ppc)) + 0.4 * math.sin(top / (135 * ppc)))
        )
        if focal:
            crop_left = int(
                np.clip(
                    round(
                        (focal.x0 + focal.x1) / 2 + x0 - 320 + rng.uniform(-100, 100)
                    ),
                    0,
                    frame_w - 640,
                )
            )
        else:
            crop_left = rng.choice([0, frame_w - 640, rng.randrange(frame_w - 640 + 1)])
        decor = FabricDecor(fab_w, renderer.length, ppc, self.seed + index, True)
        if kind == "clean":
            cx = float(
                np.clip(crop_left + 320 - x0, decor.sw + 80, fab_w - decor.sw - 80)
            )
            cy = top + view_h / 2
            if index % 3 == 0:
                s = np.linspace(0, 1, 18)
                decor.threads.append(
                    {
                        "pts": np.stack(
                            [cx + (s - 0.5) * 80, cy + np.sin(s * np.pi) * 25], 1
                        ),
                        "kind": index % 3,
                        "tint": noise_rng.uniform(0, 1, 3),
                    }
                )
            elif index % 3 == 1:
                decor.wrinkles.append(
                    {
                        "x": cx,
                        "y": cy,
                        "angle": rng.uniform(-12, 12),
                        "length": 10 * ppc,
                        "width": ppc,
                        "amp": 0.08,
                    }
                )
            else:
                decor.stickers.append(
                    {
                        "x": cx,
                        "y": cy,
                        "frame": 0,
                        "angle": rng.uniform(-12, 12),
                        "colour": rng.choice(decor.STICKER_COLOURS),
                        "left": cx < fab_w / 2,
                        "defect_id": None,
                    }
                )
        board = make_board(view_h, frame_w, self.seed + index)
        frame = render_fabric_view(
            renderer, decor, board, top, x0, index, fab_w, view_h
        )
        yy = np.linspace(-1, 1, view_h).reshape(-1, 1)
        xx = np.linspace(-1, 1, frame_w).reshape(1, -1)
        light = (1 - 0.12 * (0.6 * xx**2 + 0.4 * yy**2) - 0.04 * yy).astype(np.float32)[
            ..., None
        ]
        gain = 1 + noise_rng.normal(0, 0.006)
        gain *= 1 + 0.025 * math.sin(2 * math.pi * index / 30 / 37)
        noise = noise_rng.normal(0, 1.5, frame.shape).astype(np.float32)
        frame = apply_camera_effects(
            frame, light, gain, 20 / 60 * 100 * ppc / 500, noise
        )
        annotations = []
        for b, _key in frame_boxes:
            if b.x1 <= decor.sw or b.x0 >= fab_w - decor.sw:
                continue
            ann = clip_annotation(
                b.cls,
                (
                    max(b.x0, decor.sw) + x0,
                    b.y0,
                    min(b.x1, fab_w - decor.sw) + x0,
                    b.y1,
                ),
                crop_left,
                top,
                640,
                view_h,
                self.category,
            )
            if ann:
                annotations.append(ann)
        for thread in decor.threads:
            pts = thread["pts"]
            ann = clip_annotation(
                "loose_thread",
                (
                    pts[:, 0].min() - 3 + x0,
                    pts[:, 1].min() - 3,
                    pts[:, 0].max() + 3 + x0,
                    pts[:, 1].max() + 3,
                ),
                crop_left,
                top,
                640,
                view_h,
                self.category,
            )
            if ann:
                annotations.append(ann)
        for wrinkle in decor.wrinkles:
            if "map" not in wrinkle:
                continue
            ys, xs = np.nonzero(np.abs(wrinkle["map"] - 1) > 0.01)
            if len(xs):
                y, _y1, x, _x1 = wrinkle["box"]
                ann = clip_annotation(
                    "wrinkle",
                    (
                        x + xs.min() + x0,
                        y + ys.min(),
                        x + xs.max() + 1 + x0,
                        y + ys.max() + 1,
                    ),
                    crop_left,
                    top,
                    640,
                    view_h,
                    self.category,
                )
                if ann:
                    annotations.append(ann)
        for sticker in decor.stickers:
            points = cv2.boxPoints(
                ((sticker["x"], sticker["y"]), (2.6 * ppc, 1.6 * ppc), sticker["angle"])
            )
            ann = clip_annotation(
                "sticker",
                (
                    points[:, 0].min() + x0,
                    points[:, 1].min(),
                    points[:, 0].max() + 3 + x0,
                    points[:, 1].max() + 3,
                ),
                crop_left,
                top,
                640,
                view_h,
                self.category,
            )
            if ann:
                annotations.append(ann)
        if kind == "target" and not any(
            self.names[a["category_id"]] == chosen for a in annotations
        ):
            # Retry a centred camera view, retaining the renderer and data identities.
            if not aligned:
                return self.render(
                    split, item, chosen, index - (index // 10 % 5) * 10 + 20, kind
                )
            raise UnrenderableTarget("target fully outside rendered crop")
        infos = [self.path_info[cell.key] for row in rows for cell in row]
        infos += [
            self.path_info[str(p)]
            for p in src.good[:: max(1, len(src.good) // 20)][:20]
        ]
        all_groups = sorted({i["group"] for i in infos})
        if not set(all_groups) <= self.allowed[split]:
            raise ValueError("renderer donor/background/reference crossed source split")
        while len(src.cache) > 16:
            src.cache.popitem(last=False)
        while len(self.sources) > 24:
            removable = next((key for key in self.sources if key[1] != "aitex"), None)
            if removable is None:
                break
            self.sources.pop(removable)
        return (
            frame[:, crop_left : crop_left + 640].copy(),
            annotations,
            {
                "renderer": "DatasetSource+RollRenderer+FabricDecor+shared camera effects",
                "originals": sorted({i["original"] for i in infos}),
                "groups": all_groups,
                "background_originals": sorted(
                    {
                        self.path_info[c.key]["original"]
                        for row in rows
                        for c in row
                        if c.key != str(path)
                    }
                ),
                "reference_originals": sorted(
                    {
                        self.path_info[str(p)]["original"]
                        for p in src.good[:: max(1, len(src.good) // 20)][:20]
                    }
                ),
                "camera_top_px": top,
                "camera_alignment": "source-strip" if aligned else "partial-edge",
                "camera_crop_left_px": crop_left,
                "fabric_x0_px": x0,
                "frame_height": view_h,
                "columns": src.cols,
                "flat_field": src.flatten,
                "background_policy": "same fabric family when available; one nearest clean appearance per scene",
                "codec": "JPEG94 training frames; shared pre-encoding video raster",
            },
        )
