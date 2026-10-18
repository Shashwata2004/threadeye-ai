"""Build the ThreadEye detector dataset (COCO) from the public sources in data/external/.

    ml/.venv/bin/python ml/build_dataset.py --dry-run                 # counts only, writes nothing
    ml/.venv/bin/python ml/build_dataset.py --out data/processed/threadeye_v1
    ... --tianchi-images /kaggle/working/tianchi                      # where the Tianchi export was unpacked

Steps: read every available source → map classes to the ThreadEye taxonomy (dropping non-roll defects)
→ merge near-duplicate images into one group → group-aware split → tiles → COCO per split + manifest.
Train tiles without a defect are subsampled (``--bg-ratio`` per defect tile); val/test keep every tile so
false alarms are measured on realistic data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from fabricdata import sources  # noqa: E402
from fabricdata.classes import DEFECT_CLASSES, map_class  # noqa: E402
from fabricdata.dedupe import COPY_PRONE, Fingerprint, fingerprint, merge_near_duplicates  # noqa: E402
from fabricdata.records import Box, ImageRecord  # noqa: E402
from fabricdata.split import SPLITS, assign_splits  # noqa: E402
from fabricdata.tiles import Window, clip, scaled, windows  # noqa: E402

LICENCE = {
    "aitex": "AITEX AFID (cite the AFID paper; no licence stated by AITEX)",
    "fabricspotdefect": "CC BY 4.0",
    "moratuwa": "CC BY 4.0 (Mendeley 663j22s43c)",
    "fd_figshare": "CC BY 4.0",
    "garment_defects": "CC BY 4.0",
    "tianchi": "Tianchi 2019 Guangdong data via a Roboflow mirror (uploader: CC BY 4.0)",
    "zju_leaper": "CC BY-NC-SA 4.0 (non-commercial)",
    "raw_fabrid": "CC BY 4.0",
    "wfdd": "WFDD (Kaggle mirror hodinhtrieu/the-woven-fabric-defect-detection-wfdd; licence not stated)",
}
NON_COMMERCIAL = {"zju_leaper"}
"""Left out with --commercial-only (a model for a product that is sold)."""
MAX_SIDE = {"fabricspotdefect": 1600, "moratuwa": 1280}
"""Phone photos are shrunk first (their defects are large); line-scan and loom images keep full size."""
MIN_BOX_PX = 2.0


@dataclass
class Tile:
    record: ImageRecord
    split: str
    scale: float
    win: Window
    boxes: list[Box]

    @property
    def name(self) -> str:
        stem = sources.original_name(self.record.path.name).rsplit(".", 1)[0]
        return f"{self.record.source}__{stem}__{self.win.x0}_{self.win.y0}.jpg"


def load(external: Path, wanted: list[str], tianchi_images: Path | None) -> tuple[list[ImageRecord], Counter]:
    records: list[ImageRecord] = []
    dropped: Counter = Counter()
    for name in wanted:
        root = external / name
        if not root.exists():
            print(f"  {name}: not downloaded, skipped")
            continue
        reader = sources.READERS[name]
        found = list(reader(root, tianchi_images) if name == "tianchi" else reader(root))
        for r in found:
            kept = []
            for b in r.boxes:
                cls = map_class(r.source, b.src_cls)
                if cls is None:
                    dropped[f"{r.source}:{b.src_cls}"] += 1
                else:
                    b.cls = cls
                    kept.append(b)
            r.boxes = kept
        records += found
        print(f"  {name}: {len(found)} images, {sum(len(r.boxes) for r in found)} boxes")
    return records, dropped


def apply_caps(records: list[ImageRecord], caps: list[str], seed: int) -> list[ImageRecord]:
    """``--cap zju_leaper:clean=8000`` keeps a fixed, hash-chosen sample of that source's defect-free (or
    ``defect``) images, so one huge source cannot drown the others."""
    limits = {}
    for c in caps:
        key, n = c.split("=")
        source, kind = key.split(":")
        assert kind in ("clean", "defect"), c
        limits[(source, kind)] = int(n)
    pools: dict[tuple[str, str], list[ImageRecord]] = defaultdict(list)
    for r in records:
        pools[(r.source, "clean" if r.defect_free else "defect")].append(r)
    out = []
    for key, pool in pools.items():
        if key in limits and len(pool) > limits[key]:
            pool = sorted(pool, key=lambda r: hashlib.sha1(f"{seed}:{r.key}".encode()).hexdigest())[: limits[key]]
            print(f"  {key[0]} {key[1]}: kept {limits[key]} of {len(pools[key])}")
        out += pool
    return out


def plan(records: list[ImageRecord], split_of: dict[str, str], tile: int, overlap: float) -> list[Tile]:
    tiles = []
    for r in records:
        s = min(1.0, MAX_SIDE[r.source] / max(r.width, r.height)) if r.source in MAX_SIDE else 1.0
        w, h = round(r.width * s), round(r.height * s)
        boxes = [b for b in scaled(r.boxes, s) if b.w >= MIN_BOX_PX and b.h >= MIN_BOX_PX]
        for win in windows(w, h, tile, overlap):
            tiles.append(Tile(r, split_of[r.key], s, win, clip(boxes, win)))
    return tiles


def keep_tiles(tiles: list[Tile], bg_ratio: float, seed: int) -> list[Tile]:
    """All defect tiles; train background tiles subsampled per source to ``bg_ratio`` per defect tile."""
    pos = Counter(t.record.source for t in tiles if t.split == "train" and t.boxes)
    bg = Counter(t.record.source for t in tiles if t.split == "train" and not t.boxes)
    out = []
    for t in tiles:
        if t.boxes or t.split != "train":
            out.append(t)
            continue
        src = t.record.source
        share = min(1.0, bg_ratio * max(pos[src], 1) / max(bg[src], 1))
        if int(hashlib.sha1(f"{seed}:{t.name}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < share:
            out.append(t)
    return out


def write(tiles: list[Tile], out: Path, external: Path) -> None:
    cats = [{"id": i + 1, "name": c} for i, c in enumerate(DEFECT_CLASSES)]
    cat_id = {c: i + 1 for i, c in enumerate(DEFECT_CLASSES)}
    coco = {s: {"images": [], "annotations": [], "categories": cats} for s in SPLITS}
    by_image: dict[Path, list[Tile]] = defaultdict(list)
    for t in tiles:
        by_image[t.record.path].append(t)
    manifest = []
    ann_id = 0
    for i, (path, ts) in enumerate(by_image.items()):
        with Image.open(path) as im:
            im = im.convert("RGB")
            s = ts[0].scale
            if s < 1.0:
                im = im.resize((round(im.width * s), round(im.height * s)), Image.Resampling.LANCZOS)
            for t in ts:
                split_dir = out / t.split / "images"
                split_dir.mkdir(parents=True, exist_ok=True)
                crop = im.crop((t.win.x0, t.win.y0, t.win.x1, t.win.y1))
                crop.save(split_dir / t.name, quality=92)
                c = coco[t.split]
                img_id = len(c["images"]) + 1
                c["images"].append({"id": img_id, "file_name": t.name, "width": crop.width, "height": crop.height})
                for b in t.boxes:
                    ann_id += 1
                    c["annotations"].append({
                        "id": ann_id, "image_id": img_id, "category_id": cat_id[b.cls],
                        "bbox": [round(b.x0, 1), round(b.y0, 1), round(b.w, 1), round(b.h, 1)],
                        "area": round(b.w * b.h, 1), "iscrowd": 0,
                    })
                manifest.append({
                    "split": t.split, "tile": t.name, "source": t.record.source,
                    "original": str(path.relative_to(external)) if path.is_relative_to(external) else str(path),
                    "group": t.record.group, "boxes": len(t.boxes), "licence": LICENCE[t.record.source],
                })
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(by_image)} images")
    for s in SPLITS:
        (out / s).mkdir(parents=True, exist_ok=True)
        (out / s / "annotations.json").write_text(json.dumps(coco[s]))
    with (out / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0]))
        w.writeheader()
        w.writerows(manifest)


def summary(records: list[ImageRecord], split_of: dict[str, str], tiles: list[Tile], dropped: Counter) -> dict:
    per_split_cls: dict[str, Counter] = {s: Counter() for s in SPLITS}
    for t in tiles:
        per_split_cls[t.split].update(b.cls for b in t.boxes)
    per_source = defaultdict(lambda: Counter())
    for r in records:
        per_source[r.source][split_of[r.key]] += 1
    src_classes: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        src_classes[r.source].update(f"{b.src_cls}->{b.cls}" for b in r.boxes)
    return {
        "source_classes": {k: dict(v.most_common()) for k, v in src_classes.items()},
        "clean_images_per_source": dict(Counter(r.source for r in records if r.defect_free)),
        "images_per_source_split": {k: dict(v) for k, v in per_source.items()},
        "groups": len({r.group for r in records}),
        "tiles": dict(Counter(t.split for t in tiles)),
        "defect_tiles": dict(Counter(t.split for t in tiles if t.boxes)),
        "boxes_per_class": {s: dict(c.most_common()) for s, c in per_split_cls.items()},
        "dropped_boxes": dict(dropped),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--out", type=Path, default=Path("data/processed/threadeye_v1"))
    ap.add_argument("--sources", nargs="*", default=list(sources.READERS))
    ap.add_argument("--tianchi-images", type=Path)
    ap.add_argument("--tile", type=int, default=640)
    ap.add_argument("--overlap", type=float, default=0.2)
    ap.add_argument("--bg-ratio", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cap", action="append", default=[], help="SOURCE:clean=N or SOURCE:defect=N")
    ap.add_argument("--commercial-only", action="store_true", help="leave out non-commercial sources")
    args = ap.parse_args()

    print("reading sources")
    wanted = [s for s in args.sources if not (args.commercial_only and s in NON_COMMERCIAL)]
    records, dropped = load(args.external, wanted, args.tianchi_images)
    present = [r for r in records if r.path.exists()]
    missing = len(records) - len(present)
    if missing:
        print(f"  {missing} images listed but not on disk (e.g. Tianchi images on Kaggle): left out")
    records = apply_caps(present, args.cap, args.seed)

    print("grouping near-duplicates")
    prints = [fingerprint(r.path) if r.source in COPY_PRONE else Fingerprint(0.0, 0, 0) for r in records]
    merges = merge_near_duplicates(records, prints)
    print(f"  {merges} merges")
    split_of = assign_splits(records, seed=args.seed)
    tiles = keep_tiles(plan(records, split_of, args.tile, args.overlap), args.bg_ratio, args.seed)
    info = summary(records, split_of, tiles, dropped)
    print(json.dumps(info, indent=1))
    if args.dry_run:
        return
    print(f"writing {len(tiles)} tiles to {args.out}")
    write(tiles, args.out, args.external)
    (args.out / "summary.json").write_text(json.dumps(info, indent=1))
    print("done")


if __name__ == "__main__":
    main()
