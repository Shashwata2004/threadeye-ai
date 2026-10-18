"""One reader per source: raw files in data/external/<source>/ → ImageRecords (boxes in image pixels).

Each reader also decides which images belong together (``group``): augmented copies of one original,
photos of the same physical defect taken seconds apart, or the AITEX fabric the demo roll is made from.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from fabricdata.records import Box, ImageRecord

ROBOFLOW_SUFFIX = re.compile(r"_(jpe?g|png)\.rf\.[0-9a-f]+\.(jpe?g|png)$", re.IGNORECASE)
SESSION_GAP_S = 120
"""Photos taken less than this apart (phone time stamps in the file name) show the same defect."""

AITEX_DEMO_FABRIC = "02"
"""data/sample_roll is rendered from AITEX fabric 02 (roll_meta.json "source"): always test."""


def original_name(file_name: str) -> str:
    """Roboflow renames ``x.jpg`` to ``x_jpg.rf.<hash>.jpg`` (once per augmented copy)."""
    return ROBOFLOW_SUFFIX.sub("", Path(file_name).name)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def mask_boxes(mask: np.ndarray, *, min_area: int = 6, join_px: int = 3) -> list[tuple[int, int, int, int]]:
    """Boxes (x0, y0, x1, y1) around the blobs of a binary mask. Fragments closer than ``join_px``
    are one defect (masks of thin yarn faults are often broken up)."""
    on = mask > 0
    if join_px:
        on = ndimage.binary_dilation(on, iterations=join_px)
    labels, n = ndimage.label(on)
    boxes = []
    for sl in ndimage.find_objects(labels):
        if sl is None:
            continue
        ys, xs = sl
        # Undo the dilation and measure the real pixels inside the blob.
        real = mask[ys, xs] > 0
        if real.sum() < min_area:
            continue
        rows, cols = np.nonzero(real)
        boxes.append((xs.start + int(cols.min()), ys.start + int(rows.min()),
                      xs.start + int(cols.max()) + 1, ys.start + int(rows.max()) + 1))
    return boxes


def session_groups(items: list[tuple[str, datetime | None]], prefix: str) -> dict[str, str]:
    """Group keys whose time stamps are within SESSION_GAP_S of the previous one; no stamp → own group."""
    out: dict[str, str] = {}
    stamped = sorted((t, k) for k, t in items if t is not None)
    session, last = 0, None
    for t, k in stamped:
        if last is None or (t - last).total_seconds() > SESSION_GAP_S:
            session += 1
        out[k] = f"{prefix}:session{session}"
        last = t
    for k, t in items:
        if t is None:
            out[k] = f"{prefix}:{k}"
    return out


def stamp(name: str, pattern: str, fmt: str) -> datetime | None:
    m = re.search(pattern, name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), fmt)
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------- readers
def read_aitex(root: Path) -> Iterator[ImageRecord]:
    base = root / "extracted"
    for img in sorted((base / "Defect_images").glob("*.png")):
        _, code, fabric = img.stem.split("_")[:3]
        boxes: list[Box] = []
        for mp in sorted((base / "Mask_images").glob(img.stem + "_mask*.png")):
            mask = np.asarray(Image.open(mp).convert("L"))
            boxes += [Box(*b, src_cls=code) for b in mask_boxes(mask)]
        if not boxes:
            continue  # a defect image with an empty mask is neither labelled nor clean
        w, h = image_size(img)
        yield ImageRecord("aitex", img, w, h, boxes, group=f"aitex:{img.stem.split('_')[0]}",
                          force_split="test" if fabric == AITEX_DEMO_FABRIC else None)
    for img in sorted((base / "NODefect_images").glob("*/*.png")):
        fabric = img.stem.split("_")[2]
        w, h = image_size(img)
        yield ImageRecord("aitex", img, w, h, [], group=f"aitex:clean:{img.parent.name}:{img.stem}",
                          defect_free=True, force_split="test" if fabric == AITEX_DEMO_FABRIC else None)


def read_coco(source: str, ann_files: list[Path], group_of: Callable[[str], str],
              image_dir_of: Callable[[Path], Path] | None = None) -> Iterator[ImageRecord]:
    for ann in ann_files:
        j = json.loads(ann.read_text())
        cats = {c["id"]: c["name"] for c in j["categories"]}
        by_image: dict[int, list[Box]] = {}
        for a in j["annotations"]:
            x, y, w, h = a["bbox"]
            by_image.setdefault(a["image_id"], []).append(Box(x, y, x + w, y + h, src_cls=cats[a["category_id"]]))
        image_dir = image_dir_of(ann) if image_dir_of else ann.parent
        for im in j["images"]:
            path = image_dir / im["file_name"]
            yield ImageRecord(source, path, int(im["width"]), int(im["height"]),
                              by_image.get(im["id"], []), group=group_of(im["file_name"]))


def read_fabricspotdefect(root: Path) -> Iterator[ImageRecord]:
    anns = sorted(root.glob("extracted/*/FabricSpotDefect/Orginal/*/_annotations.coco.json"))
    yield from read_coco("fabricspotdefect", anns, lambda n: f"fabricspotdefect:{original_name(n)}")


def read_garment_defects(root: Path) -> Iterator[ImageRecord]:
    anns = sorted(root.glob("extracted/inner/*/_annotations.coco.json"))
    names = []
    for ann in anns:
        names += [im["file_name"] for im in json.loads(ann.read_text())["images"]]
    originals = {original_name(n) for n in names}
    groups = session_groups([(o, stamp(o, r"(\d{8}_\d{6})", "%Y%m%d_%H%M%S")) for o in originals], "garment")
    # Roboflow exported up to 3 augmented copies (flips, 90° turns, small rotations with black corners) per
    # original: keep one per original, the one with the least black border. Augmentation is ours to do.
    copies: dict[str, list[ImageRecord]] = {}
    for r in read_coco("garment_defects", anns, lambda n: groups[original_name(n)]):
        copies.setdefault(original_name(r.path.name), []).append(r)
    for recs in copies.values():
        yield min(recs, key=lambda r: (black_border(r.path), r.path.name))


def black_border(path: Path, width: int = 4) -> float:
    """Share of near-black pixels along the image edge (rotation padding)."""
    with Image.open(path) as im:
        a = np.asarray(im.convert("L"))
    edge = np.concatenate([a[:width].ravel(), a[-width:].ravel(), a[:, :width].ravel(), a[:, -width:].ravel()])
    return float((edge < 8).mean())


def read_tianchi(root: Path, images: Path | None = None) -> Iterator[ImageRecord]:
    """Annotations from the Roboflow export (annotations/<split>/_annotations.coco.json); the images live
    wherever the export was unpacked (on Kaggle), given as ``images`` with the same <split>/ folders."""
    anns = sorted((root / "annotations").glob("*/_annotations.coco.json"))
    img_root = images or root / "images"
    yield from read_coco("tianchi", anns, lambda n: f"tianchi:{original_name(n)}",
                         image_dir_of=lambda ann: img_root / ann.parent.name)


def read_fd_figshare(root: Path) -> Iterator[ImageRecord]:
    base = root / "extracted/FD_Dataset/YOLO"
    imgs = sorted(base.glob("*/images/*.jpg"))
    originals = {original_name(p.name) for p in imgs}
    groups = session_groups(
        [(o, stamp(o, r"photo_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", "%Y-%m-%d_%H-%M-%S")) for o in originals], "fd"
    )
    for img in imgs:
        w, h = image_size(img)
        boxes = []
        label = img.parent.parent / "labels" / (img.stem + ".txt")
        for line in label.read_text().splitlines() if label.exists() else []:
            parts = line.split()
            if len(parts) != 5:
                continue
            c, cx, cy, bw, bh = parts[0], *map(float, parts[1:])
            boxes.append(Box((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h, src_cls=c))
        yield ImageRecord("fd_figshare", img, w, h, boxes, group=groups[original_name(img.name)])


MORATUWA_MAX_BLOBS = 3
"""Some "_processed (3)" masks of line defects are noise (checked visually): images whose mask splits
into more blobs than this are left out."""
MORATUWA_LABELLED = ("hole", "horizontal", "Vertical")
"""Folders whose images come with masks ("<name>_processed (3).jpg"); "lines" and "stain" have none."""


def moratuwa_base(stem: str) -> str:
    return re.sub(r"(_processed)?\s*\(\d+\)$", "", stem).strip()


def read_moratuwa(root: Path) -> Iterator[ImageRecord]:
    base = root / "extracted/Fabric Defects Dataset/Fabric Defect Dataset"
    for folder in MORATUWA_LABELLED:
        files = sorted((base / folder).glob("*.*"))
        for img in files:
            if "_processed" in img.stem:
                continue
            mask_path = img.with_name(f"{img.stem}_processed (3){img.suffix}")
            if not mask_path.exists():
                continue  # no mask: no labels (see unlabelled())
            w, h = image_size(img)
            mask = np.asarray(Image.open(mask_path).convert("L").resize((w, h)))
            boxes = [Box(*b, src_cls=folder.lower()) for b in mask_boxes(np.where(mask > 127, 255, 0))]
            if not boxes or len(boxes) > MORATUWA_MAX_BLOBS:
                continue  # an empty or noisy mask (dozens of specks, the defect itself missed): unreliable
            yield ImageRecord("moratuwa", img, w, h, boxes, group=f"moratuwa:{folder}:{moratuwa_base(img.stem)}")


def moratuwa_unlabelled(root: Path) -> dict[str, int]:
    """Images that would need labelling before they can train a detector."""
    base = root / "extracted/Fabric Defects Dataset/Fabric Defect Dataset"
    out = {}
    for folder in ("lines", "stain", *MORATUWA_LABELLED):
        files = [p for p in (base / folder).glob("*.*") if "_processed" not in p.stem]
        if folder in MORATUWA_LABELLED:
            files = [p for p in files if not p.with_name(f"{p.stem}_processed (3){p.suffix}").exists()]
        out[folder] = len(files)
    return out


READERS: dict[str, Callable[[Path], Iterator[ImageRecord]]] = {
    "aitex": read_aitex,
    "fabricspotdefect": read_fabricspotdefect,
    "moratuwa": read_moratuwa,
    "fd_figshare": read_fd_figshare,
    "garment_defects": read_garment_defects,
    "tianchi": read_tianchi,
}
