"""Group-disjoint native moving windows and 50/30/20 replay for line-scan fine-tuning.

Uses existing packed pixels/annotations; no test pixel can enter train or validation. Derived
AITEX-paste/nuisance images are excluded because their manifest does not identify every donor.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

TARGETS = ("broken_yarn", "missing_yarn", "crease_mark", "slub")
EXCLUDED = {"aitex_paste", "synth_nuisance"}


class BalancedStream:
    """Infinite 8-image batches: every batch has 4 targets; five batches give 50/30/20 exactly."""

    def __init__(self, kinds, seed):
        self.kinds = list(kinds)
        self.seed = seed
        if set(self.kinds) != {"target", "replay", "clean"}:
            raise ValueError("all three training cohorts are required")

    def __len__(self):
        return len(self.kinds)

    def __iter__(self):
        rng = random.Random(self.seed)
        indices = {
            kind: [n for n, value in enumerate(self.kinds) if value == kind]
            for kind in ("target", "replay", "clean")
        }
        streams = {kind: [] for kind in indices}

        def take(kind):
            if not streams[kind]:
                streams[kind] = indices[kind].copy()
                rng.shuffle(streams[kind])
            return streams[kind].pop()

        while True:
            for old, clean in ((3, 1), (2, 2), (3, 1), (2, 2), (2, 2)):
                batch = (
                    [take("target") for _ in range(4)]
                    + [take("replay") for _ in range(old)]
                    + [take("clean") for _ in range(clean)]
                )
                rng.shuffle(batch)
                yield from batch


def key(seed, value):
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def split_groups(rows, seed, signatures=None):
    strata = defaultdict(set)
    for r in rows:
        if r["split"] == "train" and r["source"] not in EXCLUDED:
            subtype = (
                Path(r["original"]).stem.split("_")[1]
                if r["source"] == "aitex"
                else (signatures or {}).get(r["tile"], "other")
            )
            strata[(r["source"], subtype)].add(r["group"])
    val = set()
    for groups in strata.values():
        ordered = sorted(groups, key=lambda g: key(seed, g))
        if len(ordered) > 1:
            val.update(
                ordered[: min(len(ordered) - 1, max(1, round(len(ordered) * 0.2)))]
            )
    return val


def crop_boxes(annotations, top, height=248, width=640):
    result = []
    for ann in annotations:
        x, y, w, h = ann["bbox"]
        x0, x1 = max(x, 0), min(x + w, width)
        y0, y1 = max(y - top, 0), min(y + h - top, height)
        if x1 - x0 >= 1 and y1 - y0 >= 1:
            result.append(
                {
                    **ann,
                    "bbox": [x0, y0, x1 - x0, y1 - y0],
                    "area": (x1 - x0) * (y1 - y0),
                }
            )
    return result


def extract_selected(packed, split, names, dest):
    dest.mkdir(parents=True, exist_ok=True)
    if any(Path(name).name != name for name in names):
        raise ValueError("unsafe packed image name")
    wanted = dest / ".wanted.txt"
    wanted.write_text("\n".join(sorted(names)) + "\n")
    print("PREP_UNPACK", split, len(names), "sequential native tar", flush=True)
    # Python getmembers()+random extractfile() incurs many remote FUSE seeks on Kaggle.
    # Native tar streams the frozen archive once, matching the proven original training loader.
    subprocess.run(
        [
            "tar",
            "-xf",
            str(packed / f"{split}.tar"),
            "-C",
            str(dest),
            "--no-same-owner",
            "--verbatim-files-from",
            "--files-from",
            str(wanted),
        ],
        check=True,
    )
    wanted.unlink()


def prepare(
    packed: Path,
    out: Path,
    seed=202611043,
    train_count=10000,
    val_count=1000,
    *,
    rendered=False,
    full_aitex=None,
    reserved_groups=None,
):
    if out.exists():
        raise ValueError("refusing to overwrite prepared data")
    out.mkdir(parents=True)
    rows = list(csv.DictReader((packed / "manifest.csv").open()))
    coco = json.loads((packed / "train/annotations.json").read_text())
    cat = {c["id"]: c["name"] for c in coco["categories"]}
    by_tile = {r["tile"]: r for r in rows if r["split"] == "train"}
    anns = defaultdict(list)
    for a in coco["annotations"]:
        anns[a["image_id"]].append(a)
    signatures = {
        im["file_name"]: tuple(sorted({cat[a["category_id"]] for a in anns[im["id"]]}))
        for im in coco["images"]
    }
    reserved = (
        set(reserved_groups)
        if reserved_groups is not None
        else split_groups(rows, seed, signatures)
    )
    groups = defaultdict(set)
    pools = {
        s: {"target": defaultdict(list), "clean": [], "replay": []}
        for s in ("train", "val")
    }
    for im in coco["images"]:
        r = by_tile[im["file_name"]]
        if r["source"] in EXCLUDED:
            continue
        split = "val" if r["group"] in reserved else "train"
        item = {"image": im, "annotations": anns[im["id"]], "manifest": r}
        groups[split].add(r["group"])
        pools[split]["replay"].append(item)
        if not item["annotations"] and r["source"] in {"aitex", "wfdd", "moratuwa"}:
            pools[split]["clean"].append(item)
        for c in TARGETS:
            if any(cat[a["category_id"]] == c for a in item["annotations"]):
                pools[split]["target"][c].append(item)
    # Never put a sole subtype into validation: keep its group in train.
    # For all target classes require train/val examples rather than silently measuring an absent class.
    for split in pools:
        for c in TARGETS:
            if not pools[split]["target"][c]:
                raise ValueError(f"no independent {split} examples for {c}")
        if not pools[split]["clean"]:
            raise ValueError(f"no clean {split} source")
    if groups["train"] & groups["val"]:
        raise ValueError("source group leakage")
    raw = out / "original_tiles"
    selected = {i["image"]["file_name"] for p in pools.values() for i in p["replay"]}
    extract_selected(packed, "train", selected, raw)
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools/simulator"))
    from make_roll_video import FabricDecor, make_board

    sys.path.insert(0, str(Path(__file__).parent))
    from fabricdata import nuisance

    report = {
        "seed": seed,
        "manifest_sha256": hashlib.sha256(
            (packed / "manifest.csv").read_bytes()
        ).hexdigest(),
        "excluded_derived_sources": sorted(EXCLUDED),
        "validation_caveat": "Held out from this fine-tune; starting models have seen original packed training sources.",
        "splits": {},
        "train_val_groups_disjoint": True,
        "target_frame_pipeline": "actual simulator raster and camera"
        if rendered
        else "native source crop",
        "renderer_background_policy": "fabric-family matched; single nearest clean appearance"
        if rendered
        else None,
    }
    rendered_views = None
    if rendered:
        if full_aitex is None:
            raise ValueError(
                "renderer-matched data requires the existing full AITEX train-source bundle"
            )
        from linescan_rendered import RenderedViews

        rendered_views = RenderedViews(
            raw, out / "renderer_sources", pools, cat, full_aitex, seed
        )
        from linescan_rendered import thin_vertical

        broken_id = next(cid for cid, name in cat.items() if name == "broken_yarn")
        report["broken_yarn_source_audit"] = {
            split: {
                source: {
                    "originals": len(
                        {
                            i["manifest"]["original"]
                            for i in pool["target"]["broken_yarn"]
                            if i["manifest"]["source"] == source
                        }
                    ),
                    "thin_vertical_originals": len(
                        {
                            i["manifest"]["original"]
                            for i in pool["target"]["broken_yarn"]
                            if i["manifest"]["source"] == source
                            and thin_vertical(i["annotations"], broken_id)
                        }
                    ),
                }
                for source in sorted(
                    {i["manifest"]["source"] for i in pool["target"]["broken_yarn"]}
                )
            }
            for split, pool in pools.items()
        }
    cache = {}

    def read(item):
        name = item["image"]["file_name"]
        if name not in cache:
            if len(cache) > 128:
                cache.clear()
            im = cv2.imread(str(raw / name))
            if im is None:
                raise ValueError("missing image " + name)
            cache[name] = im
        return cache[name].copy()

    for split, count in (("train", train_count), ("val", val_count)):
        rng = np.random.default_rng(seed + (split == "val"))
        pool = pools[split]
        output = out / split
        output.mkdir()
        images = []
        labels = []
        provenance = []
        counts = Counter()
        for index in range(count):
            if index % 250 == 0:
                print("PREP_PROGRESS", split, index, count, flush=True)
            bucket = index % 10
            kind = (
                "target"
                if bucket < 5
                else "replay"
                if split == "train" and bucket < 8
                else "clean"
            )
            chosen_class = None
            if kind == "target":
                chosen_class = (
                    ["broken_yarn"] * 6 + ["missing_yarn"] * 2 + ["crease_mark", "slub"]
                )
                chosen_class = chosen_class[(index // 10 * 5 + bucket) % 10]
                candidates = pool["target"][chosen_class]
                # Balance source domains before selecting a tile; Tianchi must not drown AITEX/WFDD/Moratuwa.
                sources = sorted({r["manifest"]["source"] for r in candidates})
                source = sources[int(rng.integers(len(sources)))]
                candidates = [
                    i for i in candidates if i["manifest"]["source"] == source
                ]
                if rendered and chosen_class == "broken_yarn":
                    from linescan_rendered import thin_vertical

                    cid = next(cid for cid, name in cat.items() if name == chosen_class)
                    narrow = [
                        i for i in candidates if thin_vertical(i["annotations"], cid)
                    ]
                    if narrow and index % 5 != 0:
                        candidates = narrow
                    singleton = [
                        i
                        for i in pool["target"][chosen_class]
                        if i["manifest"]["source"] == "aitex"
                        and "_006_" in i["manifest"]["original"]
                    ]
                    if (
                        split == "train"
                        and bucket == 0
                        and (index // 10) % 6 == 0
                        and singleton
                    ):
                        candidates = singleton
            else:
                candidates = pool[kind]
            item = candidates[int(rng.integers(len(candidates)))]
            image = read(item)
            source_h, _source_w = image.shape[:2]
            annotations = item["annotations"]
            if kind != "replay":
                if chosen_class:
                    boxes = [
                        a for a in annotations if cat[a["category_id"]] == chosen_class
                    ]
                    box = boxes[int(rng.integers(len(boxes)))]["bbox"]
                    # Sliding views of the real source preserve a long yarn and its surrounding weave.
                    phase = (index // 10) % 5
                    top = round(box[1] + box[3] / 2 - 124 + (phase - 2) * 48)
                    top = int(np.clip(top, 0, max(0, source_h - 248)))
                else:
                    top = int(rng.integers(max(1, source_h - 248 + 1)))
                image = image[top : top + 248, :640]
                h, _w = image.shape[:2]
                image = cv2.copyMakeBorder(
                    image, 0, 248 - h, 0, 640 - _w, cv2.BORDER_REFLECT_101
                )
                annotations = crop_boxes(annotations, top)
                if chosen_class and not any(
                    cat[a["category_id"]] == chosen_class for a in annotations
                ):
                    # The fault can be longer than the camera; centre a view on its visible extent.
                    top = int(
                        np.clip(
                            round(box[1] + box[3] / 2 - 124), 0, max(0, source_h - 248)
                        )
                    )
                    image = read(item)[top : top + 248, :640]
                    h, _w = image.shape[:2]
                    image = cv2.copyMakeBorder(
                        image, 0, 248 - h, 0, 640 - _w, cv2.BORDER_REFLECT_101
                    )
                    annotations = crop_boxes(item["annotations"], top)
                if kind == "clean":
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    rgb = np.repeat(gray[..., None], 3, 2).astype(np.float32)
                    decor = FabricDecor(640, 248, 640 / 27.0, seed + index, True)
                    decor.wrinkles, decor.threads, decor.stickers = [], [], []
                    rgb, edge = decor.apply(rgb, 0, index)
                    board = make_board(248, 704, seed + index)
                    board[:, 32:672] = rgb
                    band, left, right = edge
                    board[:, 32 : 32 + band] = board[:, 32 : 32 + band] * left[
                        ..., None
                    ] + make_board(248, 704, seed + index)[:, 32 : 32 + band] * (
                        1 - left[..., None]
                    )
                    start = 32 + 640 - band
                    board[:, start : start + band] = board[
                        :, start : start + band
                    ] * right[..., None] + make_board(248, 704, seed + index)[
                        :, start : start + band
                    ] * (1 - right[..., None])
                    image = board[:, :640] if index % 2 else board[:, 64:]
                    if index % 3 == 0:
                        drawn = [
                            nuisance.loose_thread,
                            nuisance.wrinkle,
                            nuisance.sticker,
                        ][(index // 3) % 3](image, rng)
                        if drawn:
                            c = next(
                                cid for cid, name in cat.items() if name == drawn.cls
                            )
                            x0, y0, x1, y1 = drawn.box
                            annotations = [
                                {
                                    "category_id": c,
                                    "bbox": [x0, y0, x1 - x0, y1 - y0],
                                    "area": (x1 - x0) * (y1 - y0),
                                }
                            ]
                image = np.clip(
                    image.astype(np.float32) * rng.uniform(0.93, 1.07)
                    + rng.normal(0, rng.uniform(0, 2), image.shape),
                    0,
                    255,
                ).astype(np.uint8)
            rendered_provenance = {}
            if rendered_views is not None and kind != "replay":
                from linescan_rendered import UnrenderableTarget

                for attempt in range(10):
                    try:
                        image, annotations, rendered_provenance = rendered_views.render(
                            split, item, chosen_class, index, kind
                        )
                        break
                    except UnrenderableTarget:
                        if kind != "target" or attempt == 9:
                            raise
                        alternatives = pool["target"][chosen_class]
                        item = alternatives[int(rng.integers(len(alternatives)))]
            name = f"{'r4' if rendered else 'r3'}_{split}_{index:05d}.jpg"
            cv2.imwrite(str(output / name), image, [cv2.IMWRITE_JPEG_QUALITY, 94])
            images.append(
                {
                    "id": index + 1,
                    "file_name": name,
                    "height": image.shape[0],
                    "width": image.shape[1],
                }
            )
            for a in annotations:
                labels.append(
                    {
                        "id": len(labels) + 1,
                        "image_id": index + 1,
                        "category_id": a["category_id"],
                        "bbox": a["bbox"],
                        "area": a["area"],
                        "iscrowd": 0,
                    }
                )
            provenance.append(
                {
                    "file": name,
                    "source_tile": item["image"]["file_name"],
                    "original": item["manifest"]["original"],
                    "group": item["manifest"]["group"],
                    "kind": kind,
                    **rendered_provenance,
                }
            )
            counts[kind] += 1
        (output / "annotations.json").write_text(
            json.dumps(
                {
                    "images": images,
                    "annotations": labels,
                    "categories": coco["categories"],
                }
            )
        )
        (output / "provenance.json").write_text(json.dumps(provenance))
        report["splits"][split] = {
            "images": len(images),
            "annotations": len(labels),
            "buckets": dict(counts),
            "originals": len(
                {o for r in provenance for o in r.get("originals", [r["original"]])}
            ),
            "groups": len(
                {g for r in provenance for g in r.get("groups", [r["group"]])}
            ),
            "classes": dict(Counter(cat[a["category_id"]] for a in labels)),
        }
        print(split, report["splits"][split], flush=True)
    report["reserved_groups"] = sorted(reserved)
    (out / "preparation.json").write_text(json.dumps(report, indent=2))
    return pools, report


def prepare_videos(packed: Path, out: Path, pools: dict, seed: int):
    """Freeze validation and final-test video sources before any pilot training."""
    rows = list(csv.DictReader((packed / "manifest.csv").open()))
    manifest = {r["tile"]: r for r in rows}
    cats = json.loads((packed / "train/annotations.json").read_text())["categories"]
    names = {c["id"]: c["name"] for c in cats}
    bysplit = {}
    for split in ("val", "test"):
        if split == "val":
            items = pools["val"]["replay"]
        else:
            coco = json.loads((packed / "test/annotations.json").read_text())
            ann = defaultdict(list)
            for a in coco["annotations"]:
                ann[a["image_id"]].append(a)
            # All AITEX test defect originals were already used by regression video source pools.
            items = [
                {
                    "image": im,
                    "annotations": ann[im["id"]],
                    "manifest": manifest[im["file_name"]],
                }
                for im in coco["images"]
                if manifest[im["file_name"]]["source"]
                in {"wfdd", "moratuwa", "tianchi"}
            ]
        selected = [
            i
            for i in items
            if not i["annotations"]
            or any(names[a["category_id"]] in TARGETS for a in i["annotations"])
        ]
        groups = sorted(
            {i["manifest"]["group"] for i in selected}, key=lambda g: key(seed + 9, g)
        )
        partitions = {g: n % 4 for n, g in enumerate(groups)}
        bysplit[split] = []
        raw = out / "video_raw" / split
        if split == "test":
            extract_selected(
                packed, "test", {i["image"]["file_name"] for i in selected}, raw
            )
        else:
            raw = out / "original_tiles"
        for n in range(4):
            members = [i for i in selected if partitions[i["manifest"]["group"]] == n]
            source = out / "video_sources" / f"{split}_{n}"
            (source / "images").mkdir(parents=True)
            (source / "labels").mkdir()
            (source / "dataset.yaml").write_text(
                "names: " + json.dumps([c["name"] for c in cats])
            )
            provenance = []
            for k, item in enumerate(members):
                image = cv2.imread(str(raw / item["image"]["file_name"]))
                if image is None:
                    raise ValueError("missing video source")
                aa = item["annotations"]
                target = next(
                    (a for a in aa if names[a["category_id"]] == "broken_yarn"), None
                )
                if target is None:
                    target = next(iter(aa), None)
                h, _w = image.shape[:2]
                y = int(
                    np.clip(
                        round(target["bbox"][1] + target["bbox"][3] / 2 - 124)
                        if target
                        else 0,
                        0,
                        max(0, h - 248),
                    )
                )
                crop = image[y : y + 248, :640]
                ch, cw = crop.shape[:2]
                crop = cv2.copyMakeBorder(
                    crop, 0, 248 - ch, 0, 640 - cw, cv2.BORDER_REFLECT_101
                )
                a = crop_boxes(aa, y)
                name = f"source_{k:04d}"
                cv2.imwrite(str(source / "images" / (name + ".jpg")), crop)
                lines = []
                for b in a:
                    x0, y0, bw, bh = b["bbox"]
                    lines.append(
                        f"{b['category_id'] - 1} {(x0 + bw / 2) / 640} {(y0 + bh / 2) / 248} {bw / 640} {bh / 248}"
                    )
                (source / "labels" / (name + ".txt")).write_text("\n".join(lines))
                provenance.append(item["manifest"])
            if not any(
                any(names[a["category_id"]] == "broken_yarn" for a in i["annotations"])
                for i in members
            ):
                raise ValueError(f"no independent broken yarn in {split} video {n}")
            if not any(not i["annotations"] for i in members):
                raise ValueError("no clean video background")
            dest = out / "videos" / f"{split}_{n}"
            command = [
                sys.executable,
                str(
                    Path(__file__).parent.parent / "tools/simulator/make_roll_video.py"
                ),
                "--source",
                "yolo",
                "--dataset",
                str(source),
                "--out",
                str(dest),
                "--linescan",
                "--seam-cut",
                "--frame-width",
                "3840",
                "--roll-length-m",
                "6",
                "--seed",
                str(seed + 100 + n + (100 if split == "test" else 0)),
                "--defects-per-10m",
                "40",
                "--noise",
                "1.5",
                "--speed-m-min",
                "20",
            ]
            subprocess.run(command, check=True)
            source_report = {
                "split": split,
                "seed": seed,
                "originals": sorted({r["original"] for r in provenance}),
                "groups": sorted({r["group"] for r in provenance}),
                "basis": "held-out fine-tuning groups"
                if split == "val"
                else "official test source groups; excludes all AITEX regression pools",
                "files": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in dest.iterdir()
                    if p.is_file()
                },
            }
            (dest / "frozen_sources.json").write_text(
                json.dumps(source_report, indent=2)
            )
            bysplit[split].append(source_report)
    if {g for v in bysplit["val"] for g in v["groups"]} & {
        g for v in bysplit["test"] for g in v["groups"]
    }:
        raise ValueError("video source group leakage")
    (out / "frozen_videos.json").write_text(json.dumps(bysplit, indent=2))
