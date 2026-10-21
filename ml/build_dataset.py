"""Build the ThreadEye detector dataset (COCO) from the public sources in data/external/.

    ml/.venv/bin/python ml/build_dataset.py --dry-run                 # counts only, writes nothing
    ml/.venv/bin/python ml/build_dataset.py --out data/processed/threadeye_v1
    ... --tianchi-images /kaggle/working/tianchi                      # where the Tianchi export was unpacked
    ... --smoke 20                                                    # 20 images per source: time every step
    ... --patch-base OLD --patch fabricspotdefect --out PATCH         # rebuild one source on top of OLD

Steps: read every available source → map classes to the ThreadEye taxonomy (dropping non-roll defects)
→ merge near-duplicate images into one group → group-aware split → tiles → COCO per split + manifest.
Train tiles without a defect are subsampled (``--bg-ratio`` per defect tile); val/test keep every tile so
false alarms are measured on realistic data.

A patch (``--patch-base``/``--patch``) re-reads only the patched sources and the sources that may hold copies
of them (COPY_PRONE, for the near-duplicate groups), writes only the patched sources' tiles, and writes
annotations for the whole dataset: the base build's tiles of every other source (same file names, same
splits) plus the new ones. Non-defect tiles drawn on a patched source are left out (their boxes came from the
old records). Splits are decided per source (fabricdata.split), so the result is the full build's result for
the same code; a patched record grouped with a copy from another source takes that copy's split.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from fabricdata import sources  # noqa: E402
from fabricdata.classes import DETECTOR_CLASSES, map_class  # noqa: E402
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
    "fabric_stain": "CC0 1.0 (Kaggle priemshpathirana/fabric-stain-dataset)",
    "synth_nuisance": "ours (ml/synth_nuisance.py) on tiles of the sources above; hands from EgoHands (CC BY 4.0)",
    "aitex_paste": "ours (ml/aitex_paste.py): AITEX defects pasted onto AITEX clean images (AITEX terms apply)",
}
NON_COMMERCIAL = {"zju_leaper"}
"""Left out with --commercial-only (a model for a product that is sold)."""
MAX_SIDE = {"fabricspotdefect": 1024, "fabric_stain": 1024, "moratuwa": 1280}
"""Phone photos are shrunk first (their defects are large); line-scan and loom images keep full size.
1024 for the stain photos: at 1600 FabricSpotDefect alone gave a quarter of all train boxes (each stain cut
into several overlapping tiles), drowning the rarer classes."""
MIN_BOX_PX = 2.0


@dataclass
class Tile:
    record: ImageRecord
    split: str
    scale: float
    win: Window
    boxes: list[Box]
    zoom: float = 1.0
    """Extra enlargement (--scales): the tile shows the image at zoom × its usual size."""

    @property
    def name(self) -> str:
        # The record key's hash keeps images with the same file name apart (record.key); before 2026-10-20
        # such tiles overwrote each other while all their boxes were kept.
        stem = sources.original_name(self.record.path.name).rsplit(".", 1)[0]
        tag = hashlib.sha1(self.record.key.encode()).hexdigest()[:6]
        zoom = f"_x{self.zoom:g}" if self.zoom != 1.0 else ""
        return f"{self.record.source}__{stem}_{tag}{zoom}__{self.win.x0}_{self.win.y0}.jpg"


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


def check_pastes(records: list[ImageRecord], split_of: dict[str, str], external: Path) -> None:
    """Every AITEX image a pasted image was made from (its base and its donor defects) must be a train image of
    this build, or test pixels would be trained on; the build stops otherwise."""
    pastes = [r for r in records if r.source == "aitex_paste"]
    if not pastes:
        return
    made_from = json.loads((external / "aitex_paste/groups.json").read_text())
    aitex = {r.path.name: split_of[r.key] for r in records if r.source == "aitex"}
    bad = Counter()
    for r in pastes:
        info = made_from[r.path.name]
        for name in [info["base"], *info.get("donors", [])]:
            if aitex.get(name, "train") != "train":
                bad[f"{name} ({aitex[name]})"] += 1
    if bad:
        raise SystemExit(f"aitex_paste: {len(bad)} source images are not in train, e.g. {list(bad)[:5]}")
    print(f"  aitex_paste: {len(pastes)} images, every base and donor is a train image", flush=True)


def smoke_sample(records: list[ImageRecord], n: int, seed: int) -> list[ImageRecord]:
    """``n`` hash-chosen images per source and kind (with / without defects): a full run in minutes."""
    pools: dict[tuple[str, bool], list[ImageRecord]] = defaultdict(list)
    for r in records:
        pools[(r.source, r.defect_free)].append(r)
    return [r for pool in pools.values()
            for r in sorted(pool, key=lambda r: hashlib.sha1(f"{seed}:{r.key}".encode()).hexdigest())[:n]]


def plan(records: list[ImageRecord], split_of: dict[str, str], tile: int, overlap: float,
         zooms: dict[str, tuple[float, ...]] | None = None) -> list[Tile]:
    """Tiles of every record, at each of its source's zooms (default: 1, the usual size only)."""
    tiles = []
    for r in records:
        base = min(1.0, MAX_SIDE[r.source] / max(r.width, r.height)) if r.source in MAX_SIDE else 1.0
        for zoom in (zooms or {}).get(r.source, (1.0,)):
            s = base * zoom
            w, h = round(r.width * s), round(r.height * s)
            boxes = [b for b in scaled(r.boxes, s) if b.w >= MIN_BOX_PX and b.h >= MIN_BOX_PX]
            for win in windows(w, h, tile, overlap):
                tiles.append(Tile(r, split_of[r.key], s, win, clip(boxes, win), zoom))
    return tiles


def keep_tiles(tiles: list[Tile], bg_ratio: float, seed: int, bg_for: dict[str, float] | None = None) -> list[Tile]:
    """All defect tiles; train background tiles subsampled per source and zoom to ``bg_ratio`` per defect tile
    (per zoom, so adding an enlarged copy of a source leaves its usual-size tiles as they were)."""
    pos = Counter((t.record.source, t.zoom) for t in tiles if t.split == "train" and t.boxes)
    bg = Counter((t.record.source, t.zoom) for t in tiles if t.split == "train" and not t.boxes)
    out = []
    for t in tiles:
        if t.boxes or t.split != "train":
            out.append(t)
            continue
        src = (t.record.source, t.zoom)
        ratio = (bg_for or {}).get(t.record.source, bg_ratio)
        share = min(1.0, ratio * max(pos[src], 1) / max(bg[src], 1))
        if int(hashlib.sha1(f"{seed}:{t.name}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < share:
            out.append(t)
    return out


def cut(ts: list[Tile], out: Path) -> list[tuple[Tile, int, int]]:
    """Save the tiles of one image; (tile, width, height) for each."""
    done = []
    with sources.open_rgb(ts[0].record) as im:
        s = ts[0].scale
        if s != 1.0:
            # Enlarged as the app enlarges a frame (infer_scale: cv2 bilinear); shrunk with Lanczos.
            resample = Image.Resampling.BILINEAR if s > 1.0 else Image.Resampling.LANCZOS
            im = im.resize((round(im.width * s), round(im.height * s)), resample)
        for t in ts:
            split_dir = out / t.split / "images"
            split_dir.mkdir(parents=True, exist_ok=True)
            crop = im.crop((t.win.x0, t.win.y0, t.win.x1, t.win.y1))
            crop.save(split_dir / t.name, quality=92)
            done.append((t, crop.width, crop.height))
    return done


def write(tiles: list[Tile], out: Path, external: Path, base: Path | None = None,
          replaced: frozenset[str] = frozenset()) -> None:
    """Tiles to ``out``/<split>/images and COCO annotations + manifest for them. With ``base``, the annotations
    and manifest also hold the base build's tiles, except those of the ``replaced`` sources (and the non-defect
    tiles drawn on them); their images stay in ``base``."""
    cats = [{"id": i + 1, "name": c} for i, c in enumerate(DETECTOR_CLASSES)]
    cat_id = {c: i + 1 for i, c in enumerate(DETECTOR_CLASSES)}
    coco = {s: {"images": [], "annotations": [], "categories": cats} for s in SPLITS}
    manifest: list[dict] = []
    ann_id = 0

    def add(split: str, name: str, w: int, h: int, boxes: list[tuple[str, list[float]]]) -> None:
        nonlocal ann_id
        c = coco[split]
        img_id = len(c["images"]) + 1
        c["images"].append({"id": img_id, "file_name": name, "width": w, "height": h})
        for cls, (x, y, bw, bh) in boxes:
            ann_id += 1
            c["annotations"].append({"id": ann_id, "image_id": img_id, "category_id": cat_id[cls],
                                     "bbox": [x, y, bw, bh], "area": round(bw * bh, 1), "iscrowd": 0})

    if base is not None:
        rows = {r["tile"]: r for r in csv.DictReader((base / "manifest.csv").open())}
        dropped = Counter()
        for split in SPLITS:
            b = json.loads((base / split / "annotations.json").read_text())
            names = {c["id"]: c["name"] for c in b["categories"]}
            anns: dict[int, list] = defaultdict(list)
            for a in b["annotations"]:
                anns[a["image_id"]].append((names[a["category_id"]], a["bbox"]))
            for im in b["images"]:
                row = rows[im["file_name"]]
                # A non-defect tile keeps its base image's group, whose prefix names the base source.
                if row["source"] in replaced or (row["source"] == "synth_nuisance"
                                                 and row["group"].split(":")[0] in replaced):
                    dropped[row["source"]] += 1
                    continue
                add(split, im["file_name"], im["width"], im["height"], anns[im["id"]])
                manifest.append(row)
        print(f"  base: kept {sum(len(coco[s]['images']) for s in SPLITS)} tiles, left out {dict(dropped)}")

    names = Counter(t.name for t in tiles) + Counter(im["file_name"] for c in coco.values() for im in c["images"])
    clash = [n for n, k in names.items() if k > 1]
    assert not clash, f"{len(clash)} tile names are used more than once, e.g. {clash[:3]}"
    by_image: dict[tuple[Path, float], list[Tile]] = defaultdict(list)
    for t in tiles:
        by_image[(t.record.path, t.scale)].append(t)
    # Opening images on Kaggle's input disk waits on the disk: cut many images at once (results in order).
    with ThreadPoolExecutor(sources.READ_THREADS) as ex:
        for i, done in enumerate(ex.map(lambda ts: cut(ts, out), by_image.values())):
            for t, w, h in done:
                add(t.split, t.name, w, h, [(b.cls, [round(b.x0, 1), round(b.y0, 1), round(b.w, 1), round(b.h, 1)])
                                            for b in t.boxes])
                path = t.record.path
                manifest.append({
                    "split": t.split, "tile": t.name, "source": t.record.source,
                    "original": str(path.relative_to(external)) if path.is_relative_to(external) else str(path),
                    "group": t.record.group, "boxes": len(t.boxes), "licence": LICENCE[t.record.source],
                })
            if (i + 1) % 500 == 0:
                print(f"  {i + 1}/{len(by_image)} images", flush=True)
    for s in SPLITS:
        (out / s).mkdir(parents=True, exist_ok=True)
        (out / s / "annotations.json").write_text(json.dumps(coco[s]))
    with (out / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["split", "tile", "source", "original", "group", "boxes", "licence"])
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


def patch_summary(base: Path, info: dict, out: Path, replaced: frozenset[str]) -> dict:
    """The base build's summary with the replaced sources' entries swapped and the totals recounted."""
    merged = json.loads((base / "summary.json").read_text())
    for key in ("source_classes", "clean_images_per_source", "images_per_source_split"):
        merged[key] = {k: v for k, v in merged[key].items() if k not in replaced} | info[key]
    merged["dropped_boxes"] = {k: v for k, v in merged["dropped_boxes"].items()
                               if k.split(":")[0] not in replaced} | info["dropped_boxes"]
    per_split_cls: dict[str, Counter] = {}
    for s in SPLITS:
        c = json.loads((out / s / "annotations.json").read_text())
        names = {x["id"]: x["name"] for x in c["categories"]}
        per_split_cls[s] = Counter(names[a["category_id"]] for a in c["annotations"])
        merged["tiles"][s] = len(c["images"])
        merged["defect_tiles"][s] = len({a["image_id"] for a in c["annotations"]})
    merged["boxes_per_class"] = {s: dict(c.most_common()) for s, c in per_split_cls.items()}
    merged["patch"] = {"base_tiles": json.loads((base / "summary.json").read_text())["tiles"],
                       "replaced": sorted(replaced)}
    merged["zooms"] = info.get("zooms", {})
    return merged


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
    ap.add_argument("--smoke", type=int, default=0, help="only N images per source and kind (timing run)")
    ap.add_argument("--patch-base", type=Path, help="a finished build: keep its tiles of the other sources")
    ap.add_argument("--patch", nargs="*", default=[], help="the sources to rebuild on top of --patch-base")
    ap.add_argument("--bg-ratio-for", action="append", default=[],
                    help="SOURCE=R: that source's own --bg-ratio (more defect-free fabric against false alarms)")
    ap.add_argument("--scales", action="append", default=[],
                    help="SOURCE=1,2: also tile that source enlarged (tiny defects; the app's infer_scale)")
    args = ap.parse_args()
    replaced = frozenset(args.patch)
    if args.patch_base:
        assert replaced, "--patch-base needs --patch SOURCE..."
        # Copies of a patched source can only be in the copy-prone sources (fabricdata.dedupe.COPY_PRONE).
        args.sources = [s for s in args.sources if s in replaced or (s in COPY_PRONE and replaced & COPY_PRONE)]

    print("reading sources", flush=True)
    wanted = [s for s in args.sources if not (args.commercial_only and s in NON_COMMERCIAL)]
    records, dropped = load(args.external, wanted, args.tianchi_images)
    present = [r for r in records if r.path.exists()]
    missing = len(records) - len(present)
    if missing:
        print(f"  {missing} images listed but not on disk (e.g. Tianchi images on Kaggle): left out")
    records = apply_caps(present, args.cap, args.seed)
    if args.smoke:
        records = smoke_sample(records, args.smoke, args.seed)
        print(f"  smoke run: {len(records)} images")

    print("grouping near-duplicates", flush=True)
    # ~11,000 photo decodes (5.5 min one at a time on Kaggle): from threads, PIL decodes outside the GIL.
    prints = list(sources.threaded(
        lambda r: fingerprint(r.path) if r.source in COPY_PRONE else Fingerprint(0.0, 0, 0), records))
    merges = merge_near_duplicates(records, prints)
    print(f"  {merges} merges")
    if args.patch_base:
        # The other sources' records were read only to find copies: they keep the base build's split, and a
        # patched record in a group with one of them goes to that split.
        base_split = {r["original"]: r["split"] for r in csv.DictReader((args.patch_base / "manifest.csv").open())}
        others = [r for r in records if r.source not in replaced]
        records = [r for r in records if r.source in replaced]
        forced = {}
        for r in others:
            rel = str(r.path.relative_to(args.external)) if r.path.is_relative_to(args.external) else str(r.path)
            if rel in base_split:
                forced[r.group] = base_split[rel]
        for r in records:
            if r.group in forced:
                r.force_split = forced[r.group]
        print(f"  {sum(r.group in forced for r in records)} patched images go with a copy in another source")
        dropped = Counter({k: v for k, v in dropped.items() if k.split(":")[0] in replaced})
    split_of = assign_splits(records, seed=args.seed)
    check_pastes(records, split_of, args.external)
    zooms = {k: tuple(float(z) for z in v.split(",")) for k, v in (x.split("=") for x in args.scales)}
    bg_for = {k: float(v) for k, v in (x.split("=") for x in args.bg_ratio_for)}
    tiles = keep_tiles(plan(records, split_of, args.tile, args.overlap, zooms), args.bg_ratio, args.seed, bg_for)
    info = summary(records, split_of, tiles, dropped)
    info["zooms"] = {k: list(v) for k, v in zooms.items()}
    info["bg_ratio_for"] = bg_for
    print(json.dumps(info, indent=1))
    if args.dry_run:
        return
    print(f"writing {len(tiles)} tiles to {args.out}", flush=True)
    write(tiles, args.out, args.external, args.patch_base, replaced)
    if args.patch_base:
        info = patch_summary(args.patch_base, info, args.out, replaced)
        (args.out / "PATCH").write_text(f"{args.patch_base}\n")
    (args.out / "summary.json").write_text(json.dumps(info, indent=1))
    print("done")


if __name__ == "__main__":
    main()
