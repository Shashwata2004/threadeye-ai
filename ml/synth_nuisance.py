"""Make the non-defect training images: stickers, loose threads, wrinkles and hands on real fabric tiles.

    ml/.venv/bin/python ml/synth_nuisance.py --external data/external --hands HANDS_DIR --n 4000
    ... --preview 12          # also write a contact sheet of the first 12 images (preview.jpg)

Bases are tiles of the real sources (70 % defect-free, 30 % with defects, whose boxes are kept and never
covered), cut at the scale build_dataset.py uses. Each synthetic image keeps its base image's group, so it
lands in the same split as its base: nothing of a test fabric leaks into train. Writes
<external>/synth_nuisance/images/*.jpg, annotations.json (COCO, ThreadEye class names) and groups.json,
read by fabricdata.sources.read_synth_nuisance.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from build_dataset import MAX_SIDE  # noqa: E402
from fabricdata import nuisance, sources  # noqa: E402
from fabricdata.classes import UnmappedClass, map_class  # noqa: E402
from fabricdata.records import ImageRecord  # noqa: E402
from fabricdata.tiles import Window, clip, scaled  # noqa: E402

TILE = 640
CLEAN_SHARE = 0.7
BASE_SOURCES = ("aitex", "moratuwa", "wfdd", "raw_fabrid", "zju_leaper", "fabric_stain", "fabricspotdefect",
                "fd_figshare", "garment_defects", "tianchi")


def bases(external: Path, tianchi_images: Path | None) -> dict[bool, dict[str, list[ImageRecord]]]:
    """{defect_free: {source: records}} of the sources that are present."""
    out: dict[bool, dict[str, list[ImageRecord]]] = {True: defaultdict(list), False: defaultdict(list)}
    for name in BASE_SOURCES:
        root = external / name
        if not root.exists():
            continue
        reader = sources.READERS[name]
        for r in (reader(root, tianchi_images) if name == "tianchi" else reader(root)):
            if r.path.exists():
                out[r.defect_free or not r.boxes][name].append(r)
    return out


def base_tile(r: ImageRecord, rng: np.random.Generator) -> tuple[np.ndarray, list] | None:
    s = min(1.0, MAX_SIDE[r.source] / max(r.width, r.height)) if r.source in MAX_SIDE else 1.0
    with sources.open_rgb(r) as im:
        if s < 1.0:
            im = im.resize((round(im.width * s), round(im.height * s)), Image.Resampling.LANCZOS)
        x0 = int(rng.integers(0, max(1, im.width - TILE + 1)))
        y0 = int(rng.integers(0, max(1, im.height - TILE + 1)))
        crop = im.crop((x0, y0, min(im.width, x0 + TILE), min(im.height, y0 + TILE)))
    if min(crop.size) < 160:
        return None
    win = Window(x0, y0, x0 + crop.width, y0 + crop.height)
    defects = []
    for b in clip(scaled(r.boxes, s), win):
        try:
            cls = map_class(r.source, b.src_cls)
        except UnmappedClass:
            continue
        if cls is not None:
            defects.append((cls, (b.x0, b.y0, b.x1, b.y1)))
    return np.asarray(crop, np.float32), defects


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--tianchi-images", type=Path)
    ap.add_argument("--hands", type=Path, help="egohands_cutouts.py output; without it hands are cartoon only")
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--preview", type=int, default=0)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    hands = nuisance.load_hands(args.hands) if args.hands and (args.hands / "hands.json").exists() else []
    pool = bases(args.external, args.tianchi_images)
    print("bases:", {k: {s: len(v) for s, v in d.items()} for k, d in pool.items()}, "hand cutouts:", len(hands))
    out = args.external / "synth_nuisance"
    (out / "images").mkdir(parents=True, exist_ok=True)
    cats = list(dict.fromkeys(nuisance.NUISANCE_CLASSES))
    coco: dict = {"images": [], "annotations": [], "categories": []}
    groups: dict[str, dict] = {}
    counts: dict[str, int] = defaultdict(int)
    previews = []
    tries = 0
    while len(coco["images"]) < args.n and tries < args.n * 4:
        tries += 1
        clean = bool(pool[True]) and rng.random() < CLEAN_SHARE
        by_source = pool[True] if clean or not pool[False] else pool[False]
        source = list(by_source)[rng.integers(len(by_source))]
        r = by_source[source][rng.integers(len(by_source[source]))]
        got = base_tile(r, rng)
        if got is None:
            continue
        img, defects = got
        drawn = nuisance.compose(img, rng, hands, keep_clear=[b for _, b in defects])
        if not drawn:
            continue
        name = f"synth_{len(coco['images']):05d}.jpg"
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out / "images" / name, quality=92)
        img_id = len(coco["images"]) + 1
        coco["images"].append({"id": img_id, "file_name": name, "width": img.shape[1], "height": img.shape[0]})
        for cls, (x0, y0, x1, y1) in defects + [(d.cls, d.box) for d in drawn]:
            if cls not in cats:
                cats.append(cls)
            coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": img_id,
                                        "category_id": cats.index(cls) + 1,
                                        "bbox": [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)],
                                        "area": round((x1 - x0) * (y1 - y0), 1), "iscrowd": 0})
        for d in drawn:
            counts[d.cls] += 1
        groups[name] = {"group": r.group, "force_split": r.force_split, "base": f"{r.source}:{r.path.name}"}
        if len(previews) < args.preview:
            previews.append((img.copy(), drawn, defects))
    coco["categories"] = [{"id": i + 1, "name": c} for i, c in enumerate(cats)]
    (out / "annotations.json").write_text(json.dumps(coco))
    (out / "groups.json").write_text(json.dumps(groups))
    print(f"{len(coco['images'])} images, nuisances {dict(counts)} -> {out}")
    if previews:
        contact_sheet(previews, out / "preview.jpg")


def contact_sheet(items: list, path: Path, cell: int = 320) -> None:
    from PIL import ImageDraw

    cols = 4
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (30, 30, 30))
    colours = {"sticker": (255, 0, 255), "loose_thread": (0, 255, 255), "wrinkle": (255, 255, 0), "hand": (0, 255, 0)}
    for i, (img, drawn, defects) in enumerate(items):
        im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        s = cell / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)))
        d = ImageDraw.Draw(im)
        for x in drawn:
            d.rectangle([v * s for v in x.box], outline=colours[x.cls], width=2)
            d.text((x.box[0] * s + 2, x.box[1] * s + 2), x.cls, fill=colours[x.cls])
        for cls, b in defects:
            d.rectangle([v * s for v in b], outline=(255, 60, 60), width=2)
        sheet.paste(im, ((i % cols) * cell, (i // cols) * cell))
    sheet.save(path, quality=90)


if __name__ == "__main__":
    main()
