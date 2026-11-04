"""Extra line-scan-style training tiles from an existing frozen COCO train split.

No new source dataset or split assignment. All labels (including non-defects) are
cropped with their pixels. Validation/test images cannot be used as donors.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

TARGETS = ("broken_yarn", "missing_yarn", "crease_mark", "slub")


def augment(train: dict, images: Path, out: Path, *, n: int = 1600, seed: int = 20261104,
            forbidden: set[str] | None = None) -> tuple[dict, dict]:
    if n < 1:
        raise ValueError("augmentation count must be positive")
    names = {im["file_name"] for im in train["images"]}
    if names & (forbidden or set()):
        raise ValueError("train donors overlap validation/test image names")
    if any(Path(name).name != name for name in names):
        raise ValueError("training image names must be basenames")
    categories = {c["id"]: c["name"] for c in train["categories"]}
    annotations: dict[int, list[dict]] = defaultdict(list)
    for a in train["annotations"]:
        annotations[a["image_id"]].append(a)
    pools: dict[str, list[dict]] = defaultdict(list)
    clean = []
    for im in train["images"]:
        if not annotations[im["id"]]:
            clean.append(im)
        for cls in {categories[a["category_id"]] for a in annotations[im["id"]]} & set(TARGETS):
            pools[cls].append(im)
    classes = [cls for cls in TARGETS if pools[cls]]
    if not classes:
        raise ValueError("no target defects in the frozen training split")
    rng, noise_rng = random.Random(seed), np.random.default_rng(seed)
    next_im = max(im["id"] for im in train["images"]) + 1
    next_ann = max((a["id"] for a in train["annotations"]), default=0) + 1
    merged = {**train, "images": list(train["images"]), "annotations": list(train["annotations"])}
    out.mkdir(parents=True, exist_ok=True)
    provenance = []
    for index in range(n):
        cls = classes[index % len(classes)]
        tile = Image.new("RGB", (640, 640), (114, 114, 114))
        labels, donors = [], []
        for strip, dest_y in enumerate((0, 304)):
            pool = clean if clean and index % 5 == 0 and strip == 1 else pools[cls]
            # Half of positive strips favor the AITEX line-scan source. Others
            # preserve coverage of the existing dataset's other fabrics.
            aitex = [im for im in pool if im["file_name"].startswith("aitex__")]
            im = rng.choice(aitex if aitex and rng.random() < 0.5 else pool)
            with Image.open(images / im["file_name"]) as source:
                source = source.convert("RGB")
                boxes = annotations[im["id"]]
                anchors = [a for a in boxes if categories[a["category_id"]] == cls]
                crop_h, crop_w = min(256, source.height), min(640, source.width)
                anchor = rng.choice(anchors)["bbox"] if anchors else [0, 0, crop_w, crop_h]
                x = max(0, min(source.width - crop_w, round(anchor[0] + anchor[2] / 2 - crop_w / 2)))
                y = max(0, min(source.height - crop_h, round(anchor[1] + anchor[3] / 2 - crop_h / 2 + rng.uniform(-32, 32))))
                patch = source.crop((x, y, x + crop_w, y + crop_h))
            patch = ImageEnhance.Contrast(patch).enhance(rng.uniform(0.65, 1.2))
            patch = ImageEnhance.Brightness(patch).enhance(rng.uniform(0.85, 1.15))
            patch = patch.filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.6)))
            pixels = np.asarray(patch, dtype=np.float32)
            pixels += noise_rng.normal(0, rng.uniform(0, 2), pixels.shape)
            tile.paste(Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)), (0, dest_y))
            for a in boxes:
                ax, ay, aw, ah = a["bbox"]
                x0, y0 = max(0, ax - x), max(0, ay - y)
                x1, y1 = min(crop_w, ax + aw - x), min(crop_h, ay + ah - y)
                if x1 - x0 >= 2 and y1 - y0 >= 2:
                    labels.append({"id": next_ann, "image_id": next_im, "category_id": a["category_id"],
                                   "bbox": [x0, y0 + dest_y, x1 - x0, y1 - y0],
                                   "area": (x1 - x0) * (y1 - y0), "iscrowd": 0})
                    next_ann += 1
            donors.append({"tile": im["file_name"], "crop": [x, y, crop_w, crop_h], "offset_y": dest_y})
        name = f"linescan_addon__{seed}_{index:05d}.jpg"
        if name in names or (out / name).exists():
            raise ValueError(f"augmentation output already exists: {name}")
        tile.save(out / name, quality=92)
        merged["images"].append({"id": next_im, "file_name": name, "width": 640, "height": 640})
        merged["annotations"].extend(labels)
        provenance.append({"file": name, "target": cls, "donors": donors})
        next_im += 1
    report = {"seed": seed, "added_images": n, "target_classes": classes,
              "input_annotations_sha256": hashlib.sha256(json.dumps(train, sort_keys=True).encode()).hexdigest(),
              "split": "train", "validation_test_unchanged": True, "images": provenance}
    (out / "linescan_augmentation.json").write_text(json.dumps(report, indent=2))
    return merged, report
