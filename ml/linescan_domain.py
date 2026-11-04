"""Train-only real AITEX masks on native line-scan views with simulator edge negatives."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

TARGETS = ("broken_yarn", "missing_yarn", "crease_mark", "slub")


def verify_sources(root: Path, expected_manifest: str) -> list[dict]:
    manifest = root / "frozen_manifest.csv"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != expected_manifest:
        raise ValueError("frozen manifest identity changed")
    splits: dict[str, set[str]] = defaultdict(set)
    for row in csv.DictReader(manifest.open()):
        splits[row["original"]].add(row["split"])
    records = json.loads((root / "sources.json").read_text())
    for record in records:
        if splits.get(record["original"]) != {"train"}:
            raise ValueError("non-train source refused: " + record["original"])
        for item in [record, *record.get("masks", [])]:
            path = root / item["path"]
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("source escapes bundle")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("source pixels changed")
    return records


def generate(train: dict, root: Path, out: Path, *, n: int, seed: int, expected_manifest: str) -> tuple[dict, dict]:
    from aitex_paste import paste
    from fabricdata import nuisance
    from fabricdata.classes import SOURCE_CLASS_MAP
    from fabricdata.sources import mask_boxes

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/simulator"))
    from make_roll_video import FabricDecor, make_board

    records = verify_sources(root, expected_manifest)
    clean = [r for r in records if r["kind"] == "clean"]
    if not clean:
        raise ValueError("no known-clean training backgrounds")
    pools: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record["kind"] != "defect":
            continue
        cls = SOURCE_CLASS_MAP["aitex"].get(Path(record["path"]).stem.split("_")[1])
        if cls not in TARGETS:
            continue
        image = np.asarray(Image.open(root / record["path"]).convert("L"), dtype=np.float32)
        mask = np.zeros(image.shape, dtype=np.uint8)
        for m in record["masks"]:
            mask |= (np.asarray(Image.open(root / m["path"]).convert("L")) > 0).astype(np.uint8)
        for x0, y0, x1, y1 in mask_boxes(mask):
            x0, y0 = max(0, x0 - 6), max(0, y0 - 6)
            x1, y1 = min(image.shape[1], x1 + 6), min(image.shape[0], y1 + 6)
            pools[cls].append({"pixels": image[y0:y1, x0:x1].copy(), "mask": mask[y0:y1, x0:x1].copy(), "source": record})
    if any(not pools[c] for c in TARGETS):
        raise ValueError("not enough train-only mask donors for all target classes")
    categories = {c["name"]: c["id"] for c in train["categories"]}
    rng = np.random.default_rng(seed)
    schedule = list(rng.permutation(["broken_yarn"] * 9 + ["missing_yarn"] * 3 + ["crease_mark"] * 5 + ["slub"] * 3))
    width, height, margin = 3556, 248, 142
    ppc = width / 150
    next_im = max(im["id"] for im in train["images"]) + 1
    next_ann = max((a["id"] for a in train["annotations"]), default=0) + 1
    merged = {**train, "images": list(train["images"]), "annotations": list(train["annotations"])}
    out.mkdir(parents=True, exist_ok=True)
    details, counts = [], Counter()

    @lru_cache(maxsize=4)
    def texture(path: str) -> np.ndarray:
        img = np.asarray(Image.open(root / path).convert("L"), dtype=np.float32)
        return cv2.resize(img[:, round(img.shape[1] * 0.1):], (width, height))

    for index in range(n):
        positive = index % 5 < 3
        cls = str(schedule[(index // 5 * 3 + index % 5) % len(schedule)])
        donor = pools[cls][int(rng.integers(len(pools[cls])))] if positive else None
        same = [r for r in clean if donor and Path(r["path"]).stem.split("_")[2] == Path(donor["source"]["path"]).stem.split("_")[2]]
        bases = same or clean
        base = bases[int(rng.integers(len(bases)))]
        fabric = texture(base["path"]).copy()
        labels = []
        if donor:
            patch, mask = donor["pixels"], donor["mask"]
            scale = min(float(rng.uniform(0.85, 1.1)), (height - 12) / patch.shape[0], (width - 200) / patch.shape[1])
            size = max(2, round(patch.shape[1] * scale)), max(2, round(patch.shape[0] * scale))
            patch = cv2.resize(patch, size)
            mask = cv2.resize(mask.astype(np.float32), size, interpolation=cv2.INTER_AREA) > 0
            if rng.random() < 0.5:
                patch, mask = patch[:, ::-1].copy(), mask[:, ::-1].copy()
            x, y = int(rng.integers(80, width - size[0] - 79)), int(rng.integers(0, height - size[1] + 1))
            box = paste(fabric, patch, mask, x, y)
            labels.append((cls, box))
        rgb = np.repeat(fabric[..., None], 3, axis=2)
        decor = FabricDecor(width, height, ppc, seed + index, True)
        decor.wrinkles, decor.threads, decor.stickers = [], [], []
        rgb, edge = decor.apply(rgb, 0, 0)
        board = make_board(height, width + 2 * margin, seed + index)
        frame = board.copy()
        frame[:, margin:margin + width] = rgb
        band, left, right = edge
        frame[:, margin:margin + band] = frame[:, margin:margin + band] * left[..., None] + board[:, margin:margin + band] * (1 - left[..., None])
        r0 = margin + width - band
        frame[:, r0:r0 + band] = frame[:, r0:r0 + band] * right[..., None] + board[:, r0:r0 + band] * (1 - right[..., None])
        if positive:
            cx = (labels[0][1][0] + labels[0][1][2]) / 2 + margin
            offset = int(np.clip(cx - 320 + rng.uniform(-100, 100), 0, frame.shape[1] - 640))
        else:
            offset = 0 if index % 2 else frame.shape[1] - 640
        tile = frame[:, offset:offset + 640].copy()
        boxes = []
        for label, (x0, y0, x1, y1) in labels:
            x0, x1 = max(0, x0 + margin - offset), min(640, x1 + margin - offset)
            if x1 > x0:
                boxes.append((label, (x0, y0, x1, y1)))
        if not positive and index % 5 == 4:
            drawn = [nuisance.loose_thread, nuisance.wrinkle, nuisance.sticker][index % 3](tile, rng)
            if drawn:
                boxes.append((drawn.cls, drawn.box))
        tile *= float(rng.uniform(0.9, 1.1))
        tile += rng.normal(0, rng.uniform(0, 2), tile.shape)
        name = f"linescan_domain__{seed}_{index:05d}.jpg"
        if (out / name).exists():
            raise ValueError("refusing to overwrite augmentation")
        Image.fromarray(np.clip(tile, 0, 255).astype(np.uint8)).save(out / name, quality=94)
        merged["images"].append({"id": next_im, "file_name": name, "width": 640, "height": height})
        for label, (x0, y0, x1, y1) in boxes:
            merged["annotations"].append({"id": next_ann, "image_id": next_im, "category_id": categories[label],
                                           "bbox": [x0, y0, x1 - x0, y1 - y0], "area": (x1 - x0) * (y1 - y0), "iscrowd": 0})
            next_ann += 1
        kind = cls if positive else "edge_nuisance" if boxes else "clean_edge"
        counts[kind] += 1
        details.append({"file": name, "kind": kind, "base": base["original"], "donor": donor["source"]["original"] if donor else None})
        next_im += 1
        if (index + 1) % 500 == 0:
            print(f"native line-scan domain examples {index + 1}/{n}", flush=True)
    report = {"seed": seed, "added_images": n, "counts": dict(counts), "split": "train",
              "frozen_manifest_sha256": expected_manifest, "validation_test_unchanged": True, "images": details}
    (out / "linescan_domain.json").write_text(json.dumps(report, indent=2))
    return merged, report


def guarded_thresholds(dets: list, truths: list, classes: list[str], baseline: dict[str, float]) -> dict[str, float]:
    from fabricdata.classes import NUISANCE_CLASSES
    from fabricdata.operating import GRID, match

    result = {}
    for cls in classes:
        tc = [t for t in truths if t.cls == cls]
        dc = [d for d in dets if d.cls == cls]
        previous = baseline.get(cls, 0.3)
        if not tc:
            result[cls] = previous
            continue
        grid = [t for t in GRID if t <= previous] if cls in NUISANCE_CLASSES else [t for t in GRID if t >= previous]
        best = (-1.0, previous)
        for threshold in grid:
            selected = [d for d in dc if d.score >= threshold]
            found, tp, duplicates = match(selected, tc, lambda a, b: a == b)
            fp = len(selected) - len(tp) - len(duplicates)
            f1 = 2 * len(found) / max(len(tc) + len(tp) + fp, 1)
            if f1 > best[0]:
                best = f1, threshold
        result[cls] = best[1]
    return result
